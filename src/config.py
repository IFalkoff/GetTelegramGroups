import os
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

Period = Literal[1, 2, 3, 4, 5, 6, 7, 10, 14, 21, 30]

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.getenv("SESSION", os.path.expanduser("~/.telegram_session"))

GROUPS_CSV = "groups.csv"
CONTACTS_CSV = "contacts.csv"
ACTIVE_GROUPS_CSV = "active_groups.csv"
ACTIVE_CONTACTS_CSV = "active_contacts.csv"
