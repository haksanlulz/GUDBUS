"""Golden for parse_gcs: --capture writes GOLDEN_PATH, --check replays and exits 1 on drift."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gurps_bot.gcs.parser import GCSParseError, parse_gcs  # noqa: E402

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "tests" / "golden" / "parser_golden.json"


def _full_sheet() -> dict:
    """full v5 sheet: containers, weapon-trait, specialization, defaults, local_notes drop, levels"""
    return {
        "version": 5,
        "id": "golden_char_001",
        "total_points": 150,
        "profile": {
            "name": "Sir Brannar",
            "gender": "Male",
            "height": "6'",
            "weight": "190 lb",
            "player_name": "TestPlayer",
            "tech_level": "3",
        },
        "settings": {
            "body_type": {
                "name": "Humanoid",
                "locations": [
                    {"id": "skull", "table_name": "Skull", "hit_penalty": -7,
                     "calc": {"roll_range": "3-4", "dr": {"all": 2}}},
                    {"id": "torso", "table_name": "Torso", "hit_penalty": 0,
                     "calc": {"roll_range": "9-10", "dr": {"all": 0}}},
                ],
            },
        },
        "attributes": [
            {"attr_id": "st", "adj": 3, "calc": {"value": 13, "points": 30}},
            {"attr_id": "dx", "adj": 2, "calc": {"value": 12, "points": 40}},
            {"attr_id": "iq", "adj": 0, "calc": {"value": 10, "points": 0}},
            {"attr_id": "ht", "adj": 1, "calc": {"value": 11, "points": 10}},
            {"attr_id": "hp", "adj": 0, "calc": {"value": 13, "points": 0, "current": 13}},
            {"attr_id": "fp", "adj": 0, "calc": {"value": 11, "points": 0, "current": 11}},
            {"attr_id": "basic_speed", "adj": 0, "calc": {"value": 5.75, "points": 0}},
        ],
        "traits": [
            {"name": "Combat Reflexes", "tags": ["Advantage", "Mental"],
             "base_points": 15, "calc": {"points": 15}},
            {"name": "Sense of Duty", "local_notes": "Companions",
             "tags": ["Disadvantage", "Mental"], "base_points": -5, "calc": {"points": -5}},
            {"name": "Claws, Sharp", "tags": ["Advantage", "Physical"], "base_points": 5,
             "weapons": [{"id": "w1", "damage": {"type": "cut", "st": "thr", "modifier_per_die": -1},
                          "usage": "Slash", "reach": "C", "defaults": [{"type": "dx"}],
                          "calc": {"level": 12, "damage": "1d-1 cut"}}],
             "calc": {"points": 5}},
            {"name": "Damage Resistance", "levels": 2, "tags": ["Advantage"],
             "base_points": 5, "calc": {"points": 10}},
            {"name": "Disadvantages", "children": [
                {"name": "Bad Temper", "tags": ["Disadvantage", "Mental"],
                 "base_points": -10, "calc": {"points": -10}},
            ]},
        ],
        "skills": [
            {"name": "Broadsword", "difficulty": "dx/a", "points": 8,
             "defaults": [{"type": "dx", "modifier": -5},
                          {"type": "skill", "name": "Shortsword", "modifier": -2}],
             "calc": {"level": 14, "rsl": "DX+2"}},
            {"name": "Shield", "specialization": "Shield", "difficulty": "dx/e", "points": 4,
             "defaults": [{"type": "dx", "modifier": -4}], "calc": {"level": 13, "rsl": "DX+1"}},
        ],
        "spells": [
            {"name": "Fireball", "college": ["Fire"], "difficulty": "iq/h", "points": 4,
             "calc": {"level": 12, "rsl": "IQ+2"}},
            {"name": "Light", "college": "Light", "difficulty": "iq/e", "points": 1,
             "calc": {"level": 10, "rsl": "IQ+0"}},
        ],
        "equipment": [
            {"description": "Broadsword", "quantity": 1,
             "calc": {"extended_value": "600", "extended_weight": "3 lb"}},
            {"description": "Backpack", "children": [
                {"description": "Rations", "quantity": 7,
                 "calc": {"extended_value": "14", "extended_weight": "3.5 lb"}},
            ]},
        ],
    }


def _coercion_sheet() -> dict:
    """numeric fields arrive as strings/floats; hits _as_int/_as_float"""
    return {
        "version": 5,
        "id": "golden_char_002",
        "total_points": "200",
        "profile": {"name": "Coercion Case"},
        "attributes": [
            {"attr_id": "st", "adj": "2", "calc": {"value": "12", "points": "20"}},
        ],
        "skills": [
            {"name": "Stealth", "difficulty": "dx/a", "points": "2.0",
             "calc": {"level": "11", "rsl": "DX+0"}},
        ],
    }


def _minimal_sheet() -> dict:
    """required fields only; all optionals absent"""
    return {"version": 5, "id": "golden_char_003", "profile": {"name": "Bones"}}


INPUTS = {
    "full": _full_sheet,
    "coercion": _coercion_sheet,
    "minimal": _minimal_sheet,
}


def derive() -> dict:
    out = {}
    for key, builder in INPUTS.items():
        try:
            out[key] = asdict(parse_gcs(builder()))
        except GCSParseError as exc:  # part of the characterized behavior
            out[key] = {"__GCSParseError__": str(exc)}
    return out


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--check"
    current = derive()
    serialized = json.dumps(current, sort_keys=True, indent=2, ensure_ascii=True)

    if mode == "--capture":
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(serialized + "\n", encoding="utf-8")
        print(f"captured golden -> {GOLDEN_PATH} ({len(current)} inputs)")
        return 0

    if mode == "--check":
        if not GOLDEN_PATH.exists():
            print("FAIL: golden not captured; run --capture first", file=sys.stderr)
            return 1
        expected = GOLDEN_PATH.read_text(encoding="utf-8").rstrip("\n")
        if serialized == expected:
            print(f"OK: parser golden matches ({len(current)} inputs, behavior preserved)")
            return 0
        print("FAIL: parser output drifted from golden", file=sys.stderr)
        exp = expected.splitlines()
        got = serialized.splitlines()
        for i, (a, b) in enumerate(zip(exp, got)):
            if a != b:
                print(f"  first diff @ line {i + 1}:\n    golden: {a}\n    got:    {b}", file=sys.stderr)
                break
        if len(exp) != len(got):
            print(f"  line count: golden={len(exp)} got={len(got)}", file=sys.stderr)
        return 1

    print(f"unknown mode {mode!r}; use --capture or --check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
