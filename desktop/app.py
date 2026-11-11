
import argparse
import json
import sys
from pathlib import Path

import webview


# Ensure project root is importable when launched as:
# python desktop/app.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from chat.generator import MessageGenerator


DESKTOP_DIR = PROJECT_ROOT / "desktop"
INDEX_FILE = DESKTOP_DIR / "index.html"


def parse_args():
    parser = argparse.ArgumentParser(
        description="LitChat desktop reader."
    )

    parser.add_argument("epub", help="Path to the EPUB file")

    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--chatters", type=int, default=30)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--chapter", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)

    parser.add_argument("--emote-rate", type=float, default=0.08)
    parser.add_argument("--emote-exponent", type=float, default=1.1)

    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")

    if args.chatters < 1:
        parser.error("--chatters must be at least 1")

    if args.interval <= 0:
        parser.error("--interval must be greater than 0")

    if not 0 <= args.emote_rate <= 1:
        parser.error("--emote-rate must be between 0 and 1")

    if args.emote_exponent <= 0:
        parser.error("--emote-exponent must be greater than 0")

    if not Path(args.epub).is_file():
        parser.error(f"EPUB file not found: {args.epub}")

    return args


def main():
    args = parse_args()

    epub_path = Path(args.epub).resolve()

    print(f"Loading {epub_path}...")

    generator = MessageGenerator(
        epub_path=epub_path,
        on_message=None,
        count=args.count,
        chatters=args.chatters,
        interval=args.interval,
        chapter=args.chapter,
        seed=args.seed,
        emote_rate=args.emote_rate,
        emote_exponent=args.emote_exponent,
    )

    try:
        generator.load()
    except Exception as exc:
        print(f"Error loading book: {exc}")
        sys.exit(1)

    book = generator.book

    print(f"Book: {book.title}")
    print(f"Author: {book.author}")
    print(f"Sentences: {len(generator.sentences)}")
    print(f"Chatters: {len(generator.usernames)}")

    window = webview.create_window(
        title=f"LitChat - {book.title}",
        url=INDEX_FILE.as_uri(),
        width=420,
        height=850,
        min_size=(320, 480),
        background_color="#18181b",
    )

    def send_message(message):
        """Forward a Python message to the frontend."""

        try:
            payload = json.dumps(
                message,
                ensure_ascii=True,
            )

            window.evaluate_js(
                f"window.addChatMessage({payload});"
            )

        except Exception as exc:
            print(f"Frontend communication error: {exc}")

    # Connect the generator to the frontend.
    generator.on_message = send_message

    def on_loaded():
        """Start generating messages after the frontend loads."""

        book_info = {
            "title": book.title,
            "author": book.author,
        }

        payload = json.dumps(book_info, ensure_ascii=True)

        window.evaluate_js(
            f"window.setBookInfo({payload});"
        )

        generator.start()

    def on_closed():
        """Clean up the background thread when the window closes."""

        generator.stop()

    window.events.loaded += on_loaded
    window.events.closed += on_closed

    print("Starting LitChat...")

    webview.start(debug=False)


if __name__ == "__main__":
    main()
