import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import (
    _archive_path,
    _message_type,
    _read_ids_file,
    fetch_all_dialogs,
    get_active_contacts,
    get_active_groups,
    get_forum_topics,
    get_message_archive,
    get_new_contacts,
    get_new_groups,
    is_fresh,
    parse_args,
    save_active_lists,
    save_all_lists,
    save_new_lists,
    save_topics_list,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _aiter(items):
    for item in items:
        yield item


def _make_dialog(entity, name, date):
    d = MagicMock()
    d.entity = entity
    d.name = name
    d.date = date
    return d


def _make_msg(msg_id, date, sender_id, text="", photo=None, video=None,
              audio=None, document=None, sticker=None):
    m = MagicMock()
    m.id = msg_id
    m.date = date
    m.sender_id = sender_id
    m.text = text
    m.photo = photo
    m.video = video
    m.audio = audio
    m.document = document
    m.sticker = sticker
    return m


def _make_topic(topic_id, title, date, top_message=None, closed=False):
    from telethon.tl.types import ForumTopic

    t = MagicMock(spec=ForumTopic)
    t.id = topic_id
    t.title = title
    t.date = date
    t.closed = closed
    t.top_message = top_message if top_message is not None else topic_id
    return t


# ---------------------------------------------------------------------------
# is_fresh
# ---------------------------------------------------------------------------

class TestIsFresh:
    def test_missing_file_returns_false(self, tmp_path):
        assert is_fresh(str(tmp_path / "no_file.csv")) is False

    def test_file_modified_today_returns_true(self, tmp_path):
        f = tmp_path / "today.csv"
        f.write_text("data")
        assert is_fresh(str(f)) is True

    def test_file_modified_yesterday_returns_false(self, tmp_path):
        f = tmp_path / "old.csv"
        f.write_text("data")
        yesterday = (datetime.now() - timedelta(days=1)).timestamp()
        os.utime(str(f), (yesterday, yesterday))
        assert is_fresh(str(f)) is False


# ---------------------------------------------------------------------------
# _archive_path
# ---------------------------------------------------------------------------

class TestArchivePath:
    def test_spaces_replaced_with_underscores(self):
        path = _archive_path("groups", "My Group")
        assert "My_Group.json" in path

    def test_slash_replaced(self):
        path = _archive_path("groups", "A/B")
        assert "/" not in os.path.basename(path)
        assert "A_B.json" in path

    def test_pipe_replaced(self):
        path = _archive_path("contacts", "A | B")
        assert "A___B.json" in path

    def test_correct_category_in_path(self):
        assert "groups" in _archive_path("groups", "Test")
        assert "contacts" in _archive_path("contacts", "Test")

    def test_json_extension(self):
        assert _archive_path("groups", "Name").endswith(".json")


# ---------------------------------------------------------------------------
# _message_type
# ---------------------------------------------------------------------------

class TestMessageType:
    def _msg(self, **kwargs):
        defaults = dict(photo=None, sticker=None, video=None, audio=None, document=None)
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_photo(self):
        assert _message_type(self._msg(photo=object())) == "photo"

    def test_sticker(self):
        assert _message_type(self._msg(sticker=object())) == "sticker"

    def test_video(self):
        assert _message_type(self._msg(video=object())) == "video"

    def test_audio(self):
        assert _message_type(self._msg(audio=object())) == "audio"

    def test_document(self):
        assert _message_type(self._msg(document=object())) == "document"

    def test_text(self):
        assert _message_type(self._msg()) == "text"

    def test_sticker_takes_priority_over_document(self):
        # sticker проверяется раньше document
        assert _message_type(self._msg(sticker=object(), document=object())) == "sticker"


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_defaults(self):
        with patch("sys.argv", ["main.py"]):
            with pytest.raises(SystemExit) as exc:
                parse_args()
        assert exc.value.code == 0

    def test_period(self):
        with patch("sys.argv", ["main.py", "--period", "5"]):
            args = parse_args()
        assert args.period == 5

    def test_mode_groups(self):
        with patch("sys.argv", ["main.py", "--mode", "groups"]):
            args = parse_args()
        assert args.mode == "groups"

    def test_mode_contacts(self):
        with patch("sys.argv", ["main.py", "--mode", "contacts"]):
            args = parse_args()
        assert args.mode == "contacts"

    def test_invalid_period_exits(self):
        with patch("sys.argv", ["main.py", "--period", "99"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_invalid_mode_exits(self):
        with patch("sys.argv", ["main.py", "--mode", "all"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_all_valid_periods(self):
        for p in (1, 3, 5, 30):
            with patch("sys.argv", ["main.py", "--period", str(p)]):
                assert parse_args().period == p


# ---------------------------------------------------------------------------
# fetch_all_dialogs
# ---------------------------------------------------------------------------

class TestFetchAllDialogs:
    def _make_client(self, dialogs):
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter(dialogs)
        return client

    def test_groups_and_contacts_separated(self):
        from telethon.tl.types import Channel, Chat, User

        chat = MagicMock(spec=Chat); chat.id = 10
        channel = MagicMock(spec=Channel); channel.id = 20
        user = MagicMock(spec=User); user.bot = False; user.id = 30

        dialogs = [
            _make_dialog(chat, "Chat", None),
            _make_dialog(channel, "Channel", None),
            _make_dialog(user, "User", None),
        ]
        client = self._make_client(dialogs)
        groups, contacts = asyncio.run(fetch_all_dialogs(client))

        assert len(groups) == 2
        assert len(contacts) == 1
        assert groups[0]["id"] == -10
        assert groups[1]["id"] == int("-10020")
        assert contacts[0]["id"] == 30

    def test_bots_excluded(self):
        from telethon.tl.types import User

        bot = MagicMock(spec=User); bot.bot = True; bot.id = 99
        client = self._make_client([_make_dialog(bot, "Bot", None)])
        groups, contacts = asyncio.run(fetch_all_dialogs(client))
        assert contacts == []


# ---------------------------------------------------------------------------
# get_active_groups / get_active_contacts
# ---------------------------------------------------------------------------

class TestGetActiveGroups:
    def _make_client(self, dialogs):
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter(dialogs)
        return client

    def test_recent_group_included(self):
        from telethon.tl.types import Channel

        ch = MagicMock(spec=Channel); ch.id = 42
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        client = self._make_client([_make_dialog(ch, "Active", recent)])
        result = asyncio.run(get_active_groups(client))
        assert len(result) == 1
        assert result[0]["name"] == "Active"

    def test_old_group_excluded(self):
        from telethon.tl.types import Channel

        ch = MagicMock(spec=Channel); ch.id = 42
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        client = self._make_client([_make_dialog(ch, "Old", old)])
        result = asyncio.run(get_active_groups(client))
        assert result == []


class TestGetActiveContacts:
    def _make_client(self, dialogs):
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter(dialogs)
        return client

    def test_recent_contact_included(self):
        from telethon.tl.types import User

        u = MagicMock(spec=User); u.bot = False; u.id = 55
        recent = datetime.now(timezone.utc) - timedelta(hours=2)
        client = self._make_client([_make_dialog(u, "Alice", recent)])
        result = asyncio.run(get_active_contacts(client))
        assert len(result) == 1
        assert result[0]["id"] == 55

    def test_old_contact_excluded(self):
        from telethon.tl.types import User

        u = MagicMock(spec=User); u.bot = False; u.id = 55
        old = datetime.now(timezone.utc) - timedelta(hours=26)
        client = self._make_client([_make_dialog(u, "Old", old)])
        result = asyncio.run(get_active_contacts(client))
        assert result == []

    def test_bot_excluded(self):
        from telethon.tl.types import User

        bot = MagicMock(spec=User); bot.bot = True; bot.id = 77
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        client = self._make_client([_make_dialog(bot, "Bot", recent)])
        result = asyncio.run(get_active_contacts(client))
        assert result == []


# ---------------------------------------------------------------------------
# get_message_archive
# ---------------------------------------------------------------------------

class TestGetMessageArchive:
    def _make_client(self, messages):
        client = MagicMock()
        client.iter_messages.return_value = _aiter(messages)
        return client

    def test_messages_within_period_returned(self):
        recent = datetime.now(timezone.utc) - timedelta(hours=2)
        msgs = [_make_msg(1, recent, 100, text="hello")]
        result = asyncio.run(get_message_archive(self._make_client(msgs), 123, period=1))
        assert len(result) == 1
        assert result[0]["text"] == "hello"
        assert result[0]["from_id"] == 100

    def test_messages_outside_period_excluded(self):
        old = datetime.now(timezone.utc) - timedelta(days=2)
        msgs = [_make_msg(1, old, 100, text="old")]
        result = asyncio.run(get_message_archive(self._make_client(msgs), 123, period=1))
        assert result == []

    def test_stops_at_cutoff(self):
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        old = datetime.now(timezone.utc) - timedelta(days=5)
        msgs = [
            _make_msg(2, recent, 100, text="new"),
            _make_msg(1, old, 100, text="old"),
        ]
        result = asyncio.run(get_message_archive(self._make_client(msgs), 123, period=1))
        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_message_fields_present(self):
        recent = datetime.now(timezone.utc) - timedelta(minutes=30)
        msgs = [_make_msg(7, recent, 42, text="hi")]
        result = asyncio.run(get_message_archive(self._make_client(msgs), 1, period=1))
        assert set(result[0].keys()) == {"id", "date", "from_id", "text", "type", "media_path"}

    def test_period_30_days(self):
        date_25d = datetime.now(timezone.utc) - timedelta(days=25)
        msgs = [_make_msg(1, date_25d, 10, text="old but within 30d")]
        result = asyncio.run(get_message_archive(self._make_client(msgs), 1, period=30))
        assert len(result) == 1


# ---------------------------------------------------------------------------
# get_new_groups
# ---------------------------------------------------------------------------

class TestGetNewGroups:
    def _make_client(self, dialogs):
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter(dialogs)
        return client

    def test_recently_created_group_included(self):
        from telethon.tl.types import Channel

        ch = MagicMock(spec=Channel)
        ch.id = 10
        ch.date = datetime.now(timezone.utc) - timedelta(hours=2)
        client = self._make_client([_make_dialog(ch, "NewGroup", ch.date)])
        result = asyncio.run(get_new_groups(client, period=1))
        assert len(result) == 1
        assert result[0]["name"] == "NewGroup"
        assert "created" in result[0]

    def test_old_group_excluded(self):
        from telethon.tl.types import Channel

        ch = MagicMock(spec=Channel)
        ch.id = 10
        ch.date = datetime.now(timezone.utc) - timedelta(days=10)
        client = self._make_client([_make_dialog(ch, "OldGroup", ch.date)])
        result = asyncio.run(get_new_groups(client, period=1))
        assert result == []

    def test_chat_type_included(self):
        from telethon.tl.types import Chat

        chat = MagicMock(spec=Chat)
        chat.id = 20
        chat.date = datetime.now(timezone.utc) - timedelta(hours=1)
        client = self._make_client([_make_dialog(chat, "NewChat", chat.date)])
        result = asyncio.run(get_new_groups(client, period=1))
        assert len(result) == 1
        assert result[0]["id"] == -20

    def test_channel_id_formatted_correctly(self):
        from telethon.tl.types import Channel

        ch = MagicMock(spec=Channel)
        ch.id = 999
        ch.date = datetime.now(timezone.utc) - timedelta(hours=1)
        client = self._make_client([_make_dialog(ch, "Ch", ch.date)])
        result = asyncio.run(get_new_groups(client, period=1))
        assert result[0]["id"] == int("-100999")

    def test_period_respected(self):
        from telethon.tl.types import Channel

        ch = MagicMock(spec=Channel)
        ch.id = 1
        ch.date = datetime.now(timezone.utc) - timedelta(days=3)
        client = self._make_client([_make_dialog(ch, "Group", ch.date)])
        assert asyncio.run(get_new_groups(client, period=2)) == []
        client.iter_dialogs.return_value = _aiter([_make_dialog(ch, "Group", ch.date)])
        assert len(asyncio.run(get_new_groups(client, period=5))) == 1


# ---------------------------------------------------------------------------
# get_new_contacts
# ---------------------------------------------------------------------------

class TestGetNewContacts:
    def _make_client(self, dialogs, first_msg=None):
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter(dialogs)
        client.iter_messages.return_value = _aiter([first_msg] if first_msg else [])
        return client

    def test_new_contact_included(self):
        from telethon.tl.types import User

        u = MagicMock(spec=User); u.bot = False; u.id = 55
        first = _make_msg(1, datetime.now(timezone.utc) - timedelta(hours=2), 55)
        client = self._make_client([_make_dialog(u, "Alice", first.date)], first_msg=first)
        result = asyncio.run(get_new_contacts(client, period=1))
        assert len(result) == 1
        assert result[0]["id"] == 55
        assert "first_message" in result[0]

    def test_old_contact_excluded(self):
        from telethon.tl.types import User

        u = MagicMock(spec=User); u.bot = False; u.id = 55
        first = _make_msg(1, datetime.now(timezone.utc) - timedelta(days=10), 55)
        client = self._make_client([_make_dialog(u, "Bob", first.date)], first_msg=first)
        result = asyncio.run(get_new_contacts(client, period=1))
        assert result == []

    def test_bot_excluded(self):
        from telethon.tl.types import User

        bot = MagicMock(spec=User); bot.bot = True; bot.id = 77
        client = self._make_client([_make_dialog(bot, "Bot", datetime.now(timezone.utc))])
        result = asyncio.run(get_new_contacts(client, period=1))
        assert result == []

    def test_no_messages_excluded(self):
        from telethon.tl.types import User

        u = MagicMock(spec=User); u.bot = False; u.id = 88
        client = self._make_client([_make_dialog(u, "Ghost", datetime.now(timezone.utc))])
        result = asyncio.run(get_new_contacts(client, period=1))
        assert result == []


# ---------------------------------------------------------------------------
# _read_ids_file
# ---------------------------------------------------------------------------

class TestReadIdsFile:
    def test_reads_ids(self, tmp_path):
        f = tmp_path / "ids.txt"
        f.write_text("123\n-456\n789\n")
        assert _read_ids_file(str(f)) == [123, -456, 789]

    def test_ignores_comments(self, tmp_path):
        f = tmp_path / "ids.txt"
        f.write_text("# group\n-100123\n")
        assert _read_ids_file(str(f)) == [-100123]

    def test_ignores_empty_lines(self, tmp_path):
        f = tmp_path / "ids.txt"
        f.write_text("\n111\n\n222\n")
        assert _read_ids_file(str(f)) == [111, 222]

    def test_strips_inline_comments(self, tmp_path):
        f = tmp_path / "ids.txt"
        f.write_text("999  # this is a contact\n")
        assert _read_ids_file(str(f)) == [999]


# ---------------------------------------------------------------------------
# save_active_lists
# ---------------------------------------------------------------------------

class TestSaveActiveLists:
    def _make_client(self, groups=None, contacts=None):
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([])
        return client

    def test_creates_groups_csv(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from telethon.tl.types import Channel

        ch = MagicMock(spec=Channel); ch.id = 1
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([_make_dialog(ch, "G", recent)])
        asyncio.run(save_active_lists(client, period=1, mode="groups"))
        files = list(tmp_path.glob("active_groups_*.csv"))
        assert len(files) == 1

    def test_creates_contacts_csv(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from telethon.tl.types import User

        u = MagicMock(spec=User); u.bot = False; u.id = 2
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([_make_dialog(u, "C", recent)])
        asyncio.run(save_active_lists(client, period=1, mode="contacts"))
        files = list(tmp_path.glob("active_contacts_*.csv"))
        assert len(files) == 1

    def test_filename_contains_date_and_period(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([])
        asyncio.run(save_active_lists(client, period=7, mode="groups"))
        files = list(tmp_path.glob("active_groups_*_7d.csv"))
        assert len(files) == 1

    def test_mode_both_creates_two_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([])
        asyncio.run(save_active_lists(client, period=1, mode="both"))
        assert len(list(tmp_path.glob("active_groups_*.csv"))) == 1
        assert len(list(tmp_path.glob("active_contacts_*.csv"))) == 1


# ---------------------------------------------------------------------------
# save_new_lists
# ---------------------------------------------------------------------------

class TestSaveNewLists:
    def test_creates_new_groups_csv(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([])
        asyncio.run(save_new_lists(client, period=3, mode="groups"))
        files = list(tmp_path.glob("new_groups_*_3d.csv"))
        assert len(files) == 1

    def test_creates_new_contacts_csv(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([])
        asyncio.run(save_new_lists(client, period=5, mode="contacts"))
        files = list(tmp_path.glob("new_contacts_*_5d.csv"))
        assert len(files) == 1

    def test_filename_contains_date_and_period(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        today = datetime.now().strftime("%Y-%m-%d")
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([])
        asyncio.run(save_new_lists(client, period=14, mode="groups"))
        files = list(tmp_path.glob(f"new_groups_{today}_14d.csv"))
        assert len(files) == 1

    def test_mode_both_creates_two_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([])
        asyncio.run(save_new_lists(client, period=1, mode="both"))
        assert len(list(tmp_path.glob("new_groups_*.csv"))) == 1
        assert len(list(tmp_path.glob("new_contacts_*.csv"))) == 1


# ---------------------------------------------------------------------------
# save_all_lists
# ---------------------------------------------------------------------------

class TestSaveAllLists:
    def test_creates_groups_csv_regardless_of_activity(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from telethon.tl.types import Channel

        ch = MagicMock(spec=Channel); ch.id = 1
        old = datetime.now(timezone.utc) - timedelta(days=365)
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([_make_dialog(ch, "G", old)])
        asyncio.run(save_all_lists(client, mode="groups"))
        assert (tmp_path / "groups.csv").exists()

    def test_creates_contacts_csv_regardless_of_activity(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from telethon.tl.types import User

        u = MagicMock(spec=User); u.bot = False; u.id = 2
        old = datetime.now(timezone.utc) - timedelta(days=365)
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([_make_dialog(u, "C", old)])
        asyncio.run(save_all_lists(client, mode="contacts"))
        assert (tmp_path / "contacts.csv").exists()

    def test_mode_groups_only_creates_groups_csv(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([])
        asyncio.run(save_all_lists(client, mode="groups"))
        assert (tmp_path / "groups.csv").exists()
        assert not (tmp_path / "contacts.csv").exists()

    def test_mode_both_creates_two_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        client = MagicMock()
        client.iter_dialogs.return_value = _aiter([])
        asyncio.run(save_all_lists(client, mode="both"))
        assert (tmp_path / "groups.csv").exists()
        assert (tmp_path / "contacts.csv").exists()


# ---------------------------------------------------------------------------
# get_forum_topics
# ---------------------------------------------------------------------------

class TestGetForumTopics:
    def _make_client(self):
        client = AsyncMock()
        client.get_input_entity.return_value = "peer"
        return client

    def test_single_page(self):
        date = datetime.now(timezone.utc)
        topic = _make_topic(1, "General", date)
        client = self._make_client()
        client.return_value = SimpleNamespace(topics=[topic])

        result = asyncio.run(get_forum_topics(client, -100123))

        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["title"] == "General"
        assert result[0]["closed"] is False
        assert result[0]["created"] == date.isoformat()

    def test_deleted_topics_skipped(self):
        from telethon.tl.types import ForumTopicDeleted

        deleted = MagicMock(spec=ForumTopicDeleted)
        deleted.id = 5
        topic = _make_topic(1, "Kept", datetime.now(timezone.utc))
        client = self._make_client()
        client.return_value = SimpleNamespace(topics=[deleted, topic])

        result = asyncio.run(get_forum_topics(client, -100123))

        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_pagination_follows_offset(self):
        date1 = datetime.now(timezone.utc)
        date2 = date1 - timedelta(days=1)
        page1 = [_make_topic(i, f"Topic{i}", date1) for i in range(100)]
        page2 = [_make_topic(200, "Last", date2)]
        client = self._make_client()
        client.side_effect = [SimpleNamespace(topics=page1), SimpleNamespace(topics=page2)]

        result = asyncio.run(get_forum_topics(client, -100123))

        assert len(result) == 101
        assert result[-1]["id"] == 200

    def test_empty_result(self):
        client = self._make_client()
        client.return_value = SimpleNamespace(topics=[])

        result = asyncio.run(get_forum_topics(client, -100123))

        assert result == []


# ---------------------------------------------------------------------------
# save_topics_list
# ---------------------------------------------------------------------------

class TestSaveTopicsList:
    def test_creates_csv_named_with_group_id_and_date(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        today = datetime.now().strftime("%Y-%m-%d")
        topic = _make_topic(1, "General", datetime.now(timezone.utc))
        client = AsyncMock()
        client.get_input_entity.return_value = "peer"
        client.return_value = SimpleNamespace(topics=[topic])

        asyncio.run(save_topics_list(client, -100123456))

        files = list(tmp_path.glob(f"topics_-100123456_{today}.csv"))
        assert len(files) == 1
