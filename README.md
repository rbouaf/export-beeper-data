
Export all your Beeper messages, media, and contacts to your local machine.

Beeper currently has no built-in data export feature. This tool reads directly from Beeper Desktop's local SQLite database to give you a complete, portable copy of everything — across every connected account.

## What gets exported

- **Messages** — full history from every chat, on every account
- **Media** — images, videos, audio, and files (downloaded via the local API)
- **Contacts** — participant names and phone numbers per chat
- **Account index** — structured JSON summary per account

Supported accounts include WhatsApp, Telegram, Signal, Discord, Facebook Messenger, Instagram, LinkedIn, Slack, Google Messages, and any other network you've connected to Beeper.

## Requirements

- **Beeper Desktop** installed (v4.1.169+)
- **Python 3.9+**
- `pip install requests`

## Quick start

```bash
pip install requests

# Step 1: authorize (Beeper Desktop must be open)
python get_token.py

# Step 2: export everything
python download.py
```

Output goes to `./beeper-export/`.

---

## Step 1 — Authorize (`get_token.py`)

Launches a browser to authorize access to Beeper Desktop's local API. Saves the token to `.beeper_token`.

**Before running:**
1. Open Beeper Desktop
2. Go to `Settings → Developers → Enable Beeper Desktop API`

```bash
python get_token.py
```

The token is saved locally and never leaves your machine.

---

## Step 2 — Export (`download.py`)

Reads from Beeper's local database and downloads all messages and media.

```bash
python download.py
```

**Options:**

```
--account ID       Export only one account (e.g. whatsapp, telegram, gmessages)
--out DIR          Output directory (default: ./beeper-export)
--no-media         Skip media downloads (exports text messages only)
--list-accounts    Show all available account IDs and exit
--db PATH          Path to Beeper's index.db (auto-detected)
--token FILE       Path to token file (default: .beeper_token)
--beeper-url URL   Beeper API URL (default: http://localhost:23373)
```

**Examples:**

```bash
# See what accounts are available
python download.py --list-accounts

# Export everything
python download.py

# Export one account
python download.py --account telegram --out ./telegram-backup

# Export text only, no media (faster, no Beeper needed)
python download.py --no-media
```

---

## Output structure

```
beeper-export/
├── export_summary.json          ← totals across all accounts
├── whatsapp/
│   ├── index.json               ← account-level summary
│   ├── John_Doe__a1b2c3d4e5/
│   │   ├── messages.json        ← all messages + participant info
│   │   └── media/
│   │       ├── photo.jpg
│   │       └── video.mp4
│   └── Family_Group__f6g7h8i9j0/
│       ├── messages.json
│       └── media/
├── telegram/
│   └── ...
└── gmessages/
    └── ...
```

### `messages.json` format

```json
{
  "chat": {
    "id": "!roomID:beeper.local",
    "account_id": "whatsapp",
    "title": "John Doe",
    "type": "single",
    "participants": [
      { "name": "John Doe", "phone": "+15141234567", "is_self": false },
      { "name": "You",      "phone": "+14381234567", "is_self": true  }
    ]
  },
  "messages": [
    {
      "timestamp": "2024-11-15T14:32:10.000Z",
      "text": "Hey, what's up?",
      "isSender": false,
      "attachments": [],
      ...
    }
  ]
}
```

---

## Notes

- **No network required** for text messages — everything is read from the local database. The account doesn't need to be connected.
- **Media downloads** require Beeper Desktop to be running (uses the local API to serve cached files). Use `--no-media` if Beeper isn't open.
- Deleted messages are excluded.
- Internal system messages (`HIDDEN`, `REACTION` types) are excluded.

## Database locations

| Platform | Path |
|----------|------|
| macOS    | `~/Library/Application Support/BeeperTexts/index.db` |
| Windows  | `%APPDATA%\BeeperTexts\index.db` |
| Linux    | `~/.config/BeeperTexts/index.db` |
