from dataclasses import dataclass

from galaxy.api.types import Game

@dataclass
class GamePSN(Game):
    platform: str




