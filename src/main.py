import asyncio
import csv
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.getenv("SESSION", os.path.expanduser("~/.telegram_session"))

GROUPS_CSV = "groups.csv"
CONTACTS_CSV = "contacts.csv"
ACTIVE_GROUPS_CSV = "active_groups.csv"
ACTIVE_CONTACTS_CSV = "active_contacts.csv"


def is_fresh(path: str) -> bool:
    """Проверяет, создан ли файл сегодня.

    Args:
        path: Путь к файлу.

    Returns:
        True, если файл существует и дата его изменения совпадает с сегодняшней.
    """
    if not os.path.exists(path):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    return mtime.date() == datetime.now().date()


async def fetch_all_dialogs(client: TelegramClient) -> tuple[list[dict], list[dict]]:
    """Загружает все диалоги и разделяет их на группы и контакты.

    Args:
        client: Авторизованный экземпляр TelegramClient.

    Returns:
        Кортеж (groups, contacts), где каждый элемент — список словарей
        с полями ``id`` и ``name``.
    """
    groups = []
    contacts = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        # Telegram Bot API использует отрицательные ID:
        #   Chat    -> -<id>
        #   Channel -> -100<id>
        if isinstance(entity, Chat):
            groups.append({"id": -entity.id, "name": dialog.name})
        elif isinstance(entity, Channel):
            groups.append({"id": int(f"-100{entity.id}"), "name": dialog.name})
        elif isinstance(entity, User) and not entity.bot:
            contacts.append({"id": entity.id, "name": dialog.name})
    return groups, contacts


async def get_active_groups(client: TelegramClient) -> list[dict]:
    """Возвращает группы с новыми сообщениями за последние 24 часа.

    Args:
        client: Авторизованный экземпляр TelegramClient.

    Returns:
        Список словарей с полями ``id``, ``name`` и ``last_message``.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    active = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if not isinstance(entity, (Chat, Channel)):
            continue
        if dialog.date and dialog.date >= cutoff:
            if isinstance(entity, Chat):
                group_id = -entity.id
            else:
                group_id = int(f"-100{entity.id}")
            active.append({
                "id": group_id,
                "name": dialog.name,
                "last_message": dialog.date.isoformat(),
            })
    return active


async def get_active_contacts(client: TelegramClient) -> list[dict]:
    """Возвращает контакты, от которых были сообщения за последние 24 часа.

    Args:
        client: Авторизованный экземпляр TelegramClient.

    Returns:
        Список словарей с полями ``id``, ``name`` и ``last_message``.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    active = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if not isinstance(entity, User) or entity.bot:
            continue
        if dialog.date and dialog.date >= cutoff:
            active.append({
                "id": entity.id,
                "name": dialog.name,
                "last_message": dialog.date.isoformat(),
            })
    return active


async def main():
    async with TelegramClient(SESSION, API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Logged in as: {me.username} ({me.phone})")

        if is_fresh(GROUPS_CSV) and is_fresh(CONTACTS_CSV):
            print("groups.csv and contacts.csv are up to date, skipping fetch.")
        else:
            groups, contacts = await fetch_all_dialogs(client)

            with open(GROUPS_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["id", "name"])
                writer.writeheader()
                writer.writerows(groups)
            print(f"Saved {len(groups)} groups -> {GROUPS_CSV}")

            with open(CONTACTS_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["id", "name"])
                writer.writeheader()
                writer.writerows(contacts)
            print(f"Saved {len(contacts)} contacts -> {CONTACTS_CSV}")


asyncio.run(main())
