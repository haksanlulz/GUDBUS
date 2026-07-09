from __future__ import annotations

import json

import pytest
import pytest_asyncio

from gurps_bot.db.engine import dispose_engine, init_db, init_engine, get_session_factory


@pytest_asyncio.fixture
async def db_session():
    init_engine("sqlite+aiosqlite://")
    await init_db()
    async with get_session_factory()() as session:
        yield session
    await dispose_engine()


@pytest_asyncio.fixture
def make_character(db_session):
    """seed a parent Character — with foreign_keys=ON, child rows FK-fail without one"""
    async def _make(char_id: int, user_id: int):
        from gurps_bot.db.models import Character

        c = Character(id=char_id, discord_user_id=user_id, name=f"Char{char_id}")
        db_session.add(c)
        await db_session.flush()
        return c

    return _make


@pytest.fixture
def sample_gcs_data() -> dict:
    return {
        "version": 5,
        "id": "test_char_001",
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
                    {
                        "id": "skull",
                        "table_name": "Skull",
                        "hit_penalty": -7,
                        "calc": {"roll_range": "3-4", "dr": {"all": 2}},
                    },
                    {
                        "id": "torso",
                        "table_name": "Torso",
                        "hit_penalty": 0,
                        "calc": {"roll_range": "9-10", "dr": {"all": 0}},
                    },
                ],
            },
        },
        "attributes": [
            {"attr_id": "st", "adj": 3, "calc": {"value": 13, "points": 30}},
            {"attr_id": "dx", "adj": 2, "calc": {"value": 12, "points": 40}},
            {"attr_id": "iq", "adj": 0, "calc": {"value": 10, "points": 0}},
            {"attr_id": "ht", "adj": 1, "calc": {"value": 11, "points": 10}},
            {"attr_id": "will", "adj": 0, "calc": {"value": 10, "points": 0}},
            {"attr_id": "per", "adj": 0, "calc": {"value": 10, "points": 0}},
            {"attr_id": "hp", "adj": 0, "calc": {"value": 13, "points": 0, "current": 13}},
            {"attr_id": "fp", "adj": 0, "calc": {"value": 11, "points": 0, "current": 11}},
            {"attr_id": "basic_speed", "adj": 0, "calc": {"value": 5.75, "points": 0}},
            {"attr_id": "basic_move", "adj": 0, "calc": {"value": 5, "points": 0}},
        ],
        "traits": [
            {
                "name": "Combat Reflexes",
                "tags": ["Advantage", "Mental"],
                "base_points": 15,
                "calc": {"points": 15},
            },
            {
                "name": "High Pain Threshold",
                "tags": ["Advantage", "Physical"],
                "base_points": 10,
                "calc": {"points": 10},
            },
            {
                "name": "Sense of Duty",
                "local_notes": "Companions",
                "tags": ["Disadvantage", "Mental"],
                "base_points": -5,
                "calc": {"points": -5},
            },
            {
                "name": "Claws, Sharp",
                "tags": ["Advantage", "Physical"],
                "base_points": 5,
                "weapons": [
                    {
                        "id": "w1",
                        "damage": {"type": "cut", "st": "thr", "modifier_per_die": -1},
                        "usage": "Slash",
                        "reach": "C",
                        "defaults": [{"type": "dx"}],
                        "calc": {"level": 12, "damage": "1d-1 cut"},
                    },
                ],
                "calc": {"points": 5},
            },
            {
                "name": "Disadvantages",
                "children": [
                    {
                        "name": "Bad Temper",
                        "tags": ["Disadvantage", "Mental"],
                        "base_points": -10,
                        "calc": {"points": -10},
                    },
                ],
            },
        ],
        "skills": [
            {
                "name": "Broadsword",
                "difficulty": "dx/a",
                "points": 8,
                "defaults": [
                    {"type": "dx", "modifier": -5},
                    {"type": "skill", "name": "Shortsword", "modifier": -2},
                ],
                "calc": {"level": 14, "rsl": "DX+2"},
            },
            {
                "name": "Shield",
                "specialization": "Shield",
                "difficulty": "dx/e",
                "points": 4,
                "defaults": [{"type": "dx", "modifier": -4}],
                "calc": {"level": 13, "rsl": "DX+1"},
            },
            {
                "name": "First Aid",
                "difficulty": "iq/e",
                "points": 1,
                "defaults": [{"type": "iq", "modifier": -4}],
                "calc": {"level": 10, "rsl": "IQ+0"},
            },
            {
                "name": "Skills",
                "children": [
                    {
                        "name": "Stealth",
                        "difficulty": "dx/a",
                        "points": 2,
                        "defaults": [{"type": "dx", "modifier": -5}],
                        "calc": {"level": 12, "rsl": "DX+0"},
                    },
                ],
            },
        ],
        "spells": [
            {
                "name": "Ignite Fire",
                "college": ["Fire"],
                "difficulty": "iq/h",
                "spell_class": "Regular",
                "casting_cost": "1-3",
                "maintenance_cost": "None",
                "casting_time": "1 sec",
                "duration": "Instantaneous",
                "points": 2,
                "calc": {"level": 10, "rsl": "IQ+0"},
            },
        ],
        "equipment": [
            {
                "description": "Thrusting Broadsword",
                "quantity": 1,
                "equipped": True,
                "weapons": [
                    {
                        "id": "weq1",
                        "damage": {"type": "cut", "st": "sw", "base": "1"},
                        "usage": "Swung",
                        "reach": "1",
                        "parry": "0",
                        "defaults": [{"type": "skill", "name": "Broadsword"}],
                        "calc": {
                            "level": 14,
                            "damage": "2d cut",
                            "parry": "10",
                            "reach": "1",
                        },
                    },
                    {
                        "id": "weq2",
                        "damage": {"type": "imp", "st": "thr", "base": "1"},
                        "usage": "Thrust",
                        "reach": "1",
                        "parry": "0",
                        "defaults": [{"type": "skill", "name": "Broadsword"}],
                        "calc": {
                            "level": 14,
                            "damage": "1d+1 imp",
                            "parry": "10",
                            "reach": "1",
                        },
                    },
                ],
                "calc": {"extended_weight": "3 lb", "extended_value": 600},
            },
            {
                "description": "Medium Shield",
                "quantity": 1,
                "equipped": True,
                "weapons": [
                    {
                        "id": "weq3",
                        "damage": {"type": "cr", "st": "thr"},
                        "usage": "Shield Bash",
                        "reach": "1",
                        "block": "0",
                        "defaults": [{"type": "skill", "name": "Shield", "specialization": "Shield"}],
                        "calc": {"level": 13, "damage": "1d cr", "block": "10"},
                    },
                ],
                "calc": {"extended_weight": "15 lb", "extended_value": 60},
            },
        ],
        "other_equipment": [],
        "calc": {
            "swing": "2d",
            "thrust": "1d",
            "basic_lift": "34 lb",
            "move": [5, 4, 3, 2, 1],
            "dodge": [8, 7, 6, 5, 4],
        },
    }
