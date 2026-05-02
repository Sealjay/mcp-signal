from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

import sigexport.data

from .config import SignalConfig


def _parse_ts(raw: dict[str, Any]) -> datetime | None:
    ts = raw.get("sent_at") or raw.get("timestamp")
    if isinstance(ts, int | float):
        return datetime.fromtimestamp(ts / 1000)
    if isinstance(ts, str):
        return datetime.fromisoformat(ts)
    return None


def _is_outgoing(raw: dict[str, Any], self_id: str | None) -> bool:
    return raw.get("type") == "outgoing" or (
        self_id is not None and raw.get("source") == self_id
    )


def _build_sid_lookup(contacts: Any) -> dict[str, Any]:
    return {contact.serviceId: contact for contact in contacts.values() if contact.serviceId}


def _sender_name(
    raw: dict[str, Any],
    self_id: str | None,
    contact: Any,
    sid_lookup: dict[str, Any] | None = None,
) -> str:
    if _is_outgoing(raw, self_id):
        return "Me"
    source = raw.get("source")
    if contact.is_group and source and sid_lookup:
        sender = sid_lookup.get(source)
        if sender:
            return sender.name or sender.profile_name or sender.number or source
        return source
    return contact.name or contact.number or "Unknown"


def _format_message(
    chat_name: str,
    raw: dict[str, Any],
    self_id: str | None,
    contact: Any,
    sid_lookup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dt = _parse_ts(raw)
    return {
        "chat_name": chat_name,
        "date": dt.isoformat() if dt else "",
        "sender": _sender_name(raw, self_id, contact, sid_lookup),
        "body": raw.get("body", "") or "",
        "quote": raw.get("quote", "") or "",
        "sticker": raw.get("sticker", "") or "",
        "reactions": raw.get("reactions", []) or [],
        "attachments": raw.get("has_attachments", "") or "",
        "_content_type": "untrusted_user_content",
    }


class DesktopReader:
    def __init__(self, config: SignalConfig) -> None:
        self._config = config

    def _fetch_data(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> tuple[Any, Any, Any]:
        return sigexport.data.fetch_data(
            source_dir=self._config.source_dir,
            password=self._config.signal_db_password,
            key=self._config.signal_db_key,
            chats="",
            include_empty=False,
            include_disappearing=True,
            start_date=start_date,
            end_date=end_date,
        )

    def list_chats(self, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        convos, contacts, self_contact = self._fetch_data()
        self_id = self_contact.serviceId if self_contact else None
        sid_lookup = _build_sid_lookup(contacts)
        query_lower = query.strip().lower()
        rows: list[dict[str, Any]] = []
        for chat_id, messages in convos.items():
            contact = contacts.get(chat_id)
            if not contact:
                continue
            name = contact.name or contact.number or "Unknown"
            number = contact.number or ""
            if (
                query_lower
                and query_lower not in name.lower()
                and query_lower not in number.lower()
            ):
                continue
            row: dict[str, Any] = {
                "name": name,
                "number": number,
                "service_id": contact.serviceId,
                "is_group": contact.is_group,
                "total_messages": len(messages),
                "last_message_date": "",
                "last_message_sender": "",
                "last_message_body": "",
            }
            if messages:
                latest = max(messages, key=lambda message: message.get_ts())
                raw = asdict(latest)
                dt = _parse_ts(raw)
                row["last_message_date"] = dt.isoformat() if dt else ""
                row["last_message_sender"] = _sender_name(raw, self_id, contact, sid_lookup)
                row["last_message_body"] = raw.get("body", "") or ""
            rows.append(row)
        rows.sort(key=lambda item: item["last_message_date"], reverse=True)
        return rows[:limit]

    def list_local_groups(self, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        groups = [chat for chat in self.list_chats(query=query, limit=10_000) if chat["is_group"]]
        for group in groups:
            group["group_id"] = None
        return groups[:limit]

    def chat_activity(self, limit: int = 50) -> list[dict[str, Any]]:
        convos, contacts, self_contact = self._fetch_data()
        self_id = self_contact.serviceId if self_contact else None
        sid_lookup = _build_sid_lookup(contacts)
        rows: list[dict[str, Any]] = []
        for chat_id, messages in convos.items():
            contact = contacts.get(chat_id)
            if not contact or not messages:
                continue

            sorted_messages = sorted(messages, key=lambda message: message.get_ts(), reverse=True)
            latest_raw = asdict(sorted_messages[0])
            last_dt = _parse_ts(latest_raw)

            last_reply_ts = 0
            last_reply_dt: datetime | None = None
            for message in sorted_messages:
                raw = asdict(message)
                if _is_outgoing(raw, self_id):
                    last_reply_ts = message.get_ts()
                    last_reply_dt = _parse_ts(raw)
                    break

            unanswered = 0
            for message in sorted_messages:
                if message.get_ts() <= last_reply_ts:
                    break
                raw = asdict(message)
                if not _is_outgoing(raw, self_id):
                    unanswered += 1

            rows.append(
                {
                    "name": contact.name,
                    "number": contact.number,
                    "is_group": contact.is_group,
                    "total_messages": len(messages),
                    "last_message_date": last_dt.isoformat() if last_dt else "",
                    "last_message_sender": _sender_name(
                        latest_raw,
                        self_id,
                        contact,
                        sid_lookup,
                    ),
                    "last_reply_date": last_reply_dt.isoformat() if last_reply_dt else "",
                    "unanswered_count": unanswered,
                }
            )
        rows.sort(key=lambda item: item["last_message_date"], reverse=True)
        return rows[:limit]

    def read_messages(
        self,
        chat_name: str,
        *,
        limit: int = 20,
        offset: int = 0,
        after: str | None = None,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            start_date = datetime.fromisoformat(after) if after else None
            end_date = datetime.fromisoformat(before) if before else None
        except ValueError as exc:
            raise ValueError(f"Invalid date format (expected ISO 8601): {exc}") from exc
        convos, contacts, self_contact = self._fetch_data(start_date=start_date, end_date=end_date)
        self_id = self_contact.serviceId if self_contact else None
        sid_lookup = _build_sid_lookup(contacts)
        for chat_id, messages in convos.items():
            contact = contacts.get(chat_id)
            if not contact:
                continue
            name = contact.name or contact.number or "Unknown"
            if name != chat_name:
                continue
            sorted_messages = sorted(messages, key=lambda message: message.get_ts(), reverse=True)
            end_idx = offset + limit if limit else len(sorted_messages)
            return [
                _format_message(name, asdict(message), self_id, contact, sid_lookup)
                for message in sorted_messages[offset:end_idx]
            ]
        return []

    def search_messages(
        self,
        query: str,
        *,
        chat_name: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        convos, contacts, self_contact = self._fetch_data()
        self_id = self_contact.serviceId if self_contact else None
        sid_lookup = _build_sid_lookup(contacts)
        query_lower = query.lower()
        results: list[dict[str, Any]] = []
        for chat_id, messages in convos.items():
            contact = contacts.get(chat_id)
            if not contact:
                continue
            name = contact.name or contact.number or "Unknown"
            if chat_name is not None and name != chat_name:
                continue
            sorted_messages = sorted(messages, key=lambda message: message.get_ts(), reverse=True)
            for message in sorted_messages:
                raw = asdict(message)
                body = raw.get("body", "") or ""
                if query_lower in body.lower():
                    results.append(_format_message(name, raw, self_id, contact, sid_lookup))
                    if len(results) >= limit:
                        return results
        return results

    def find_direct_chat_matches(self, chat_name: str) -> list[dict[str, Any]]:
        target = chat_name.strip().casefold()
        matches = []
        for chat in self.list_chats(limit=10_000):
            if chat["is_group"]:
                continue
            if chat["name"].strip().casefold() == target:
                matches.append(chat)
        return matches
