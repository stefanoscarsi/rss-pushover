import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import requests

SEEN_FILE = Path(__file__).parent / "seen.json"
FEEDS_FILE = Path(__file__).parent / "feeds.txt"
MAX_AGE_DAYS = 7

PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
PUSHOVER_USER_KEY = os.environ["PUSHOVER_USER_KEY"]
PUSHOVER_API_TOKEN = os.environ["PUSHOVER_API_TOKEN"]


def load_seen() -> dict:
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    return {}


def save_seen(seen: dict) -> None:
    SEEN_FILE.write_text(json.dumps(seen, indent=2, ensure_ascii=False), encoding="utf-8")


def prune_seen(seen: dict) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    return {
        guid: ts
        for guid, ts in seen.items()
        if datetime.fromisoformat(ts) > cutoff
    }


def load_feeds() -> list[str]:
    lines = FEEDS_FILE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def feed_display_name(feed_url: str, parsed) -> str:
    try:
        return parsed.feed.title
    except AttributeError:
        return feed_url


def send_pushover(title: str, message: str, url: str) -> bool:
    payload = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": title,
        "message": message,
        "url": url,
        "url_title": "Apri articolo",
        "priority": 0,
    }
    try:
        resp = requests.post(PUSHOVER_API_URL, data=payload, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"  [ERROR] Pushover failed: {e}", file=sys.stderr)
        return False


def get_entry_guid(entry) -> str:
    return getattr(entry, "id", None) or getattr(entry, "link", None) or entry.get("title", "")


def process_feed(url: str, seen: dict) -> int:
    print(f"Checking: {url}")
    try:
        parsed = feedparser.parse(url)
    except Exception as e:
        print(f"  [ERROR] Failed to parse feed: {e}", file=sys.stderr)
        return 0

    if parsed.bozo and not parsed.entries:
        print(f"  [WARN] Feed returned no entries or is malformed", file=sys.stderr)
        return 0

    name = feed_display_name(url, parsed)
    now_iso = datetime.now(timezone.utc).isoformat()
    notified = 0

    for entry in parsed.entries:
        guid = get_entry_guid(entry)
        if not guid or guid in seen:
            continue

        title = getattr(entry, "title", "(no title)")
        link = getattr(entry, "link", url)

        print(f"  [NEW] {title}")
        if send_pushover(name, title, link):
            seen[guid] = now_iso
            notified += 1

    if notified == 0:
        print("  No new entries.")

    return notified


def main():
    feeds = load_feeds()
    seen = load_seen()
    seen = prune_seen(seen)

    total = 0
    for url in feeds:
        total += process_feed(url, seen)

    save_seen(seen)
    print(f"\nDone. {total} new article(s) notified.")


if __name__ == "__main__":
    main()
