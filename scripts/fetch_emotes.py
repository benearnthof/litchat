
import argparse
import json
import random
import re
import sys
import tempfile
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_METADATA = (
    PROJECT_ROOT / "data" / "betterttv" / "animated_emotes.json"
)

DEFAULT_OUTPUT = PROJECT_ROOT / "assets" / "emotes"

# Download settings
DEFAULT_WORKERS = 8
DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT = 20

USER_AGENT = "LitChat/1.0 EmoteAssetFetcher"


def load_emotes(metadata_path):
    """Load and validate emote metadata."""

    with metadata_path.open("r", encoding="utf-8") as f:
        metadata = json.load(f)

    emotes = metadata.get("emotes", [])

    if not isinstance(emotes, list):
        raise ValueError("Invalid emote metadata: 'emotes' must be a list")

    # Deduplicate by emote ID.
    unique_emotes = {}

    for emote in emotes:
        if not emote.get("animated"):
            continue

        emote_id = emote.get("id")
        cdn_url = emote.get("cdn_url")

        if not emote_id or not cdn_url:
            continue

        # IDs are used as filenames.
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", emote_id):
            continue

        # Only accept HTTPS CDN URLs.
        parsed_url = urlparse(cdn_url)

        if parsed_url.scheme != "https":
            continue

        unique_emotes.setdefault(emote_id, emote)

    return list(unique_emotes.values())


def download_emote(emote, output_dir, retries, timeout):
    """Download one emote with retries and atomic file saving."""

    emote_id = emote["id"]
    url = emote["cdn_url"]

    output_path = output_dir / f"{emote_id}.gif"

    # Skip already downloaded files.
    if output_path.exists() and output_path.stat().st_size > 0:
        return "skipped", emote_id, None

    for attempt in range(retries + 1):
        temp_path = None

        try:
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "image/gif",
            }

            with requests.get(
                url,
                headers=headers,
                timeout=timeout,
                stream=True,
            ) as response:

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < retries:
                        retry_after = response.headers.get("Retry-After")

                        try:
                            delay = float(retry_after)
                        except (TypeError, ValueError):
                            delay = 2 ** attempt

                        time.sleep(min(delay + random.random(), 30))
                        continue

                response.raise_for_status()

                # Save to a temporary file first.
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=output_dir,
                    suffix=".tmp",
                    delete=False,
                ) as temp_file:

                    temp_path = Path(temp_file.name)

                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            temp_file.write(chunk)

            # Validate GIF signature.
            with temp_path.open("rb") as f:
                signature = f.read(6)

            if signature not in (b"GIF87a", b"GIF89a"):
                temp_path.unlink(missing_ok=True)
                return "failed", emote_id, "Invalid GIF file"

            # Atomically move into its final location.
            temp_path.replace(output_path)

            return "downloaded", emote_id, None

        except requests.RequestException as exc:
            if temp_path:
                temp_path.unlink(missing_ok=True)

            if attempt == retries:
                return "failed", emote_id, str(exc)

            time.sleep(min(2 ** attempt + random.random(), 30))

        except OSError as exc:
            if temp_path:
                temp_path.unlink(missing_ok=True)

            return "failed", emote_id, str(exc)

    return "failed", emote_id, "Maximum retries exceeded"


def main():
    parser = argparse.ArgumentParser(
        description="Download BetterTTV animated emotes."
    )

    parser.add_argument(
        "--metadata",
        type=Path,
        default=DEFAULT_METADATA,
        help="Path to BetterTTV metadata JSON",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory for downloaded GIFs",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Number of concurrent downloads (default: 8)",
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help="Number of retries per failed download (default: 3)",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Request timeout in seconds (default: 20)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit downloads (useful for testing)",
    )

    args = parser.parse_args()

    if args.workers < 1 or args.retries < 0 or args.timeout < 1:
        parser.error("Workers and timeout must be positive; retries cannot be negative")

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    if not args.metadata.exists():
        parser.error(f"Metadata file not found: {args.metadata}")

    args.output.mkdir(parents=True, exist_ok=True)

    print("Loading BetterTTV metadata...")

    try:
        emotes = load_emotes(args.metadata)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        parser.error(f"Could not load metadata: {exc}")

    if args.limit:
        emotes = emotes[:args.limit]

    total = len(emotes)

    print(f"Found {total} animated emotes.")
    print(f"Output directory: {args.output.resolve()}")
    print(f"Concurrent workers: {args.workers}")
    print()

    results = {
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
    }

    failures = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                download_emote,
                emote,
                args.output,
                args.retries,
                args.timeout,
            ): emote
            for emote in emotes
        }

        for completed, future in enumerate(as_completed(futures), 1):
            try:
                status, emote_id, error = future.result()
            except Exception as exc:
                emote_id = futures[future]["id"]
                status = "failed"
                error = str(exc)

            results[status] += 1

            if status == "failed":
                failures.append((emote_id, error))

            print(
                f"\rProgress: {completed}/{total} | "
                f"Downloaded: {results['downloaded']} | "
                f"Skipped: {results['skipped']} | "
                f"Failed: {results['failed']}",
                end="",
                flush=True,
            )

    print("\n\nDownload complete.")
    print("-----------------")
    print(f"Total:      {total}")
    print(f"Downloaded: {results['downloaded']}")
    print(f"Skipped:    {results['skipped']}")
    print(f"Failed:     {results['failed']}")

    if failures:
        print("\nFailed emotes:")

        for emote_id, error in failures:
            print(f"  {emote_id}: {error}")

        print("\nYou can rerun the script to retry failed downloads.")

    print(f"\nAssets saved to: {args.output.resolve()}")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
