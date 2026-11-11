
import json
import random
from pathlib import Path


DEFAULT_EMOTES_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "betterttv"
    / "animated_emotes.json"
)


class EmoteSampler:
    def __init__(self, emotes, rng, exponent=1.1):
        if not emotes:
            raise ValueError("The emote list is empty.")

        if exponent <= 0:
            raise ValueError("The exponent must be greater than 0.")

        self.rng = rng
        self.emotes = emotes

        # Rank 1 gets the highest weight.
        self.weights = [
            1 / (emote["rank"] ** exponent)
            for emote in emotes
        ]

    @classmethod
    def from_file(cls, rng, path=DEFAULT_EMOTES_PATH, exponent=1.1):
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

        emotes = data["emotes"]

        return cls(
            emotes=emotes,
            rng=rng,
            exponent=exponent,
        )

    def sample(self):
        """Return one emote, weighted by its popularity rank."""
        return self.rng.choices(
            self.emotes,
            weights=self.weights,
            k=1,
        )[0]

    def maybe_add_emote(self, message, probability=0.08):
        """Optionally append a textual emote placeholder to a message."""
        if self.rng.random() >= probability:
            return message

        emote = self.sample()
        return f"{message} [{emote['keyword']}]"
