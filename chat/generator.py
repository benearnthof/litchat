
import random
import threading

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


class MessageGenerator:
    def __init__(
        self,
        epub_path,
        on_message,
        count=50,
        chatters=30,
        interval=2.0,
        chapter=None,
        seed=None,
        emote_rate=0.08,
        emote_exponent=1.1,
    ):
        self.epub_path = epub_path
        self.on_message = on_message

        self.count = count
        self.chatters = chatters
        self.interval = interval
        self.chapter = chapter
        self.seed = seed
        self.emote_rate = emote_rate
        self.emote_exponent = emote_exponent

        self.rng = random.Random(seed)
        self.stop_event = threading.Event()

        self.sentences = []
        self.usernames = []
        self.emote_sampler = None

        self.thread = None

        self.book = None

    def load(self):
        """Load the EPUB and initialize message generation."""

        self.book = parse_epub(self.epub_path)

        language = get_nltk_language(self.book.language)

        lines = tokenize_book(self.book, language=language)

        self.sentences = [
            line
            for line in lines
            if line.kind == "sentence"
            and (
                self.chapter is None
                or line.chapter_index == self.chapter
            )
        ]

        if not self.sentences:
            raise ValueError(
                "No sentences found for the selected chapter."
            )

        username_generator = UsernameGenerator()

        self.usernames = username_generator.generate_usernames(
            self.chatters
        )

        if self.emote_rate > 0:
            self.emote_sampler = EmoteSampler.from_file(
                rng=self.rng,
                exponent=self.emote_exponent,
            )

    def generate_message(self, index):
        """Generate one structured chat message."""

        sentence = self.sentences[index % len(self.sentences)]
        username = self.rng.choice(self.usernames)

        message = {
            "type": "chat",
            "username": username,
            "content": [
                {
                    "type": "text",
                    "value": sentence.text,
                }
            ],
        }

        if self.emote_sampler is not None:
            if self.rng.random() < self.emote_rate:
                emote = self.emote_sampler.sample()

                message["content"].append({
                    "type": "text",
                    "value": " ",
                })

                message["content"].append({
                    "type": "emote",
                    "name": emote["keyword"],
                    "id": emote["id"],
                })

        return message

    def start(self):
        """Start the message generation thread."""

        if self.thread and self.thread.is_alive():
            return

        self.stop_event.clear()

        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
        )

        self.thread.start()

    def stop(self):
        """Stop message generation."""

        self.stop_event.set()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

    def _run(self):
        """Generate and dispatch messages."""

        try:
            for i in range(self.count):
                if self.stop_event.is_set():
                    break

                if i > 0:
                    delay = self.rng.expovariate(
                        1.0 / self.interval
                    )

                    if self.stop_event.wait(delay):
                        break

                if self.stop_event.is_set():
                    break

                message = self.generate_message(i)

                self.on_message(message)

        except Exception as exc:
            self.on_message({
                "type": "error",
                "text": str(exc),
            })
