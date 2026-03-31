#!/usr/bin/env python3
"""
Export all data from Beeper Desktop — messages, media, and contacts
across every connected account (WhatsApp, Telegram, Signal, Discord, etc.)

Usage:
    python download.py                        # export everything
    python download.py --account gmessages    # one account only
    python download.py --no-media             # skip media download
    python download.py --list-accounts        # show available accounts
"""

import argparse
import json
import os
import platform
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── args ──────────────────────────────────────────────────────────────────────

def default_db():
    system = platform.system()
    if system == "Darwin":
        return str(Path.home() / "Library/Application Support/BeeperTexts/index.db")
    elif system == "Windows":
        return str(Path(os.environ.get("APPDATA", "")) / "BeeperTexts/index.db")
    else:
        return str(Path.home() / ".config/BeeperTexts/index.db")

parser = argparse.ArgumentParser(description="Export all Beeper Desktop data")
parser.add_argument("--account", help="Export only this account ID (default: all accounts)")
parser.add_argument("--db", default=default_db(), help="Path to Beeper index.db")
parser.add_argument("--out", default="beeper-export", help="Output directory (default: ./beeper-export)")
parser.add_argument("--token", default=".beeper_token", help="Path to Beeper API token file")
parser.add_argument("--beeper-url", default="http://localhost:23373", help="Beeper Desktop API URL")
parser.add_argument("--no-media", action="store_true", help="Skip downloading media attachments")
parser.add_argument("--list-accounts", action="store_true", help="List available accounts and exit")
args = parser.parse_args()

# ── setup ─────────────────────────────────────────────────────────────────────

DB_PATH = args.db
OUT = Path(args.out)
BASE = args.beeper_url

if not Path(DB_PATH).exists():
    print(f"ERROR: Beeper database not found at: {DB_PATH}")
    print("Make sure Beeper Desktop is installed, or pass --db with the correct path.")
    raise SystemExit(1)

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row

if args.list_accounts:
    rows = con.execute(
        "SELECT accountID, COUNT(*) as chats FROM threads GROUP BY accountID ORDER BY chats DESC"
    ).fetchall()
    print("Accounts in Beeper database:")
    for r in rows:
        if not r["accountID"].startswith("$"):
            print(f"  {r['accountID']:<45} {r['chats']} chats")
    con.close()
    raise SystemExit(0)

# Load token for media
token = None
headers = {}
if not args.no_media:
    token_path = Path(args.token)
    if token_path.exists():
        token = token_path.read_text().strip()
        headers = {"Authorization": f"Bearer {token}"}
    else:
        print(f"NOTE: Token file '{args.token}' not found. Run get_token.py first, or use --no-media.")
        print()

# Which accounts to export
if args.account:
    accounts_to_export = [args.account]
else:
    rows = con.execute(
        "SELECT DISTINCT accountID FROM threads WHERE accountID NOT LIKE '$%' ORDER BY accountID"
    ).fetchall()
    accounts_to_export = [r["accountID"] for r in rows]

# ── helpers ───────────────────────────────────────────────────────────────────

def safe_name(s):
    return re.sub(r'[^\w\-. ]', '_', str(s))[:80].strip()

def fmt_date(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def download_media(mxc_url, dest_path):
    if not token:
        return False
    try:
        r = requests.get(
            f"{BASE}/v1/assets/serve",
            headers=headers,
            params={"url": mxc_url},
            timeout=60,
            stream=True,
        )
        if r.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return True
    except Exception:
        pass
    return False

def get_participants(thread_id, account_id):
    rows = con.execute(
        """SELECT p.full_name, p.is_self,
                  pi.identifier as phone
           FROM participants p
           LEFT JOIN participant_identifiers pi
             ON pi.account_id = p.account_id
            AND pi.participant_id = p.id
            AND pi.identifier_type = 'phone'
           WHERE p.room_id = ? AND p.is_network_bot = 0""",
        (thread_id,)
    ).fetchall()
    return [
        {
            "name": r["full_name"],
            "phone": r["phone"],
            "is_self": bool(r["is_self"]),
        }
        for r in rows
    ]

def get_messages(thread_id):
    rows = con.execute(
        """SELECT message FROM mx_room_messages
           WHERE roomID = ? AND isDeleted = 0 AND type NOT IN ('HIDDEN', 'REACTION')
           ORDER BY hsOrder ASC""",
        (thread_id,)
    ).fetchall()
    messages = []
    for row in rows:
        try:
            messages.append(json.loads(row["message"]))
        except Exception:
            pass
    return messages

# ── export ────────────────────────────────────────────────────────────────────

OUT.mkdir(parents=True, exist_ok=True)

export_summary = {
    "exported_at": datetime.now(tz=timezone.utc).isoformat(),
    "accounts": [],
}

grand_total_chats = 0
grand_total_messages = 0
grand_total_media = 0
grand_total_media_ok = 0

for account_id in accounts_to_export:
    threads = con.execute(
        "SELECT threadID, thread FROM threads WHERE accountID = ? ORDER BY timestamp DESC",
        (account_id,)
    ).fetchall()

    if not threads:
        continue

    print(f"\n{'='*60}")
    print(f"Account: {account_id}  ({len(threads)} chats)")
    print(f"{'='*60}")

    account_dir = OUT / safe_name(account_id)
    account_dir.mkdir(parents=True, exist_ok=True)

    account_summary = {
        "account_id": account_id,
        "chats": [],
        "total_messages": 0,
        "total_media": 0,
    }

    for i, trow in enumerate(threads, 1):
        thread_id = trow["threadID"]
        thread = json.loads(trow["thread"])

        participants = get_participants(thread_id, account_id)
        others = [p for p in participants if not p["is_self"]]
        names  = [p["name"] for p in others if p["name"]]
        phones = [p["phone"] for p in others if p["phone"]]

        title = (
            thread.get("title")
            or (", ".join(names) if names else None)
            or (", ".join(phones) if phones else None)
            or thread_id
        )

        short_id = thread_id.split("!")[1][:10] if "!" in thread_id else thread_id[-10:]
        folder_name = safe_name(title) + "__" + safe_name(short_id)
        chat_dir = account_dir / folder_name
        chat_dir.mkdir(parents=True, exist_ok=True)
        media_dir = chat_dir / "media"

        messages = get_messages(thread_id)
        total_media = 0
        media_ok = 0

        if not args.no_media:
            for msg in messages:
                for att in msg.get("attachments") or []:
                    mxc = att.get("id")
                    if not mxc:
                        continue
                    total_media += 1
                    media_dir.mkdir(exist_ok=True)
                    mime = att.get("mimeType", "")
                    ext = ("." + mime.split("/")[-1].replace("jpeg", "jpg")) if mime else ""
                    fname = att.get("fileName") or att.get("file_name") or f"{msg.get('eventID','x')[-16:]}{ext}"
                    dest = media_dir / safe_name(fname)
                    if dest.exists():
                        att["_local_path"] = str(dest)
                        media_ok += 1
                        continue
                    if download_media(mxc, dest):
                        att["_local_path"] = str(dest)
                        media_ok += 1
                    else:
                        src = att.get("srcURL", "")
                        if src.startswith("file://"):
                            local = src[7:]
                            if os.path.exists(local):
                                shutil.copy2(local, dest)
                                att["_local_path"] = str(dest)
                                media_ok += 1

        # Save chat JSON
        chat_data = {
            "chat": {
                "id": thread_id,
                "account_id": account_id,
                "title": title,
                "type": thread.get("type"),
                "participants": participants,
            },
            "messages": messages,
        }
        with open(chat_dir / "messages.json", "w") as f:
            json.dump(chat_data, f, indent=2, default=str)

        media_str = f"  {media_ok}/{total_media} media" if total_media else ""
        print(f"  [{i}/{len(threads)}] {title}: {len(messages)} messages{media_str}")

        account_summary["chats"].append({
            "title": title,
            "thread_id": thread_id,
            "message_count": len(messages),
            "media_count": total_media,
            "participants": others,
        })
        account_summary["total_messages"] += len(messages)
        account_summary["total_media"] += total_media

        grand_total_chats += 1
        grand_total_messages += len(messages)
        grand_total_media += total_media
        grand_total_media_ok += media_ok

    # Save account-level JSON index
    with open(account_dir / "index.json", "w") as f:
        json.dump(account_summary, f, indent=2, default=str)

    export_summary["accounts"].append({
        "account_id": account_id,
        "chats": len(threads),
        "messages": account_summary["total_messages"],
        "media": account_summary["total_media"],
    })

con.close()

# Save top-level summary
export_summary["totals"] = {
    "accounts": len(accounts_to_export),
    "chats": grand_total_chats,
    "messages": grand_total_messages,
    "media": grand_total_media,
}
with open(OUT / "export_summary.json", "w") as f:
    json.dump(export_summary, f, indent=2, default=str)

print(f"\n{'='*60}")
print(f"Export complete")
print(f"  Accounts:  {len(accounts_to_export)}")
print(f"  Chats:     {grand_total_chats}")
print(f"  Messages:  {grand_total_messages}")
if not args.no_media:
    print(f"  Media:     {grand_total_media_ok}/{grand_total_media} downloaded")
print(f"  Output:    {OUT}/")
