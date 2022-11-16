from typing import List
from dataclasses import dataclass

from galaxy.api.types import Game

@dataclass
class GamePSN(Game):
    platform: str

@dataclass
class PSNLink():
    gameTitle: str
    platform: str

    alias : List[str]




