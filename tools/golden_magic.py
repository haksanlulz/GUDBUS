"""Golden for mechanics/magic.py: output must byte-match tests/golden/magic_golden.txt."""

from __future__ import annotations

from gurps_bot.mechanics import magic


def show(label: str, fn) -> None:
    try:
        result = fn()
    except Exception as exc:  # characterize the error path too
        print(f"{label} = {type(exc).__name__}: {exc}")
    else:
        print(f"{label} = {result!r}")


def main() -> None:
    print("# magic.spell_energy_reduction")
    for skill in range(0, 31):
        for low in (False, True):
            show(f"reduction(skill={skill}, low_mana={low})",
                 lambda s=skill, l=low: magic.spell_energy_reduction(s, low_mana=l))

    print("# magic.effective_spell_cost")
    cost_cases = [
        dict(base_cost=0, skill=10), dict(base_cost=1, skill=10),
        dict(base_cost=2, skill=10), dict(base_cost=3, skill=10),
        dict(base_cost=0.5, skill=10), dict(base_cost=1.5, skill=10),
        dict(base_cost=4, skill=15), dict(base_cost=4, skill=20),
        dict(base_cost=4, skill=25), dict(base_cost=4, skill=30),
        dict(base_cost=2, skill=20, size_modifier=1),
        dict(base_cost=2, skill=20, size_modifier=3),
        dict(base_cost=2, skill=20, area_radius=1),
        dict(base_cost=2, skill=20, area_radius=2),
        dict(base_cost=0.5, skill=10, area_radius=3),
        dict(base_cost=3, skill=25, low_mana=True),
        dict(base_cost=3, skill=25, size_modifier=2, area_radius=2),  # ValueError
        dict(base_cost=-1, skill=10),  # ValueError
        dict(base_cost=2, skill=10, area_radius=-1),  # ValueError
    ]
    for kw in cost_cases:
        show(f"effective_spell_cost({kw})", lambda k=kw: magic.effective_spell_cost(**k))

    print("# magic.maintenance_cost")
    for base in (0, 1, 2, 3, 5):
        for skill in (10, 15, 20, 25, 30):
            for low in (False, True):
                show(f"maintenance(base={base}, skill={skill}, low_mana={low})",
                     lambda b=base, s=skill, l=low: magic.maintenance_cost(b, s, low_mana=l))

    print("# magic.casting_time")
    for base in (1, 2, 5, 10):
        for skill in (5, 10, 15, 20, 25, 30):
            for low in (False, True):
                for cer in (False, True):
                    show(f"casting_time(base={base}, skill={skill}, low_mana={low}, ceremonial={cer})",
                         lambda b=base, s=skill, l=low, c=cer: magic.casting_time(b, s, low_mana=l, ceremonial=c))
    show("casting_time(base=0, skill=10)", lambda: magic.casting_time(0, 10))  # ValueError

    print("# magic.ceremonial_energy")
    cer_cases = [
        dict(spell_cost=10), dict(spell_cost=10, caster_energy=5),
        dict(spell_cost=10, caster_energy=10, mage_energy=2),
        dict(spell_cost=10, mage_energy=20),
        dict(spell_cost=10, skilled_nonmages=4), dict(spell_cost=10, low_skill_mages=4),
        dict(spell_cost=10, supporters=50), dict(spell_cost=10, supporters=200),
        dict(spell_cost=10, opposers=1), dict(spell_cost=10, opposers=50),
        dict(spell_cost=20, caster_energy=20, mage_energy=20, supporters=10),
        dict(spell_cost=5, caster_energy=10), dict(spell_cost=5, caster_energy=20),
        dict(spell_cost=0),  # ValueError
        dict(spell_cost=10, caster_energy=-1),  # ValueError
    ]
    for kw in cer_cases:
        show(f"ceremonial_energy({kw})", lambda k=kw: magic.ceremonial_energy(**k))

    print("# magic.long_distance_modifier")
    for yards in (0, 50, 200, 880, 1760, 5280, 17600, 176000):
        show(f"long_distance(yards={yards})", lambda y=yards: magic.long_distance_modifier(yards=y))
    for miles in (0, 0.5, 1, 3, 10, 30, 100, 300, 1000, 3000, 10000):
        show(f"long_distance(miles={miles})", lambda m=miles: magic.long_distance_modifier(miles=m))
    show("long_distance(yards=1, miles=1)", lambda: magic.long_distance_modifier(yards=1, miles=1))  # ValueError
    show("long_distance()", lambda: magic.long_distance_modifier())  # ValueError
    show("long_distance(miles=-1)", lambda: magic.long_distance_modifier(miles=-1))  # ValueError

    print("# magic.regular_spell_distance_penalty")
    for yards in (0, 0.5, 1, 1.5, 2, 5, 10):
        for touch in (False, True):
            for see in (True, False):
                show(f"regular_penalty(yards={yards}, can_touch={touch}, can_see={see})",
                     lambda y=yards, t=touch, s=see: magic.regular_spell_distance_penalty(y, can_touch=t, can_see=s))
    show("regular_penalty(yards=-1)", lambda: magic.regular_spell_distance_penalty(-1))  # ValueError

    print("# magic.missile_spell_damage")
    for magery in (0, 1, 2, 3, 4):
        for seconds in (1, 2, 3, 4):
            for energy in (None, 0, 1, 5, 100):
                show(f"missile(magery={magery}, seconds={seconds}, energy={energy})",
                     lambda m=magery, s=seconds, e=energy: magic.missile_spell_damage(m, seconds=s, energy=e))
    show("missile(magery=-1)", lambda: magic.missile_spell_damage(-1))  # ValueError
    show("missile(magery=2, seconds=0)", lambda: magic.missile_spell_damage(2, seconds=0))  # ValueError


if __name__ == "__main__":
    main()
