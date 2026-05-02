from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import patch

from mcp_signal.config import SignalConfig
from mcp_signal.reader import DesktopReader


@dataclass
class FakeMessage:
    timestamp: str
    body: str
    source: str
    ts: int

    def get_ts(self) -> int:
        return self.ts


@dataclass
class FakeContact:
    name: str | None
    number: str | None
    serviceId: str | None
    is_group: bool
    profile_name: str | None = None


def build_reader() -> DesktopReader:
    config = SignalConfig(
        source_dir=None,  # type: ignore[arg-type]
        signal_cli_path="signal-cli",
        signal_account=None,
        signal_db_password=None,
        signal_db_key=None,
        jsonrpc_timeout_seconds=30,
    )
    return DesktopReader(config)


def fake_fetch_data(*, start_date=None, end_date=None, **kwargs):
    del kwargs
    direct_msg = FakeMessage(
        "2026-05-02T10:00:00+00:00",
        "Lunch tomorrow?",
        "+44111",
        1,
    )
    group_msg = FakeMessage(
        "2026-05-02T11:00:00+00:00",
        "Meet at 7",
        "sid-friend",
        2,
    )
    convos = {
        "chat-direct": [direct_msg],
        "chat-group": [group_msg],
    }
    contacts = {
        "chat-direct": FakeContact("Alice", "+44111", "sid-alice", False),
        "chat-group": FakeContact("Weekend Plans", None, "group-service-id", True),
        "sid-friend": FakeContact("Bob", "+44222", "sid-friend", False),
    }
    if start_date or end_date:
        body = direct_msg.body
        ts = datetime.fromisoformat(direct_msg.timestamp)
        if start_date and ts < start_date:
            convos["chat-direct"] = []
        if end_date and ts > end_date:
            convos["chat-direct"] = []
        if not body:
            convos["chat-direct"] = []
    return convos, contacts, FakeContact("Me", "+44000", "self-service-id", False)


@patch("mcp_signal.reader.sigexport.data.fetch_data", side_effect=fake_fetch_data)
def test_list_chats_includes_groups(mock_fetch):
    del mock_fetch
    chats = build_reader().list_chats()
    assert chats[0]["name"] == "Weekend Plans"
    assert chats[1]["name"] == "Alice"
    assert chats[0]["is_group"] is True


@patch("mcp_signal.reader.sigexport.data.fetch_data", side_effect=fake_fetch_data)
def test_search_messages_across_all_chats(mock_fetch):
    del mock_fetch
    matches = build_reader().search_messages("meet")
    assert len(matches) == 1
    assert matches[0]["chat_name"] == "Weekend Plans"
    assert matches[0]["sender"] == "Bob"


@patch("mcp_signal.reader.sigexport.data.fetch_data", side_effect=fake_fetch_data)
def test_find_direct_chat_matches_only_directs(mock_fetch):
    del mock_fetch
    matches = build_reader().find_direct_chat_matches("Alice")
    assert len(matches) == 1
    assert matches[0]["number"] == "+44111"


@patch("mcp_signal.reader.sigexport.data.fetch_data", side_effect=fake_fetch_data)
def test_chat_activity_reports_unanswered_count(mock_fetch):
    del mock_fetch
    rows = build_reader().chat_activity(limit=5)
    assert rows[0]["name"] == "Weekend Plans"
    assert rows[0]["unanswered_count"] == 1
