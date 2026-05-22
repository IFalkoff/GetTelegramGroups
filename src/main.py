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

# Пути к выходным CSV-файлам
GROUPS_CSV = "groups.csv"
CONTACTS_CSV = "contacts.csv"
ACTIVE_GROUPS_CSV = "active_groups.csv"
ACTIVE_CONTACTS_CSV = "active_contacts.csv"


async def get_active_groups(client: TelegramClient) -> list[dict]:
    """Возвращает группы и каналы, в которых были новые сообщения за последние 24 часа."""
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
    """Возвращает пользователей, от которых были сообщения за последние 24 часа."""
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

        groups = []    # список групп и каналов, в которых участвует пользователь
        contacts = []  # список пользователей, с которыми есть личная переписка

        async for dialog in client.iter_dialogs():
            entity = dialog.entity

            # Группы (обычные чаты) и каналы/супергруппы.
            # Telegram Bot API использует отрицательные ID:
            #   Chat    -> -<id>
            #   Channel -> -100<id>
            if isinstance(entity, Chat):
                groups.append({"id": -entity.id, "name": dialog.name})
            elif isinstance(entity, Channel):
                groups.append({"id": int(f"-100{entity.id}"), "name": dialog.name})

            # Личные диалоги с реальными пользователями (не боты)
            elif isinstance(entity, User) and not entity.bot:
                contacts.append({"id": entity.id, "name": dialog.name})

        # Сохраняем список групп
        with open(GROUPS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name"])
            writer.writeheader()
            writer.writerows(groups)

        print(f"Saved {len(groups)} groups -> {GROUPS_CSV}")

        # Сохраняем список пользователей
        with open(CONTACTS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name"])
            writer.writeheader()
            writer.writerows(contacts)

        print(f"Saved {len(contacts)} contacts -> {CONTACTS_CSV}")

        # Группы с активностью за последние 24 часа
        active_groups = await get_active_groups(client)
        with open(ACTIVE_GROUPS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name", "last_message"])
            writer.writeheader()
            writer.writerows(active_groups)

        print(f"\nActive groups (last 24 h): {len(active_groups)}")
        for g in active_groups:
            print(f"  [{g['id']}] {g['name']}  —  {g['last_message']}")
        print(f"Saved -> {ACTIVE_GROUPS_CSV}")

        # Пользователи с активностью за последние 24 часа
        active_contacts = await get_active_contacts(client)
        with open(ACTIVE_CONTACTS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name", "last_message"])
            writer.writeheader()
            writer.writerows(active_contacts)

        print(f"\nActive contacts (last 24 h): {len(active_contacts)}")
        for c in active_contacts:
            print(f"  [{c['id']}] {c['name']}  —  {c['last_message']}")
        print(f"Saved -> {ACTIVE_CONTACTS_CSV}")


asyncio.run(main())
