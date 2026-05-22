# GetTelegramGroups

Инструмент для выгрузки данных из Telegram: списки групп и контактов, архивы сообщений с медиафайлами. Работает через Telegram User API (Telethon) — от имени пользователя, не бота.

## Содержание

- [Требования](#требования)
- [Установка](#установка)
- [Настройка](#настройка)
- [Использование](#использование)
- [Структура выходных файлов](#структура-выходных-файлов)
- [Логирование](#логирование)
- [Тесты](#тесты)

---

## Требования

- Python 3.14+
- Telegram API credentials (API ID и API Hash)

---

## Установка

```bash
git clone https://github.com/IFalkoff/GetTelegramGroups.git
cd GetTelegramGroups
python -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows
pip install -e .
pip install -e ".[dev]"         # для запуска тестов
```

---

## Настройка

1. Получите **API ID** и **API Hash** на [my.telegram.org](https://my.telegram.org).
2. Создайте файл `.env` в корне проекта:

```env
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890
# SESSION=~/.telegram_session   # необязательно, путь к файлу сессии
```

При первом запуске Telethon запросит номер телефона и код подтверждения — сессия сохранится в файл и повторная авторизация не потребуется.

---

## Использование

Все команды запускаются из корня проекта:

```bash
python src/main.py [флаги]
```

Имена флагов регистронезависимы: `--Period`, `--PERIOD`, `--period` — одно и то же.

### Справка

```bash
python src/main.py
```

```
usage: main.py [-h] [--period {1,2,3,4,5,6,7,10,14,21,30}]
               [--mode {groups,contacts,both}] [--list] [--new]
               [--id CHAT_ID] [--ids CHAT_ID [CHAT_ID ...]] [--ids-file FILE]
```

---

### Режимы работы

#### 1. Архив активных групп и контактов (режим по умолчанию)

Выгружает сообщения за указанный период из всех групп и контактов, в которых была активность. Медиафайлы скачиваются автоматически.

```bash
# За последний день (по умолчанию), группы и контакты
python src/main.py --period 1

# За последние 7 дней, только группы
python src/main.py --period 7 --mode groups

# За последние 30 дней, только контакты
python src/main.py --period 30 --mode contacts
```

**`--period`** — допустимые значения: `1 2 3 4 5 6 7 10 14 21 30`

**`--mode`** — `groups`, `contacts`, `both` (по умолчанию `both`)

Результат:
- `groups.csv` / `contacts.csv` — полные списки групп и контактов (обновляются раз в сутки)
- `archives/groups/<Название>.json` — архив сообщений группы
- `archives/contacts/<Имя>.json` — архив сообщений контакта
- `archives/groups/<Название>/` — медиафайлы группы
- `archives/contacts/<Имя>/` — медиафайлы контакта

---

#### 2. Архив конкретного чата по ID

```bash
# Один ID
python src/main.py --id 516283938 --period 7

# Несколько ID через пробел (группы и контакты вперемешку)
python src/main.py --ids 516283938 -1001645934290 123456789 --period 3

# Список ID из файла
python src/main.py --ids-file ids.txt --period 5

# Комбинация источников
python src/main.py --id 516283938 --ids -1001645934290 --ids-file more.txt
```

**Формат файла `ids.txt`:**
```
# группы (отрицательные ID)
-1001645934290
-1009876543210

# контакты (положительные ID)
516283938
967271328
```

Результат:
- `archives/<ID>.json` — архив сообщений
- `archives/<ID>/` — медиафайлы

Если ID не найден в кэше сессии — выводится предупреждение и обработка продолжается.

---

#### 3. Список активных групп и контактов (`--list`)

Сохраняет CSV-файлы с группами/контактами, в которых были сообщения за период.

```bash
# Активные группы и контакты за 7 дней
python src/main.py --list --period 7

# Только активные группы за 3 дня
python src/main.py --list --period 3 --mode groups

# Только активные контакты за 1 день
python src/main.py --list --mode contacts
```

Результат:
- `active_groups_2026-05-22_7d.csv` — поля: `id`, `name`, `last_message`
- `active_contacts_2026-05-22_7d.csv` — поля: `id`, `name`, `last_message`

---

#### 4. Список новых групп и контактов (`--new`)

Сохраняет CSV-файлы с группами/контактами, которые появились за период:
- **Группы** — дата создания группы/канала попадает в период
- **Контакты** — первое сообщение в переписке попадает в период

```bash
# Новые группы и контакты за 7 дней
python src/main.py --new --period 7

# Только новые группы за 30 дней
python src/main.py --new --period 30 --mode groups

# Только новые контакты за 14 дней
python src/main.py --new --period 14 --mode contacts
```

Результат:
- `new_groups_2026-05-22_7d.csv` — поля: `id`, `name`, `created`
- `new_contacts_2026-05-22_7d.csv` — поля: `id`, `name`, `first_message`

---

## Структура выходных файлов

```
.
├── groups.csv                          # все группы (id, name)
├── contacts.csv                        # все контакты (id, name)
├── active_groups_YYYY-MM-DD_Nd.csv     # активные группы за N дней
├── active_contacts_YYYY-MM-DD_Nd.csv   # активные контакты за N дней
├── new_groups_YYYY-MM-DD_Nd.csv        # новые группы за N дней
├── new_contacts_YYYY-MM-DD_Nd.csv      # новые контакты за N дней
├── archives/
│   ├── groups/
│   │   ├── Название_группы.json        # архив сообщений
│   │   └── Название_группы/            # медиафайлы
│   │       ├── photo_12345.jpg
│   │       └── voice_67890.ogg
│   ├── contacts/
│   │   ├── Имя_контакта.json
│   │   └── Имя_контакта/
│   └── <ID>.json                       # архив при запуске с --id/--ids
└── logs/
    ├── app.log                         # текущий лог
    └── app.log.1 … app.log.5          # ротированные логи
```

### Формат JSON-архива сообщений

```json
{
  "id": -1001645934290,
  "name": "Название группы",
  "messages": [
    {
      "id": 12345,
      "date": "2026-05-22T18:30:00+00:00",
      "from_id": 516283938,
      "text": "Текст сообщения",
      "type": "text",
      "media_path": null
    },
    {
      "id": 12346,
      "date": "2026-05-22T18:31:00+00:00",
      "from_id": 967271328,
      "text": "",
      "type": "photo",
      "media_path": "photo_12346.jpg"
    }
  ]
}
```

**Типы сообщений:** `text`, `photo`, `video`, `audio`, `document`, `sticker`

**Скачиваемые медиа:** фото, голосовые сообщения, аудио, видео, документы. Стикеры не скачиваются.

---

## Логирование

Логи пишутся одновременно в консоль и файл `logs/app.log`.
При достижении 1 МБ файл ротируется — хранится до 5 архивов.

```
2026-05-22 20:12:26 INFO Logged in as: username (+79001234567)
2026-05-22 20:12:27 INFO Fetching archives (period=7d, mode=both): 12 groups, 5 contacts
2026-05-22 20:12:28 INFO   group   [-1001645934290] My Group: 42 messages (3 media) -> archives/groups/My_Group.json
```

---

## Тесты

```bash
python -m pytest tests/ -v
```

Покрытие: `is_fresh`, `_archive_path`, `_message_type`, `parse_args`, `fetch_all_dialogs`, `get_active_groups`, `get_active_contacts`, `get_new_groups`, `get_new_contacts`, `get_message_archive`, `_read_ids_file`, `save_active_lists`, `save_new_lists`.
