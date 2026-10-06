from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Player:
    github: str
    slack: str


@dataclass(frozen=True)
class ReviewEvent:
    pr: str
    reviewer: str
    author: str
    submitted_at: datetime


@dataclass(frozen=True)
class Standing:
    player: Player
    given: int
    received: int
    position: int

    @property
    def points(self) -> int:
        return self.given + self.received
