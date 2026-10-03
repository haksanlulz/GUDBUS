"""GURPS dice notation parser/roller — "3d6", "2d+1"; bare "3d" means 3d6"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

# 3d6, 8d, 2d+1, d6, 8d6+3
_DICE_RE = re.compile(
    r"^(?P<count>\d+)?d(?P<sides>\d+)?(?P<mod>[+-]\d+)?$",
    re.IGNORECASE,
)

# bare "8" = 8d6 shorthand
_BARE_COUNT_RE = re.compile(r"^(?P<count>\d+)$")


@dataclass(frozen=True, slots=True)
class DiceSpec:
    count: int
    sides: int
    modifier: int

    def __str__(self) -> str:
        base = f"{self.count}d{self.sides}" if self.sides != 6 else f"{self.count}d"
        if self.modifier > 0:
            return f"{base}+{self.modifier}"
        if self.modifier < 0:
            return f"{base}{self.modifier}"
        return base

    @property
    def min(self) -> int:
        return self.count + self.modifier

    @property
    def max(self) -> int:
        return self.count * self.sides + self.modifier

    @property
    def average(self) -> float:
        return self.count * (self.sides + 1) / 2 + self.modifier


@dataclass(frozen=True, slots=True)
class RollResult:
    spec: DiceSpec
    dice: tuple[int, ...]
    total: int

    def __str__(self) -> str:
        dice_str = ", ".join(str(d) for d in self.dice)
        return f"{self.spec} = [{dice_str}] = {self.total}"


def parse_dice(notation: str) -> DiceSpec:
    notation = notation.strip().lower()
    m = _DICE_RE.match(notation)
    if not m:
        bare = _BARE_COUNT_RE.match(notation)
        if bare:
            count = int(bare.group("count"))
            if count < 1:
                raise ValueError("Dice count must be at least 1")
            if count > 100:
                raise ValueError("Dice count cannot exceed 100")
            return DiceSpec(count=count, sides=6, modifier=0)
        raise ValueError(f"Invalid dice notation: {notation!r}")

    count = int(m.group("count") or 1)
    sides = int(m.group("sides") or 6)
    modifier = int(m.group("mod") or 0)

    if count < 1:
        raise ValueError("Dice count must be at least 1")
    if count > 100:
        raise ValueError("Dice count cannot exceed 100")
    if sides < 1:
        raise ValueError("Dice sides must be at least 1")
    if sides > 1000:
        raise ValueError("Dice sides cannot exceed 1000")
    # unbounded modifier digits would blow Discord's 1024-char embed field and
    # 400 the send; the cog turns this ValueError into a friendly reply
    if abs(modifier) > 10000:
        raise ValueError("Dice modifier cannot exceed ±10000")

    return DiceSpec(count=count, sides=sides, modifier=modifier)


def roll(spec: DiceSpec | str) -> RollResult:
    if isinstance(spec, str):
        spec = parse_dice(spec)

    dice = tuple(random.randint(1, spec.sides) for _ in range(spec.count))
    total = sum(dice) + spec.modifier
    return RollResult(spec=spec, dice=dice, total=total)


def roll_3d6() -> RollResult:
    return roll(DiceSpec(count=3, sides=6, modifier=0))
