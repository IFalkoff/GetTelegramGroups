import argparse
import asyncio
import csv
import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import get_args

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User

from config import (
    API_HASH,
    API_ID,
    CONTACTS_CSV,
    GROUPS_CSV,
    SESSION,
    Period,
)

def _setup_logging() -> logging.Logger:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    os.makedirs("logs", exist_ok=True)
    rotated = logging.handlers.RotatingFileHandler(
        "logs/app.log", maxBytes=1 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    rotated.setFormatter(fmt)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(console)
    logger.addHandler(rotated)
    return logger

log = _setup_logging()


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


def _archive_path(category: str, name: str) -> str:
    """Формирует путь к файлу архива.

    Args:
        category: Подкаталог — ``"groups"`` или ``"contacts"``.
        name: Отображаемое имя сущности; пробелы заменяются на ``_``.

    Returns:
        Путь вида ``archives/groups/<name>.json``.
    """
    safe_name = name.replace(" ", "_")
    # Символы, недопустимые в именах файлов Windows: \ / : * ? " < > |
    for char in r'\/:*?"<>|':
        safe_name = safe_name.replace(char, "_")
    return os.path.join("archives", category, f"{safe_name}.json")


async def fetch_active_archives(
    client: TelegramClient,
    period: Period = 1,
    mode: str = "both",
) -> None:
    """Собирает архивы сообщений по активным группам и/или контактам за указанный период.

    Для каждой сущности создаётся отдельный JSON-файл в каталоге ``archives/groups/``
    или ``archives/contacts/``. Имя файла совпадает с именем группы/контакта,
    пробелы и недопустимые символы заменяются на ``_``.

    Args:
        client: Авторизованный экземпляр TelegramClient.
        period: Глубина выборки в днях. Допустимые значения: 1, 3, 5, 30.
        mode: Режим выгрузки — ``"groups"``, ``"contacts"`` или ``"both"``.
    """
    os.makedirs(os.path.join("archives", "groups"), exist_ok=True)
    os.makedirs(os.path.join("archives", "contacts"), exist_ok=True)

    active_groups = await get_active_groups(client) if mode in ("groups", "both") else []
    active_contacts = await get_active_contacts(client) if mode in ("contacts", "both") else []

    log.info("Fetching archives (period=%dd, mode=%s): %d groups, %d contacts",
             period, mode, len(active_groups), len(active_contacts))

    total = 0
    for g in active_groups:
        messages = await get_message_archive(client, g["id"], period=period)
        path = _archive_path("groups", g["name"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"id": g["id"], "name": g["name"], "messages": messages}, f, ensure_ascii=False, indent=2)
        total += len(messages)
        log.info("  group   [%s] %s: %d messages -> %s", g["id"], g["name"], len(messages), path)

    for c in active_contacts:
        messages = await get_message_archive(client, c["id"], period=period)
        path = _archive_path("contacts", c["name"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"id": c["id"], "name": c["name"], "messages": messages}, f, ensure_ascii=False, indent=2)
        total += len(messages)
        log.info("  contact [%s] %s: %d messages -> %s", c["id"], c["name"], len(messages), path)

    log.info("Saved %d total messages across %d files", total, len(active_groups) + len(active_contacts))


def parse_args() -> argparse.Namespace:
    """Разбирает аргументы командной строки.

    Returns:
        Namespace с полями ``period`` и ``mode``.
    """
    parser = argparse.ArgumentParser(description="Export Telegram message archives.")
    parser.add_argument(
        "--period",
        type=int,
        choices=list(get_args(Period)),
        default=1,
        help="Number of days to look back (default: 1).",
    )
    parser.add_argument(
        "--mode",
        type=str.lower,
        choices=["groups", "contacts", "both"],
        default="both",
        help="What to export: groups, contacts, or both (default: both).",
    )
    parser.add_argument(
        "--id",
        type=int,
        metavar="CHAT_ID",
        help="Fetch archive for a specific chat/contact by ID (skips all other steps).",
    )
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    async with TelegramClient(SESSION, API_ID, API_HASH) as client:
        me = await client.get_me()
        log.info("Logged in as: %s (%s)", me.username, me.phone)

        if args.id is not None:
            os.makedirs(os.path.join("archives"), exist_ok=True)
            messages = await get_message_archive(client, args.id, period=args.period)
            path = os.path.join("archives", f"{args.id}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"id": args.id, "messages": messages}, f, ensure_ascii=False, indent=2)
            log.info("Saved %d messages -> %s", len(messages), path)
            return

        if is_fresh(GROUPS_CSV) and is_fresh(CONTACTS_CSV):
            log.info("groups.csv and contacts.csv are up to date, skipping fetch.")
        else:
            groups, contacts = await fetch_all_dialogs(client)

            with open(GROUPS_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["id", "name"])
                writer.writeheader()
                writer.writerows(groups)
            log.info("Saved %d groups -> %s", len(groups), GROUPS_CSV)

            with open(CONTACTS_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["id", "name"])
                writer.writeheader()
                writer.writerows(contacts)
            log.info("Saved %d contacts -> %s", len(contacts), CONTACTS_CSV)

        await fetch_active_archives(client, period=args.period, mode=args.mode)


if __name__ == "__main__":
    asyncio.run(main())
