import asyncio
import csv
import os

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
            #   Chat    → -<id>
            #   Channel → -100<id>
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

        print(f"Saved {len(groups)} groups → {GROUPS_CSV}")

        # Сохраняем список пользователей
        with open(CONTACTS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name"])
            writer.writeheader()
            writer.writerows(contacts)

        print(f"Saved {len(contacts)} contacts → {CONTACTS_CSV}")


asyncio.run(main())
