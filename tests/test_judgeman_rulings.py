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


# ---------------------------------------------------------------- negated activations still count (FAQ 23158, 7813)
SOLEMN = {"spells_traps": [{"card": "Solemn Judgment", "face_up": False}], "deck_filler": 10}


def test_soul_crossing_counts_a_negated_activation():
    # FAQ 23158: after Soul Crossing, a negated activation still uses the 1 activation you have
    d = start({"hand": ["Soul Crossing", "Obelisk the Tormentor", "Pot of Greed", "Pot of Greed"], "deck_filler": 15},
              {"monsters": [{"card": "Mystical Shine Ball", "zone": 1}, {"card": "Mystical Shine Ball", "zone": 2}], **SOLEMN})
    d.play(["Set Soul Crossing", "P1 Spell & Trap Zone 1", "End the turn", "End the turn",
            "Normal Summon Mystical Shine Ball", "P1 Monster Zone 1", "Pass", "Activate Soul Crossing", "Pass",
            [0, 1, 2], "P1 Monster Zone 1"])  # Tribute Summon Obelisk with your monster and the opponent's two
    out = d.play(["Activate Pot of Greed", "P1 Spell & Trap Zone 1", "Activate Solemn Judgment"])
    assert "its activation is negated" in out
    assert "Activate Pot of Greed" not in d.describe_decision()


def test_draw_of_fate_counts_a_negated_activation():
    # FAQ 23158 (same for Draw of Fate)
    # Draw of Fate needs lower LP than the opponent, the opponent's monster with the highest ATK and 3 different cards in the Deck
    d = start({"lp": 7000, "spells_traps": [{"card": "Draw of Fate", "face_up": False}], "hand": ["Pot of Greed", "Pot of Greed"],
               "deck": ["Dark Magician", "Mystical Elf", "Celtic Guardian", "Kuriboh", "Feral Imp", "Giant Soldier of Stone"]},
              {"monsters": [{"card": "Blue-Eyes White Dragon"}], **SOLEMN})
    d.play(["Activate Draw of Fate", "Pass", [0, 1, 2]])  # reveal 3 cards; the opponent picks the one you draw
    out = d.play(["Activate Pot of Greed", "P1 Spell & Trap Zone 2", "Activate Solemn Judgment"])
    assert "its activation is negated" in out
    assert "Activate Pot of Greed" not in d.describe_decision()


def test_once_per_turn_card_can_be_activated_again_after_its_activation_is_negated():
    # FAQ 21245: "only 1 per turn" counts a card only if its activation was not negated (unchanged by the patch; guard)
    d = start({"hand": ["Pot of Desires", "Pot of Desires"], "deck_filler": 30}, SOLEMN)
    d.play([1, 1, "Activate Pot of Desires", "P1 Spell & Trap Zone 1"])
    out = d.play(["Activate Solemn Judgment"])
    assert "its activation is negated" in out
    assert "Activate Pot of Desires" in d.describe_decision()


def test_mulcharmy_counts_a_negated_activation():
    # FAQ 7813 (B): a Mulcharmy effect whose activation was negated still counts, so after the 2nd one resolves,
    # a 3rd Mulcharmy effect cannot be activated that turn
    d = start({"hand": ["Mulcharmy Fuwalos", "Mulcharmy Fuwalos", "Mulcharmy Fuwalos"], "deck_filler": 15},
              {"spells_traps": [{"card": "Solemn Strike", "face_up": False}], "deck_filler": 10})
    out = d.play(["Activate Mulcharmy Fuwalos", "Activate Solemn Strike"])
    assert "its activation is negated" in out
    d.play(["Activate Mulcharmy Fuwalos"])  # the 2nd one is allowed
    while "Pass" in d.describe_decision() and "Mulcharmy" not in d.describe_decision():
        d.play(["Pass"])
    for _ in range(4):  # the following Draw/Standby/Main Phase windows
        assert "Activate Mulcharmy Fuwalos" not in d.describe_decision()
        if "Main Phase 1: choose an action" in d.describe_decision():
            break
        d.play(["Pass"])
    assert "Main Phase 1: choose an action" in d.describe_decision()


def test_soul_crossing_still_limits_you_to_one_activation():
    # guard: after Soul Crossing, a resolved activation uses up the 1 activation you have (unchanged)
    d = start({"hand": ["Soul Crossing", "Obelisk the Tormentor", "Pot of Greed", "Pot of Greed"], "deck_filler": 15},
              {"monsters": [{"card": "Mystical Shine Ball", "zone": 1}, {"card": "Mystical Shine Ball", "zone": 2}], **SOLEMN})
    d.play(["Set Soul Crossing", "P1 Spell & Trap Zone 1", "End the turn", "End the turn",
            "Normal Summon Mystical Shine Ball", "P1 Monster Zone 1", "Pass", "Activate Soul Crossing", "Pass",
            [0, 1, 2], "P1 Monster Zone 1"])
    out = d.play(["Activate Pot of Greed", "P1 Spell & Trap Zone 1", "Pass"])
    assert "P1 draws" in out
    assert "Activate Pot of Greed" not in d.describe_decision()


# ---------------------------------------------------------------- Inspector Boarder (FAQ 21490, card script)
def inspector_board(trap):
    # the opponent's Inspector Boarder with 1 kind of Extra Deck monster on the field: 1 monster effect per turn
    return start({"monsters": [{"card": "Card Trooper", "zone": 1}, {"card": "Card Trooper", "zone": 2}], "hand": ["Pot of Greed"],
                  "deck_filler": 20},
                 {"monsters": [{"card": "Inspector Boarder", "zone": 1, "summoned": "special", "properly_summoned": True},
                               {"card": "Linkuriboh", "zone": 2, "summoned": "link", "properly_summoned": True}],
                  "spells_traps": [{"card": trap, "face_up": False}], "deck_filler": 10})


def test_inspector_boarder_count_is_kept_when_a_spell_activation_is_negated():
    d = inspector_board("Solemn Judgment")
    d.play([1, 1])  # Card Trooper's effect: the 1 monster effect of this turn
    assert "Activate Card Trooper" not in d.describe_decision()
    out = d.play(["Activate Pot of Greed", "P1 Spell & Trap Zone 1", "Activate Solemn Judgment"])
    assert "its activation is negated" in out
    assert "Activate Card Trooper" not in d.describe_decision()


def test_inspector_boarder_counts_a_negated_monster_effect():
    # FAQ 21490 (unchanged by the patch; guard)
    d = inspector_board("Solemn Strike")
    d.play(["Activate Card Trooper (P1 Monster Zone 1)"])
    while "Solemn Strike" not in d.describe_decision():
        d.play([1] if "declare" in d.describe_decision().lower() or "number" in d.describe_decision().lower() else [0])
    out = d.play(["Activate Solemn Strike"])
    assert "its activation is negated" in out
    assert "Activate Card Trooper" not in d.describe_decision()


# ---------------------------------------------------------------- Loka Samsara (card script)
def test_loka_samsara_does_not_take_back_a_negated_activation():
    # Its monster "can only activate its effects once"; a negated activation counts as that once (the rule of FAQ 7813,
    # 21490 and 23158 for limits on activating effects). No board in the card pool shows the difference (every
    # 3000 ATK "Heart" monster has its own once per turn limit), so this checks the script and that it still runs.
    script = (db.scripts / "official" / "c2116237.lua").read_text(encoding="utf-8")
    assert "EVENT_CHAIN_NEGATED" not in script
    d = start({"monsters": [{"card": "Visas Starfrost", "zone": 1}], "spells_traps": [{"card": "Loka Samsara", "face_up": False}],
               "extra_deck": ["Tearlaments Kaleido-Heart"], "deck_filler": 15},
              {"monsters": [{"card": "Mystical Shine Ball", "zone": 1}], "deck_filler": 10})
    d.play(["Activate Loka Samsara", 0, "Face-up attack"])  # the first zone, Attack Position
    assert "activate/use the effect of Tearlaments Kaleido-Heart" in d.describe_decision()
