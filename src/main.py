import asyncio
import csv
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Literal

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User

Period = Literal[1, 3, 5, 30]

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
            active.append(
                {
                    "id": group_id,
                    "name": dialog.name,
                    "last_message": dialog.date.isoformat(),
                }
            )
    return active


def _message_type(msg) -> str:
    """Определяет тип сообщения по вложению.

    Args:
        msg: Объект сообщения Telethon.

    Returns:
        Строка с типом: ``"photo"``, ``"sticker"``, ``"video"``, ``"audio"``,
        ``"document"`` или ``"text"``.
    """
    if msg.photo:
        return "photo"
    if msg.sticker:
        return "sticker"
    if msg.video:
        return "video"
    if msg.audio:
        return "audio"
    if msg.document:
        return "document"
    return "text"


async def get_message_archive(
    client: TelegramClient,
    entity_id: int,
    period: Period = 1,
) -> list[dict]:
    """Возвращает архив сообщений для группы или контакта за указанный период.

    Сообщения запрашиваются от новых к старым и собираются до тех пор, пока
    дата сообщения не окажется раньше отсечки. Требует, чтобы сущность была
    предварительно закеширована Telethon (например, после вызова
    ``fetch_all_dialogs``).

    Args:
        client: Авторизованный экземпляр TelegramClient.
        entity_id: ID группы (отрицательный) или контакта (положительный).
        period: Глубина выборки в днях. Допустимые значения: 1, 3, 5, 30.

    Returns:
        Список словарей с полями:
            - ``id`` — идентификатор сообщения;
            - ``date`` — дата в формате ISO 8601;
            - ``from_id`` — ID отправителя;
            - ``text`` — текст сообщения;
            - ``type`` — тип вложения или ``"text"``.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=period)
    messages = []
    async for msg in client.iter_messages(entity_id):
        if msg.date < cutoff:
            break
        messages.append(
            {
                "id": msg.id,
                "date": msg.date.isoformat(),
                "from_id": msg.sender_id,
                "text": msg.text or "",
                "type": _message_type(msg),
            }
        )
    return messages


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
            active.append(
                {
                    "id": entity.id,
                    "name": dialog.name,
                    "last_message": dialog.date.isoformat(),
                }
            )

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

        archive = await get_message_archive(client, 200521298, period=5)
        archive_path = "archive_124435179.json"
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)
        print(f"Archive for 124435179: {len(archive)} messages -> {archive_path}")


asyncio.run(main())
