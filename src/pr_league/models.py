from dataclasses import dataclass
from datetime import datetime

GIVEN_POINTS = 2
RECEIVED_POINTS = 1


@dataclass(frozen=True)
class Player:
    github: str
    slack: str
    team: str | None = None


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
        return GIVEN_POINTS * self.given + RECEIVED_POINTS * self.received


@dataclass(frozen=True)
class TeamStanding:
    name: str
    points: int
    position: int
