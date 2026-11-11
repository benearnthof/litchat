
"""
Twitch-style username generator.

Loads adjectives and nouns from customizable text files.

    generate_username() -> str
    generate_usernames(count=10) -> list[str]

Usage:
    python username_generator.py
    python username_generator.py --count 20
    python username_generator.py --count 20 --seed 42
    python username_generator.py --config ./custom_config
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path


# Default configuration directory, relative to this file.
CONFIG_DIR = Path(__file__).parent / "config"


def load_words(path: Path) -> list[str]:
    """Load words from a text file, ignoring comments and empty lines."""
    if not path.exists():
        raise FileNotFoundError(f"Word list not found: {path}")

    words = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            word = line.strip()

            if word and not word.startswith("#"):
                words.append(word)

    if not words:
        raise ValueError(f"Word list is empty: {path}")

    return words


class UsernameGenerator:
    """Generates random usernames from configurable word lists."""

    def __init__(
        self,
        config_dir: Path = CONFIG_DIR,
        seed: int | None = None,
    ):
        self.rng = random.Random(seed)

        self.adjectives = load_words(config_dir / "adjectives.txt")
        self.nouns = load_words(config_dir / "nouns.txt")

    def generate_username(self) -> str:
        """Generate one random username."""

        adjective = self.rng.choice(self.adjectives)
        noun = self.rng.choice(self.nouns)

        # Randomly select a separator/style.
        style = self.rng.choice([
            "underscore",
            "hyphen",
            "camel",
        ])

        if style == "underscore":
            username = f"{adjective}_{noun}"

        elif style == "hyphen":
            username = f"{adjective}-{noun}"

        else:
            username = f"{adjective}{noun.capitalize()}"

        # Add a number approximately 50% of the time.
        if self.rng.random() < 0.5:
            number = self.rng.randint(0, 9999)
            username += str(number)

        return username

    def generate_usernames(self, count: int = 10) -> list[str]:
        """Generate multiple unique usernames."""

        if count < 0:
            raise ValueError("count cannot be negative")

        usernames = set()

        # Avoid infinite loops if the word lists are small.
        max_attempts = count * 20

        for _ in range(max_attempts):
            if len(usernames) >= count:
                break

            usernames.add(self.generate_username())

        return list(usernames)


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate random Twitch-style usernames."
    )

    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of usernames to generate (default: 10)",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible results",
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_DIR,
        help="Directory containing adjectives.txt and nouns.txt",
    )

    args = parser.parse_args()

    if args.count < 0:
        parser.error("--count cannot be negative")

    try:
        generator = UsernameGenerator(
            config_dir=args.config,
            seed=args.seed,
        )

        usernames = generator.generate_usernames(args.count)

        for username in usernames:
            print(username)

    except (FileNotFoundError, ValueError) as e:
        parser.error(str(e))

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
