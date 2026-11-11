
#!/usr/bin/env python3

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "betterttv"

OUTPUT_FILE = DATA_DIR / "animated_emotes.json"
CHECKPOINT_FILE = DATA_DIR / ".animated_emotes_checkpoint.json"

# BetterTTV API
API_URL = "https://api.betterttv.net/3/emotes/shared/top"
CDN_URL = "https://cdn.betterttv.net/emote/{}/2x.{}"

PAGE_SIZE = 84
TARGET_COUNT = 1000
MAX_RETRIES = 5
REQUEST_TIMEOUT = 30

HEADERS = {
    "Accept": "application/json",
    "Origin": "https://betterttv.com",
    "Referer": "https://betterttv.com/",
    "User-Agent": "litchat-emote-collector/1.0",
}


def fetch_page(before=None):
    """Fetch one popularity-ranked page from BetterTTV."""

    params = {"limit": PAGE_SIZE}

    if before:
        params["before"] = before

    url = f"{API_URL}?{urlencode(params)}"

    for attempt in range(MAX_RETRIES):
        request = Request(url, headers=HEADERS)

        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))

                if not isinstance(data, list):
                    raise ValueError("Unexpected API response: expected a list")

                return data

        except HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                retry_after = exc.headers.get("Retry-After")
                delay = (
                    int(retry_after)
                    if retry_after and retry_after.isdigit()
                    else min(2 ** attempt, 30)
                )

                print(
                    f"HTTP {exc.code}. Retrying in {delay}s "
                    f"({attempt + 1}/{MAX_RETRIES})..."
                )
                time.sleep(delay)
                continue

            raise

        except (URLError, TimeoutError) as exc:
            delay = min(2 ** attempt, 30)

            print(
                f"Request failed: {exc}. Retrying in {delay}s "
                f"({attempt + 1}/{MAX_RETRIES})..."
            )
            time.sleep(delay)

    raise RuntimeError("Maximum number of retries exceeded")


def make_emote_record(item, rank):
    """Convert a BetterTTV API entry into our local schema."""

    emote = item.get("emote", {})
    creator = emote.get("user") or {}

    emote_id = emote.get("id")
    keyword = emote.get("code")
    image_type = emote.get("imageType")

    return {
        "rank": rank,
        "id": emote_id,
        "keyword": keyword,
        "animated": True,
        "image_type": image_type,
        "popularity": item.get("total", 0),
        "creator": creator.get("displayName") or creator.get("name"),
        "cdn_url": CDN_URL.format(emote_id, image_type),
        "created_at": emote.get("createdAt"),
        "updated_at": emote.get("updatedAt"),
    }


def save_json(path, data):
    """Write JSON atomically to avoid corrupting files on interruption."""

    temporary_path = path.with_suffix(path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
        file.write("\n")

    temporary_path.replace(path)


def load_checkpoint():
    """Resume a previously interrupted collection."""

    if not CHECKPOINT_FILE.exists():
        return {
            "emotes": [],
            "seen_ids": [],
            "before": None,
            "pages_fetched": 0,
        }

    with CHECKPOINT_FILE.open("r", encoding="utf-8") as file:
        checkpoint = json.load(file)

    print(
        f"Resuming collection: {len(checkpoint['emotes'])} emotes "
        f"already collected."
    )

    return checkpoint


def collect_emotes(target_count=TARGET_COUNT, fresh=False):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if fresh and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()

    checkpoint = load_checkpoint()

    emotes = checkpoint["emotes"]
    seen_ids = set(checkpoint["seen_ids"])
    before = checkpoint["before"]
    pages_fetched = checkpoint["pages_fetched"]

    print("Starting BetterTTV animated emote collection...")
    print(f"Target: {target_count} emotes")
    print(f"Page size: {PAGE_SIZE}")
    print()

    while len(emotes) < target_count:
        page = fetch_page(before)

        if not page:
            print("API returned an empty page. Stopping.")
            break

        pages_fetched += 1
        added_this_page = 0

        for item in page:
            emote = item.get("emote") or {}

            emote_id = emote.get("id")
            if not emote_id:
                continue

            # Avoid duplicates.
            if emote_id in seen_ids:
                continue

            # Keep only active, shared animated emotes.
            if emote.get("animated") is not True:
                continue

            if emote.get("live") is not True:
                continue

            if emote.get("sharing") is not True:
                continue

            if not emote.get("code") or not emote.get("imageType"):
                continue

            seen_ids.add(emote_id)

            rank = len(emotes) + 1
            emotes.append(make_emote_record(item, rank))
            added_this_page += 1

            if len(emotes) >= target_count:
                break

        # The cursor must come from the LAST raw API result,
        # not the last animated result.
        next_cursor = page[-1].get("id")

        print(
            f"Page {pages_fetched}: "
            f"{len(page)} results, "
            f"+{added_this_page} animated, "
            f"{len(emotes)}/{target_count} collected"
        )

        if len(emotes) >= target_count:
            break

        if not next_cursor or next_cursor == before:
            print("Pagination cursor missing or unchanged. Stopping.")
            break

        before = next_cursor

        # Save progress after every page.
        checkpoint = {
            "emotes": emotes,
            "seen_ids": list(seen_ids),
            "before": before,
            "pages_fetched": pages_fetched,
        }

        save_json(CHECKPOINT_FILE, checkpoint)

        # Be polite to the API.
        time.sleep(0.25)

    # Write final dataset.
    result = {
        "provider": "betterttv",
        "category": "animated",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "target_count": target_count,
        "collected_count": len(emotes),
        "pages_fetched": pages_fetched,
        "filters": {
            "animated": True,
            "live": True,
            "sharing": True,
        },
        "emotes": emotes,
    }

    save_json(OUTPUT_FILE, result)

    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()

    print()
    print("Collection complete.")
    print(f"Collected: {len(emotes)} emotes")
    print(f"Pages fetched: {pages_fetched}")
    print(f"Output: {OUTPUT_FILE}")

    if len(emotes) < target_count:
        print(
            f"WARNING: Only {len(emotes)} of {target_count} "
            "requested emotes were found."
        )
        return 1

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Collect popular animated emotes from BetterTTV."
    )

    parser.add_argument(
        "--count",
        type=int,
        default=TARGET_COUNT,
        help=f"Number of emotes to collect (default: {TARGET_COUNT})",
    )

    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Discard an existing checkpoint and start again.",
    )

    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")

    try:
        return collect_emotes(
            target_count=args.count,
            fresh=args.fresh,
        )
    except KeyboardInterrupt:
        print("\nInterrupted. Progress checkpoint preserved.")
        return 130
    except Exception as exc:
        print(f"\nCollection failed: {exc}", file=sys.stderr)
        print("Any existing checkpoint has been preserved.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
