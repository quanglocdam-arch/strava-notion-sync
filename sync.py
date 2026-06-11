"""
Strava → Notion Sync
Fetches recent running activities from Strava and adds new ones to a Notion database.
Skips activities already synced (dedup by Strava activity URL).
"""

import os
import sys
import requests
from datetime import datetime

# ── Config from environment variables ──────────────────────────
STRAVA_CLIENT_ID     = os.environ["STRAVA_CLIENT_ID"]
STRAVA_CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
STRAVA_REFRESH_TOKEN = os.environ["STRAVA_REFRESH_TOKEN"]
NOTION_TOKEN         = os.environ["NOTION_TOKEN"]
NOTION_PAGE_ID       = os.environ["NOTION_PAGE_ID"]   # Parent page to create/find database in

DB_NAME          = "🏃 Strava Runs"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API       = "https://www.strava.com/api/v3"
NOTION_API       = "https://api.notion.com/v1"
NOTION_VERSION   = "2022-06-28"

# How many recent activities to fetch each run (Strava API max: 200)
FETCH_LIMIT = 30


# ── Formatters ──────────────────────────────────────────────────
def fmt_duration(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_pace(mps: float) -> str:
    if not mps or mps <= 0:
        return "—"
    spk = 1000 / mps
    return f"{int(spk // 60)}:{int(spk % 60):02d} /km"


# ── Strava ──────────────────────────────────────────────────────
def get_strava_token() -> str:
    """Exchange refresh token for a fresh access token."""
    resp = requests.post(STRAVA_TOKEN_URL, json={
        "client_id":     STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "refresh_token": STRAVA_REFRESH_TOKEN,
        "grant_type":    "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Strava token error: {data}")
    return data["access_token"]


def get_runs(token: str) -> list[dict]:
    """Return recent Run activities from Strava (newest first)."""
    resp = requests.get(
        f"{STRAVA_API}/athlete/activities",
        headers={"Authorization": f"Bearer {token}"},
        params={"per_page": FETCH_LIMIT},
        timeout=15,
    )
    resp.raise_for_status()
    return [
        a for a in resp.json()
        if a.get("type") == "Run" or a.get("sport_type") == "Run"
    ]


# ── Notion ──────────────────────────────────────────────────────
def notion_headers() -> dict:
    return {
        "Authorization":  f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type":   "application/json",
    }


def clean_page_id(raw: str) -> str:
    """Normalize page ID — strips URL, dashes, then reformats."""
    # Handle full Notion URLs
    if "notion.so" in raw:
        raw = raw.split("notion.so/")[-1]
        # Remove query string
        raw = raw.split("?")[0]
        # Last 32-char hex block is the ID
        parts = raw.replace("-", "").split("/")
        raw = next((p for p in reversed(parts) if len(p) == 32), parts[-1])
    raw = raw.replace("-", "")
    if len(raw) == 32:
        return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    return raw


def find_or_create_db() -> str:
    """Find existing Strava Runs database or create one under NOTION_PAGE_ID."""
    # Search workspace for the database by title
    resp = requests.post(
        f"{NOTION_API}/search",
        headers=notion_headers(),
        json={"query": DB_NAME, "filter": {"value": "database", "property": "object"}},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if results:
        db_id = results[0]["id"]
        print(f"  Found existing database: {db_id}")
        return db_id

    # Create new database
    print(f"  Creating new database '{DB_NAME}'...")
    page_id = clean_page_id(NOTION_PAGE_ID)
    resp = requests.post(
        f"{NOTION_API}/databases",
        headers=notion_headers(),
        json={
            "parent": {"type": "page_id", "page_id": page_id},
            "title":  [{"type": "text", "text": {"content": DB_NAME}}],
            "properties": {
                "Name":              {"title": {}},
                "Date":              {"date": {}},
                "Distance (km)":     {"number": {"format": "number"}},
                "Duration":          {"rich_text": {}},
                "Pace":              {"rich_text": {}},
                "Elevation (m)":     {"number": {"format": "number"}},
                "Heart Rate (bpm)":  {"number": {"format": "number"}},
                "Strava Link":       {"url": {}},
            },
        },
        timeout=15,
    )
    resp.raise_for_status()
    db_id = resp.json()["id"]
    print(f"  Created database: {db_id}")
    return db_id


def get_synced_ids(db_id: str) -> set[str]:
    """Return set of Strava activity IDs already in the Notion database."""
    synced = set()
    cursor = None

    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor

        resp = requests.post(
            f"{NOTION_API}/databases/{db_id}/query",
            headers=notion_headers(),
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        for page in data.get("results", []):
            url = (
                page.get("properties", {})
                    .get("Strava Link", {})
                    .get("url") or ""
            )
            if url:
                synced.add(url.rstrip("/").split("/")[-1])

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return synced


def add_to_notion(db_id: str, activity: dict) -> None:
    """Create one Notion page for a Strava activity."""
    props: dict = {
        "Name":          {"title":     [{"text": {"content": activity.get("name", "Run")}}]},
        "Date":          {"date":      {"start": activity.get("start_date_local", "")[:10]}},
        "Distance (km)": {"number":    round(activity.get("distance", 0) / 1000, 2)},
        "Duration":      {"rich_text": [{"text": {"content": fmt_duration(activity.get("moving_time", 0))}}]},
        "Pace":          {"rich_text": [{"text": {"content": fmt_pace(activity.get("average_speed"))}}]},
        "Elevation (m)": {"number":    round(activity.get("total_elevation_gain", 0))},
        "Strava Link":   {"url":       f"https://www.strava.com/activities/{activity['id']}"},
    }
    if activity.get("average_heartrate"):
        props["Heart Rate (bpm)"] = {"number": round(activity["average_heartrate"])}

    resp = requests.post(
        f"{NOTION_API}/pages",
        headers=notion_headers(),
        json={"parent": {"database_id": db_id}, "properties": props},
        timeout=15,
    )
    resp.raise_for_status()


# ── Main ────────────────────────────────────────────────────────
def main() -> None:
    print(f"🏃 Strava → Notion sync — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 1. Strava token
    print("\n[1/4] Getting Strava access token...")
    token = get_strava_token()

    # 2. Fetch runs
    print(f"[2/4] Fetching last {FETCH_LIMIT} runs from Strava...")
    runs = get_runs(token)
    print(f"      Found {len(runs)} run(s)")

    if not runs:
        print("Nothing to sync. Exiting.")
        return

    # 3. Find / create Notion database
    print("[3/4] Locating Notion database...")
    db_id = find_or_create_db()

    # 4. Sync
    print("[4/4] Syncing new activities...")
    synced_ids = get_synced_ids(db_id)
    print(f"      Already in Notion: {len(synced_ids)}")

    added = skipped = failed = 0
    for run in runs:
        rid = str(run["id"])
        if rid in synced_ids:
            skipped += 1
            continue
        try:
            add_to_notion(db_id, run)
            dist = run.get("distance", 0) / 1000
            date = run.get("start_date_local", "")[:10]
            print(f"      ✅  {run['name']}  {dist:.2f} km  {date}")
            added += 1
        except Exception as exc:
            print(f"      ❌  {run['name']}: {exc}")
            failed += 1

    print(f"\n✅  Done — added: {added}  |  skipped: {skipped}  |  failed: {failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
