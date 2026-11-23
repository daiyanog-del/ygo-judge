"""JudgemanAI changes to the rules engine (patches/ygopro-core), checked against Konami's official Q&As.

Each test builds the board of one Q&A and checks the result the Q&A gives. The FAQ id is the `fid` of
https://www.db.yugioh-card.com/yugiohdb/faq_search.action?ope=5&fid=<id>.
"""

import re

from ygo_judge.cards import CardDB
from ygo_judge.duel import Duel
from ygo_judge.scenario import Setup


db = CardDB()


def start(p1=None, p2=None, seed=1):
    d = Duel(db, Setup.model_validate({"p1": p1 or {}, "p2": p2 or {}, "seed": seed}))
    d.play([])
    return d


def damage(log: str) -> dict[str, int]:
    """Total battle damage each player took in the log: {"P1": ..., "P2": ...}"""
    out = {"P1": 0, "P2": 0}
    for who, value in re.findall(r"(P[12]) takes (\d+) damage", log):
        out[who] += int(value)
    return out


# ---------------------------------------------------------------- destruction replacement (FAQ 24071)
HUGIN_BOARD = {
    "hand": ["Runick Slumber"],
    "monsters": [{"card": "Hugin the Runick Wings", "zone": "EMZ left"}, {"card": "Genex Controller"}, {"card": "Gene-Warped Warwolf"}],
    "field_spell": {"card": "Runick Fountain"},
    "extra_deck": ["Black Rose Dragon"],
    "deck_filler": 10,
}


def test_hugin_that_survives_by_runick_slumber_cannot_replace_the_destruction_of_other_cards():
    d = start(HUGIN_BOARD, {"deck_filler": 10})
    d.play([1, 1, 0])  # pass the Draw and Standby Phase windows, activate Runick Slumber
    d.play(["P1 Spell & Trap Zone 1", "Apply the effect on a target monster", "Hugin the Runick Wings"])
    d.play(["No"])  # Runick Fountain's effect
    d.play(["Black Rose Dragon", 0, 0, 0])  # Synchro Summon with Genex Controller and Gene-Warped Warwolf
    out = d.play(["Face-up attack", "Yes"])  # and activate Black Rose Dragon
    assert "avoid destruction" not in d.describe_decision()
    assert "Black Rose Dragon: P1 Monster Zone 1 → P1 GY — destroyed by an effect" in out
    assert "Runick Fountain: P1 Field Zone → P1 GY — destroyed by an effect" in out
    assert "Hugin the Runick Wings" in d.board()  # it survives by Runick Slumber


def test_hugin_still_replaces_when_it_is_not_destroyed_itself():
    d = start({"hand": ["Mystical Space Typhoon"], "monsters": [{"card": "Hugin the Runick Wings", "zone": "EMZ left"}],
               "field_spell": {"card": "Runick Fountain"}, "deck_filler": 10}, {"deck_filler": 10})
    d.play([1, 1, "Activate Mystical Space Typhoon", "P1 Spell & Trap Zone 1"])
    assert "avoid destruction" in d.describe_decision()
    out = d.play(["Yes"])
    assert "Hugin the Runick Wings: P1 Extra Monster Zone left → P1 banished" in out
    assert "Runick Fountain" in d.board()


# ---------------------------------------------------------------- battle damage (FAQ 23822)
OHIME_WITH_SWORD = {
    "monsters": [{"card": "Ohime the Manifested Mikanko", "position": "attack", "summoned": "special", "properly_summoned": True}],
    "spells_traps": [{"card": "Double-Edged Sword", "face_up": True, "equipped_to": "p1:Ohime the Manifested Mikanko"}],
    "deck_filler": 10,
}


def battle(p2_monster):
    d = start(OHIME_WITH_SWORD, {"monsters": [p2_monster], "deck_filler": 10})
    d.play(["End the turn", "End the turn", "Enter the Battle Phase", "Attack with Ohime the Manifested Mikanko"])
    return damage(d.play([p2_monster["card"]]))


def test_ohime_and_double_edged_sword_vs_dark_storm():
    # (C) the Dark Storm player takes the difference twice, the Ohime player once
    dmg = battle({"card": "Number C96: Dark Storm", "position": "attack", "summoned": "xyz",
                  "materials": ["Mystical Shine Ball"] * 4})
    assert dmg["P2"] == 2 * dmg["P1"] and dmg["P1"] > 0


def test_ohime_and_double_edged_sword_vs_another_ohime():
    # (D) each player takes the difference once
    dmg = battle({"card": "Ohime the Manifested Mikanko", "position": "attack", "summoned": "special", "properly_summoned": True})
    assert dmg["P1"] == dmg["P2"] > 0


def test_ohime_and_double_edged_sword_direct_attack():
    # (A) the opponent takes Ohime's ATK twice (this already matched before the change; kept as a guard)
    d = start(OHIME_WITH_SWORD, {"deck_filler": 10})
    d.play(["End the turn", "End the turn", "Enter the Battle Phase"])
    assert damage(d.play(["Attack with Ohime the Manifested Mikanko"])) == {"P1": 0, "P2": 4000}


def test_ohime_and_double_edged_sword_vs_odd_eyes():
    # (E) the Odd-Eyes player takes the difference twice, not doubled (already matched before; kept as a guard)
    dmg = battle({"card": "Odd-Eyes Pendulum Dragon", "position": "attack", "summoned": "special"})
    assert dmg == {"P1": 0, "P2": 1000}


# ---------------------------------------------------------------- Succumbing-Song Morganite (FAQ 24087, card script)
def morganite_battle(p1_monster, p2_monster):
    d = start({"hand": ["Succumbing-Song Morganite"], "monsters": [p1_monster], "deck_filler": 10},
              {"monsters": [p2_monster], "deck_filler": 10})
    d.play(["Activate Succumbing-Song Morganite", "P1 Spell & Trap Zone 1", "End the turn", "End the turn", "Enter the Battle Phase",
            f"Attack with {p1_monster['card']}"])
    return damage(d.play([p2_monster["card"]]))


BEWD = {"card": "Blue-Eyes White Dragon", "position": "attack"}


def test_morganite_does_not_double_damage_that_ohime_passes_to_the_opponent():
    # (A) only the opponent takes 3000
    ohime = {"card": "Ohime the Manifested Mikanko", "position": "attack", "summoned": "ritual"}
    assert morganite_battle(ohime, BEWD) == {"P1": 0, "P2": 3000}


def test_morganite_does_not_double_damage_that_recital_starling_shares():
    # (B) both players take 3000
    starling = {"card": "Lyrilusc - Recital Starling", "position": "attack", "summoned": "xyz",
                "materials": ["Lyrilusc - Cobalt Sparrow", "Lyrilusc - Cobalt Sparrow"]}
    assert morganite_battle(starling, BEWD) == {"P1": 3000, "P2": 3000}


def test_morganite_still_doubles_damage_your_monster_inflicts():
    assert morganite_battle(BEWD, {"card": "Dark Magician", "position": "attack"}) == {"P1": 0, "P2": 1000}
