import os

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION", os.path.expanduser("~/.telegram_session"))

client = TelegramClient(SESSION, API_ID, API_HASH)


async def main():
    me = await client.get_me()
    print(f"Logged in as: {me.username} ({me.phone})")

    async for dialog in client.iter_dialogs():
        print(dialog.name, "has ID", dialog.id)


with client:
    client.loop.run_until_complete(main())
