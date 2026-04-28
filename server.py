import platform
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import sigexport.data
from fastmcp import FastMCP

mcp = FastMCP(
    "Signal MCP Server",
    version="0.2.0",
    strict_input_validation=True,
    mask_error_details=True,
)


def _default_signal_dir() -> Path:
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        return home / "AppData" / "Roaming" / "Signal"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "Signal"
    if system == "Linux":
        flatpak = home / ".var" / "app" / "org.signal.Signal" / "config" / "Signal"
        return flatpak if flatpak.exists() else home / ".config" / "Signal"
    raise RuntimeError(f"Unsupported OS: {system}")


def _parse_ts(raw: dict[str, Any]) -> datetime | None:
    ts = raw.get("sent_at") or raw.get("timestamp")
    if isinstance(ts, int | float):
        return datetime.fromtimestamp(ts / 1000)
    if isinstance(ts, str):
        return datetime.fromisoformat(ts)
    return None


def _is_outgoing(raw: dict[str, Any], self_id: str | None) -> bool:
    return raw.get("type") == "outgoing" or (self_id is not None and raw.get("source") == self_id)


def _build_sid_lookup(contacts: Any) -> dict[str, Any]:
    return {c.serviceId: c for c in contacts.values() if c.serviceId}


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


def _format_msg(
    raw: dict[str, Any],
    self_id: str | None,
    contact: Any,
    sid_lookup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dt = _parse_ts(raw)
    return {
        "date": dt.isoformat() if dt else "",
        "sender": _sender_name(raw, self_id, contact, sid_lookup),
        "body": raw.get("body", "") or "",
        "quote": raw.get("quote", "") or "",
        "sticker": raw.get("sticker", "") or "",
        "reactions": raw.get("reactions", []) or [],
        "attachments": raw.get("has_attachments", "") or "",
    }


@mcp.tool()
def signal_list_chats(
    source_dir: Path = _default_signal_dir(),
    password: str | None = None,
    key: str | None = None,
    chats: str = "",
    include_empty: bool = False,
    include_disappearing: bool = True,
) -> list[dict[str, Any]]:
    """List all Signal chats sorted by most recent message.

    Returns name, number, ServiceId, message count, last_message_date, and last_message_sender.
    """
    convos, contacts, self_contact = sigexport.data.fetch_data(
        source_dir=source_dir,
        password=password,
        key=key,
        chats=chats,
        include_empty=include_empty,
        include_disappearing=include_disappearing,
    )
    self_id = self_contact.serviceId if self_contact else None
    sid_lookup = _build_sid_lookup(contacts)

    output = []
    for chat_id, messages in convos.items():
        contact = contacts.get(chat_id)
        if not contact:
            continue
        entry: dict[str, Any] = {
            "name": contact.name,
            "number": contact.number,
            "ServiceId": contact.serviceId,
            "is_group": contact.is_group,
            "total_messages": len(messages),
            "last_message_date": "",
            "last_message_sender": "",
        }
        if messages:
            latest = max(messages, key=lambda m: m.get_ts())
            raw = asdict(latest)
            dt = _parse_ts(raw)
            entry["last_message_date"] = dt.isoformat() if dt else ""
            entry["last_message_sender"] = _sender_name(raw, self_id, contact, sid_lookup)
        output.append(entry)

    output.sort(key=lambda x: x["last_message_date"], reverse=True)
    return output


@mcp.tool()
def signal_get_chat_messages(
    chat_name: str,
    limit: int | None = None,
    offset: int = 0,
    after: str | None = None,
    before: str | None = None,
    source_dir: Path = _default_signal_dir(),
    password: str | None = None,
    key: str | None = None,
    chats: str = "",
    include_empty: bool = False,
    include_disappearing: bool = True,
) -> list[dict[str, Any]]:
    """Get messages from a specific Signal chat, optionally filtered by date range.

    Args:
        chat_name: Name of the chat to retrieve messages from.
        limit: Maximum number of messages to return.
        offset: Number of messages to skip (for pagination).
        after: Only messages after this ISO datetime (e.g. '2025-01-01' or '2025-01-01T09:00:00').
        before: Only messages before this ISO datetime.
    """
    start_date = datetime.fromisoformat(after) if after else None
    end_date = datetime.fromisoformat(before) if before else None

    convos, contacts, self_contact = sigexport.data.fetch_data(
        source_dir=source_dir,
        password=password,
        key=key,
        chats=chats,
        include_empty=include_empty,
        include_disappearing=include_disappearing,
        start_date=start_date,
        end_date=end_date,
    )
    self_id = self_contact.serviceId if self_contact else None
    sid_lookup = _build_sid_lookup(contacts)

    for chat_id, messages in convos.items():
        contact = contacts.get(chat_id)
        if not (contact and contact.name == chat_name):
            continue
        sorted_msgs = sorted(messages, key=lambda m: m.get_ts(), reverse=True)
        end_idx = offset + limit if limit else len(sorted_msgs)
        return [
            _format_msg(asdict(msg), self_id, contact, sid_lookup)
            for msg in sorted_msgs[offset:end_idx]
        ]
    return []


@mcp.tool()
def signal_search_chat(
    chat_name: str,
    query: str,
    limit: int | None = None,
    source_dir: Path = _default_signal_dir(),
    password: str | None = None,
    key: str | None = None,
    chats: str = "",
    include_empty: bool = False,
    include_disappearing: bool = True,
) -> list[dict[str, Any]]:
    """Search for text within a Signal chat.

    Args:
        chat_name: Name of the chat to search within.
        query: Text to search for in message bodies.
        limit: Maximum number of matching messages to return.
    """
    convos, contacts, self_contact = sigexport.data.fetch_data(
        source_dir=source_dir,
        password=password,
        key=key,
        chats=chats,
        include_empty=include_empty,
        include_disappearing=include_disappearing,
    )
    self_id = self_contact.serviceId if self_contact else None
    sid_lookup = _build_sid_lookup(contacts)
    query_lower = query.lower()

    for chat_id, messages in convos.items():
        contact = contacts.get(chat_id)
        if not (contact and contact.name == chat_name):
            continue
        sorted_msgs = sorted(messages, key=lambda m: m.get_ts(), reverse=True)
        results: list[dict[str, Any]] = []
        for msg in sorted_msgs:
            raw = asdict(msg)
            body = raw.get("body", "") or ""
            if query_lower in body.lower():
                results.append(_format_msg(raw, self_id, contact, sid_lookup))
                if limit and len(results) >= limit:
                    break
        return results
    return []


@mcp.tool()
def signal_chat_activity(
    source_dir: Path = _default_signal_dir(),
    password: str | None = None,
    key: str | None = None,
    include_empty: bool = False,
    include_disappearing: bool = True,
) -> list[dict[str, Any]]:
    """Per-chat activity: last message, last reply, unanswered. Sorted by most recent.

    Returns per chat: name, number, is_group, total_messages, last_message_date,
    last_message_sender, last_reply_date (when you last sent), and unanswered_count
    (incoming messages since your last reply).
    """
    convos, contacts, self_contact = sigexport.data.fetch_data(
        source_dir=source_dir,
        password=password,
        key=key,
        chats="",
        include_empty=include_empty,
        include_disappearing=include_disappearing,
    )
    self_id = self_contact.serviceId if self_contact else None
    sid_lookup = _build_sid_lookup(contacts)

    output = []
    for chat_id, messages in convos.items():
        contact = contacts.get(chat_id)
        if not contact or not messages:
            continue

        sorted_msgs = sorted(messages, key=lambda m: m.get_ts(), reverse=True)
        latest_raw = asdict(sorted_msgs[0])
        last_dt = _parse_ts(latest_raw)

        last_reply_ts = 0
        last_reply_dt: datetime | None = None
        for msg in sorted_msgs:
            raw = asdict(msg)
            if _is_outgoing(raw, self_id):
                last_reply_ts = msg.get_ts()
                last_reply_dt = _parse_ts(raw)
                break

        unanswered = 0
        for msg in sorted_msgs:
            if msg.get_ts() <= last_reply_ts:
                break
            raw = asdict(msg)
            if not _is_outgoing(raw, self_id):
                unanswered += 1

        output.append(
            {
                "name": contact.name,
                "number": contact.number,
                "is_group": contact.is_group,
                "total_messages": len(messages),
                "last_message_date": last_dt.isoformat() if last_dt else "",
                "last_message_sender": _sender_name(latest_raw, self_id, contact, sid_lookup),
                "last_reply_date": last_reply_dt.isoformat() if last_reply_dt else "",
                "unanswered_count": unanswered,
            }
        )

    output.sort(key=lambda x: x["last_message_date"], reverse=True)
    return output


@mcp.prompt()
def signal_summarize_chat_prompt(chat_name: str) -> str:
    return f"Summarize the recent messages in the Signal chat named '{chat_name}'."


@mcp.prompt()
def signal_chat_topic_prompt(chat_name: str) -> str:
    return f"What are the topics of discussion in the Signal chat named '{chat_name}'?"


@mcp.prompt()
def signal_chat_sentiment_prompt(chat_name: str) -> str:
    return f"Analyze the sentiment of messages in the Signal chat named '{chat_name}'."


@mcp.prompt()
def signal_search_chat_prompt(chat_name: str, query: str) -> str:
    return f"Search for the text '{query}' in the Signal chat named '{chat_name}'."


if __name__ == "__main__":
    mcp.run()
