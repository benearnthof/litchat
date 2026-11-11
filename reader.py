
import argparse
import random
import time

from parser import parse_epub
from tokenizer import tokenize_book
from namegen import UsernameGenerator
from emotes import EmoteSampler


def get_nltk_language(language_code):
    """Convert an EPUB language code into an NLTK language name."""
    languages = {
        "en": "english",
        "eng": "english",
        "de": "german",
        "deu": "german",
        "ger": "german",
        "fr": "french",
        "fra": "french",
        "es": "spanish",
        "spa": "spanish",
        "it": "italian",
        "ita": "italian",
        "pt": "portuguese",
        "por": "portuguese",
        "nl": "dutch",
        "nld": "dutch",
        "ja": "japanese",
        "jpn": "japanese",
    }

    if not language_code:
        return "english"

    return languages.get(language_code.lower(), language_code.lower())


def main():
    arg_parser = argparse.ArgumentParser(
        description="Read an EPUB as a simulated live chat."
    )

    arg_parser.add_argument("epub", help="Path to the EPUB file")
    arg_parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="Number of chat messages to display (default: 50)",
    )
    arg_parser.add_argument(
        "--chatters",
        type=int,
        default=30,
        help="Number of usernames in the chat pool (default: 30)",
    )
    arg_parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Average delay between messages in seconds (default: 2.0)",
    )
    arg_parser.add_argument(
        "--chapter",
        type=int,
        default=None,
        help="Only display sentences from this chapter index",
    )
    arg_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible output",
    )
    arg_parser.add_argument(
    "--emote-rate",
    type=float,
    default=0.08,
    help="Probability that a message contains an emote (default: 0.08)",
    )
    arg_parser.add_argument(
        "--emote-exponent",
        type=float,
        default=1.1,
        help="Popularity distribution exponent (default: 1.1)",
    )

    args = arg_parser.parse_args()

    if args.count < 1:
        arg_parser.error("--count must be at least 1")

    if args.chatters < 1:
        arg_parser.error("--chatters must be at least 1")

    if args.interval <= 0:
        arg_parser.error("--interval must be greater than 0")

    if not 0 <= args.emote_rate <= 1:
        arg_parser.error("--emote-rate must be between 0 and 1")

    if args.emote_exponent <= 0:
        arg_parser.error("--emote-exponent must be greater than 0")

    rng = random.Random(args.seed)

    print(f"Loading {args.epub}...")

    book = parse_epub(args.epub)
    language = get_nltk_language(book.language)

    print(f"Book: {book.title}")
    print(f"Author: {book.author}")
    print(f"Language: {language}")

    lines = tokenize_book(book, language=language)

    sentences = [
        line
        for line in lines
        if line.kind == "sentence"
        and (
            args.chapter is None
            or line.chapter_index == args.chapter
        )
    ]

    if not sentences:
        print("No sentences found for the selected chapter.")
        return

    username_generator = UsernameGenerator()
    usernames = username_generator.generate_usernames(args.chatters)

    emote_sampler = None

    if args.emote_rate > 0:
        emote_sampler = EmoteSampler.from_file(
            rng=rng,
            exponent=args.emote_exponent,
        )

    print(f"\nStarting chat with {len(usernames)} chatters...")
    print("Press Ctrl+C to stop.\n")

    displayed = 0

    try:
        for i in range(args.count):
            if i > 0:
                delay = rng.expovariate(1.0 / args.interval)
                time.sleep(delay)

            sentence = sentences[i % len(sentences)]
            username = rng.choice(usernames)

            message = sentence.text

            if emote_sampler is not None:
                message = emote_sampler.maybe_add_emote(
                    message,
                    probability=args.emote_rate,
                )

            print(f"{username}: {message}", flush=True)
            displayed += 1

    except KeyboardInterrupt:
        print("\nChat stopped.")

    print(f"\nDisplayed {displayed} messages.")


if __name__ == "__main__":
    main()
