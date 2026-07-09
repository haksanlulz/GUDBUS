# formulas only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Jump distance/height math (B352): high = 6*M - 10 inches, broad = 2*M - 3 feet."""

from __future__ import annotations

from dataclasses import dataclass

INCHES_PER_FOOT: float = 12.0
FEET_PER_YARD: float = 3.0

# B352: jump multiplier by encumbrance level
ENCUMBRANCE_FACTORS: dict[str, float] = {
    "none": 1.0,
    "light": 0.8,
    "medium": 0.6,
    "heavy": 0.4,
    "extra-heavy": 0.2,
}


@dataclass(frozen=True, slots=True)
class JumpResult:
    """``value`` is inches for a high jump, yards for a long jump; ``feet`` is the same in feet."""

    kind: str
    value: float
    feet: float
    effective_move: float
    capped: bool
    super_jump_multiplier: int
    encumbrance_factor: float

    def __str__(self) -> str:
        if self.kind == "high":
            unit = "in"
        else:
            unit = "yd"
        cap = " (capped)" if self.capped else ""
        return f"{self.kind} jump: {self.value:g} {unit}{cap}"


def effective_move(
    basic_move: float,
    *,
    running_start: bool = False,
    yards_run: float = 0.0,
    enhanced_move: float = 0.0,
    jumping_skill: int | None = None,
    st: int | None = None,
    use_st_jump: bool = False,
) -> float:
    """Effective M (B352): a running start adds yards_run (Enhanced Move replaces the add); skill/2 and ST/4 substitute when better."""
    base = float(basic_move)

    if running_start:
        if enhanced_move > 0:
            base = base * enhanced_move
        else:
            base = base + yards_run

    if use_st_jump and st is not None:
        base = max(base, float(st // 4))

    if jumping_skill is not None:
        base = max(base, float(jumping_skill // 2))

    return base


def high_jump(
    basic_move: float,
    *,
    running_start: bool = False,
    yards_run: float = 0.0,
    enhanced_move: float = 0.0,
    super_jump: int = 0,
    jumping_skill: int | None = None,
    st: int | None = None,
    use_st_jump: bool = False,
    encumbrance: float = 1.0,
) -> JumpResult:
    """High jump in inches (B352): 6*M - 10; a running jump caps at 2x standing, applied before Super Jump."""
    multiplier = _super_jump_multiplier(super_jump)

    m = effective_move(
        basic_move,
        running_start=running_start,
        yards_run=yards_run,
        enhanced_move=enhanced_move,
        jumping_skill=jumping_skill,
        st=st,
        use_st_jump=use_st_jump,
    )
    height = (6.0 * m) - 10.0

    capped = False
    if running_start:
        standing_m = effective_move(
            basic_move,
            running_start=False,
            jumping_skill=jumping_skill,
            st=st,
            use_st_jump=use_st_jump,
        )
        standing_height = (6.0 * standing_m) - 10.0
        cap = 2.0 * standing_height
        if height > cap:
            height = cap
            capped = True

    height = height * multiplier
    height = height * encumbrance
    height = max(0.0, height)

    return JumpResult(
        kind="high",
        value=height,
        feet=height / INCHES_PER_FOOT,
        effective_move=m,
        capped=capped,
        super_jump_multiplier=multiplier,
        encumbrance_factor=encumbrance,
    )


def long_jump(
    basic_move: float,
    *,
    running_start: bool = False,
    yards_run: float = 0.0,
    enhanced_move: float = 0.0,
    super_jump: int = 0,
    jumping_skill: int | None = None,
    st: int | None = None,
    use_st_jump: bool = False,
    encumbrance: float = 1.0,
) -> JumpResult:
    """Broad jump in yards (B352): feet = 2*M - 3; a running jump caps at 2x standing, applied before Super Jump."""
    multiplier = _super_jump_multiplier(super_jump)

    m = effective_move(
        basic_move,
        running_start=running_start,
        yards_run=yards_run,
        enhanced_move=enhanced_move,
        jumping_skill=jumping_skill,
        st=st,
        use_st_jump=use_st_jump,
    )
    feet = (2.0 * m) - 3.0

    capped = False
    if running_start:
        standing_m = effective_move(
            basic_move,
            running_start=False,
            jumping_skill=jumping_skill,
            st=st,
            use_st_jump=use_st_jump,
        )
        standing_feet = (2.0 * standing_m) - 3.0
        cap = 2.0 * standing_feet
        if feet > cap:
            feet = cap
            capped = True

    feet = feet * multiplier
    feet = feet * encumbrance
    feet = max(0.0, feet)

    return JumpResult(
        kind="long",
        value=feet / FEET_PER_YARD,
        feet=feet,
        effective_move=m,
        capped=capped,
        super_jump_multiplier=multiplier,
        encumbrance_factor=encumbrance,
    )


def _super_jump_multiplier(super_jump: int) -> int:
    levels = max(0, int(super_jump))
    return 2 ** levels
