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


# ---------------------------------------------------------------- Archfiend Matriarch (FAQ 24264, card script)
def test_ghost_belle_can_respond_to_archfiend_matriarch_in_the_main_monster_zone():
    d = start({"hand": ["Archfiend Matriarch", "Throne of the Archfiends", "Dark Magician"], "deck_filler": 10},
              {"hand": ["Ghost Belle & Haunted Mansion"], "spells_traps": [{"card": "Mirror Force", "face_up": False}],
               "graveyard": ["Pot of Greed"], "deck_filler": 10})
    # Ritual Summon it to a Main Monster Zone (the opponent passes on the Ritual Spell), then activate its effect
    d.play(["Activate Throne of the Archfiends (P1 hand)", "P1 Spell & Trap Zone 1", "Pass", "Dark Magician (P1 hand)",
            "P1 Monster Zone 3", "Face-up attack", "Yes"])
    assert "Activate Ghost Belle & Haunted Mansion" in d.describe_decision()


# ---------------------------------------------------------------- Blue-Eyes Twin Burst Dragon (FAQ 23430, card script)
def twin_burst_attacks(target):
    d = start({"monsters": [{"card": "Blue-Eyes Twin Burst Dragon", "zone": 3, "summoned": "special", "properly_summoned": True}],
               "deck_filler": 10}, {"monsters": [{"card": target, "zone": 3}], "deck_filler": 10})
    out = d.play(["End the turn", "End the turn", "Enter the Battle Phase", "Attack with Blue-Eyes Twin Burst Dragon (P1 Monster Zone 3)",
                  f"{target} (P2 Monster Zone 3)"])
    return d, out


def test_twin_burst_cannot_banish_after_an_effect_destroys_it_in_the_damage_step():
    # Bloom Diva survives the battle and destroys Twin Burst Dragon with its effect after damage calculation
    d, out = twin_burst_attacks("Bloom Diva the Melodious Choir")
    out += d.play(["Yes"])  # the opponent activates Bloom Diva's effect
    assert "Blue-Eyes Twin Burst Dragon: P1 Monster Zone 3 → P1 GY — destroyed by an effect" in out
    assert "activate/use the effect of Blue-Eyes Twin Burst Dragon" not in d.describe_decision()


def test_twin_burst_still_banishes_a_monster_that_survived_the_battle():
    # guard: Marshmallon is not destroyed by battle and Twin Burst Dragon stays on the field
    d, _ = twin_burst_attacks("Marshmallon")
    assert "activate/use the effect of Blue-Eyes Twin Burst Dragon" in d.describe_decision()


# ---------------------------------------------------------------- attacking all monsters after a direct attack (FAQ 16016, core)
def pick(d, want):
    """Pass every other response window until the decision offers `want`, then choose it."""
    for _ in range(40):
        text = d.describe_decision()
        if want in text:
            return d.play([want])
        assert "Pass" in text, text
        d.play(["Pass"])
    raise AssertionError(f"never offered: {want}")


def tecuhtlica_board(dust_tornado):
    p2 = {"monsters": [{"card": "Gene-Warped Warwolf"}, {"card": "Celtic Guardian"}], "deck_filler": 5}
    if dust_tornado:
        p2["spells_traps"] = [{"card": "Dust Tornado", "face_up": False}]
    d = start({"monsters": [{"card": "Mementoal Tecuhtlica - Combined Creation", "summoned": "special", "properly_summoned": True}],
               "spells_traps": [{"card": "Shooting Star Bow - Ceal", "face_up": True,
                                 "equipped_to": "p1:Mementoal Tecuhtlica - Combined Creation"}], "deck_filler": 5}, p2)
    for want in ("End the turn", "End the turn", "Enter the Battle Phase"):
        pick(d, want)
    return d


def test_tecuhtlica_cannot_attack_another_monster_after_a_replayed_direct_attack():
    # (D): it declared a direct attack (Shooting Star Bow), the Bow was destroyed, and the replay made it attack a monster
    d = tecuhtlica_board(dust_tornado=True)
    for want in ("Attack with Mementoal", "Yes", "Activate Dust Tornado", "Yes", "Gene-Warped Warwolf"):
        pick(d, want)
    assert "Attack with Mementoal" not in d.describe_decision()


def test_tecuhtlica_still_attacks_each_monster_once():
    # guard: without a direct attack it attacks every monster once
    d = tecuhtlica_board(dust_tornado=False)
    for want in ("Attack with Mementoal", "No", "Gene-Warped Warwolf"):
        pick(d, want)
    assert "Attack with Mementoal" in d.describe_decision()


# ---------------------------------------------------------------- Myutant Mist (FAQ 23652) and Rose Girl (FAQ 23082), card scripts


def _mist_opponent(extra_p2=None):
    p2 = {"monsters": [{"card": "Myutant Mist", "zone": 5, "summoned": "special", "properly_summoned": True}],
          "deck_filler": 10}
    p2.update(extra_p2 or {})
    return p2


def test_myutant_mist_cannot_be_targeted_by_opponent_activating_its_controllers_field_spell():
    # FAQ 23652: No. When your opponent activates the (2) effect of "Vaylantz World - Konig Wissen" in your Field Zone, they cannot target your "Myutant Mist".
    d = start(
        {"monsters": [{"card": "Mystical Shine Ball", "zone": 1}],
         "field_spell": {"card": "Vaylantz World - Shinra Bansho", "face_up": True}, "deck_filler": 10},
        _mist_opponent({"field_spell": {"card": "Vaylantz World - Konig Wissen", "face_up": True}}),
    )
    decision = d.describe_decision()
    assert "Konig Wissen" not in decision, decision


def test_myutant_mist_still_cannot_be_targeted_by_opponents_own_spell():
    # Guard: the opponent's own Spell Card ("Book of Moon") still cannot target "Myutant Mist".
    d = start({"hand": ["Book of Moon"], "deck_filler": 10}, _mist_opponent())
    decision = d.describe_decision()
    assert "Activate Book of Moon" not in decision, decision


def _rose_girl_board(monster):
    return {"hand": ["Rose Girl", "Tribute to the Doomed", "Mystical Shine Ball"],
            "monsters": [{"card": monster}], "extra_deck": ["Queen of Thorns"], "deck_filler": 10}


def _destroy_with_tribute_to_the_doomed(d):
    d.play([0])
    d.play([0])
    return d.play(["Mystical Shine Ball (P1 hand)"])


def test_rose_girl_cannot_activate_when_monster_was_plant_only_on_field():
    # FAQ 23082: No. "Assault Sentinel" that became a Plant with its own effect is a Beast-Warrior again in the GY, so "Rose Girl" (1) cannot be activated.
    d = start(_rose_girl_board("Assault Sentinel"), {"deck_filler": 10})
    d.play(["Activate Assault Sentinel (P1 Monster Zone 1)"])  # reveal Queen of Thorns: becomes Plant
    out = _destroy_with_tribute_to_the_doomed(d)
    assert "Assault Sentinel: P1 Monster Zone 1 → P1 GY" in out, out
    assert "Activate Rose Girl" not in d.describe_decision(), out + "\n" + d.describe_decision()


def test_rose_girl_activates_when_real_plant_is_sent_to_gy():
    # Guard: a monster that is a Plant both on the field and in the GY still lets "Rose Girl" (1) be activated.
    d = start(_rose_girl_board("Lonefire Blossom"), {"deck_filler": 10})
    out = _destroy_with_tribute_to_the_doomed(d)
    assert "Lonefire Blossom: P1 Monster Zone 1 → P1 GY" in out, out
    assert "Activate Rose Girl" in d.describe_decision(), out + "\n" + d.describe_decision()


# ---------------------------------------------------------------- Senet Switch (FAQ 23651) and Super Strident Blaze (FAQ 23781), card scripts


SENET_P1 = {
    "monsters": [
        {"card": "Cyber Dragon", "zone": 1},
        {"card": "Mystical Shine Ball", "zone": 3},
        {"card": "Blue-Eyes White Dragon", "zone": 5},
    ],
    "spells_traps": [{"card": "Senet Switch", "face_up": True}],
    "deck_filler": 10,
}
SENET_P2 = {
    "monsters": [{"card": "Cairngorgon, Antiluminescent Knight",
                  "materials": ["Mystical Shine Ball", "Mystical Shine Ball"]}],
    "deck_filler": 10,
}


def test_senet_switch_cairngorgon_only_adjacent_to_designated_zone():
    # FAQ 23651: Cairngorgon can switch Senet Switch's target, but only to a monster in a zone adjacent to the designated zone.
    d = start(SENET_P1, SENET_P2)
    d.play(["Activate Senet Switch", "Cyber Dragon"])  # designated zone = Monster Zone 2 (only option)
    out = d.play(["Activate Cairngorgon, Antiluminescent Knight", 0])
    # Blue-Eyes (zone 5) is not adjacent to zone 2, so the only valid new target is Shine Ball (zone 3)
    # (picked without a choice); then Shine Ball moves to zone 2 and Blue-Eyes stays in zone 5.
    assert "Targets: Mystical Shine Ball (P1 Monster Zone 3)" in out
    dec = d.describe_decision()
    assert "Mystical Shine Ball (P1 Monster Zone 2)" in dec
    assert "Blue-Eyes White Dragon (P1 Monster Zone 5)" in dec
    assert "Cyber Dragon (P1 Monster Zone 1)" in dec


def test_senet_switch_without_cairngorgon_moves_target():
    # Normal case: Senet Switch moves its target into the designated adjacent zone.
    d = start(SENET_P1, SENET_P2)
    d.play(["Activate Senet Switch", "Cyber Dragon", "Pass"])
    dec = d.describe_decision()
    assert "Cyber Dragon (P1 Monster Zone 2)" in dec


BLAZE_P1 = {
    "hand": ["Super Strident Blaze"],
    "monsters": [{"card": "Cyberdark End Dragon"}],
    "graveyard": ["Cyber Dragon", "Cyber Dragon", "Mystical Shine Ball"],
    "deck_filler": 10,
}
BLAZE_P2 = {
    "monsters": [{"card": "Mystical Shine Ball", "position": "defense"} for _ in range(3)],
    "deck_filler": 10,
}


def blaze_to_battle():
    d = start(BLAZE_P1, BLAZE_P2)
    d.play(["End the turn", "End the turn", 1, 0, 0, "Activate Super Strident Blaze", 0, "Enter the Battle Phase"])
    return d


def test_strident_blaze_not_after_first_of_two_attacks():
    # FAQ 23781: With 2 equips, Cyberdark End Dragon attacks twice; Blaze's chain attack can't be activated after the 1st attack, only after the 2nd.
    d = blaze_to_battle()
    out = d.play(["Attack with Cyberdark End Dragon", 0])
    assert "destroyed by battle" in out
    dec = d.describe_decision()
    assert "Super Strident Blaze" not in dec
    assert "Attack with Cyberdark End Dragon" in dec


def test_strident_blaze_after_second_attack_gives_third():
    # FAQ 23781: After the 2nd attack, Blaze can be activated and Cyberdark End Dragon attacks a 3rd time.
    d = blaze_to_battle()
    d.play(["Attack with Cyberdark End Dragon", 0, "Attack with Cyberdark End Dragon", 0])
    dec = d.describe_decision()
    assert "Super Strident Blaze" in dec
    d.play(["Super Strident Blaze"])
    for _ in range(5):
        dec = d.describe_decision()
        if "Attack with Cyberdark End Dragon" in dec:
            break
        d.play([0])
    assert "Attack with Cyberdark End Dragon" in d.describe_decision()
    out = d.play(["Attack with Cyberdark End Dragon", 0])
    assert "destroyed by battle" in out


# ---------------------------------------------------------------- Parasomnia Pillow (FAQ 23544) and Raiza the Mega Monarch (FAQ 23458), card scripts


def test_parasomnia_pillow_trap_monster_destroyed_no_effect2():
    # Konami FAQ 23544: if the equipped Trap Monster (Conquistador) is destroyed, Pillow's (2) cannot be activated (it must be in the GY as a monster).
    d = start({"hand": ["Parasomnia Pillow"],
               "spells_traps": [{"card": "Conquistador of the Golden Land"}], "deck_filler": 10},
              {"deck_filler": 10})
    d.play([0, 0, 0, 0, 1, "End the turn"])
    assert "Parasomnia Pillow (P1 Spell & Trap Zone 2)?" in d.describe_decision()
    out = d.play([0])
    assert "Conquistador of the Golden Land: P1 Monster Zone 1 → P1 GY" in out
    assert "Parasomnia Pillow: P1 Spell & Trap Zone 2 → P1 GY" in out
    assert "Parasomnia Pillow (P1 GY)" not in out
    assert "Parasomnia Pillow (P1 GY)" not in d.describe_decision()


def test_parasomnia_pillow_normal_monster_destroyed_effect2_still_available():
    # Guard: when an ordinary equipped monster is destroyed and sent to the GY, Pillow's (2) can still be activated.
    d = start({"hand": ["Parasomnia Pillow"], "monsters": [{"card": "Dark Magician"}], "deck_filler": 10},
              {"deck_filler": 10})
    out = d.play([0, 0])
    assert "equipped to Dark Magician (P1 Monster Zone 1)" in out
    d.play(["End the turn"])
    assert "Parasomnia Pillow (P1 Spell & Trap Zone 1)?" in d.describe_decision()
    out = d.play([0])
    assert "Dark Magician: P1 Monster Zone 1 → P1 GY" in out
    assert "activate/use the effect of Parasomnia Pillow (P1 GY)?" in d.describe_decision()


RAIZA_P1 = {"hand": ["Raiza the Mega Monarch"],
            "monsters": [{"card": "Floowandereeze & Eglen"}, {"card": "Floowandereeze & Robina"}],
            "deck_filler": 10}


def test_raiza_empty_graveyards_targets_only_return_to_hand():
    # Konami FAQ 23458: with no cards in either GY, after tributing WIND monsters Raiza can activate targeting only 1 field card to return to the hand.
    d = start(RAIZA_P1, {"monsters": [{"card": "Dark Magician"}], "deck_filler": 10})
    d.play([0, [0, 1], 0])
    dec = d.describe_decision()
    assert "return to the hand" in dec
    assert "return to the Deck" not in dec
    out = d.play(["Dark Magician (P2 Monster Zone 1)"])
    assert "Targets: Dark Magician (P2 Monster Zone 1)" in out
    out = d.play(["Pass (don't respond)"])
    while "respond" in d.describe_decision():
        out += d.play(["Pass (don't respond)"])
    assert "Dark Magician: P2 Monster Zone 1 → P2 hand" in out
    assert "→ P2 Deck" not in out


def test_raiza_with_graveyard_card_still_targets_deck_return_first():
    # Guard: with a card in the GY, Raiza still targets 1 field card and 1 GY card for the Deck, then may add the return-to-hand target.
    d = start(RAIZA_P1, {"monsters": [{"card": "Dark Magician"}], "graveyard": ["Mystical Shine Ball"],
                         "deck_filler": 10})
    d.play([0, [0, 1], 0])
    assert "return to the Deck" in d.describe_decision()
    out = d.play(["Dark Magician (P2 Monster Zone 1)"])
    assert "Targets: Dark Magician (P2 Monster Zone 1)" in out
    assert "Targets: Mystical Shine Ball (P2 GY)" in out
    assert "return to hand" in d.describe_decision()
    out = d.play(["Yes"])
    assert "Targets: Raiza the Mega Monarch (P1 Monster Zone 1)" in out
    out = d.play(["Pass (don't respond)"])
    while "respond" in d.describe_decision():
        out += d.play(["Pass (don't respond)"])
    assert "Dark Magician: P2 Monster Zone 1 → P2 Deck" in out
    assert "Mystical Shine Ball: P2 GY → P2 Deck" in out


# ---------------------------------------------------------------- EN Wave (FAQ 23634) and Cyberdarkness Dragon (FAQ 12429), card scripts


def _en_wave_board(first_material):
    return {
        "hand": ["Polymerization"],
        "monsters": [{"card": first_material}, {"card": "Neo-Spacian Aqua Dolphin"}],
        "spells_traps": [{"card": "EN Wave", "face_up": True}],
        "extra_deck": ["Elemental HERO Absolute Zero"],
        "deck": ["Neo-Spacian Grand Mole", "Elemental HERO Neos"],
        "deck_filler": 10,
    }


def test_en_wave_triggers_when_dark_panther_copied_elemental_hero_name():
    # FAQ 23634: Yes. A monster whose name became an "Elemental HERO" monster in the Monster Zone and is sent to the GY as Fusion Material satisfies EN Wave's (1) condition.
    d = start(_en_wave_board("Neo-Spacian Dark Panther"), {"monsters": [{"card": "Elemental HERO Neos"}], "deck_filler": 10})
    d.play([0])  # Dark Panther copies the opponent's Neos
    d.play([0, 0])  # Polymerization
    d.play(["Select Neo-Spacian Dark Panther (P1 Monster Zone 1)", "Select Neo-Spacian Aqua Dolphin (P1 Monster Zone 2)"])
    d.play([0])
    out = d.play([0])
    assert "EN Wave" in d.describe_decision(), out + "\n" + d.describe_decision()


def test_en_wave_triggers_with_real_elemental_hero_material():
    # Guard: a real "Elemental HERO" monster used as Fusion Material still lets EN Wave's (1) be activated.
    d = start(_en_wave_board("Elemental HERO Bubbleman"), {"deck_filler": 10})
    d.play([0, 0])
    d.play(["Select Elemental HERO Bubbleman (P1 Monster Zone 1)", "Select Neo-Spacian Aqua Dolphin (P1 Monster Zone 2)"])
    d.play([0])
    out = d.play([0])
    assert "EN Wave" in d.describe_decision(), out + "\n" + d.describe_decision()


def _cyberdarkness_duel(p2_monster):
    d = start(
        {"monsters": [{"card": "Relinquished", "summoned": "ritual", "properly_summoned": True},
                      {"card": "Cyberdarkness Dragon", "summoned": "fusion", "properly_summoned": True}],
         "deck_filler": 10},
        {"hand": ["Pot of Greed"], "monsters": [p2_monster], "deck_filler": 10},
    )
    d.play([0])  # Relinquished equips the opponent's monster
    d.play([0])
    d.play(["End the turn"])
    d.play([0])  # opponent activates Pot of Greed
    out = d.play([0])
    return d, out


def test_cyberdarkness_can_send_face_down_equipped_monster_as_cost():
    # FAQ 12429: Yes. A monster equipped by Relinquished while face-down is an Equip Card, so it can be sent to the GY for Cyberdarkness Dragon's (3) cost.
    d, out = _cyberdarkness_duel({"card": "Celtic Guardian", "position": "set"})
    assert "Cyberdarkness Dragon" in d.describe_decision(), out + "\n" + d.describe_decision()


def test_cyberdarkness_can_send_face_up_equipped_monster_as_cost():
    # Guard: a monster equipped face-up by Relinquished can still be used for Cyberdarkness Dragon's (3) cost.
    d, out = _cyberdarkness_duel({"card": "Celtic Guardian"})
    assert "Negate effect" in d.describe_decision(), out + "\n" + d.describe_decision()


def test_cyberdarkness_cannot_send_set_equip_spell_as_cost():
    # Guard: a Set Equip Spell that is not equipped to anything is not an Equip Card, so it cannot pay Cyberdarkness Dragon's (3) cost.
    d = start(
        {"monsters": [{"card": "Cyberdarkness Dragon", "summoned": "fusion", "properly_summoned": True}],
         "spells_traps": [{"card": "Axe of Despair"}],
         "deck_filler": 10},
        {"hand": ["Pot of Greed"], "deck_filler": 10},
    )
    assert "Activate Axe of Despair" in d.describe_decision()  # the Equip Spell is Set face-down
    d.play(["End the turn"])
    d.play([0])  # opponent activates Pot of Greed
    out = d.play([0])
    assert "Cyberdarkness Dragon" not in d.describe_decision()
    assert "P2 draws" in out


# ---------------------------------------------------------------- a cost that would re-enable a GY redirect (FAQ 6878, 23801, core)
FORTRESS_BOARD = {"monsters": [{"card": "Cyber Dragon", "zone": 1}, {"card": "Jinzo", "zone": 2}],
                  "spells_traps": [{"card": "Macro Cosmos", "face_up": True}], "extra_deck": ["Chimeratech Fortress Dragon"], "deck_filler": 10}


def test_fortress_cannot_use_jinzo_that_negates_macro_cosmos():
    # Jinzo would be banished by Macro Cosmos the moment it leaves, so it cannot be sent to the GY for the summon
    d = start(FORTRESS_BOARD, {"deck_filler": 10})
    assert "Special Summon Chimeratech Fortress Dragon" not in d.describe_decision()


def test_fortress_still_uses_other_machines_while_jinzo_negates_macro_cosmos():
    # guard: Macro Cosmos stays negated by Jinzo, so the other two Machine monsters can be sent
    board = {**FORTRESS_BOARD, "monsters": FORTRESS_BOARD["monsters"] + [{"card": "Proto-Cyber Dragon", "zone": 3}]}
    d = start(board, {"deck_filler": 10})
    d.play(["Special Summon Chimeratech Fortress Dragon"])
    assert "Jinzo" not in d.describe_decision() and "Proto-Cyber Dragon" in d.describe_decision()


def droplet(spells_traps):
    d = start({"hand": ["Forbidden Droplet"], "monsters": [{"card": "Virtual World Kyubi - Shenshen"}], "spells_traps": spells_traps,
               "deck_filler": 10}, {"monsters": [{"card": "Cyber Dragon"}], "deck_filler": 10})
    d.play(["Activate Forbidden Droplet", 0])
    return d.describe_decision()


def test_forbidden_droplet_cannot_send_the_skill_drain_that_negates_shenshen():
    assert "Skill Drain" not in droplet([{"card": "Skill Drain", "face_up": True}])


def test_forbidden_droplet_can_send_one_of_two_skill_drains():
    # guard: the other Skill Drain keeps Shenshen negated
    assert "Skill Drain" in droplet([{"card": "Skill Drain", "face_up": True}, {"card": "Skill Drain", "face_up": True}])


# ---------------------------------------------------------------- Metaverse activates a Spell Card (FAQ 24193, 12712, core + utility.lua)
def test_dark_magician_of_destruction_counts_a_field_spell_activated_by_metaverse():
    d = start({"monsters": [{"card": "Dark Magician"}], "spells_traps": [{"card": "Metaverse"}], "deck": ["The Sanctuary in the Sky"],
               "deck_filler": 5, "extra_deck": ["Dark Magician of Destruction"]}, {"deck_filler": 5})
    d.play([1, 1, 0, "Activate it"])  # to Main Phase 1, Metaverse: activate The Sanctuary in the Sky
    assert "The Sanctuary in the Sky" in d.board()
    assert "Special Summon Dark Magician of Destruction" in d.describe_decision()


# ---------------------------------------------------------------- control for a set period and a temporary banish (FAQ 17476, core)
def control_then_banish(take, steps):
    p1 = {"hand": ["Change of Heart"], "spells_traps": [{"card": "Interdimensional Matter Forwarder", "face_up": True}], "deck_filler": 5}
    if take == "bigeye":
        p1["monsters"] = [{"card": "Number 11: Big Eye", "materials": ["Mystical Shine Ball", "Mystical Shine Ball"], "zone": 3}]
    d = start(p1, {"monsters": [{"card": "Blue-Eyes White Dragon"}], "deck_filler": 5})
    for s in steps:
        d.play(s)
    return d.board()


def test_change_of_heart_control_ends_when_the_monster_is_banished_temporarily():
    board = control_then_banish("coh", [["Activate Change of Heart", 0, "Blue-Eyes White Dragon", 0],
                                        ["Activate Interdimensional Matter Forwarder", "Blue-Eyes White Dragon", 0, 0]])
    p2 = board.split("P2:")[1]
    assert "Blue-Eyes White Dragon" in p2  # back to its owner at once


def test_big_eye_control_is_kept_after_a_temporary_banish():
    # guard: control with no set period stays (FAQ 17476 (A))
    board = control_then_banish("bigeye", [["Activate Number 11: Big Eye", 0, "Blue-Eyes White Dragon", 0],
                                           ["Activate Interdimensional Matter Forwarder", "Blue-Eyes White Dragon", 0]])
    p1 = board.split("P2:")[0]
    assert "Blue-Eyes White Dragon" in p1


# ---------------------------------------------------------------- Special Summoned from the Extra Deck, then face-down (FAQ 23476, core)
def okami_board(turn_face_down):
    hand = ["Gizmek Okami, the Dreaded Deluge Dragon"] + (["Book of Moon"] if turn_face_down else [])
    return start({"hand": hand, "monsters": [{"card": "Performapal Celestial Magician", "position": "set" if turn_face_down else "attack",
                                              "summoned": "special", "summoned_from": "extra deck"}], "deck_filler": 10},
                 {"monsters": [{"card": "Performapal Momoncarpet", "position": "attack", "summoned": "pendulum", "summoned_from": "extra deck"}],
                  "deck_filler": 10})


def test_okami_does_not_count_a_monster_turned_face_down():
    d = okami_board(turn_face_down=True)
    d.play([0, 0])  # Book of Moon on the opponent's Momoncarpet
    assert "Gizmek Okami" not in d.describe_decision()


def test_okami_counts_face_up_monsters_from_the_extra_deck():
    d = okami_board(turn_face_down=False)
    assert "Gizmek Okami" in d.describe_decision()


# ---------------------------------------------------------------- Dueltaining and a redone coin toss (FAQ 11503, card script)
def test_dueltaining_counts_a_redone_coin_toss_once():
    d = start({"field_spell": {"card": "Dueltaining"}, "spells_traps": [{"card": "Second Coin Toss", "face_up": True}],
               "monsters": [{"card": "Barrel Dragon"}], "deck_filler": 10},
              {"monsters": [{"card": "Mystical Shine Ball"}], "deck_filler": 10})
    out = d.play(["Pass (don't respond)"]) if "Pass (don't respond)" in d.describe_decision() else ""
    out += d.play(["Activate Barrel Dragon"])
    out += d.play([0])  # redo the coin tosses with Second Coin Toss
    for _ in range(4):
        if "Pass (don't respond)" in d.describe_decision():
            out += d.play(["Pass (don't respond)"])
    assert "Coin toss" in out
    assert "Dueltaining's effect applies" not in out


# ---------------------------------------------------------------- Proxy Horse with Micro Coder (FAQ 23161, card script)
def test_proxy_horse_and_micro_coder_apply_at_the_same_time():
    d = start({"monsters": [{"card": "Proxy Horse"}], "hand": ["Micro Coder", "Cyberse Gadget"], "extra_deck": ["Decode Talker"],
               "deck_filler": 10}, {"deck_filler": 10})
    assert "Special Summon Decode Talker" in d.describe_decision()


# ---------------------------------------------------------------- the shared Extra Monster Zones (board setup)
import pytest  # noqa: E402


def emz_setup(p1_zone, p2_zone):
    m = lambda zone: {"card": "Decode Talker", "zone": zone, "summoned": "link", "properly_summoned": True}  # noqa: E731
    return {"p1": {"monsters": [m(p1_zone)], "deck_filler": 5}, "p2": {"monsters": [m(p2_zone)], "deck_filler": 5}, "seed": 1}


@pytest.mark.parametrize("p1_zone,p2_zone", [("EMZ left", "EMZ right"), ("EMZ right", "EMZ left")])
def test_one_extra_monster_zone_cannot_hold_both_players_monsters(p1_zone, p2_zone):
    # P1's left Extra Monster Zone is P2's right one; two monsters there crashed the engine before this check
    with pytest.raises(ValueError, match="shared"):
        Duel(db, Setup.model_validate(emz_setup(p1_zone, p2_zone)))


def test_each_player_can_use_a_different_extra_monster_zone():
    d = Duel(db, Setup.model_validate(emz_setup("EMZ left", "EMZ left")))
    d.play([])
    assert d.board().count("Decode Talker") == 2


# ---------------------------------------------------------------- Cyber Dragon Infinity (FAQ 15005) and Lord of the Heavenly Prison (FAQ 24116), card scripts
def _e_options(d):
    return re.findall(r"\[(\d+)\] (.*)", d.describe_decision())


def _e_pick(d, text):
    """Pass response windows until an option containing `text` appears, then choose it."""
    out = ""
    for _ in range(30):
        opts = _e_options(d)
        hit = [n for n, s in opts if text in s]
        if hit:
            return out + d.play([int(hit[0])])
        passes = [n for n, s in opts if s.startswith("Pass")]
        assert passes, f"no option {text!r} and no Pass:\n{d.describe_decision()}"
        out += d.play([int(passes[0])])
    raise AssertionError(f"option {text!r} never appeared")


# --- FAQ 15005: Cyber Dragon Infinity ---

def _e_xyz_infinity_on_nova(d):
    _e_pick(d, "Special Summon Cyber Dragon Infinity")
    d.play(["Cyber Dragon Nova (P1 Monster Zone 1)"])
    d.play([0])  # zone
    return d.play([0])  # face-up attack


def test_cyber_dragon_infinity_can_xyz_on_nova_again_after_summon_negated():
    # FAQ 15005: Yes. If the Xyz Summon of "Cyber Dragon Infinity" on "Cyber Dragon Nova" is negated, you can Xyz Summon it that way again that turn.
    d = start(
        {"hand": ["Monster Reborn"], "monsters": [{"card": "Cyber Dragon Nova"}],
         "extra_deck": ["Cyber Dragon Infinity", "Cyber Dragon Infinity"], "deck_filler": 10},
        {"spells_traps": [{"card": "Angel Statue - Azurune"}], "deck_filler": 10},
    )
    _e_pick(d, "Activate Angel Statue - Azurune")
    d.play([0])
    d.play([0])
    _e_xyz_infinity_on_nova(d)
    out = _e_pick(d, "Negate the special summon")
    assert "Cyber Dragon Infinity: P1 Monster Zone 1 → P1 GY" in out, out
    _e_pick(d, "Activate Monster Reborn")
    d.play([0])  # S/T zone
    d.play([0])  # monster zone
    out = d.play([0])
    assert "Cyber Dragon Nova is Special Summoned" in out, out
    assert "Special Summon Cyber Dragon Infinity" in d.describe_decision(), out + "\n" + d.describe_decision()


def test_cyber_dragon_infinity_on_nova_still_once_per_turn_after_success():
    # Guard: after a successful Xyz Summon on "Cyber Dragon Nova", the second Infinity cannot be Xyz Summoned on another Nova that turn.
    d = start(
        {"monsters": [{"card": "Cyber Dragon Nova", "zone": 1}, {"card": "Cyber Dragon Nova", "zone": 2}],
         "extra_deck": ["Cyber Dragon Infinity", "Cyber Dragon Infinity"], "deck_filler": 10},
        {"deck_filler": 10},
    )
    out = _e_xyz_infinity_on_nova(d)
    assert "Cyber Dragon Infinity is Special Summoned" in out, out
    out = d.play([])
    assert "Special Summon Cyber Dragon Infinity" not in d.describe_decision(), out + "\n" + d.describe_decision()


# --- FAQ 24116: Lord of the Heavenly Prison + Argostars - Lightning Tydeu ---

def _e_lord_sets_tydeu():
    d = start(
        {"hand": ["Lord of the Heavenly Prison", "Mystical Shine Ball"],
         "spells_traps": [{"card": "Jar of Greed"}],
         "deck": ["Mystical Shine Ball", "Argostars - Lightning Tydeu"], "deck_filler": 10},
        {"deck_filler": 10},
    )
    _e_pick(d, "Reveal")
    _e_pick(d, "End the turn")
    d.play([1])  # pass in the End Phase
    _e_pick(d, "Activate Jar of Greed")   # Turn 2 (opponent's turn)
    _e_pick(d, "Yes")                      # Lord of the Heavenly Prison
    d.play([0])
    d.play([0])
    _e_pick(d, "Yes")                      # Set 1 Spell/Trap from the Deck
    d.play([0])                         # Tydeu to S/T zone 1
    return d


def test_lord_of_heavenly_prison_banishes_tydeu_that_returned_to_spell_trap_zone():
    # FAQ 24116: Yes. "Argostars - Lightning Tydeu" Set by "Lord of the Heavenly Prison" that Special Summoned itself and was placed face-up in the Spell & Trap Zone is still banished in the End Phase of the next turn.
    d = _e_lord_sets_tydeu()
    _e_pick(d, "End the turn")             # end Turn 2
    _e_pick(d, "Activate Argostars - Lightning Tydeu")
    _e_pick(d, "Yes")                      # use the Special Summon effect
    d.play([0])                         # discard
    d.play([0])
    out = d.play([0])
    assert "Argostars - Lightning Tydeu is Special Summoned" in out, out
    _e_pick(d, "Place this card")
    d.play([0])
    out = _e_pick(d, "End the turn")
    assert "Argostars - Lightning Tydeu: P1 Spell & Trap Zone 1 → P1 banished" in out, out


def test_lord_of_heavenly_prison_banishes_untouched_set_card_only_next_turn():
    # Guard: a card Set by "Lord of the Heavenly Prison" that stays Set is not banished in the turn it was Set, and is banished in the End Phase of the next turn.
    d = _e_lord_sets_tydeu()
    out = _e_pick(d, "End the turn")       # end Turn 2
    assert "banished" not in out, out
    out = _e_pick(d, "End the turn")       # end Turn 3 without activating Tydeu
    if "Activate Lord of the Heavenly Prison" in d.describe_decision():
        out += d.play(["Activate Lord of the Heavenly Prison (P1 Monster Zone 1)"])
    assert "Argostars - Lightning Tydeu: P1 Spell & Trap Zone 1 → P1 banished" in out, out


# ---------------------------------------------------------------- Raidraptor - Vanishing Lanius (FAQ 24030) and Graydle Alligator (FAQ 10018), card scripts
def _f_lanius_duel():
    return start({"hand": ["Raidraptor - Vanishing Lanius", "Book of Moon", "Book of Taiyou",
                           "Raidraptor - Mimicry Lanius"], "deck_filler": 10},
                 {"deck_filler": 10})


def test_vanishing_lanius_cannot_activate_after_being_turned_face_down_and_back():
    # FAQ 24030: No. "Raidraptor - Vanishing Lanius" must stay face-up from its summon until activation; once it was face-down it cannot activate even if it is face-up again.
    d = _f_lanius_duel()
    d.play(["Normal Summon Raidraptor - Vanishing Lanius (P1 hand)", 0, "Pass"])
    assert "Activate Raidraptor - Vanishing Lanius" in d.describe_decision(), d.describe_decision()
    out = d.play(["Activate Book of Moon (P1 hand)", 0])
    assert "changes to face-down Defense Position" in out, out
    out = d.play(["Activate Book of Taiyou (P1 hand)", 0])
    assert "changes to face-up Attack Position" in out, out
    assert "Activate Raidraptor - Vanishing Lanius" not in d.describe_decision(), d.describe_decision()


def test_vanishing_lanius_still_activates_after_normal_summon():
    # Guard: a "Raidraptor - Vanishing Lanius" that stayed face-up since its Normal Summon can activate (1) and Special Summon a Raidraptor.
    d = _f_lanius_duel()
    d.play(["Normal Summon Raidraptor - Vanishing Lanius (P1 hand)", 0, "Pass"])
    out = d.play(["Activate Raidraptor - Vanishing Lanius (P1 Monster Zone 1)", "Pass", 0, 0])
    assert "Raidraptor - Mimicry Lanius is Special Summoned to P1 Monster Zone 2" in out, out


def _f_alligator_duel(opponent_monster):
    d = start({"hand": ["Tribute to The Doomed", "Mystical Shine Ball"],
               "monsters": [{"card": "Graydle Alligator"}], "deck_filler": 10},
              {"monsters": [{"card": opponent_monster}], "deck_filler": 10})
    d.play(["Activate Tribute to The Doomed (P1 hand)", 0, "Graydle Alligator (P1 Monster Zone 1)"])
    return d


def test_graydle_alligator_can_target_and_equip_botanical_lion():
    # FAQ 10018: Yes. "Graydle Alligator" can target and equip to "Botanical Lion" that cannot change control; control is not taken, but the destroy-on-leave effect applies.
    d = _f_alligator_duel("Botanical Lion")
    assert "Graydle Alligator" in d.describe_decision(), d.describe_decision()
    out = d.play(["Yes", 0])
    assert "Targets: Botanical Lion (P2 Monster Zone 1)" in out, out
    assert "Graydle Alligator (P1 Spell & Trap Zone 1) is equipped to Botanical Lion (P2 Monster Zone 1)" in out, out
    assert "Botanical Lion" not in d.describe_decision(), d.describe_decision()  # control is not gained


def test_graydle_alligator_still_takes_control_of_normal_monster():
    # Guard: "Graydle Alligator" still equips to and takes control of a monster whose control can change.
    d = _f_alligator_duel("Crystron Smiger")
    out = d.play(["Yes", 0, 0])
    assert "is equipped to Crystron Smiger (P2 Monster Zone 1)" in out, out
    assert "Crystron Smiger (P1 Monster Zone 1)" in d.describe_decision(), d.describe_decision()


# ---------------------------------------------------------------- Goblin Biker Boom Mach (FAQ 24024) and Burst Breath (FAQ 23605), card scripts
_g_BOOM_P1 = {"hand": ["Goblin Biker Boom Mach", "Mystical Shine Ball"],
           "monsters": [{"card": "Xyz Armor Fortress", "materials": ["Mystical Shine Ball"] * 3}],
           "spells_traps": [{"card": "Raigeki Break", "face_up": False}], "deck_filler": 10}
_g_BOOM_P2 = {"spells_traps": [{"card": "Monster Reborn", "face_up": False}], "deck_filler": 10}


def _g_boom_chain_2(discard):
    d = start(_g_BOOM_P1, _g_BOOM_P2)
    d.play([1, 1, "Activate Goblin Biker Boom Mach (P1 hand)", "Activate Raigeki Break (P1 Spell & Trap Zone 1)"])
    out = d.play([discard, "Monster Reborn (P2 Spell & Trap Zone 1)"])
    return d, out


def test_boom_mach_discarded_as_cost_can_activate_again_from_gy_at_chain_link_3():
    # FAQ 24024: Yes. The Boom Mach discarded as a cost for Chain Link 2 can activate its effect 1 from the GY at Chain Link 3 or later.
    d, out = _g_boom_chain_2("Goblin Biker Boom Mach (P1 hand)")
    assert "Goblin Biker Boom Mach: P1 hand → P1 GY" in out
    assert "Activate Goblin Biker Boom Mach (P1 GY)" in d.describe_decision()


def test_boom_mach_still_in_hand_cannot_activate_again_while_its_effect_is_on_the_chain():
    # FAQ 24024 (control): while the same Boom Mach stays in the hand with its effect 1 on the chain, it cannot activate effect 1 again.
    d, out = _g_boom_chain_2("Mystical Shine Ball (P1 hand)")
    assert "Mystical Shine Ball: P1 hand → P1 GY" in out
    assert "Activate Goblin Biker Boom Mach" not in d.describe_decision()


_g_BURST_P1 = {"lp": 3000, "monsters": [{"card": "Rabidragon"}], "hand": ["Blackwing - Gale the Whirlwind"],
            "graveyard": ["Burst Breath"],
            "spells_traps": [{"card": "Trap of Darkness"}, {"card": "Transaction Rollback"}, {"card": "Fake Feather"},
                             {"card": "Burst Breath"}, {"card": "Labrynth Barrage"}], "deck_filler": 10}
_g_BURST_P2 = {"graveyard": ["Burst Breath"], "monsters": [{"card": "Mystical Shine Ball"}], "deck_filler": 10}


def test_burst_breath_in_gy_cannot_be_copied_by_trap_of_darkness_fake_feather_or_transaction_rollback():
    # FAQ 23605: No. Burst Breath needs the ATK of the monster Tributed as its cost, so these cards cannot apply its effect.
    d = start(_g_BURST_P1, _g_BURST_P2)
    decision = d.describe_decision()
    assert "Activate Burst Breath (P1 Spell & Trap Zone 4)" in decision
    assert "Activate Trap of Darkness" not in decision
    assert "Activate Fake Feather" not in decision
    assert "Activate Transaction Rollback" not in decision


def test_labrynth_barrage_cannot_chain_to_burst_breath_and_burst_breath_itself_still_resolves():
    # FAQ 23605: No. Labrynth Barrage cannot be activated in response to Burst Breath; Burst Breath's own activation still works.
    d = start(_g_BURST_P1, _g_BURST_P2)
    out = d.play(["Activate Burst Breath (P1 Spell & Trap Zone 4)", 0])
    assert "Rabidragon: P1 Monster Zone 1 → P1 GY" in out
    assert "Activate Labrynth Barrage" not in d.describe_decision()
    assert "Mystical Shine Ball: P2 Monster Zone 1 → P2 GY" in out


# ---------------------------------------------------------------- Six Samurai - Yaichi (FAQ 10502), World Legacy Clash (FAQ 21250), Rage with Eyes of Blue (FAQ 12596), card scripts
_h_YAICHI_P1 = {"monsters": [{"card": "The Six Samurai - Yaichi", "zone": 2},
                          {"card": "The Six Samurai - Kamon", "zone": 3}],
             "spells_traps": [{"card": "Skill Drain", "face_up": False}], "deck_filler": 5}
_h_YAICHI_P2 = {"spells_traps": [{"card": "Monster Reborn", "face_up": False}], "deck_filler": 5}


def _h_to_turn3_main1(d):
    for _ in range(40):
        dec = d.describe_decision()
        if "Turn 3" in d.play([])[:200] and "Activate The Six Samurai - Yaichi" in dec:
            return
        opts = [l for l in dec.splitlines() if l.strip().startswith("[")]
        pick = next((o for o in opts if "Pass" in o or "End the turn" in o), None)
        assert pick is not None, dec
        d.play([int(pick.strip()[1:pick.strip().index("]")])])
    raise AssertionError("did not reach turn 3 main phase 1")


def test_yaichi_skill_drain_chained_still_cannot_attack():
    # FAQ 10502: After activating Yaichi's destroy effect, Yaichi cannot declare an attack that turn even if Skill Drain is chained to it.
    d = start(_h_YAICHI_P1, _h_YAICHI_P2)
    _h_to_turn3_main1(d)
    d.play(["Activate The Six Samurai - Yaichi"])
    if "Reborn" in d.describe_decision():
        d.play(["Monster Reborn"])
    out = d.play(["Activate Skill Drain"])
    for _ in range(10):
        dec = d.describe_decision()
        if "Main Phase 1: choose an action" in dec:
            break
        out += d.play([0 if "Yes" in dec or "Pass" not in dec else "Pass"])
    assert "Skill Drain" in out
    dec = _h_enter_battle(d)
    assert "Attack with The Six Samurai - Kamon" in dec
    assert "Attack with The Six Samurai - Yaichi" not in dec


def test_yaichi_without_effect_can_attack():
    # Guard: if Yaichi does not activate its effect, it can declare an attack under Skill Drain.
    d = start(_h_YAICHI_P1, _h_YAICHI_P2)
    _h_to_turn3_main1(d)
    assert "Attack with The Six Samurai - Yaichi" in _h_enter_battle(d)


def _h_enter_battle(d):
    d.play(["Enter the Battle Phase"])
    for _ in range(5):
        dec = d.describe_decision()
        if "Attack with" in dec or "Pass" not in dec:
            return dec
        d.play(["Pass"])
    return d.describe_decision()


def test_world_legacy_clash_banishing_swamp_mirrorer():
    # FAQ 21250: Swamp Mirrorer treated as a monster can be banished for World Legacy Clash; the target loses 1800 ATK and 1000 DEF.
    d = start({"hand": ["World Legacy Clash"], "spells_traps": [{"card": "Swamp Mirrorer", "face_up": False}], "deck_filler": 5},
              {"monsters": [{"card": "Dark Magician", "zone": 3}], "deck_filler": 5})
    d.play(["Activate Swamp Mirrorer", 0, 0, 0, 0])
    assert "Swamp Mirrorer, face-up Attack, ATK 1800/DEF 1000" in d.board()
    out = d.play(["Activate World Legacy Clash", 1])
    assert "Swamp Mirrorer: P1 Monster Zone 1 → P1 banished — as a cost" in out
    assert "Dark Magician, face-up Attack, ATK 700/DEF 1100" in d.board(), d.board()


def test_world_legacy_clash_normal_monster():
    # Guard: banishing a normal monster (Dark Magician 2500/2100) lowers the target by its original ATK/DEF.
    d = start({"hand": ["World Legacy Clash"], "monsters": [{"card": "Dark Magician", "zone": 2}], "deck_filler": 5},
              {"monsters": [{"card": "Blue-Eyes White Dragon", "zone": 3}], "deck_filler": 5})
    d.play(["Activate World Legacy Clash", 0])
    assert "Blue-Eyes White Dragon, face-up Attack, ATK 500/DEF 400" in d.board(), d.board()


_h_RAGE_P1 = {"hand": ["Rage with Eyes of Blue"], "field_spell": {"card": "Necrovalley", "face_up": True},
           "deck": ["Blue-Eyes White Dragon"], "deck_filler": 5}


def test_rage_with_eyes_of_blue_negated_by_necrovalley():
    # FAQ 12596: Rage with Eyes of Blue can be activated under Necrovalley, but if your GY has cards at resolution its effect is negated.
    d = start(dict(_h_RAGE_P1, graveyard=["Kuriboh", "Polymerization"]), {"deck_filler": 5})
    out = _h_activate_rage(d)
    assert "Chain Link 1 (Rage with Eyes of Blue): its effect is negated" in out
    assert "Monster Zone" not in d.describe_decision()
    assert "Blue-Eyes White Dragon" not in out
    assert "Necrovalley: P1 Field Zone" not in out


def test_rage_with_eyes_of_blue_empty_gy_under_necrovalley():
    # Guard: with an empty GY, Necrovalley does not negate it and Blue-Eyes is Special Summoned.
    d = start(_h_RAGE_P1, {"deck_filler": 5})
    _h_activate_rage(d)
    assert "Monster Zone" in d.describe_decision()


def _h_activate_rage(d):
    out = ""
    for _ in range(5):
        if "Activate Rage with Eyes of Blue" in d.describe_decision() and "Main Phase 1" in d.describe_decision():
            break
        out += d.play(["Pass"])
    out += d.play(["Activate Rage with Eyes of Blue (P1 hand)", 0])
    dec = d.describe_decision()
    if "Pass" in dec:
        out += d.play(["Pass"])
    return out


# ---------------------------------------------------------------- Prior of the Ice Barrier (FAQ 23144) and Tellus the Little Angel (FAQ 23167), card scripts
_i_PRIOR_P1 = {"hand": ["Prior of the Ice Barrier", "Monster Reborn"], "monsters": [{"card": "Dewdark of the Ice Barrier"}],
            "graveyard": ["Tri-Horned Dragon"], "deck_filler": 10}


def test_prior_of_the_ice_barrier_negated_summon_does_not_lock_level_5_or_higher():
    # FAQ 23144: Yes. The Level 5+ lock applies only when the Special Summon by effect 1 actually succeeds.
    d = start(_i_PRIOR_P1, {"spells_traps": [{"card": "Solemn Strike", "face_up": False}], "deck_filler": 10})
    d.play(["Special Summon Prior of the Ice Barrier (P1 hand)", 0, "Face-up attack"])
    out = d.play(["Activate Solemn Strike (P2 Spell & Trap Zone 1)"])
    assert "Prior of the Ice Barrier: P1 Monster Zone 2 → P1 GY" in out
    d.play(["Activate Monster Reborn (P1 hand)", "P1 Spell & Trap Zone 1"])
    assert "Tri-Horned Dragon" in d.describe_decision()


def test_prior_of_the_ice_barrier_successful_summon_still_locks_level_5_or_higher():
    # FAQ 23144 (control): when the Special Summon by effect 1 succeeds, Level 5+ monsters cannot be Special Summoned that turn.
    d = start(_i_PRIOR_P1, {"deck_filler": 10})
    out = d.play(["Special Summon Prior of the Ice Barrier (P1 hand)", 0, "Face-up attack"])
    assert "Prior of the Ice Barrier is Special Summoned" in out
    d.play(["Activate Monster Reborn (P1 hand)", "P1 Spell & Trap Zone 1"])
    assert "Tri-Horned Dragon" not in d.describe_decision()


def test_tellus_can_activate_with_a_tellus_wing_token_equipped_in_your_spell_trap_zone():
    # FAQ 23167: Yes. A "Tellus Wing Token" in your Spell & Trap Zone as an Equip Card counts as one on your field.
    d = start({"hand": ["Fissure", "Pot of Greed"], "monsters": [{"card": "Thousand-Eyes Restrict", "summoned": "fusion"}],
               "graveyard": ["Tellus the Little Angel"], "deck_filler": 10},
              {"monsters": [{"card": "Tellus the Little Angel"}], "deck_filler": 10})
    d.play(["Activate Fissure (P1 hand)", 0, "Yes", 0, "Face-up attack"])  # P2's Tellus makes a token
    out = d.play(['Activate Thousand-Eyes Restrict (P1 Monster Zone 1): "Equip"', "P1 Spell & Trap Zone 1"])
    assert "Tellus Wing Token (P1 Spell & Trap Zone 1) is equipped to Thousand-Eyes Restrict" in out
    assert "Activate Tellus the Little Angel (P1 GY)" in d.describe_decision()


def test_tellus_cannot_activate_without_a_tellus_wing_token():
    # FAQ 23167 (control): with no "Tellus Wing Token" on your field, effect 2 cannot be activated.
    d = start({"hand": ["Pot of Greed"], "graveyard": ["Tellus the Little Angel"], "deck_filler": 10},
              {"monsters": [{"card": "Tellus the Little Angel"}], "deck_filler": 10})
    assert "Activate Pot of Greed (P1 hand)" in d.describe_decision()
    assert "Tellus the Little Angel" not in d.describe_decision()


# ---------------------------------------------------------------- third batch of 100 Q&As: Underclock Taker (FAQ 21486), Rainbow Ruins (FAQ 6642),
# Normal Traps kept after activation (FAQ 23603, 23606, 23607), Mystical Fairy Elfuria (FAQ 7960), negated Flip Summon (FAQ 24012)
def test_underclock_taker_that_left_the_field_does_not_lower_atk():
    # FAQ 21486: if Underclock Taker is no longer on the field at resolution, nothing happens.
    d = start({"monsters": [{"card": "Underclock Taker", "zone": "EMZ left"}, {"card": "Excode Talker", "zone": 2}], "deck_filler": 10},
              {"monsters": [{"card": "Summoned Skull"}], "spells_traps": [{"card": "Compulsory Evacuation Device"}], "deck_filler": 10})
    out = d.play([1, 1, 0, 0, "Underclock Taker (P1 Extra Monster Zone left)"])
    assert "Underclock Taker: P1 Extra Monster Zone left → P1 Extra Deck" in out
    assert "Summoned Skull, face-up Attack, ATK 2500" in d.board()


def test_underclock_taker_on_the_field_lowers_atk():
    d = start({"monsters": [{"card": "Underclock Taker", "zone": "EMZ left"}, {"card": "Excode Talker", "zone": 2}], "deck_filler": 10},
              {"monsters": [{"card": "Summoned Skull"}], "deck_filler": 10})
    d.play(["Activate Underclock Taker"])
    assert "Summoned Skull, face-up Attack, ATK 200" in d.board()


def test_rainbow_ruins_still_negates_when_crystal_beasts_dropped_to_2_at_resolution():
    # FAQ 6642: the 3+ effect resolves even if only 2 "Crystal Beast" cards are left (also the 4+ and 5 effects).
    d = start({"field_spell": {"card": "Ancient City - Rainbow Ruins"}, "monsters": [{"card": "Crystal Beast Sapphire Pegasus"}],
               "spells_traps": [{"card": "Crystal Beast Ruby Carbuncle", "face_up": True}, {"card": "Crystal Beast Amethyst Cat", "face_up": True},
                                {"card": "Crystal Beast Emerald Tortoise", "face_up": True}], "deck_filler": 10},
              {"hand": ["Mystical Shine Ball"], "spells_traps": [{"card": "Raigeki Break", "face_up": False},
                                                                 {"card": "Mystical Space Typhoon", "face_up": False}], "deck_filler": 10})
    d.play(["Activate Mystical Space Typhoon", "Ancient City - Rainbow Ruins (P1 Field Zone)"])
    d.play(["Activate Ancient City - Rainbow Ruins"])  # Crystal Beast Sapphire Pegasus is sent as the cost
    out = d.play(["Activate Raigeki Break", "Crystal Beast Ruby Carbuncle (P1 Spell & Trap Zone 1)"])
    assert "Crystal Beast Ruby Carbuncle: P1 Spell & Trap Zone 1 → P1 GY" in out
    assert "Chain Link 1 (Mystical Space Typhoon): its activation is negated" in out


_i_COPIERS = ["Activate Trap of Darkness", "Activate Fake Feather", "Activate Transaction Rollback (P1 Spell & Trap Zone 3)",
              "Activate Transaction Rollback (P1 GY)", "Activate Junk Collector"]


def _i_copy_targets(kept, copier):
    d = start({"lp": 3000, "hand": ["Blackwing - Gale the Whirlwind"], "monsters": [{"card": "Junk Collector"}],
               "spells_traps": [{"card": "Trap of Darkness"}, {"card": "Fake Feather"}, {"card": "Transaction Rollback"}],
               "graveyard": [kept, "Jar of Greed", "Transaction Rollback"], "deck_filler": 10},
              {"graveyard": [kept, "Jar of Greed"], "deck_filler": 10})
    out = d.play(["Pass (don't respond)", "Pass (don't respond)", copier])
    return out + d.describe_decision()  # Fake Feather picks its only legal target (in P2's GY) by itself


def test_normal_traps_kept_after_activation_cannot_be_copied():
    # FAQ 23606 (Special Summons itself), 23603 (shuffles itself into the Deck), 23607 (becomes an Equip Card): none of the copiers can use them.
    for kept in ["Traptrix Holeutea", "Pharaoh's Treasure", "Altergeist Camouflage"]:
        for copier in _i_COPIERS:
            decision = _i_copy_targets(kept, copier)
            assert "Jar of Greed (P" in decision, (kept, copier)  # an ordinary Normal Trap still can
            assert kept not in decision, (kept, copier)


def test_labrynth_barrage_cannot_chain_to_a_normal_trap_kept_after_activation():
    # FAQ 23606 / 23603: no. An ordinary Set Normal Trap still can.
    for trap, offered in [("Traptrix Holeutea", False), ("Pharaoh's Treasure", False), ("Jar of Greed", True)]:
        d = start({"spells_traps": [{"card": trap}, {"card": "Labrynth Barrage"}], "deck_filler": 10}, {"deck_filler": 10})
        d.play([f"Activate {trap} (P1 Spell & Trap Zone 1)"])
        assert ("Activate Labrynth Barrage" in d.describe_decision()) == offered, trap


def _i_kept_traps_in_scripts():
    """Normal Traps whose activation Special Summons the card itself or equips it, read from the scripts (see utility.lua)."""
    import sqlite3
    from ygo_judge.cards import DATA
    con = sqlite3.connect(DATA / "BabelCDB" / "cards.cdb")
    found = set()
    for code, in con.execute("select id from datas where type=4"):  # TYPE_TRAP only = Normal Trap
        path = DATA / "CardScripts" / "official" / f"c{code}.lua"
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8", errors="ignore")
        funcs = {m.group(1): m.group(0) for m in re.finditer(r"^function s\.(\w+)\(.*?^end", src, re.S | re.M)}
        init = funcs.get("initial_effect", "")
        todo = [o for v in re.findall(r"(\w+):SetType\(EFFECT_TYPE_ACTIVATE\)", init)
                for o in re.findall(v + r":SetOperation\(s\.(\w+)\)", init)]
        body, seen = "", set()
        while todo:
            f = todo.pop()
            if f in seen or f not in funcs:
                continue
            seen.add(f)
            body += funcs[f]
            todo += re.findall(r"s\.(\w+)\(", funcs[f])
        if "AddMonsterAttribute" in body or re.search(r"Duel\.Equip\(\w+,\s*(c|e:GetHandler\(\))\s*,", body):
            found.add(code)
    return found


def test_kept_normal_trap_list_covers_every_script():
    from ygo_judge.cards import DATA
    util = (DATA / "CardScripts" / "utility.lua").read_text(encoding="utf-8")
    block = util.split("Auxiliary.NormalTrapsKeptAfterActivation={", 1)[1].split("}", 1)[0]
    listed = {int(c) for c in re.findall(r"\[(\d+)\]=true", block)}
    found = _i_kept_traps_in_scripts()
    assert found - listed == set()  # a new card of this kind must be added to the list
    assert listed - found == {63571750}  # Pharaoh's Treasure (shuffles itself into the Deck) is the only one added by hand


def test_elfuria_does_not_stop_an_xyz_summon_on_top_of_an_xyz_monster():
    # FAQ 7960: Xyz Monsters have no Level, so Utopia Ray can still be Xyz Summoned on top of Utopia.
    d = start({"hand": ["Speedroid Terrortop"], "monsters": [{"card": "Mystical Fairy Elfuria"},
               {"card": "Number 39: Utopia", "materials": ["Mystical Shine Ball"]}],
               "extra_deck": ["Number C39: Utopia Ray"], "deck_filler": 10}, {"deck_filler": 10}, seed=2)
    out = d.play(["Activate Mystical Fairy Elfuria"])
    assert "Revealed to P2: Speedroid Terrortop" in out
    assert "Special Summon Number C39: Utopia Ray" in d.describe_decision()


def test_elfuria_still_stops_monsters_with_a_different_level():
    # Control: after revealing a Level 4 monster, Elfuria (Level 3) and a Level 3 monster cannot make a Rank 3.
    d = start({"hand": ["Harpie Lady"], "monsters": [{"card": "Mystical Fairy Elfuria"}, {"card": "Mystical Fairy Elfuria"}],
               "extra_deck": ["Number 30: Acid Golem of Destruction"], "deck_filler": 10}, {"deck_filler": 10}, seed=2)
    assert "Special Summon Number 30: Acid Golem of Destruction" in d.describe_decision()
    d.play(["Activate Mystical Fairy Elfuria (P1 Monster Zone 1)"])
    assert "Special Summon Number 30: Acid Golem of Destruction" not in d.describe_decision()


def test_pendulum_monster_whose_flip_summon_is_negated_goes_to_the_extra_deck():
    # FAQ 24012: a negated Flip Summon destroys the monster in the Monster Zone, so a Pendulum Monster goes face-up to the Extra Deck.
    d = start({"monsters": [{"card": "Performapal Momoncarpet", "position": "set"}], "deck_filler": 10},
              {"spells_traps": [{"card": "Solemn Judgment", "face_up": False}], "deck_filler": 10})
    out = d.play(["Change the battle position of Performapal Momoncarpet", "Activate Solemn Judgment"])
    assert "Performapal Momoncarpet: P1 Monster Zone 1 → P1 Extra Deck — destroyed by an effect" in out


def test_pendulum_monster_whose_normal_summon_is_negated_still_goes_to_the_gy():
    # Control: a negated Normal Summon never puts the monster on the field, so it goes to the GY.
    d = start({"hand": ["Performapal Momoncarpet"], "deck_filler": 10},
              {"spells_traps": [{"card": "Solemn Judgment", "face_up": False}], "deck_filler": 10})
    out = d.play(["Normal Summon Performapal Momoncarpet", "P1 Monster Zone 1", "Activate Solemn Judgment"])
    assert "Performapal Momoncarpet: P1 Monster Zone 1 → P1 GY" in out


# ---------------------------------------------------------------- face-up Traps in the setup are activated when the duel starts
_RARE_METALMORPH_BOARD = {
    "hand": ["The Big Cattle Drive", "Book of Moon"],
    "monsters": [{"card": "Cyber Dragon"}, {"card": "Gazelle the King of Mythical Beasts"}],
    "spells_traps": [{"card": "Rare Metalmorph", "face_up": True, "targets": ["Cyber Dragon"]}],
    "deck_filler": 10,
}


def _s_main_phase(d):
    while d.decision.kind != "idle":
        d.play(["Pass (don't respond)"])
    return d.describe_decision()


def test_face_up_rare_metalmorph_in_the_setup_negates_a_spell_targeting_its_monster():
    # Its negation is applied by its activation, so a Trap only placed face-up did not have it.
    d = start(_RARE_METALMORPH_BOARD, {"deck_filler": 10})
    assert "Setup: Rare Metalmorph (P1 Spell & Trap Zone 1) was activated on Cyber Dragon (P1 Monster Zone 1)" in "\n".join(d.log)
    assert "Cyber Dragon, face-up Attack, ATK 2600" in d.board()
    _s_main_phase(d)
    out = d.play(["Activate Book of Moon", "P1 Spell & Trap Zone 2", "Cyber Dragon"])
    assert "Chain Link 1 (Book of Moon): its effect is negated" in out


def test_activation_at_the_start_is_not_counted_in_this_turns_records():
    # The Big Cattle Drive can't be activated after a Spell/Trap activation this turn; the setup's activation is from an earlier turn.
    d = start(_RARE_METALMORPH_BOARD, {"deck_filler": 10})
    assert "Activate The Big Cattle Drive (P1 hand)" in _s_main_phase(d)


def test_face_up_equip_trap_in_the_setup_applies_its_activation():
    d = start({"monsters": [{"card": "Cyber Dragon"}], "spells_traps": [{"card": "Metalmorph", "face_up": True, "equipped_to": "Cyber Dragon"}],
               "deck_filler": 10}, {"deck_filler": 10})
    assert "Cyber Dragon, face-up Attack, ATK 2400/DEF 1900" in d.board()
    assert "Metalmorph, face-up, equipped to the card in P1 Monster Zone 1" in d.board()


def test_face_up_trap_whose_activation_summons_keeps_its_target_set_directly():
    # Call of the Haunted targets a monster in the GY, so it can't be activated again on the monster it revived.
    d = start({"monsters": [{"card": "Cyber Dragon"}], "spells_traps": [{"card": "Call of the Haunted", "face_up": True, "targets": ["Cyber Dragon"]}],
               "deck_filler": 10}, {"deck_filler": 10})
    assert not any(line.startswith("Setup:") for line in d.log)
    assert "Call of the Haunted, face-up" in d.board()


def test_face_up_trap_that_cant_be_activated_on_its_target_is_an_error():
    with pytest.raises(ValueError, match="Can't set up Rare Metalmorph .* it can't target Gazelle"):
        start({"monsters": [{"card": "Gazelle the King of Mythical Beasts"}, {"card": "Cyber Dragon"}],
               "spells_traps": [{"card": "Rare Metalmorph", "face_up": True, "targets": ["Gazelle the King of Mythical Beasts"]}], "deck_filler": 10},
              {"deck_filler": 10})


def test_which_traps_are_activated_at_the_start():
    from ygo_judge.scenario import replays_activation
    for name, replays in [("Rare Metalmorph", True), ("Metalmorph", True), ("Fiendish Chain", True), ("Spellbinding Circle", True),
                          ("Call of the Haunted", False), ("Seal of Wickedness", False), ("Mystical Space Typhoon", False)]:
        assert replays_activation(db.resolve(name), db) == replays, name


def test_exported_puzzle_keeps_the_face_up_trap_and_its_target():
    # EDOPro has no Debug.ResetTurnRecords, and players open the board as it was described.
    d = start(_RARE_METALMORPH_BOARD, {"deck_filler": 10})
    assert "Debug.PreSetTarget(" in d.puzzle and "ResetTurnRecords" not in d.puzzle
    assert ",LOCATION_SZONE,0,POS_FACEUP) --Rare Metalmorph" in d.puzzle


def test_undo_after_the_start_activation_rebuilds_the_same_board():
    d = start(_RARE_METALMORPH_BOARD, {"deck_filler": 10})
    _s_main_phase(d)
    before, made = d.board(), d.decisions
    d.play(["Activate Book of Moon", "P1 Spell & Trap Zone 2", "Cyber Dragon"])
    d.undo(d.decisions - made)
    assert d.board() == before and d.decision.kind == "idle"


# ---------------------------------------------------------------- fourth batch of 100 Q&As
def _b4_turn(d, turn):
    """Pass every window and end turns until the Main Phase 1 of `turn`."""
    for _ in range(40):
        if d.turn == turn and d.decision.kind == "idle":
            return
        d.play(["Pass (don't respond)"] if d.decision.kind == "chain" else ["End the turn"])
    raise AssertionError(f"turn {turn} never came:\n{d.describe_decision()}")


def _b4_until(d, wanted):
    """Pass every window until an option starting with `wanted` is offered."""
    for _ in range(20):
        if any(o.label.startswith(wanted) for o in d.decision.options):
            return
        d.play(["Pass (don't respond)"] if d.decision.kind == "chain" else ["End the turn"])
    raise AssertionError(f"{wanted!r} was never offered:\n{d.describe_decision()}")


def test_update_jammer_inflicts_damage_when_both_monsters_are_destroyed():
    # FAQ 22202: yes, even if your Cyberse monster is destroyed by the same battle.
    d = start({"monsters": [{"card": "Update Jammer", "zone": "EMZ left"}, {"card": "Backup Secretary", "zone": 2}], "deck_filler": 10},
              {"monsters": [{"card": "Backup Secretary", "zone": 1}], "deck_filler": 10})
    _b4_turn(d, 3)
    out = d.play(["Enter the Battle Phase", "Attack with Backup Secretary", "Backup Secretary (P2 Monster Zone 1)", "Yes"])
    assert "Backup Secretary: P1 Monster Zone 2 → P1 GY — destroyed by battle" in out
    assert "P2 takes 1000 damage" in out


def test_wind_pegasus_destroyed_with_the_other_monsters_cannot_activate():
    # FAQ 22856: no, when it is destroyed together with them.
    d = start({"monsters": [{"card": "Dark Templar @Ignister", "zone": "EMZ left"}, {"card": "Wind Pegasus @Ignister", "zone": 2}], "deck_filler": 10},
              {"hand": ["Raigeki"], "monsters": [{"card": "Mystical Shine Ball", "zone": 1}], "deck_filler": 10})
    _b4_turn(d, 2)
    out = d.play(["Activate Raigeki", "P2 Spell & Trap Zone 1"])
    assert "Wind Pegasus @Ignister: P1 Monster Zone 2 → P1 GY" in out
    assert "Wind Pegasus" not in d.describe_decision()


def test_wind_pegasus_on_the_field_still_activates_when_another_card_is_destroyed():
    d = start({"monsters": [{"card": "Wind Pegasus @Ignister"}], "spells_traps": [{"card": "Pot of Greed"}], "deck_filler": 10},
              {"spells_traps": [{"card": "Dust Tornado"}], "monsters": [{"card": "Mystical Shine Ball"}], "deck_filler": 10})
    _b4_until(d, "Activate Dust Tornado")
    out = d.play(["Activate Dust Tornado", "P1 Spell & Trap Zone 1"])
    assert "Pot of Greed: P1 Spell & Trap Zone 1 → P1 GY — destroyed by an effect" in out
    assert "activate/use the effect of Wind Pegasus @Ignister (P1 Monster Zone 1)" in d.describe_decision()


def test_valiant_shark_lancer_sees_the_water_attribute_the_destroyed_monster_had():
    # FAQ 22945: Black Ray Lancer revived by Xyz Revive Splash is WATER, so Valiant Shark Lancer can activate.
    d = start({"monsters": [{"card": "Valiant Shark Lancer", "zone": "EMZ left", "materials": ["Mystical Shine Ball", "Mystical Shine Ball"]}],
               "graveyard": [{"card": "Black Ray Lancer", "properly_summoned": True}], "spells_traps": [{"card": "Xyz Revive Splash"}],
               "deck": ["Mystical Shine Ball", "Raigeki"], "deck_filler": 10},
              {"spells_traps": [{"card": "Raigeki Break"}], "hand": ["Mystical Shine Ball"], "deck_filler": 10})
    d.play(["Activate Xyz Revive Splash", "Black Ray Lancer", "Pass (don't respond)", "P1 Monster Zone 1", "Face-up attack"])
    _b4_until(d, "Activate Raigeki Break")
    out = d.play(["Activate Raigeki Break", "Mystical Shine Ball", "Black Ray Lancer"])
    assert "Black Ray Lancer: P1 Monster Zone 1 → P1 GY — destroyed by an effect" in out
    assert "activate/use the effect of Valiant Shark Lancer" in d.describe_decision()


def test_two_mirrors_of_the_ice_barrier_banish_up_to_4_cards():
    # FAQ 10199: the number of banished cards adds up.
    d = start({"hand": ["Sangan"], "spells_traps": [{"card": "Mirror of the Ice Barrier"}, {"card": "Mirror of the Ice Barrier"}], "deck_filler": 10},
              {"hand": ["Mystical Shine Ball"] * 5, "monsters": [{"card": "Junk Synchron"}, {"card": "Gemini Elf"}, {"card": "Mystical Shine Ball"}],
               "extra_deck": ["Trishula, Dragon of the Ice Barrier"], "deck_filler": 10})
    for zone in (1, 2):  # on P2's turn: they last until its End Phase
        for _ in range(20):
            mirror = f"Activate Mirror of the Ice Barrier (P1 Spell & Trap Zone {zone})"
            if d.turn == 2 and any(o.label.startswith(mirror) for o in d.decision.options):
                break
            d.play(["Pass (don't respond)"] if d.decision.kind == "chain" else ["End the turn"])
        d.play([mirror])
    _b4_turn(d, 2)
    out = d.play(["Special Summon Trishula", ["Junk Synchron", "Gemini Elf", "Mystical Shine Ball"], "P2 Monster Zone 1", "Face-up attack", "Yes", "No"])
    out += d.play(["Banish 2 cards", "Banish 2 cards"])  # once for each Mirror
    assert out.count("Mystical Shine Ball: P2 hand → P2 banished") == 4


def test_emerald_eagle_inflicts_the_original_atk_of_a_trap_monster():
    # FAQ 22051: Embodiment of Apophis is destroyed and its controller takes 1600 damage.
    d = start({"monsters": [{"card": "Salamangreat Emerald Eagle", "summoned": "ritual", "properly_summoned": True, "zone": 1},
                            {"card": "Salamangreat Almiraj", "zone": 2}], "deck_filler": 10},
              {"spells_traps": [{"card": "Embodiment of Apophis"}], "deck_filler": 10})
    _b4_turn(d, 2)
    d.play(["Activate Embodiment of Apophis", "Pass (don't respond)", "P2 Monster Zone 1", "Face-up attack"])
    _b4_turn(d, 3)
    d.play(["Activate Salamangreat Emerald Eagle", "Salamangreat Almiraj"])
    out = d.play(["Enter the Battle Phase", "Attack with Salamangreat Emerald Eagle", "Embodiment of Apophis"])
    out += d.play(["Pass (don't respond)"] * 3)
    assert "Embodiment of Apophis: P2 Monster Zone 1 → P2 GY — destroyed by an effect" in out
    assert "P2 takes 1600 damage" in out


def test_folgo_counts_formud_skipper_as_the_type_it_was_used_as():
    # FAQ 22009: with Formud Skipper used as a Spellcaster, Folgo can't Special Summon a Spellcaster "Fur Hire" monster.
    # (The engine already did this; the test run that reported otherwise had not answered Formud Skipper's prompt.)
    d = start({"monsters": [{"card": "Formud Skipper"}, {"card": "Backup Secretary"}, {"card": "Recon, Scout Fur Hire"}],
               "extra_deck": ["Summon Sorceress", "Folgo, Justice Fur Hire"],
               "deck": ["Dyna, Hero Fur Hire", "Rafale, Champion Fur Hire", "Sagitta, Maverick Fur Hire", "Wiz, Sage Fur Hire"], "deck_filler": 10},
              {"deck_filler": 10})
    _b4_turn(d, 1)
    d.play(["Activate Formud Skipper", "Summon Sorceress"])
    d.play(["Special Summon Folgo", ["Formud Skipper", "Backup Secretary", "Recon, Scout Fur Hire"], "Yes", "P1 Extra Monster Zone left", "Yes"])
    decision = d.describe_decision()
    assert "Dyna, Hero Fur Hire" in decision  # Winged Beast: none of the 3 materials
    assert "Wiz, Sage Fur Hire" not in decision  # Spellcaster, as Formud Skipper was used


def test_multirole_counts_a_sky_striker_field_spell_activated_by_metaverse():
    # FAQ 22468: yes, Area Zero activated by Metaverse while Multirole is face-up counts.
    d = start({"spells_traps": [{"card": "Sky Striker Mecha Modules - Multirole", "face_up": True}, {"card": "Metaverse"}],
               "graveyard": ["Sky Striker Mobilize - Engage!"], "deck": ["Sky Striker Airspace - Area Zero"], "deck_filler": 10},
              {"deck_filler": 10})
    d.play(["Activate Metaverse", "Activate it"])
    _b4_turn(d, 1)
    d.play(["End the turn"])
    assert "activate/use the effect of Sky Striker Mecha Modules - Multirole" in d.describe_decision()


def test_battleguard_rage_returns_a_trap_monster_it_destroys_to_the_hand():
    # FAQ 6858 (and 7628, Dracocension): a Trap Monster destroyed by battle goes to the hand instead of the GY.
    d = start({"monsters": [{"card": "Axe Raider"}], "spells_traps": [{"card": "Battleguard Rage", "face_up": True, "targets": ["Axe Raider"]}],
               "deck_filler": 10}, {"spells_traps": [{"card": "Embodiment of Apophis"}], "deck_filler": 10})
    _b4_turn(d, 2)
    d.play(["Activate Embodiment of Apophis", "P2 Monster Zone 1", "Face-up attack"])
    _b4_turn(d, 3)
    out = d.play(["Enter the Battle Phase", "Attack with Axe Raider", "Embodiment of Apophis"])
    assert "Embodiment of Apophis: P2 Monster Zone 1 → P2 hand" in out


# ---------------------------------------------------------------- the 3 left from the fourth batch
def test_the_sun_does_not_count_a_normal_pendulum_monster_outside_the_pendulum_zone():
    # FAQ 24114 (B): Tempura of Fortune - EBI in the Monster Zone is not a card with a coin toss effect.
    d = start({"hand": ["Arcana Force XIX - The Sun"], "monsters": [{"card": "Tempura of Fortune - EBI"}], "deck_filler": 10}, {"deck_filler": 10})
    assert "Arcana Force XIX - The Sun" not in d.describe_decision()


def test_the_sun_counts_tempura_of_fortune_ebi_in_the_pendulum_zone():
    d = start({"hand": ["Arcana Force XIX - The Sun"], "pendulum_zones": ["Tempura of Fortune - EBI"], "deck_filler": 10}, {"deck_filler": 10})
    assert "Arcana Force XIX - The Sun" in d.describe_decision()


def test_minimum_ray_destroyed_by_blast_sphere_cannot_activate_on_that_damage():
    # FAQ 22657: "destroy it, and inflict damage" happen at the same time, so Minimum Ray was not in the GY yet.
    d = start({"monsters": [{"card": "Vision HERO Minimum Ray"}], "deck_filler": 10},
              {"monsters": [{"card": "Blast Sphere", "position": "set"}], "deck_filler": 10})
    _b4_turn(d, 3)
    d.play(["Enter the Battle Phase", "Attack with Vision HERO Minimum Ray", "Blast Sphere", "P2 Spell & Trap Zone 1"])
    _b4_turn(d, 5)
    assert "Vision HERO Minimum Ray: P1 Monster Zone 1 → P1 GY — destroyed by an effect" in d.log
    assert "Minimum Ray" not in d.describe_decision()


def test_minimum_ray_already_in_the_gy_activates_on_damage():
    d = start({"graveyard": ["Vision HERO Minimum Ray"], "deck_filler": 10}, {"hand": ["Ookazi"], "deck_filler": 10})
    _b4_turn(d, 2)
    d.play(["Activate Ookazi", "P2 Spell & Trap Zone 1"])
    assert "activate/use the effect of Vision HERO Minimum Ray (P1 GY)" in d.describe_decision()


def test_mereologic_aggregator_sent_for_ext_ryzeal_activates_after_the_summon_is_negated():
    # FAQ 24102: after Sauravis negates and banishes Ext Ryzeal, Aggregator's effect activates as Chain Link 1.
    # (The engine was already right; the board needs a face-up card whose effects can be negated.)
    d = start({"hand": ["Ext Ryzeal"], "extra_deck": ["Mereologic Aggregator"], "monsters": [{"card": "Sangan"}], "deck_filler": 10},
              {"monsters": [{"card": "Sauravis, the Ancient and Ascended"}], "deck_filler": 10})
    d.play(["Special Summon Ext Ryzeal", "Select Mereologic Aggregator (P1 Extra Deck)", "P1 Monster Zone 2", "Face-up attack"])
    out = d.play(["Activate Sauravis, the Ancient and Ascended"])
    assert "Ext Ryzeal: P1 Monster Zone 2 → P1 banished — by an effect" in out
    assert "activate/use the effect of Mereologic Aggregator (P1 GY)" in d.describe_decision()


def test_a_counter_only_one_card_uses_goes_by_that_card_name():
    d = start({"field_spell": {"card": "Sacred Scrolls of the Gizmek Legend", "counters": {"Sacred Scrolls of the Gizmek Legend": 10}},
               "deck_filler": 10}, {"deck_filler": 10})
    assert '10 Counter ("Sacred Scrolls of the Gizmek Legend")' in d.board()


def test_an_unknown_counter_lists_similar_ones():
    with pytest.raises(ValueError, match=r'Similar: .*Sacred Scrolls of the Gizmek Legend'):
        start({"field_spell": {"card": "Sacred Scrolls of the Gizmek Legend", "counters": {"Gizmek Counter": 10}}, "deck_filler": 10},
              {"deck_filler": 10})


# ---------------------------------------------------------------- fifth batch of 100 Q&As
def test_evil_twin_present_lets_its_player_choose_both_zones():
    # FAQ 23069: the player who activated it chooses where both monsters go.
    d = start({"monsters": [{"card": "Live☆Twin Ki-sikil", "zone": 1}, {"card": "Live☆Twin Lil-la", "zone": 2}],
               "spells_traps": [{"card": "Evil★Twin Present"}], "deck_filler": 10},
              {"monsters": [{"card": "Mystical Shine Ball", "zone": 1}], "deck_filler": 10})
    d.play(["Activate Evil★Twin Present", "Live☆Twin Ki-sikil", "Mystical Shine Ball", "P1 Monster Zone 3"])
    assert d.decision.player == 0 and "P2 Monster Zone 4" in d.describe_decision()
    d.play(["P2 Monster Zone 4"])
    assert "P1 Monster Zone 3: Mystical Shine Ball" in d.board() and "P2 Monster Zone 4: Live☆Twin Ki-sikil" in d.board()


def _numerounia(book_of_moon):
    d = start({"hand": ["Book of Moon"], "monsters": [{"card": "Number C1000: Numerounius", "zone": 2, "materials": ["Mystical Shine Ball"] * 5}],
               "extra_deck": ["Number iC1000: Numerounius Numerounia"], "deck_filler": 10},
              {"hand": ["Mystical Shine Ball"], "spells_traps": [{"card": "Raigeki Break"}], "deck_filler": 10})
    d.play(["Pass (don't respond)", "Activate Raigeki Break", "Pass (don't respond)", "Yes", "P1 Monster Zone 2", "Face-up attack"])
    if book_of_moon:
        d.play(["Activate Book of Moon", "P1 Spell & Trap Zone 1"])
        _b4_turn(d, 3)
        d.play(["Change the battle position of Number iC1000"])
    return d


def test_numerounia_turned_face_down_no_longer_wins():
    # FAQ 23248: once face-down it is no longer the monster Special Summoned by Numerounius.
    d = _numerounia(book_of_moon=True)
    out = ""
    for _ in range(30):
        if d.turn == 5:
            break
        out += d.play(["Pass (don't respond)"] if d.decision.kind == "chain" else ["End the turn"])
    assert d.turn == 5 and "wins" not in out


def test_numerounia_summoned_by_numerounius_wins_at_the_end_phase():
    # FAQ 23250
    d = _numerounia(book_of_moon=False)
    out = ""
    for _ in range(30):
        if "wins" in out:
            break
        out += d.play(["Pass (don't respond)"] if d.decision.kind == "chain" else ["End the turn"])
    assert 'P1 wins (Victory by the effect of "Number iC1000: Numerounius Numerounia")' in out


def test_different_dimension_ground_does_not_banish_shade_brigandine():
    # FAQ 23545: it goes to the GY (a Trap Card Special Summoned as a monster, like FAQ 7959).
    d = start({"spells_traps": [{"card": "The Phantom Knights of Shade Brigandine"}, {"card": "Different Dimension Ground"}], "deck_filler": 10},
              {"hand": ["Raigeki"], "deck_filler": 10})
    d.play(["Activate The Phantom Knights of Shade Brigandine", "Pass (don't respond)", "P1 Monster Zone 1"])
    _b4_turn(d, 2)
    out = d.play(["Activate Raigeki", "P2 Spell & Trap Zone 1", "Activate Different Dimension Ground"])
    out += d.play(["Pass (don't respond)"] * 2)
    assert "The Phantom Knights of Shade Brigandine: P1 Monster Zone 1 → P1 GY — destroyed by an effect" in out


def test_dimensional_fissure_does_not_banish_a_trap_card_summoned_as_a_monster():
    # FAQ 7959: such monsters are sent to the GY as usual, even ones "not treated as a Trap".
    d = start({"spells_traps": [{"card": "The Phantom Knights of Shade Brigandine"}, {"card": "Dimensional Fissure", "face_up": True}],
               "monsters": [{"card": "Axe Raider", "zone": 3}], "deck_filler": 10}, {"hand": ["Raigeki"], "deck_filler": 10})
    d.play(["Activate The Phantom Knights of Shade Brigandine", "P1 Monster Zone 1"])
    _b4_turn(d, 2)
    out = d.play(["Activate Raigeki", "P2 Spell & Trap Zone 1"])
    assert "The Phantom Knights of Shade Brigandine: P1 Monster Zone 1 → P1 GY — destroyed by an effect" in out
    assert "Axe Raider: P1 Monster Zone 3 → P1 banished — destroyed by an effect" in out


def test_shade_brigandine_turned_face_down_stays_in_the_monster_zone():
    # FAQ 8627 (B): a monster "not treated as a Trap" is not Set in the Spell & Trap Zone.
    d = start({"hand": ["Book of Moon"], "spells_traps": [{"card": "The Phantom Knights of Shade Brigandine"}], "deck_filler": 10}, {"deck_filler": 10})
    d.play(["Activate The Phantom Knights of Shade Brigandine", "P1 Monster Zone 1"])
    d.play(["Activate Book of Moon", "P1 Spell & Trap Zone 2", "The Phantom Knights of Shade Brigandine"])
    assert "P1 Monster Zone 1: The Phantom Knights of Shade Brigandine, face-down Defense" in d.board()


# ---------------------------------------------------------------- the sixth 100 official Q&As
def _chain_options(d):
    return [o.label for o in d.decision.options]


def test_kagetokage_and_simorgh_can_be_activated_in_the_same_chain():
    # FAQ 23413: Simorgh's (1) Normal Summons a "Simorgh" monster; it is not a hand trigger that summons itself.
    for first, second in (("Kagetokage", "Simorgh, Bird of Perfection"), ("Simorgh, Bird of Perfection", "Kagetokage")):
        d = start({"hand": ["Kagetokage", "Simorgh, Bird of Perfection", "Blackwing - Bora the Spear"], "deck_filler": 10}, {"deck_filler": 10})
        d.play(["Normal Summon Blackwing - Bora the Spear", "P1 Monster Zone 1"])
        d.play([f"Activate {first}"])
        assert any(o.startswith(f"Activate {second}") for o in _chain_options(d)), d.describe_decision()


def _bahalutiya(hand, monsters):
    d = start({"hand": hand, "monsters": [{"card": "Effect Veiler", "zone": z} for z in range(1, monsters + 1)], "deck_filler": 10},
              {"hand": ["Reinforcement of the Army"], "deck": ["Mystical Shine Ball", "Marauding Captain"], "deck_filler": 10})
    _b4_turn(d, 2)
    d.play(["Activate Reinforcement of the Army", "P2 Spell & Trap Zone 1"])
    return d


def test_bahalutiya_and_puppet_king_cannot_both_be_activated():
    # FAQ 23414: only one of them, as both summon themselves from the hand.
    d = _bahalutiya(["Bahalutiya, the Grand Radiance", "Puppet King"], 1)
    opts = _chain_options(d)
    assert any(o.startswith("Activate Puppet King") for o in opts) and any(o.startswith("Activate Bahalutiya") for o in opts), d.describe_decision()
    out = d.play(["Activate Puppet King"])
    assert "Chain Link 1: P1 activates Puppet King" in out
    assert not any(o.startswith("Activate Bahalutiya") for o in _chain_options(d)), d.describe_decision()


def test_two_bahalutiya_cannot_both_be_activated():
    # FAQ 21041
    d = _bahalutiya(["Bahalutiya, the Grand Radiance", "Bahalutiya, the Grand Radiance"], 4)
    assert sum(o.startswith("Activate Bahalutiya") for o in _chain_options(d)) == 2, d.describe_decision()
    out = d.play([0])
    assert "Chain Link 1: P1 activates Bahalutiya" in out
    assert not any(o.startswith("Activate Bahalutiya") for o in _chain_options(d)), d.describe_decision()


def test_sword_fish_activates_once_after_two_special_summons_in_a_chain():
    # FAQ 23436 (also 18253, 18435, 22741, 12800): once after the chain, however many summons.
    d = start({"monsters": [{"card": "Performapal Sword Fish", "zone": 1}], "graveyard": ["Mystical Shine Ball", "Kuriboh"],
               "spells_traps": [{"card": "Call of the Haunted"}, {"card": "Call of the Haunted"}], "deck_filler": 10},
              {"monsters": [{"card": "Blue-Eyes White Dragon"}], "deck_filler": 10})
    out = d.play([0, "Mystical Shine Ball", 0, "Kuriboh"])
    for _ in range(10):
        if d.decision.kind == "idle":
            break
        out += d.play([0])
    assert out.count("activates Performapal Sword Fish") == 1, out
    assert "Blue-Eyes White Dragon (P2 Monster Zone 1): ATK 2400" in d.board() or "2400" in d.board(), d.board()


def test_sword_fish_activates_again_for_a_summon_in_a_later_chain():
    # each chain is counted on its own
    d = start({"monsters": [{"card": "Performapal Sword Fish", "zone": 1}], "graveyard": ["Mystical Shine Ball", "Kuriboh"],
               "spells_traps": [{"card": "Call of the Haunted"}, {"card": "Call of the Haunted"}], "deck_filler": 10},
              {"monsters": [{"card": "Blue-Eyes White Dragon"}], "deck_filler": 10})
    out = ""
    for target in ("Mystical Shine Ball", "Kuriboh"):
        out += d.play([0, target, "Pass (don't respond)"])
        for _ in range(10):
            if d.decision.kind in ("idle",) or (d.decision.kind == "chain" and any("Call of the Haunted" in o for o in _chain_options(d))):
                break
            out += d.play([0])
    assert out.count("activates Performapal Sword Fish") == 2, out


def test_criosphinx_activates_when_a_trap_monster_returns_to_the_hand():
    # FAQ 6789: "Embodiment of Apophis" treated as a monster returns to the hand -> Criosphinx activates
    d = start({"hand": ["Effect Veiler"], "monsters": [{"card": "Criosphinx", "zone": 1}],
               "spells_traps": [{"card": "Embodiment of Apophis"}, {"card": "Compulsory Evacuation Device"}], "deck_filler": 10}, {"deck_filler": 10})
    d.play(["Pass (don't respond)", "Pass (don't respond)", "Activate Embodiment of Apophis", "Pass (don't respond)", "P1 Monster Zone 2", "Face-up attack"])
    out = d.play(["Activate Compulsory Evacuation Device", "Embodiment of Apophis"])
    assert "Embodiment of Apophis: P1 Monster Zone 2 → P1 hand" in out
    assert "Select the card(s) to send to the GY" in d.describe_decision(), out + d.describe_decision()


def test_djinn_detached_as_xyz_material_for_a_ritual_summon_gives_no_protection():
    # FAQ 21257: detached by "Drytron Mu Beta Fafnir" instead of being Tributed -> no immunity to Traps
    d = start({"hand": ["Machine Angel Ritual", "Cyber Angel Benten"],
               "monsters": [{"card": "Drytron Mu Beta Fafnir", "position": "attack", "zone": 1,
                             "materials": ["Djinn Disserere of Rituals"] + ["Effect Veiler"] * 5}], "deck_filler": 10},
              {"spells_traps": [{"card": "Torrential Tribute"}], "deck_filler": 10})
    d.play([0, 0, [0, 1, 2, 3, 4, 5], 0, 0])
    out = d.play(["Activate Torrential Tribute", "No"])
    assert "Cyber Angel Benten: P1 Monster Zone 2 → P1 GY — destroyed by an effect" in out, out


def test_barrel_behind_the_door_can_respond_to_blast_held_by_destiny():
    # FAQ 23671: it inflicts damage equal to the original ATK of the destroyed monster
    d = start({"monsters": [{"card": "Kuriboh", "zone": 1}], "spells_traps": [{"card": "Blast Held by Destiny"}], "deck_filler": 10},
              {"monsters": [{"card": "Battle Ox", "zone": 1}], "spells_traps": [{"card": "Barrel Behind the Door"}], "deck_filler": 10})
    d.play(["End the turn", "Enter the Battle Phase", "Attack with Battle Ox", "Kuriboh", "Activate Blast Held by Destiny"])
    assert any(o.startswith("Activate Barrel Behind the Door") for o in _chain_options(d)), d.describe_decision()


def test_exosister_irene_activates_when_the_opponent_banishes_their_own_gy_by_smile_action():
    # FAQ 23405: each player banishes from their own GY; the opponent's cards left the GY by the opponent
    d = start({"hand": ["Smile Action"], "monsters": [{"card": "Exosister Irene", "zone": 1}], "graveyard": ["Raigeki"],
               "extra_deck": ["Exosister Mikailis"], "deck_filler": 10}, {"graveyard": ["Dark Hole"], "deck_filler": 10})
    out = d.play(["Activate Smile Action", "Yes", "Raigeki", "Yes", "Dark Hole"])
    assert "Dark Hole: P2 GY → P2 banished (face-down)" in out
    assert "effect of Exosister Irene" in d.describe_decision(), out + d.describe_decision()


def test_exosister_irene_does_not_activate_when_you_banish_your_own_gy_by_smile_action():
    d = start({"hand": ["Smile Action"], "monsters": [{"card": "Exosister Irene", "zone": 1}], "graveyard": ["Raigeki"],
               "extra_deck": ["Exosister Mikailis"], "deck_filler": 10}, {"graveyard": ["Dark Hole"], "deck_filler": 10})
    out = d.play(["Activate Smile Action", "Yes", "Raigeki", "No"])
    assert "Raigeki: P1 GY → P1 banished (face-down)" in out
    assert "effect of Exosister Irene" not in d.describe_decision(), d.describe_decision()


def test_silent_wolf_calupo_sends_a_card_declared_by_prohibition_to_the_gy():
    # FAQ 23805
    d = start({"hand": ["Prohibition", "Silent Wolf Calupo"], "deck": ["Kuriboh"], "deck_filler": 10}, {"deck_filler": 10})
    d.play(["Activate Prohibition", "P1 Spell & Trap Zone 1", "Kuriboh", "Pass (don't respond)"])
    out = d.play(["Normal Summon Silent Wolf Calupo", "P1 Monster Zone 1"])
    assert "Kuriboh: P1 Deck → P1 GY" in out, out
    assert "equipped" not in d.board()


def test_zombie_world_still_makes_monsters_on_the_field_zombies_with_necrovalley():
    # FAQ 23829: Necrovalley only stops the change in the GY
    d = start({"monsters": [{"card": "Ryu Kokki", "zone": 1}], "field_spell": {"card": "Zombie World"}, "deck_filler": 10},
              {"monsters": [{"card": "Black Luster Soldier", "zone": 1, "position": "defense", "summoned": "ritual", "properly_summoned": True}],
               "field_spell": {"card": "Necrovalley"}, "deck_filler": 10})
    out = d.play(["End the turn", "End the turn", "Enter the Battle Phase", "Attack with Ryu Kokki", "Black Luster Soldier"])
    assert "Damage calculation" in out and "activates Ryu Kokki" not in out, out


def test_zombie_world_does_not_change_monsters_in_the_gy_with_necrovalley():
    # FAQ 23829: the monsters in the GY keep their Types ("Book of Life" needs a Zombie in the GY)
    d = start({"hand": ["Book of Life"], "graveyard": ["Celtic Guardian"], "field_spell": {"card": "Zombie World"}, "deck_filler": 10},
              {"field_spell": {"card": "Necrovalley"}, "deck_filler": 10})
    assert not any(o.startswith("Activate Book of Life") for o in _chain_options(d)), d.describe_decision()


def test_brave_eyes_negates_an_effect_activated_at_0_atk_even_if_the_monster_is_turned_face_down():
    # FAQ 23622
    d = start({"hand": ["Polymerization", "Odd-Eyes Pendulum Dragon", "Gearfried the Iron Knight"], "extra_deck": ["Brave-Eyes Pendulum Dragon"],
               "spells_traps": [{"card": "Book of Moon"}], "deck_filler": 10},
              {"monsters": [{"card": "Tri-Brigade Fraktall", "zone": 1}], "graveyard": ["Tri-Brigade Kerass", "Tri-Brigade Kitt"],
               "extra_deck": ["Tri-Brigade Ferrijit the Barren Blossom"], "deck_filler": 10})
    d.play(["Pass (don't respond)", "Pass (don't respond)", "Activate Polymerization", 0, "Pass (don't respond)", [0, 0], 0, 0, "Yes"])
    _b4_turn(d, 2)
    out = d.play(["Activate Tri-Brigade Fraktall"])
    for _ in range(10):
        if "Activate Book of Moon" in d.describe_decision():
            break
        out += d.play([0])
    out += d.play(["Activate Book of Moon", "Tri-Brigade Fraktall"])
    for _ in range(10):
        if d.decision.kind == "idle":
            break
        out += d.play(["Pass (don't respond)"] if d.decision.kind == "chain" else [0])
    assert "Tri-Brigade Fraktall" in out and "Special Summoned" not in out.split("Resolving Chain Link 1")[-1], out


def test_vaylantz_grand_duke_can_target_a_monster_card_with_0_atk():
    # FAQ 23631
    d = start({"hand": ["Polymerization"], "monsters": [{"card": "Saion the Vaylantz Archer", "zone": 1, "summoned": "special", "properly_summoned": True},
                                                       {"card": "Shinonome the Vaylantz Priestess", "zone": 2, "summoned": "special", "properly_summoned": True}],
               "extra_deck": ["Vaylantz Genesis Grand Duke"], "deck_filler": 10},
              {"pendulum_zones": ["Supreme King Gate Zero"], "deck_filler": 10})
    out = ""
    for _ in range(14):
        text = d.describe_decision()
        if "Vaylantz Genesis Grand Duke (P1 Monster Zone" in text and ("Yes" in text or "Activate" in text):
            return
        out += d.play(["Activate Polymerization"] if "Activate Polymerization" in text else [0])
    raise AssertionError(out + d.describe_decision())


def test_en_wave_activates_for_materials_banished_face_down_by_necro_fusion():
    # FAQ 23640
    d = start({"graveyard": ["Elemental HERO Avian", "Elemental HERO Burstinatrix"], "extra_deck": ["Elemental HERO Flame Wingman"],
               "deck": ["Elemental HERO Neos"], "spells_traps": [{"card": "Necro Fusion"}, {"card": "EN Wave", "face_up": True}], "deck_filler": 10},
              {"deck_filler": 10})
    d.play(["Pass (don't respond)", "Pass (don't respond)", "Activate Necro Fusion", [0, 0], 0, 0])
    assert "effect of EN Wave" in d.describe_decision(), d.describe_decision()


def test_evocator_chevalier_summoned_again_is_still_special_summoned_from_the_gy():
    # FAQ 23456: "The Zombie Vampire" can be targeted
    d = start({"hand": ["Axe of Despair", "Monster Reborn"], "graveyard": [{"card": "Evocator Chevalier", "properly_summoned": True}], "deck_filler": 10},
              {"monsters": [{"card": "The Zombie Vampire", "zone": 1, "summoned": "xyz"}], "deck_filler": 10})
    out = d.play(["Activate Monster Reborn"])
    for _ in range(8):
        if d.decision.kind == "idle":
            break
        out += d.play([0])
    out += d.play(["Normal Summon Evocator Chevalier"])
    out += d.play(["Activate Axe of Despair"])
    for _ in range(8):
        if d.decision.kind == "idle":
            break
        out += d.play([0])
    assert any(o.startswith("Activate Evocator Chevalier") for o in _chain_options(d)), out + d.describe_decision()


def test_sapphire_pegasus_can_use_a_spell_trap_zone_freed_by_the_same_destruction():
    # FAQ 23404: the Spell & Trap Zone emptied by "Judgment Dragon" at the same time can take it
    d = start({"monsters": [{"card": "Crystal Beast Sapphire Pegasus", "zone": 1},
                            {"card": "Judgment Dragon", "zone": 2, "summoned": "special", "properly_summoned": True}],
               "spells_traps": [{"card": "Mirror Force"}] * 5, "deck_filler": 10}, {"deck_filler": 10})
    d.play(["Activate Judgment Dragon"])
    assert "Place \"Crystal Beast Sapphire Pegasus\" in the Spell & Trap Zone?" in d.describe_decision(), d.describe_decision()
    out = d.play(["Yes"])
    for _ in range(6):
        if d.decision.kind == "idle":
            break
        out += d.play([0])
    assert "Crystal Beast Sapphire Pegasus: P1 Monster Zone 1 → P1 Spell & Trap Zone" in out, out + d.describe_decision()
    assert re.search(r"Spell & Trap Zone \d: Crystal Beast Sapphire Pegasus", d.board()), d.board()


def test_musical_sumo_moves_into_the_zone_in_front_of_tiamaton():
    # FAQ 23773: the zone holding the opponent's monster is not an unused zone, so Sumo moves there and attaches it
    d = start({"monsters": [{"card": "Iron Dragon Tiamaton", "zone": 1, "summoned": "special", "properly_summoned": True},
                            {"card": "Musical Sumo Dice Games", "zone": 3, "materials": ["Gemini Elf", "Gemini Elf"]}], "deck_filler": 10},
              {"monsters": [{"card": "Battle Ox", "zone": 5}], "deck_filler": 10}, seed=3)
    out = d.play(["End the turn", "Enter the Battle Phase"])
    assert "Die roll for P1: 3" in out, out
    assert "Musical Sumo Dice Games: P1 Monster Zone 3 → P1 GY" not in out, out
    assert "P2 Monster Zone 5: Musical Sumo Dice Games" in d.board(), d.board()


# ---------------------------------------------------------------- the seventh 100 official Q&As
def test_sanguine_swamp_is_destroyed_on_the_second_standby_phase_under_imperial_custom():
    # FAQ 10345: destroying itself on the 2nd Standby Phase is not destruction by a card effect
    d = start({"spells_traps": [{"card": "Imperial Custom", "face_up": True}, {"card": "Sanguine Swamp"}], "deck_filler": 10},
              {"deck_filler": 10})
    d.play(["Activate Sanguine Swamp"])
    assert "Sanguine Swamp" in d.board(), d.board()
    _b4_turn(d, 3)
    assert "Spell & Trap Zone 2: Sanguine Swamp" not in d.board() and re.search(r"GY: .*Sanguine Swamp", d.board()), d.board()


def test_overdoom_line_is_destroyed_on_the_second_end_phase_under_imperial_custom():
    # FAQ 8588
    d = start({"spells_traps": [{"card": "Imperial Custom", "face_up": True}, {"card": "Overdoom Line"}], "deck_filler": 10},
              {"deck_filler": 10})
    d.play(["Activate Overdoom Line"])
    assert "Spell & Trap Zone 2: Overdoom Line" in d.board(), d.board()
    _b4_turn(d, 3)
    assert "Spell & Trap Zone 2: Overdoom Line" in d.board(), d.board()
    _b4_turn(d, 4)
    assert re.search(r"GY: .*Overdoom Line", d.board()), d.board()


def _javelin(armor):
    p1 = {"hand": ["Fissure"], "monsters": [{"card": "Blue-Eyes White Dragon", "zone": 1}], "deck_filler": 10}
    if armor:
        p1["spells_traps"] = [{"card": "Metalsilver Armor", "face_up": True, "equipped_to": "p1:Blue-Eyes White Dragon"}]
    d = start(p1, {"monsters": [{"card": "Dragunity Javelin", "zone": 1}, {"card": "Dragunity Dux", "zone": 2}], "deck_filler": 10})
    return d, d.play(["Activate Fissure"])


def test_dragunity_javelin_cannot_equip_to_a_monster_metalsilver_armor_protects():
    # FAQ 10056: once equipped it keeps targeting the monster, so the opponent's Armor stops it
    d, out = _javelin(True)
    for _ in range(4):
        if d.decision.kind == "idle":
            break
        assert "Dragunity Javelin" not in d.describe_decision().split("Decision for")[-1].split("\n")[0], d.describe_decision()
        out += d.play([0])
    assert "Dragunity Javelin: P2 Monster Zone 1 → P2 GY" in out, out


def test_dragunity_javelin_equips_without_metalsilver_armor():
    d, out = _javelin(False)
    for _ in range(4):
        if d.decision.kind == "idle":
            break
        out += d.play([0])
    assert "Dragunity Javelin: P2 Monster Zone 1 → P2 GY" not in out, out
    assert re.search(r"Spell & Trap Zone \d: Dragunity Javelin", d.board()), d.board()


def test_vanitys_emptiness_activates_once_for_foolish_burial_and_its_own_card():
    # FAQ 12929: the monster from the Deck and the resolved "Foolish Burial" itself trigger it once
    d = start({"hand": ["Foolish Burial"], "deck": ["Kuriboh"], "spells_traps": [{"card": "Vanity's Emptiness", "face_up": True}], "deck_filler": 10},
              {"deck_filler": 10})
    out = d.play(["Activate Foolish Burial", "Kuriboh"])
    for _ in range(8):
        if d.decision.kind == "idle":
            break
        out += d.play([0])
    assert out.count("activates Vanity's Emptiness") == 1, out
    assert re.search(r"GY: .*Vanity's Emptiness", d.board()), d.board()


_EXODIA = ["Exodia the Forbidden One", "Right Leg of the Forbidden One", "Left Leg of the Forbidden One", "Right Arm of the Forbidden One"]


def test_exodia_wins_before_skull_invitation_damage_from_graceful_charity():
    # FAQ 6184: complete when Graceful Charity finishes, so the win comes first and Skull Invitation deals no damage
    d = start({"lp": 300, "hand": ["Graceful Charity"] + _EXODIA, "deck": ["Left Arm of the Forbidden One", "Kuriboh", "Kuriboh"],
               "spells_traps": [{"card": "Skull Invitation", "face_up": True}], "deck_filler": 10}, {"deck_filler": 10})
    out = d.play(["Activate Graceful Charity", 0])
    hand = [o.label for o in d.decision.options]
    out += d.play([[i for i, h in enumerate(hand) if "Kuriboh" in h]])
    assert "P1 wins" in out, out
    assert "P2 wins" not in out and "takes 600 damage" not in out, out


def test_exodia_does_not_win_when_graceful_charity_discards_a_piece():
    # FAQ 11354: drawing the last piece is not enough if the discard sends a piece away
    d = start({"hand": ["Graceful Charity"] + _EXODIA, "deck": ["Left Arm of the Forbidden One", "Kuriboh", "Kuriboh"], "deck_filler": 10},
              {"deck_filler": 10})
    out = d.play(["Activate Graceful Charity", 0])
    hand = [o.label for o in d.decision.options]
    out += d.play([[hand.index(next(h for h in hand if "Exodia the Forbidden One" in h)), hand.index(next(h for h in hand if "Kuriboh" in h))]])
    assert "P1 wins" not in out, out


def test_grandsoil_skips_the_next_battle_phase_even_under_skill_drain():
    # FAQ 12644: the skip still applies when it left the field while negated by "Skill Drain"
    for drain in (True, False):
        d = start({"monsters": [{"card": "Grandsoil the Elemental Lord", "zone": 1, "summoned": "special", "properly_summoned": True}],
                   "spells_traps": [{"card": "Skill Drain", "face_up": True}] if drain else [], "deck_filler": 10},
                  {"hand": ["Dark Hole"], "deck_filler": 10})
        d.play(["End the turn", "Activate Dark Hole", "P2 Spell & Trap Zone 1"])
        assert "Grandsoil the Elemental Lord" in d.board().split("GY:")[1], d.board()
        _b4_turn(d, 3)
        out = d.play(["Enter the Battle Phase"])
        assert "P1 enters the End Phase" in out and d.turn == 4, out


# ---------------------------------------------------------------- the eighth 100 official Q&As
def _black_wing_revenge(declare, monster):
    d = start({"monsters": [{"card": monster, "zone": 1}],
               "spells_traps": [{"card": "DNA Surgery"}, {"card": "Black Wing Revenge"}], "deck_filler": 10},
              {"monsters": [{"card": "Dark Magician", "zone": 1}], "deck_filler": 10})
    _b4_turn(d, 1)
    if declare:
        d.play(["Activate DNA Surgery", declare])
    _b4_turn(d, 2)
    out = d.play(["Enter the Battle Phase", "Attack with Dark Magician", monster])
    for _ in range(12):
        if "Activate Black Wing Revenge" in d.describe_decision() or d.decision.kind == "idle":
            break
        out += d.play([P if P in [o.label for o in d.decision.options] else 0])
    return d, out


P = "Pass (don't respond)"


def test_black_wing_revenge_needs_a_winged_beast_on_the_field_and_in_the_gy():
    # FAQ 6163: neither a Warrior made Winged Beast nor a Winged Beast made Warrior by "DNA Surgery" counts
    for declare, monster in (("Winged Beast", "Celtic Guardian"), ("Warrior", "Harpie Lady 1")):
        d, out = _black_wing_revenge(declare, monster)
        assert f"{monster}: P1 Monster Zone 1 → P1 GY" in out, out
        assert "Activate Black Wing Revenge" not in d.describe_decision(), d.describe_decision()


def test_black_wing_revenge_activates_for_a_winged_beast():
    d, out = _black_wing_revenge(None, "Harpie Lady 1")
    assert "Activate Black Wing Revenge" in d.describe_decision(), out + d.describe_decision()


def test_pitch_black_power_stone_cannot_target_gateway_to_chaos_being_activated():
    # FAQ 14131 (also 14130): it becomes a card Spell Counters can be placed on only once its activation resolves
    d = start({"hand": ["Gateway to Chaos"], "monsters": [{"card": "Breaker the Magical Warrior", "zone": 2}],
               "spells_traps": [{"card": "Pitch-Black Power Stone", "face_up": True, "counters": {"Spell Counter": 3}}],
               "deck": ["Gaia The Fierce Knight"], "deck_filler": 10}, {"deck_filler": 10})
    _b4_turn(d, 1)
    d.play(["Activate Gateway to Chaos"])
    for _ in range(3):
        if any(o.label.startswith("Activate Pitch-Black Power Stone") for o in d.decision.options):
            break
        d.play([0])
    d.play(["Activate Pitch-Black Power Stone"])
    labels = [o.label for o in d.decision.options]
    assert not any("Gateway to Chaos" in o for o in labels), d.describe_decision()
    assert any("Breaker the Magical Warrior" in o for o in labels), d.describe_decision()


def test_synchro_boost_can_equip_a_link_monster_and_only_raises_its_atk():
    # FAQ 20779
    d = start({"hand": ["Synchro Boost"], "monsters": [{"card": "Link Spider", "position": "attack", "zone": "EMZ left"}], "deck_filler": 10},
              {"deck_filler": 10})
    d.play(["Activate Synchro Boost"])
    for _ in range(3):
        if d.decision.kind == "idle":
            break
        d.play([0])
    assert re.search(r"Link Spider[^\n]*ATK 1500", d.board()), d.board()


def _until(d, want, limit=15):
    out = ""
    for _ in range(limit):
        if want(d):
            return out
        labels = [o.label for o in d.decision.options]
        out += d.play([P if P in labels else "End the turn" if "End the turn" in labels else 0])
    raise AssertionError(out + d.describe_decision())


def test_zoodiac_combo_cannot_attach_a_card_prohibition_declared():
    # FAQ 7967: a declared card cannot become Xyz Material from outside the field
    d = start({"monsters": [{"card": "Zoodiac Broadbull", "zone": 1, "materials": ["Zoodiac Ratpier", "Zoodiac Ratpier"]}],
               "spells_traps": [{"card": "Zoodiac Combo"}], "deck": ["Zoodiac Thoroughblade", "Zoodiac Ratpier"], "deck_filler": 10},
              {"spells_traps": [{"card": "Prohibition"}], "deck_filler": 10})
    _b4_turn(d, 2)
    out = d.play(["Activate Prohibition", "Zoodiac Thoroughblade", P])
    assert "Resolving Chain Link 1 (Prohibition)" in out, out
    _until(d, lambda d: any(o.label.startswith("Activate Zoodiac Combo") for o in d.decision.options))
    out = d.play(["Activate Zoodiac Combo"])
    out += _until(d, lambda d: "Resolving Chain Link 1 (Zoodiac Combo)" in out or d.decision.kind == "idle")
    if "Select the card(s) to use as Xyz Material" in d.describe_decision():
        assert not any("Zoodiac Thoroughblade" in o.label for o in d.decision.options), d.describe_decision()
        out += d.play([0])
    assert "Zoodiac Thoroughblade (P1 Deck) becomes Xyz Material" not in out, out
    assert "Zoodiac Ratpier (P1 Deck) becomes Xyz Material" in out, out


def test_supply_squad_draws_when_merrowgeist_returns_the_monster_to_the_deck():
    # FAQ 85: the monster is still destroyed by battle, it only goes to the Deck instead
    d = start({"monsters": [{"card": "Gene-Warped Warwolf", "zone": 1}], "spells_traps": [{"card": "Supply Squad", "face_up": True}], "deck_filler": 10},
              {"monsters": [{"card": "Evigishki Merrowgeist", "zone": 1, "materials": ["Battle Ox", "Battle Ox"]}], "deck_filler": 10})
    _b4_turn(d, 2)
    out = d.play(["Enter the Battle Phase", "Attack with Evigishki Merrowgeist", "Gene-Warped Warwolf"])
    out += d.play(["Yes", 0])
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "Gene-Warped Warwolf: P1 Monster Zone 1 → P1 Deck" in out, out
    assert "activates Supply Squad" in out and "P1 draws" in out, out


def test_major_riot_needs_the_monster_to_leave_your_own_field():
    # FAQ 207: your "Goblin Attack Force" taken by "Creature Swap" and bounced from the opponent's field does not count
    d = start({"hand": ["Creature Swap"], "monsters": [{"card": "Goblin Attack Force", "zone": 1}],
               "spells_traps": [{"card": "Major Riot"}], "deck_filler": 10},
              {"monsters": [{"card": "Kuriboh", "zone": 1}], "spells_traps": [{"card": "Compulsory Evacuation Device"}], "deck_filler": 10})
    _b4_turn(d, 1)
    d.play(["Activate Creature Swap"])
    _until(d, lambda d: d.decision.kind == "idle")
    assert "P2 Monster Zone" in d.board() and "Goblin Attack Force" in d.board().split("P2:")[1], d.board()
    d.play(["End the turn"])
    _until(d, lambda d: any(o.label.startswith("Activate Compulsory Evacuation Device") for o in d.decision.options))
    out = d.play(["Activate Compulsory Evacuation Device", "Goblin Attack Force"])
    out += _until(d, lambda d: d.decision.kind == "idle" or "Major Riot" in d.describe_decision())
    assert "Goblin Attack Force" in out and "Major Riot" not in d.describe_decision(), out + d.describe_decision()


def test_last_counter_in_response_to_scrubbed_raid_keeps_the_battle_phase():
    # FAQ 242: Last Counter enters the damage step, so Scrubbed Raid's "end the Battle Phase" is not applied
    d = start({"monsters": [{"card": "Battlin' Boxer Glassjaw", "zone": 1}, {"card": "Battlin' Boxer Lead Yoke", "zone": 2}],
               "spells_traps": [{"card": "Last Counter"}], "deck_filler": 10},
              {"monsters": [{"card": "Dark Magician", "zone": 1}],
               "spells_traps": [{"card": "Scrubbed Raid", "face_up": True}, {"card": "Mystical Space Typhoon"}], "deck_filler": 10})
    _b4_turn(d, 3)
    d.play(["Enter the Battle Phase"])
    _until(d, lambda d: any(o.label.startswith("Attack with Battlin' Boxer Glassjaw") for o in d.decision.options))
    d.play(["Attack with Battlin' Boxer Glassjaw", "Dark Magician"])
    _until(d, lambda d: any(o.label.startswith("Activate Scrubbed Raid") for o in d.decision.options))
    d.play(["Activate Scrubbed Raid", "Mystical Space Typhoon"])
    _until(d, lambda d: any(o.label.startswith("Activate Last Counter") for o in d.decision.options))
    out = d.play(["Activate Last Counter"])
    assert "Damage calculation: Battlin' Boxer Lead Yoke" in out, out
    assert "P1, Battle Phase" in d.describe_decision() or "attacks directly" in out, out + d.describe_decision()
    assert "enters the Main Phase 2" not in out, out


def test_synchro_material_uses_the_opponents_phantom_king_hydride_only_as_a_tuner():
    # FAQ 253
    d = start({"monsters": [{"card": "Nitro Synchron", "zone": 1}], "spells_traps": [{"card": "Synchro Material"}],
               "extra_deck": ["Ally of Justice Catastor"], "deck_filler": 10},
              {"monsters": [{"card": "Phantom King Hydride", "zone": 1}], "deck_filler": 10})
    _b4_turn(d, 1)
    d.play(["Activate Synchro Material"])
    _until(d, lambda d: d.decision.kind == "idle")
    assert not any("Ally of Justice Catastor" in o.label for o in d.decision.options), d.describe_decision()


# ---------------------------------------------------------------- the ninth 100 official Q&As
def _go(d, label):
    """advance (pass / end the turn) until an option starting with label appears, then choose it"""
    out = _until(d, lambda d: any(o.label.startswith(label) for o in d.decision.options), limit=40)
    return out + d.play([next(o.label for o in d.decision.options if o.label.startswith(label))])


def test_phantom_of_chaos_loses_exodius_banishing_as_it_leaves():
    # FAQ 7038: the effects it gained are gone as it leaves the field, so it goes to the GY
    d = start({"hand": ["Dark Hole"], "monsters": [{"card": "Phantom of Chaos", "zone": 1},
                                                   {"card": "Exodius the Ultimate Forbidden Lord", "zone": 2, "summoned": "special",
                                                    "properly_summoned": True}],
               "graveyard": [{"card": "Exodius the Ultimate Forbidden Lord", "properly_summoned": True}], "deck_filler": 10}, {"deck_filler": 10})
    out = _go(d, "Activate Phantom of Chaos")
    out += _until(d, lambda d: d.decision.kind == "idle")
    out += _go(d, "Activate Dark Hole")
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "Phantom of Chaos: P1 Monster Zone 1 → P1 GY" in out, out
    assert "Exodius the Ultimate Forbidden Lord: P1 Monster Zone 2 → P1 banished" in out, out


def test_infernal_prodigy_draws_even_when_banished_as_tribute():
    # FAQ 7042: banished by "Banisher of the Light" instead of the GY, it still draws in the End Phase
    d = start({"hand": ["Destiny HERO - Dasher"], "monsters": [{"card": "Evil HERO Infernal Prodigy", "zone": 1}], "deck_filler": 10},
              {"monsters": [{"card": "Banisher of the Light", "zone": 1}], "deck_filler": 10})
    out = _go(d, "Normal Summon Destiny HERO - Dasher")
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "Evil HERO Infernal Prodigy: P1 Monster Zone 1 → P1 banished" in out, out
    out += d.play(["End the turn"])
    out += _until(d, lambda d: "activates Evil HERO Infernal Prodigy" in out or d.turn >= 2)
    assert "activates Evil HERO Infernal Prodigy (P1 banished)" in out, out


def test_extra_gate_cannot_be_activated_as_the_only_card_in_hand():
    # FAQ 6251
    d = start({"hand": ["Extra Gate"], "deck_filler": 10}, {"extra_deck": ["Ally of Justice Catastor"], "deck_filler": 10})
    _b4_turn(d, 1)
    assert not any(o.label.startswith("Activate Extra Gate") for o in d.decision.options), d.describe_decision()
    d = start({"hand": ["Extra Gate", "Kuriboh"], "deck_filler": 10}, {"extra_deck": ["Ally of Justice Catastor"], "deck_filler": 10})
    _b4_turn(d, 1)
    assert any(o.label.startswith("Activate Extra Gate") for o in d.decision.options), d.describe_decision()


def test_cocoon_of_evolution_stays_equipped_under_armored_glass():
    # FAQ 6222: with equip effects negated, Petit Moth with Cocoon can still be Tributed for "Larvae Moth"
    d = start({"hand": ["Cocoon of Evolution", "Larvae Moth", "Axe of Despair"],
               "monsters": [{"card": "Petit Moth", "zone": 1}, {"card": "Cyber Jar", "zone": 2}],
               "spells_traps": [{"card": "Armored Glass"}], "deck_filler": 20}, {"deck_filler": 20})
    out = _go(d, "Activate Cocoon of Evolution")
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "Cocoon of Evolution (P1 Spell & Trap Zone 2) is equipped to Petit Moth" in out, out
    _b4_turn(d, 5)
    out = _go(d, "Activate Axe of Despair")
    out += d.play(["Cyber Jar"])
    out += _go(d, "Activate Armored Glass")
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "Cocoon of Evolution: P1 Spell & Trap Zone 2 → P1 GY" not in out, out
    assert any(o.label.startswith("Special Summon Larvae Moth") for o in d.decision.options), d.describe_decision()


def test_cunning_of_the_six_samurai_can_target_the_monster_sent_as_its_cost():
    # FAQ 6817: with no "Six Samurai" in the GY, the one sent as the cost is the target
    d = start({"monsters": [{"card": "The Six Samurai - Yaichi", "zone": 1}], "spells_traps": [{"card": "Cunning of the Six Samurai"}],
               "deck_filler": 10}, {"deck_filler": 10})
    out = _go(d, "Activate Cunning of the Six Samurai")
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "The Six Samurai - Yaichi: P1 Monster Zone 1 → P1 GY — as a cost" in out, out
    assert "The Six Samurai - Yaichi is Special Summoned" in out, out


# ---------------------------------------------------------------- the tenth 100 official Q&As
def test_felgrand_unaffected_by_other_effects_still_cannot_attack_under_heliosphere():
    # FAQ 8360: "Heliosphere Dragon" stops the player declaring attacks; it is not an effect the monster receives
    d = start({"monsters": [{"card": "Divine Dragon Knight Felgrand", "zone": 1, "materials": ["Mystical Shine Ball", "Mystical Shine Ball"]}],
               "deck_filler": 10}, {"monsters": [{"card": "Heliosphere Dragon", "zone": 1}], "deck_filler": 10})
    _b4_turn(d, 3)
    out = _go(d, "Activate Divine Dragon Knight Felgrand")
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "Resolving Chain Link 1 (Divine Dragon Knight Felgrand)" in out, out
    d.play(["Enter the Battle Phase"])
    _until(d, lambda d: d.decision.kind == "idle" or "Battle Phase: choose an action" in d.describe_decision())
    assert not any(o.label.startswith("Attack with") for o in d.decision.options), d.describe_decision()


# ---------------------------------------------------------------- the eleventh 100 official Q&As
def _atk(d, name):
    m = re.search(re.escape(name) + r", face-up \w+, ATK (\d+)", d.board())
    assert m, d.board()
    return int(m.group(1))


def test_temple_of_the_sun_stops_once_the_monster_was_turned_face_down():
    # FAQ 9488 (also 23467): turned face-down, it is no longer "Special Summoned from the GY"
    d = start({"hand": ["Book of Moon"], "monsters": [{"card": "Sabersaurus", "zone": 1, "summoned": "special", "summoned_from": "graveyard"}],
               "spells_traps": [{"card": "Temple of the Sun", "face_up": True}], "deck_filler": 10}, {"deck_filler": 10})
    _b4_turn(d, 1)
    assert _atk(d, "Sabersaurus") == 2200, d.board()
    _go(d, "Activate Book of Moon")
    _until(d, lambda d: d.decision.kind == "idle")
    _go(d, "Change the battle position of Sabersaurus")
    _until(d, lambda d: d.decision.kind == "idle")
    assert _atk(d, "Sabersaurus") == 1900, d.board()


def test_hundred_eyes_dragon_loses_the_atk_gained_with_a_copied_effect():
    # FAQ 9109: the ATK raised by the copied "Dark Crusader" effect ends with the copy
    d = start({"hand": ["Summoned Skull"], "monsters": [{"card": "Hundred Eyes Dragon", "zone": 1}], "graveyard": ["Dark Crusader"],
               "deck_filler": 10}, {"deck_filler": 10})
    _b4_turn(d, 1)
    _go(d, "Activate Hundred Eyes Dragon")
    _until(d, lambda d: d.decision.kind == "idle")
    _go(d, "Activate Hundred Eyes Dragon")
    _until(d, lambda d: d.decision.kind == "idle")
    assert _atk(d, "Hundred Eyes Dragon") == 3400, d.board()
    _b4_turn(d, 3)
    assert _atk(d, "Hundred Eyes Dragon") == 3000, d.board()


def test_ogre_of_the_scarlet_sorrow_does_not_count_a_negated_direct_attack():
    # FAQ 9450
    d = start({"hand": ["Ogre of the Scarlet Sorrow"], "spells_traps": [{"card": "Magic Cylinder"}], "deck_filler": 10},
              {"monsters": [{"card": "Giant Rat", "zone": 1}, {"card": "Giant Rat", "zone": 2}], "deck_filler": 10})
    _b4_turn(d, 2)
    d.play(["Enter the Battle Phase"])
    _go(d, "Attack with Giant Rat")
    out = _go(d, "Activate Magic Cylinder")
    out += _until(d, lambda d: any(o.label.startswith("Attack with Giant Rat") for o in d.decision.options))
    out += d.play([next(o.label for o in d.decision.options if o.label.startswith("Attack with Giant Rat"))])
    assert "attacks directly" in out, out
    assert "Ogre of the Scarlet Sorrow" not in d.describe_decision(), d.describe_decision()


def test_merrowgeist_returns_the_monster_to_the_deck_under_macro_cosmos():
    # FAQ 9305
    d = start({"monsters": [{"card": "Evigishki Merrowgeist", "zone": 1, "materials": ["Giant Rat", "Giant Rat"]}],
               "spells_traps": [{"card": "Macro Cosmos", "face_up": True}], "deck_filler": 10},
              {"monsters": [{"card": "Giant Rat", "zone": 1}], "deck_filler": 10})
    _b4_turn(d, 3)
    d.play(["Enter the Battle Phase"])
    out = _go(d, "Attack with Evigishki Merrowgeist")
    out += d.play(["Giant Rat", "Yes", 0])
    out += _until(d, lambda d: d.decision.kind == "idle" or "Battle Phase: choose" in d.describe_decision())
    assert "Giant Rat: P2 Monster Zone 1 → P2 Deck — destroyed by battle" in out, out


def test_dark_valkyria_loses_its_counter_as_a_normal_monster_and_can_place_one_again():
    # FAQ 8749
    d = start({"hand": ["Mystical Space Typhoon"], "monsters": [{"card": "Dark Valkyria", "zone": 1, "summoned": "normal"}],
               "spells_traps": [{"card": "Supervise", "face_up": True, "equipped_to": "Dark Valkyria"}], "deck_filler": 10}, {"deck_filler": 10})
    out = _go(d, "Activate Dark Valkyria")
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "1 Spell Counter(s) placed on Dark Valkyria" in out, out
    out = _go(d, "Activate Mystical Space Typhoon")
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "Supervise: P1 Spell & Trap Zone 1 → P1 GY" in out and "Spell Counter(s) removed from Dark Valkyria" in out, out
    _go(d, "Normal Summon Dark Valkyria")
    _until(d, lambda d: d.decision.kind == "idle")
    assert any("Place 1 Spell Counter" in o.label for o in d.decision.options), d.describe_decision()


def test_gemini_trap_hole_counts_a_gemini_monster_with_effects_at_damage_calculation():
    # FAQ 8757: "Superalloy Beast Raptinus" destroyed in the same battle stops giving effects, but the Trap can still be activated
    d = start({"hand": ["Rush Recklessly"], "monsters": [{"card": "Evocator Eveque", "zone": 1}], "spells_traps": [{"card": "Gemini Trap Hole"}],
               "deck_filler": 10}, {"monsters": [{"card": "Superalloy Beast Raptinus", "zone": 1}, {"card": "Mystical Shine Ball", "zone": 2}],
                                    "deck_filler": 10})
    _b4_turn(d, 3)
    d.play(["Enter the Battle Phase"])
    _go(d, "Attack with Evocator Eveque")
    d.play(["Superalloy Beast Raptinus"])
    out = _go(d, "Activate Rush Recklessly")
    out += _until(d, lambda d: any(o.label.startswith("Activate Gemini Trap Hole") for o in d.decision.options)
                  or "Battle Phase: choose" in d.describe_decision())
    assert "Superalloy Beast Raptinus: P2 Monster Zone 1 → P2 GY — destroyed by battle" in out, out
    assert any(o.label.startswith("Activate Gemini Trap Hole") for o in d.decision.options), d.describe_decision()


# ---------------------------------------------------------------- the twelfth 100 official Q&As
def test_forbidden_arts_of_the_gishki_can_use_djinn_releaser_in_your_gy():
    # FAQ 10671
    d = start({"hand": ["Forbidden Arts of the Gishki", "Evigishki Gustkraken"], "monsters": [{"card": "Legendary Six Samurai - Shinai", "zone": 1}],
               "graveyard": ["Djinn Releaser of Rituals"], "deck_filler": 10}, {"deck_filler": 10})
    _b4_turn(d, 1)
    assert any(o.label.startswith("Activate Forbidden Arts of the Gishki") for o in d.decision.options), d.describe_decision()


def test_barbaroid_deals_damage_for_a_trap_monster_destroyed_by_battle():
    # FAQ 10435: "Embodiment of Apophis" treated as a monster counts
    d = start({"monsters": [{"card": "Barbaroid, the Ultimate Battle Machine", "zone": 1, "summoned": "fusion", "properly_summoned": True}],
               "deck_filler": 10}, {"spells_traps": [{"card": "Embodiment of Apophis"}], "deck_filler": 10})
    _b4_turn(d, 2)
    _go(d, "Activate Embodiment of Apophis")
    _until(d, lambda d: d.decision.kind == "idle")
    _b4_turn(d, 3)
    d.play(["Enter the Battle Phase"])
    out = _go(d, "Attack with Barbaroid")
    out += d.play(["Embodiment of Apophis"])
    out += _until(d, lambda d: d.decision.kind == "idle" or "Battle Phase: choose" in d.describe_decision())
    assert "Embodiment of Apophis: P2 Monster Zone 1 → P2 GY — destroyed by battle" in out, out
    assert "P2 takes 1000 damage" in out, out


def test_jetstream_cannot_be_activated_for_a_blackwing_waboku_protects():
    # FAQ 10486
    d = start({"hand": ["Blackwing - Jetstream the Blue Sky"], "monsters": [{"card": "Blackwing - Gale the Whirlwind", "zone": 1}],
               "spells_traps": [{"card": "Waboku"}], "deck_filler": 10}, {"monsters": [{"card": "Dark Magician", "zone": 1}], "deck_filler": 10})
    _b4_turn(d, 3)
    d.play(["Enter the Battle Phase"])
    _go(d, "Activate Waboku")
    _until(d, lambda d: any(o.label.startswith("Attack with") for o in d.decision.options))
    d.play(["Attack with Blackwing - Gale the Whirlwind", "Dark Magician"])
    out = _until(d, lambda d: d.decision.kind == "idle" or "Battle Phase: choose" in d.describe_decision()
                 or any("Jetstream" in o.label for o in d.decision.options))
    assert not any("Jetstream" in o.label for o in d.decision.options), out + d.describe_decision()


def test_caius_banishes_the_target_and_its_namesakes_together():
    # FAQ 9927: field and GY "Evilswarm Kerykeion" are banished by the same effect, so "Jewels of the Valiant" cannot be activated
    d = start({"monsters": [{"card": "Evilswarm Kerykeion", "zone": 1}], "graveyard": ["Evilswarm Kerykeion"],
               "spells_traps": [{"card": "Jewels of the Valiant", "face_up": True}], "deck_filler": 12},
              {"hand": ["Caius the Mega Monarch"], "monsters": [{"card": "Gagagigo", "zone": 1, "summoned": "normal"},
                                                                {"card": "Gagagigo", "zone": 2, "summoned": "normal"}], "deck_filler": 12})
    _b4_turn(d, 2)
    out = _go(d, "Normal Summon Caius the Mega Monarch")
    out += d.play([[0, 1], 0])
    out += d.play(["Evilswarm Kerykeion"])
    out += _until(d, lambda d: d.decision.kind == "idle" or any("Jewels of the Valiant" in o.label for o in d.decision.options))
    assert "Evilswarm Kerykeion: P1 GY → P1 banished" in out and "P1 takes 1000 damage" in out, out
    assert not any("Jewels of the Valiant" in o.label for o in d.decision.options) and "activates Jewels of the Valiant" not in out, out


def test_scrap_twin_dragon_does_not_destroy_its_own_target_taken_by_the_opponent():
    # FAQ 10228
    d = start({"monsters": [{"card": "Scrap Twin Dragon", "zone": 1}, {"card": "Skull Servant", "zone": 2}], "deck_filler": 10},
              {"monsters": [{"card": "Dragon Zombie", "zone": 1}, {"card": "Zombie Warrior", "zone": 2}, {"card": "Gemini Elf", "zone": 3}],
               "spells_traps": [{"card": "Enemy Controller"}], "deck_filler": 10})
    _b4_turn(d, 1)
    out = _go(d, "Activate Scrap Twin Dragon")
    out += d.play([1, [0, 1]])
    out += _go(d, "Activate Enemy Controller")
    out += d.play(["Take control of an opponent's monster", 2, "Skull Servant", 0])
    out += _until(d, lambda d: d.decision.kind == "idle")
    after = out.split("Resolving Chain Link 1 (Scrap Twin Dragon)")[-1]
    assert "Resolving Chain Link 1 (Scrap Twin Dragon)" in out, out
    assert "Skull Servant:" not in after and "→ P2 hand" not in after, out


def test_majestic_star_dragon_does_not_gain_a_six_samurai_destruction_replacement():
    # FAQ 10002: it gains only the effects that are activated
    d = start({"hand": ["Offerings to the Doomed"], "monsters": [{"card": "Majestic Star Dragon", "zone": 1, "properly_summoned": True},
                                                                {"card": "The Six Samurai - Kamon", "zone": 2}], "deck_filler": 10},
              {"monsters": [{"card": "The Six Samurai - Yaichi", "zone": 1}], "deck_filler": 10})
    _b4_turn(d, 1)
    out = _go(d, "Activate Majestic Star Dragon")
    out += _until(d, lambda d: d.decision.kind == "idle")
    out += _go(d, "Activate Offerings to the Doomed")
    out += d.play([0, "Majestic Star Dragon"])
    out += _until(d, lambda d: d.decision.kind == "idle" or "avoid destruction" in d.describe_decision())
    assert "avoid destruction" not in d.describe_decision(), d.describe_decision()
    assert "Majestic Star Dragon: P1 Monster Zone 1 → P1 GY — destroyed by an effect" in out, out


def _shadow_feeler(negate):
    d = start({"hand": ["Dark Hole"], "monsters": [{"card": "Gimmick Puppet Shadow Feeler", "zone": 1}, {"card": "Gimmick Puppet Magnet Doll", "zone": 2}],
               "extra_deck": ["Number 15: Gimmick Puppet Giant Grinder"], "deck_filler": 10},
              {"spells_traps": [{"card": "Solemn Judgment"}], "deck_filler": 10})
    _b4_turn(d, 1)
    out = _go(d, "Special Summon Number 15")
    out += d.play([[0, 1]])
    if negate:
        out += _go(d, "Activate Solemn Judgment")
    out += _until(d, lambda d: d.decision.kind == "idle")
    if not negate:
        out += _go(d, "Activate Dark Hole")
        out += _until(d, lambda d: d.decision.kind == "idle")
    return out


def test_shadow_feeler_goes_to_the_gy_when_the_xyz_summon_is_negated():
    # FAQ 10042
    out = _shadow_feeler(True)
    assert "Gimmick Puppet Shadow Feeler: P1 Xyz Material → P1 GY" in out, out


def test_shadow_feeler_is_banished_when_its_xyz_monster_leaves_the_field():
    out = _shadow_feeler(False)
    assert "Gimmick Puppet Shadow Feeler: P1 Xyz Material → P1 banished" in out, out


# ---------------------------------------------------------------- the thirteenth 100 official Q&As
def test_shining_elf_activates_for_lava_golem_the_opponent_summons_to_your_field():
    # FAQ 11508
    d = start({"monsters": [{"card": "Shining Elf", "zone": 1, "materials": ["Flelf", "Flelf"]},
                            {"card": "Mystical Shine Ball", "zone": 2}, {"card": "Mystical Shine Ball", "zone": 3}], "deck_filler": 10},
              {"hand": ["Lava Golem"], "deck_filler": 10})
    _b4_turn(d, 2)
    out = _go(d, "Special Summon Lava Golem")
    out += d.play([[1, 1], 0])
    out += _until(d, lambda d: d.decision.kind == "idle" or "Shining Elf" in d.describe_decision())
    assert "Lava Golem is Special Summoned to P1 Monster Zone" in out, out
    assert "Shining Elf" in d.describe_decision(), d.describe_decision()


def test_triple_star_trion_does_not_activate_after_its_tribute_summon_is_negated():
    # FAQ 11514
    d = start({"hand": ["Dark Ruler Ha Des"], "monsters": [{"card": "Triple Star Trion", "zone": 1}], "deck_filler": 10},
              {"spells_traps": [{"card": "Solemn Judgment"}], "deck_filler": 10})
    _b4_turn(d, 1)
    out = _go(d, "Normal Summon Dark Ruler Ha Des")
    out += d.play([0, 0])
    out += _go(d, "Activate Solemn Judgment")
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "Dark Ruler Ha Des" in out and "Resolving Chain Link 1 (Solemn Judgment)" in out, out
    out = d.play(["End the turn"])
    out += _until(d, lambda d: d.turn >= 2 or "Triple Star Trion" in d.describe_decision())
    assert "Triple Star Trion" not in d.describe_decision() and "activates Triple Star Trion" not in out, out + d.describe_decision()


def test_fiends_hand_mirror_can_move_the_target_to_a_monster():
    # FAQ 11296
    d = start({"monsters": [{"card": "Sangan", "zone": 1, "summoned": "normal"}],
               "spells_traps": [{"card": "Fiend's Hand Mirror"}, {"card": "Mystical Space Typhoon"}, {"card": "Dark Hole"}], "deck_filler": 10},
              {"hand": ["Gemini Spark"], "monsters": [{"card": "Elemental HERO Neos Alius", "zone": 1, "summoned": "normal"}], "deck_filler": 10})
    _b4_turn(d, 2)
    _go(d, "Activate Gemini Spark")
    _until(d, lambda d: any("Mystical Space Typhoon" in o.label for o in d.decision.options) and "destroy" in d.describe_decision())
    d.play([next(o.label for o in d.decision.options if "Mystical Space Typhoon" in o.label)])
    _go(d, "Activate Fiend's Hand Mirror")
    assert any(o.label.startswith("Sangan") for o in d.decision.options), d.describe_decision()


# ---------------------------------------------------------------- the fourteenth 100 official Q&As
def test_forbidden_lance_lets_the_opponent_negate_a_machine_under_magnet_force():
    # FAQ 11947: unaffected by Spells, the monster no longer gets "Magnet Force"'s protection
    d = start({"hand": ["Forbidden Lance", "Mystical Shine Ball"], "monsters": [{"card": "Machine King", "zone": 1}],
               "spells_traps": [{"card": "Magnet Force"}], "deck_filler": 10}, {"hand": ["Effect Veiler"], "deck_filler": 10})
    _b4_turn(d, 1)
    _go(d, "Activate Magnet Force")
    _until(d, lambda d: d.decision.kind == "idle")
    _go(d, "Activate Forbidden Lance")
    _until(d, lambda d: d.decision.kind == "idle")
    _go(d, "Normal Summon Mystical Shine Ball")
    out = _until(d, lambda d: any(o.label.startswith("Activate Effect Veiler") for o in d.decision.options))
    d.play(["Activate Effect Veiler"])
    _until(d, lambda d: d.decision.kind == "idle")
    assert re.search(r"Machine King, face-up \w+, ATK \d+/DEF \d+ \([^)]*\), effects negated", d.board()), d.board()


def test_magnet_force_alone_keeps_a_machine_from_being_negated():
    d = start({"hand": ["Mystical Shine Ball"], "monsters": [{"card": "Machine King", "zone": 1}],
               "spells_traps": [{"card": "Magnet Force"}], "deck_filler": 10}, {"hand": ["Effect Veiler"], "deck_filler": 10})
    _b4_turn(d, 1)
    _go(d, "Activate Magnet Force")
    _until(d, lambda d: d.decision.kind == "idle")
    _go(d, "Normal Summon Mystical Shine Ball")
    _until(d, lambda d: d.decision.kind == "idle" or any(o.label.startswith("Activate Effect Veiler") for o in d.decision.options))
    assert "effects negated" not in d.board(), d.board()


def test_fencing_fire_ferret_does_nothing_if_its_target_was_turned_face_down():
    # FAQ 12668
    d = start({"monsters": [{"card": "Fencing Fire Ferret", "zone": 1, "summoned": "normal"}], "deck_filler": 10},
              {"hand": ["Lightning Vortex", "Mystical Shine Ball"], "monsters": [{"card": "Fire King Avatar Barong", "zone": 1, "summoned": "normal"}],
               "spells_traps": [{"card": "Book of Eclipse"}], "deck_filler": 10})
    _b4_turn(d, 2)
    out = _go(d, "Activate Lightning Vortex")
    out += _until(d, lambda d: any(o.label.startswith("Activate Book of Eclipse") for o in d.decision.options)
                  and "Fencing Fire Ferret" in d.describe_decision(), limit=20)
    out += d.play(["Activate Book of Eclipse"])
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "activates Fencing Fire Ferret" in out, out
    assert "Fire King Avatar Barong: P2 Monster Zone 1 → P2 GY" not in out and "P2 takes 500 damage" not in out, out


# ---------------------------------------------------------------- the 15th-18th 100 official Q&As
def _run(p1, p2, goals, seed=1):
    """play like scratchpad go.py: "@N" = until Main Phase 1 of turn N, "#i" = option i, [..] = list, other = option label prefix
    (passing / ending the turn until it appears). Returns (duel, log)."""
    d = start(p1, p2, seed=seed)
    out = ""
    for g in goals:
        if isinstance(g, list):
            out += d.play([g])
        elif g.startswith("@"):
            _b4_turn(d, int(g[1:]))
        elif g.startswith("#"):
            out += d.play([int(g[1:])])
        else:
            out += _until(d, lambda d: any(o.label.startswith(g) for o in d.decision.options), limit=40)
            out += d.play([next(o.label for o in d.decision.options if o.label.startswith(g))])
    return d, out


def _offered(d, label):
    return any(o.label.startswith(label) for o in d.decision.options)


def test_megingjord_cannot_target_a_monster_that_declared_a_direct_attack():
    # FAQ 13807
    d, out = _run({"monsters": [{"card": "Dverg of the Nordic Alfar", "zone": 1}], "spells_traps": [{"card": "Nordic Relic Megingjord"}],
                   "deck_filler": 10}, {"deck_filler": 10}, ["@3", "Enter the Battle Phase", "Attack with Dverg"])
    out += _until(d, lambda d: "Battle Phase: choose" in d.describe_decision() or _offered(d, "Activate Nordic Relic Megingjord"))
    assert "attacks directly" in out and not _offered(d, "Activate Nordic Relic Megingjord"), out + d.describe_decision()


def test_naturia_pineapple_resolves_even_if_a_non_plant_reaches_the_gy():
    # FAQ 13822
    d, out = _run({"monsters": [{"card": "Dark Magician", "zone": 1}], "graveyard": ["Naturia Pineapple"], "deck_filler": 10},
                  {"spells_traps": [{"card": "Ring of Destruction"}], "deck_filler": 10}, ["Yes", "Activate Ring of Destruction", "#0"])
    out += _until(d, lambda d: d.decision.kind == "idle" or "battle position of Naturia Pineapple" in d.describe_decision())
    assert "Dark Magician: P1 Monster Zone 1 → P1 GY" in out, out
    assert "battle position of Naturia Pineapple" in d.describe_decision() or "Naturia Pineapple is Special Summoned" in out, out


def test_greed_grado_counts_a_face_down_synchro_flipped_by_the_attack():
    # FAQ 13826
    d, out = _run({"monsters": [{"card": "Dark Magician", "zone": 1}], "spells_traps": [{"card": "Greed Grado"}], "deck_filler": 10},
                  {"monsters": [{"card": "Junk Warrior", "zone": 1, "position": "set", "summoned": "synchro"}],
                   "deck_filler": 10}, ["@3", "Enter the Battle Phase", "Attack with Dark Magician", "#0"])
    out += _until(d, lambda d: _offered(d, "Activate Greed Grado") or d.decision.kind == "idle")
    assert "Junk Warrior: P2 Monster Zone 1 → P2 GY — destroyed by battle" in out and _offered(d, "Activate Greed Grado"), out


def test_smashing_horn_cannot_answer_horn_of_heaven_on_a_flip_summon():
    # FAQ 13882
    d, out = _run({"monsters": [{"card": "Mystical Shine Ball", "zone": 1, "position": "set"}], "spells_traps": [{"card": "Smashing Horn"}],
                   "deck_filler": 10}, {"monsters": [{"card": "Dark Magician", "zone": 1}], "spells_traps": [{"card": "Horn of Heaven"}], "deck_filler": 10},
                  ["@3", "Change the battle position of Mystical Shine Ball", "Activate Horn of Heaven", "#0"])
    assert not _offered(d, "Activate Smashing Horn"), out + d.describe_decision()


def test_barrel_behind_the_door_can_answer_d_boyz():
    # FAQ 14022
    d, out = _run({"monsters": [{"card": "D-Boyz", "zone": 1, "position": "set", "summoned": "normal"}], "spells_traps": [{"card": "Barrel Behind the Door"}],
                   "deck": ["D-Boyz", "D-Boyz"], "deck_filler": 10}, {"deck_filler": 10}, ["#0", "#0"])
    assert _offered(d, "Activate Barrel Behind the Door"), out + d.describe_decision()


def test_bujingi_pavo_needs_a_beast_warrior_on_the_field():
    # FAQ 13684: a "Bujin" made Winged Beast by "DNA Surgery" does not count; a normal one does
    for dna in (True, False):
        p1 = {"hand": ["Bujingi Pavo"], "monsters": [{"card": "Bujin Yamato", "zone": 1}], "deck": ["Mystical Shine Ball", "Bujin Mikazuchi"],
              "spells_traps": [{"card": "DNA Surgery"}] if dna else [], "deck_filler": 10}
        goals = (["Activate DNA Surgery", "Winged Beast"] if dna else []) + ["End the turn", "No", "Enter the Battle Phase", "Attack with Dark Magician", "#0"]
        d, out = _run(p1, {"monsters": [{"card": "Dark Magician", "zone": 1}], "deck_filler": 10}, goals)
        out += _until(d, lambda d: _offered(d, "Activate Bujingi Pavo") or "Battle Phase: choose" in d.describe_decision())
        assert "Bujin Yamato: P1 Monster Zone 1 → P1 GY — destroyed by battle" in out, out
        assert _offered(d, "Activate Bujingi Pavo") == (not dna), (dna, out + d.describe_decision())


def test_synchron_carrier_needs_a_synchron_on_the_field_and_in_the_gy():
    # FAQ 14519
    d, out = _run({"hand": ["Hero Mask"], "monsters": [{"card": "Synchron Carrier", "zone": 1}, {"card": "Junk Synchron", "zone": 2}, {"card": "Kuriboh", "zone": 3}],
                   "extra_deck": ["Armory Arm"], "deck": ["Elemental HERO Avian"], "deck_filler": 5}, {"deck_filler": 10},
                  ["Activate Hero Mask", "#0", "#1", "Special Summon Armory Arm", "#0", "#0", "#0", "#0"])
    assert "Synchron Carrier" not in d.describe_decision().split("Decision for")[-1].split("\n")[0], out + d.describe_decision()
    d, out = _run({"monsters": [{"card": "Synchron Carrier", "zone": 1}, {"card": "Junk Synchron", "zone": 2}, {"card": "Synchron Explorer", "zone": 3}],
                   "extra_deck": ["Junk Warrior"], "deck_filler": 10}, {"deck_filler": 10},
                  ["Special Summon Junk Warrior", "Select Junk Synchron", "Select Synchron Explorer", "#0", "#0"])
    assert _offered(d, "Activate Synchron Carrier"), out + d.describe_decision()


def test_bedwyr_cannot_move_gwenhwyfar_equipped_as_a_monster():
    # FAQ 14611
    d, out = _run({"hand": ["Gwenhwyfar, Queen of Noble Arms"], "monsters": [{"card": "Noble Knight Bedwyr", "zone": 1},
                   {"card": "Noble Knight Artorigus", "zone": 2}, {"card": "Noble Knight Gawayn", "zone": 3}], "deck_filler": 10}, {"deck_filler": 10},
                  ["Activate Gwenhwyfar", "Noble Knight Artorigus"])
    _until(d, lambda d: d.decision.kind == "idle")
    assert not _offered(d, "Activate Noble Knight Bedwyr"), d.describe_decision()


def test_diceversity_rolls_a_die():
    # FAQ 14942: the flag it checked was never set, so it did nothing
    d, out = _run({"monsters": [{"card": "Cyber Dragon", "zone": 2}], "spells_traps": [{"card": "Level Retuner"}, {"card": "Diceversity"}],
                   "deck_filler": 10}, {"deck_filler": 10},
                  ["@1", "Activate Level Retuner", "Pass", "Reduce Level by 1", "Activate Diceversity", "#0"])
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "Resolving Chain Link 1 (Diceversity)" in out and out.split("Resolving Chain Link 1 (Diceversity)")[-1].count("Die roll for P1") == 1, out


def test_gigagloves_cannot_be_activated_against_a_0_atk_attacker():
    # FAQ 14884
    d, out = _run({"graveyard": ["Superheavy Samurai Gigagloves"], "deck": ["Superheavy Samurai Soulpiercer"], "deck_filler": 10},
                  {"monsters": [{"card": "Yosenju Kodam", "zone": 1}], "deck_filler": 10}, ["End the turn", "Enter the Battle Phase", "Attack with"])
    assert "Gigagloves" not in d.describe_decision(), out + d.describe_decision()


def test_aroma_garden_activates_twice_for_destructions_in_two_chain_links():
    # FAQ 15544 (15545: once for a simultaneous destruction)
    d, out = _run({"monsters": [{"card": "Aromage Rosemary", "zone": 1, "summoned": "normal"}, {"card": "Aromage Cananga", "zone": 2, "summoned": "normal"}],
                   "field_spell": {"card": "Aroma Garden"}, "deck_filler": 10},
                  {"hand": ["Dark Hole", "Dark Hole"], "spells_traps": [{"card": "Raigeki Break"}, {"card": "Raigeki Break"}], "deck_filler": 10},
                  ["#0", "#0", "#0", "#0", "#1"])
    assert sum(o.label.startswith("Activate Aroma Garden") for o in d.decision.options) == 2, out + d.describe_decision()


def test_fluffal_crane_needs_a_fluffal_on_the_field():
    # FAQ 15270: "Fluffal Bear" renamed by "Hero Mask"
    d, out = _run({"hand": ["Hero Mask"], "monsters": [{"card": "Fluffal Bear", "zone": 1}], "spells_traps": [{"card": "Fluffal Crane"}],
                   "deck": ["Elemental HERO Neos"], "deck_filler": 10},
                  {"hand": ["Mystical Elf"], "spells_traps": [{"card": "Raigeki Break"}], "deck_filler": 10},
                  ["Activate Hero Mask", "#0", "#1", "Activate Raigeki Break", "#0"])
    out += _until(d, lambda d: d.decision.kind == "idle" or _offered(d, "Activate Fluffal Crane"))
    assert "Fluffal Bear: P1 Monster Zone 1 → P1 GY" in out and not _offered(d, "Activate Fluffal Crane"), out + d.describe_decision()


def test_damage_juggler_cannot_be_activated_in_the_end_step():
    # FAQ 15396
    d, out = _run({"hand": ["Performage Damage Juggler"], "monsters": [{"card": "Odd-Eyes Saber Dragon", "zone": 1}], "deck_filler": 10},
                  {"monsters": [{"card": "Odd-Eyes Pendulum Dragon", "zone": 1}], "deck_filler": 10},
                  ["End the turn", "End the turn", "Enter the Battle Phase", "Pass", "Go to Main Phase 2"])
    assert not _offered(d, "Activate Performage Damage Juggler"), out + d.describe_decision()


def test_chaofeng_does_not_activate_for_a_face_down_monster_returned_to_the_deck():
    # FAQ 15142
    d, out = _run({"monsters": [{"card": "Chaofeng, Phantom of the Yang Zing", "zone": 1, "summoned": "synchro", "properly_summoned": True},
                   {"card": "Mystic Swordsman LV6", "zone": 2, "summoned": "special", "properly_summoned": True}],
                   "deck": ["Mystical Shine Ball", "Bixi, Water of the Yang Zing"], "deck_filler": 8},
                  {"monsters": [{"card": "Performapal Skeeter Skimmer", "zone": 1, "position": "set"}], "deck_filler": 8},
                  ["@3", "Enter the Battle Phase", "Attack with Mystic", "#0", "#0"])
    assert "Performapal Skeeter Skimmer: P2 Monster Zone 1 → P2 Deck" in out, out
    assert "Chaofeng" not in d.describe_decision().split("\n")[0] and "activate/use the effect of Chaofeng" not in d.describe_decision(), out


def test_yosen_whirlwind_needs_a_yosenju_on_the_field():
    # FAQ 15214
    d, out = _run({"hand": ["Hero Mask"], "monsters": [{"card": "Yosenju Kama 1", "zone": 1}],
                   "spells_traps": [{"card": "Yosen Whirlwind", "face_up": True}, {"card": "Compulsory Evacuation Device"}],
                   "deck": ["Elemental HERO Stratos"], "deck_filler": 10},
                  {"hand": ["Mystical Shine Ball"], "monsters": [{"card": "Performapal Stamp Turtle", "zone": 1}], "deck_filler": 10},
                  ["Activate Hero Mask", "#0", "Pass", "#0", "#0"])
    assert "Yosenju Kama 1: P1 Monster Zone 1 → P1 hand" in out and "Yosen Whirlwind" not in d.describe_decision(), out + d.describe_decision()


# ---------------------------------------------------------------- the 19th-22nd 100 official Q&As
def test_trick_box_needs_a_performage_destroyed_under_that_name():
    # FAQ 15732: "Performage Hat Tricker" renamed by "Hero Mask" is not a "Performage" when destroyed
    d, out = _run({"hand": ["Hero Mask", "Mystical Shine Ball"], "monsters": [{"card": "Performage Hat Tricker", "zone": 1}],
                   "spells_traps": [{"card": "Trick Box"}, {"card": "Raigeki Break"}], "deck": ["Elemental HERO Sparkman"], "deck_filler": 10},
                  {"monsters": [{"card": "Mystical Shine Ball", "zone": 1}], "deck_filler": 10},
                  ["@1", "Activate Hero Mask", "#0", "#1", "Activate Raigeki Break", "#0"])
    out += _until(d, lambda d: d.decision.kind == "idle" or _offered(d, "Activate Trick Box"))
    assert "Performage Hat Tricker: P1 Monster Zone 1 → P1 GY — destroyed by an effect" in out, out
    assert not _offered(d, "Activate Trick Box"), out + d.describe_decision()


def test_graydle_split_equips_a_target_the_opponent_took_control_of():
    # FAQ 16622
    d, out = _run({"monsters": [{"card": "Graydle Cobra", "zone": 1}], "spells_traps": [{"card": "Graydle Split"}], "deck_filler": 10},
                  {"monsters": [{"card": "Mystical Shine Ball", "zone": 1}], "spells_traps": [{"card": "Enemy Controller"}], "deck_filler": 10},
                  ["Activate Graydle Split", "Activate Enemy Controller", "#1", "#0", "#0"])
    out += _until(d, lambda d: d.decision.kind == "idle" or "P1: choose a zone" in d.describe_decision())
    assert "Graydle Split (P1 Spell & Trap Zone 1) is equipped to Graydle Cobra (P2 Monster Zone 1)" in out, out


def test_alich_cannot_target_a_token_or_a_normal_monster():
    # FAQ 17028
    d, out = _run({"hand": ["Scapegoat"], "monsters": [{"card": "Alich, Malebranche of the Burning Abyss", "zone": 1}], "deck_filler": 10},
                  {"monsters": [{"card": "Blue-Eyes White Dragon", "zone": 1}, {"card": "Dark Magician Girl", "zone": 2}], "deck_filler": 10},
                  ["@1", "Activate Scapegoat", "#0", "#0", "#0", "#0", "#0"])
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert "Targets: Dark Magician Girl (P2 Monster Zone 2)" in out, out + d.describe_decision()


def _dice_roll_battle(vanity):
    d, out = _run({"hand": ["Speedroid CarTurbo"], "graveyard": ["Speedroid Terrortop"], "extra_deck": ["Hi-Speedroid Kendama"],
                   "spells_traps": [{"card": "Dice Roll Battle"}], "deck_filler": 10},
                  {"monsters": [{"card": "Goyo Predator", "zone": 1}], "spells_traps": [{"card": "Vanity's Emptiness"}], "deck_filler": 10},
                  ["@2", "Enter the Battle Phase", "Attack with Goyo", "#1", "Activate Dice Roll Battle", "#0" if vanity else "#1"])
    return d, out + _until(d, lambda d: d.decision.kind == "idle" or "Battle Phase: choose" in d.describe_decision())


def test_dice_roll_battle_still_banishes_under_vanitys_emptiness():
    # FAQ 16727
    d, out = _dice_roll_battle(True)
    assert "Speedroid CarTurbo: P1 hand → P1 banished — by an effect" in out, out
    assert "Speedroid Terrortop: P1 GY → P1 banished — by an effect" in out and "Hi-Speedroid Kendama" not in out.split("Resolving Chain Link 1")[-1], out


def test_dice_roll_battle_synchro_summons_without_vanitys_emptiness():
    d, out = _dice_roll_battle(False)
    assert "Speedroid Terrortop: P1 GY → P1 banished — by an effect" in out and "Hi-Speedroid Kendama is Special Summoned" in out, out


# ---------------------------------------------------------------- Q&As of cards written in the same unconfirmed way (wideW)
def _w_seen(d, name, limit=15):
    """Pass until `name` asks to activate (an "Activate <name>" option or a yes/no prompt for its effect),
    or until the Main Phase / the duel ends. Returns (seen, log)."""
    out = ""
    for _ in range(limit):
        desc = d.describe_decision()
        if "effect of " + name in desc or _offered(d, "Activate " + name):
            return True, out
        if d.decision.kind == "idle" or "The duel is over" in desc:
            return False, out
        labels = [o.label for o in d.decision.options]
        out += d.play([P if P in labels else "End the turn" if "End the turn" in labels else 0])
    return False, out

def _w_turn(d, turn):
    """Pass every window (choosing the first zone or option when asked) until the Main Phase 1 of `turn`."""
    out = ""
    for _ in range(80):
        if d.turn == turn and d.decision.kind == "idle":
            return out
        labels = [o.label for o in d.decision.options]
        out += d.play([P if P in labels else "End the turn" if "End the turn" in labels else 0])
    raise AssertionError(f"turn {turn} never came: {d.describe_decision()}")


def _w_run(p1, p2, goals, seed=1):
    """_run, but "@N" also gets through zone and position choices."""
    d = start(p1, p2, seed=seed)
    out = ""
    for g in goals:
        if isinstance(g, list):
            out += d.play([g])
        elif g.startswith("@"):
            out += _w_turn(d, int(g[1:]))
        elif g.startswith("#"):
            out += d.play([int(g[1:])])
        else:
            out += _until(d, lambda d: any(o.label.startswith(g) for o in d.decision.options), limit=40)
            out += d.play([next(o.label for o in d.decision.options if o.label.startswith(g))])
    return d, out


def test_fragile_armor_sees_the_name_a_monster_had_when_destroyed():
    # FAQ 17616
    d, out = _w_run({'hand': ['The Phantom Knights of Fragile Armor', 'Mystical Shine Ball'], 'monsters': [{'card': 'Phantom of Chaos', 'position': 'attack', 'zone': 1, 'summoned': 'special', 'properly_summoned': True}], 'graveyard': ['The Phantom Knights of Ancient Cloak'], 'deck_filler': 10},
                  {'spells_traps': [{'card': 'Ring of Destruction', 'face_up': False}], 'deck_filler': 10},
                  ['@1', 'Activate Phantom of Chaos', '#1', 'Activate Ring of Destruction', '#0'], seed=1)
    seen, more = _w_seen(d, 'The Phantom Knights of Fragile Armor')
    assert seen or "activates The Phantom Knights of Fragile Armor" in out, out + more + d.describe_decision()


def test_shinobird_salvation_counts_a_monster_that_was_a_spirit_on_the_field():
    # FAQ 20137
    d, out = _w_run({'hand': ['Hebo, Lord of the River', 'Mystical Shine Ball'], 'monsters': [{'card': 'Spiritual Whisper', 'position': 'attack', 'zone': 1}], 'spells_traps': [{'card': 'Shinobird Salvation', 'face_up': True}, {'card': 'Raigeki Break', 'face_up': False}], 'deck_filler': 10},
                  {'monsters': [{'card': 'Battle Ox', 'position': 'attack', 'zone': 1}], 'deck_filler': 10},
                  ['@1', 'Normal Summon Hebo', '#0', 'Yes', '#0', '#1', 'Activate Raigeki Break', '#1', 'End the turn'], seed=1)
    assert "Spiritual Whisper: P1 Monster Zone 1 → P1 hand" in out, out
    seen, more = _w_seen(d, 'Shinobird Salvation')
    assert seen or "activates Shinobird Salvation" in out, out + more + d.describe_decision()


def test_headhunt_negation_ends_when_the_control_returns():
    # FAQ 23499
    d, out = _w_run({'monsters': [{'card': 'D/D/D Flame King Genghis', 'position': 'attack', 'zone': 1}], 'spells_traps': [{'card': 'D/D/D Headhunt', 'face_up': False}], 'deck_filler': 10},
                  {'monsters': [{'card': 'Dark Magician Girl', 'position': 'attack', 'zone': 1}], 'graveyard': ['Dark Magician'], 'deck_filler': 10},
                  ['Activate D/D/D Headhunt'], seed=1)
    _until(d, lambda d: d.decision.kind == "idle")
    out += _w_turn(d, 3)
    assert "Dark Magician Girl, face-up Attack, ATK 2300" in d.board(), d.board()


def test_zexal_alliance_can_be_activated_with_10_lp():
    # FAQ 23448
    d, out = _w_run({'lp': 10, 'monsters': [{'card': 'Number C39: Utopia Ray', 'position': 'attack', 'zone': 1}, {'card': 'Dinomorphia Stealthbergia', 'position': 'attack', 'zone': 2}], 'spells_traps': [{'card': 'Zexal Alliance', 'face_up': False}], 'graveyard': [{'card': 'Number 39: Utopia', 'properly_summoned': True}], 'deck_filler': 10},
                  {'hand': ['Offerings to the Doomed'], 'deck_filler': 10},
                  ['End the turn', 'Activate Offerings to the Doomed', '#0', '#0'], seed=1)
    seen, more = _w_seen(d, 'Zexal Alliance')
    assert seen or "activates Zexal Alliance" in out, out + more + d.describe_decision()


def test_miracle_rupture_needs_two_cards_in_the_deck_with_fossil_fusion():
    # FAQ 23032
    d, out = _w_run({'hand': ['Miracle Rupture'], 'deck': ['Giant Soldier of Stone'], 'graveyard': ['Fossil Fusion'], 'deck_filler': 0},
                  {'deck_filler': 10},
                  ['@1'], seed=1)
    assert not _offered(d, "Activate Miracle Rupture"), d.describe_decision()


def test_miracle_rupture_with_fossil_fusion_and_two_cards():
    # FAQ 23032
    d, out = _w_run({'hand': ['Miracle Rupture'], 'deck': ['Giant Soldier of Stone', 'Mystical Shine Ball'], 'graveyard': ['Fossil Fusion'], 'deck_filler': 0},
                  {'deck_filler': 10},
                  ['@1'], seed=1)
    assert _offered(d, "Activate Miracle Rupture"), d.describe_decision()


def test_malefic_tune_destroyed_with_the_malefic_cannot_search():
    # FAQ 22448
    d, out = _w_run({'monsters': [{'card': 'Malefic Parallel Gear', 'position': 'attack', 'zone': 1}], 'spells_traps': [{'card': 'Malefic Tune', 'face_up': False}], 'field_spell': {'card': 'Malefic World'}, 'deck_filler': 10, 'deck': ['Malefic Blue-Eyes White Dragon']},
                  {'monsters': [{'card': 'Harpie Lady', 'zone': 1}], 'spells_traps': [{'card': 'Icarus Attack', 'face_up': False}], 'deck_filler': 10},
                  ['#0', '#0', [0, 1]], seed=1)
    assert "Malefic Tune: P1 Spell & Trap Zone 1 → P1 GY" in out, out
    seen, more = _w_seen(d, 'Malefic Tune')
    assert not seen and "activates Malefic Tune" not in out + more, out + more + d.describe_decision()


def test_bonding_d2o_sent_with_water_dragon_does_not_return():
    # FAQ 21058
    d, out = _w_run({'monsters': [{'card': 'Water Dragon', 'position': 'attack', 'zone': 1, 'summoned': 'special', 'properly_summoned': True}], 'spells_traps': [{'card': 'Bonding - D2O', 'face_up': False}], 'deck_filler': 10},
                  {'monsters': [{'card': 'Scrap Searcher', 'position': 'attack', 'zone': 1}], 'spells_traps': [{'card': 'Icarus Attack', 'face_up': False}], 'deck_filler': 10},
                  ['#0', '#0', '#0'], seed=1)
    assert "Bonding - D2O: P1 Spell & Trap Zone 1 → P1 GY" in out, out
    seen, more = _w_seen(d, 'Bonding - D2O')
    assert not seen and "activates Bonding - D2O" not in out + more, out + more + d.describe_decision()


def test_red_eyes_fang_with_chain_does_not_change_atk_of_an_unaffected_monster():
    # FAQ 21054
    d, out = _w_run({'monsters': [{'card': 'Red-Eyes Retro Dragon', 'position': 'attack', 'zone': 1}], 'spells_traps': [{'card': 'Red-Eyes Fang with Chain', 'face_up': True, 'equipped_to': 'Red-Eyes Retro Dragon'}], 'deck_filler': 10},
                  {'monsters': [{'card': 'The Legendary Fisherman', 'position': 'attack', 'zone': 1}], 'spells_traps': [{'card': 'Forbidden Lance', 'face_up': False}], 'deck_filler': 10},
                  ['#0', '#0', '#0', '@3'], seed=1)
    assert "Red-Eyes Retro Dragon, face-up Attack, ATK 1700" in d.board(), out + d.board()


def test_titanic_galaxy_does_not_activate_for_an_xyz_returned_to_the_extra_deck():
    # FAQ 17966
    d, out = _w_run({'monsters': [{'card': 'Daigusto Emeral', 'position': 'attack', 'zone': 1, 'materials': ['Battle Ox', 'Battle Ox']}, {'card': 'Number 38: Hope Harbinger Dragon Titanic Galaxy', 'position': 'attack', 'zone': 2, 'materials': ['Battle Ox', 'Battle Ox']}], 'deck_filler': 10},
                  {'monsters': [{'card': 'Evigishki Merrowgeist', 'position': 'attack', 'zone': 1, 'materials': ['Battle Ox', 'Battle Ox']}], 'deck_filler': 10},
                  ['@2', 'Enter the Battle', 'Attack with', '#0', 'No', 'Yes', '#0'], seed=1)
    assert "Daigusto Emeral: P1 Monster Zone 1 → P1 Extra Deck" in out, out
    seen, more = _w_seen(d, 'Number 38: Hope Harbinger Dragon Titanic Galaxy')
    assert not seen and "activates Number 38: Hope Harbinger Dragon Titanic Galaxy" not in out + more, out + more + d.describe_decision()


def test_inferno_reckless_summon_lets_the_opponent_choose_any_face_up_monster():
    # FAQ 19956
    d, out = _w_run({'hand': ['Bujingi Wolf'], 'deck': ['Bujin Mikazuchi'], 'monsters': [{'card': 'Bujin Mikazuchi', 'position': 'attack', 'zone': 1}, {'card': 'Bujingi Wolf', 'position': 'attack', 'zone': 2}], 'deck_filler': 10},
                  {'hand': ['Monster Reborn'], 'deck': ['Card Trooper'], 'graveyard': ['Card Trooper'], 'spells_traps': [{'card': 'Inferno Reckless Summon', 'face_up': False}], 'deck_filler': 10},
                  ['@2', 'Activate Monster Reborn', '#0', '#0', 'Activate Inferno', '#0'], seed=1)
    assert _offered(d, "Bujin Mikazuchi") and _offered(d, "Bujingi Wolf"), out + d.describe_decision()


def test_demiurgia_loses_its_link_material_flag_when_banished_temporarily():
    # FAQ 22383
    d, out = _w_run({'hand': ['Interdimensional Matter Transporter'], 'monsters': [{'card': 'Blue-Eyes White Dragon', 'zone': 1}, {'card': 'Dark Magician', 'zone': 2}, {'card': 'Gaia The Fierce Knight', 'zone': 3}], 'extra_deck': ['World Gears of Theurlogical Demiurgy'], 'deck_filler': 10},
                  {'monsters': [{'card': 'Cyber Jar', 'zone': 1, 'position': 'set'}], 'deck_filler': 10},
                  ['@1', 'Special Summon World Gears', '#0', '#0', '#0', '#0', 'Set Interdimensional', '#0', 'End the turn', 'Activate Interdimensional', '@3'], seed=1)
    assert "World Gears of Theurlogical Demiurgy: P1 banished → P1 Monster Zone" in out, out
    assert not _offered(d, "Activate World Gears"), d.describe_decision()


def test_demiurgia_keeps_its_link_material_flag():
    # FAQ 22383
    d, out = _w_run({'hand': ['Interdimensional Matter Transporter'], 'monsters': [{'card': 'Blue-Eyes White Dragon', 'zone': 1}, {'card': 'Dark Magician', 'zone': 2}, {'card': 'Gaia The Fierce Knight', 'zone': 3}], 'extra_deck': ['World Gears of Theurlogical Demiurgy'], 'deck_filler': 10},
                  {'monsters': [{'card': 'Cyber Jar', 'zone': 1, 'position': 'set'}], 'deck_filler': 10},
                  ['@1', 'Special Summon World Gears', '#0', '#0', '#0', '#0', '@3'], seed=1)
    assert _offered(d, "Activate World Gears"), d.describe_decision()


def test_gagaga_samurai_cannot_target_a_monster_that_cannot_attack():
    # FAQ 23911
    d, out = _w_run({'monsters': [{'card': 'Gagaga Samurai', 'zone': 1, 'materials': ['Gagaga Magician', 'Gagaga Magician']}], 'deck_filler': 10},
                  {'hand': ['Swords of Revealing Light'], 'monsters': [{'card': 'Amabie', 'zone': 1}], 'deck_filler': 10},
                  ['@2', 'Activate Swords', '@3'], seed=1)
    assert not _offered(d, "Activate Gagaga Samurai"), d.describe_decision()


def test_gagaga_samurai_can_target_a_monster_that_can_attack():
    # FAQ 23911
    d, out = _w_run({'monsters': [{'card': 'Gagaga Samurai', 'zone': 1, 'materials': ['Gagaga Magician', 'Gagaga Magician']}], 'deck_filler': 10},
                  {'hand': ['Swords of Revealing Light'], 'monsters': [{'card': 'Amabie', 'zone': 1}], 'deck_filler': 10},
                  ['@3'], seed=1)
    assert _offered(d, "Activate Gagaga Samurai"), d.describe_decision()


def test_grandpa_demetto_needs_an_originally_dark_monster_under_barrier_statue():
    # FAQ 23163
    d, out = _w_run({'monsters': [{'card': 'Grandpa Demetto', 'zone': 1}, {'card': 'Princess Cologne', 'zone': 2, 'materials': ['Ojama Green', 'Ojama Green']}], 'graveyard': ['Ojama Green'], 'deck_filler': 10},
                  {'monsters': [{'card': 'Barrier Statue of the Abyss', 'zone': 1}], 'deck_filler': 10},
                  ['@1'], seed=1)
    assert not _offered(d, "Activate Grandpa Demetto"), d.describe_decision()


def test_grandpa_demetto_without_barrier_statue():
    # FAQ 23163
    d, out = _w_run({'monsters': [{'card': 'Grandpa Demetto', 'zone': 1}, {'card': 'Princess Cologne', 'zone': 2, 'materials': ['Ojama Green', 'Ojama Green']}], 'graveyard': ['Ojama Green'], 'deck_filler': 10},
                  {'deck_filler': 10},
                  ['@1'], seed=1)
    assert _offered(d, "Activate Grandpa Demetto"), d.describe_decision()


def test_mind_control_monster_can_be_tributed_after_it_is_set():
    # FAQ 24100
    d, out = _w_run({'hand': ['Mind Control', 'Book of Moon', 'Patrician of Darkness'], 'deck_filler': 10},
                  {'monsters': [{'card': 'Marshmallon', 'position': 'attack'}], 'deck_filler': 10},
                  ['@1', 'Activate Mind Control', '#0', '#1', '#0', 'Activate Book of Moon', '#0'], seed=1)
    assert _offered(d, "Normal Summon Patrician of Darkness"), out + d.describe_decision()


def test_double_summon_cannot_be_activated_while_you_cannot_normal_summon():
    # FAQ 61
    d, out = _w_run({'hand': ['Lava Golem', 'Double Summon', 'Mystical Shine Ball'], 'monsters': [{'card': 'Floowandereeze & Snowl', 'position': 'attack', 'summoned': 'tribute'}], 'deck_filler': 10},
                  {'monsters': [{'card': 'Marshmallon', 'position': 'attack'}, {'card': 'Moremarshmallon', 'position': 'attack'}], 'deck_filler': 10},
                  ['@1', 'Special Summon Lava Golem', [0, 1], '#0', '#0', '#0', '#0'], seed=1)
    assert "Lava Golem is Special Summoned" in out, out
    assert not _offered(d, "Activate Double Summon") and not _offered(d, "Activate Floowandereeze & Snowl"), d.describe_decision()


def test_mayakashi_metamorphosis_protection_keeps_the_activating_players_opponent():
    # FAQ 22062
    d, out = _w_run({'hand': ['Mystical Shine Ball', 'Creature Swap'], 'spells_traps': [{'card': 'Mayakashi Metamorphosis', 'face_up': False}, {'card': 'Compulsory Evacuation Device', 'face_up': False}], 'graveyard': ['Tsukahagi, the Poisonous Mayakashi'], 'deck_filler': 10},
                  {'monsters': [{'card': 'Marshmallon', 'position': 'attack'}], 'spells_traps': [{'card': 'Compulsory Evacuation Device', 'face_up': False}], 'deck_filler': 10},
                  ['@1', 'Activate Mayakashi Metamorphosis', '#0', '#1', '#1', '#0', '#0', '#1', 'Activate Creature Swap', '#0', '#1', '#1', '#0', '#0', 'Activate Compulsory'], seed=1)
    assert _offered(d, "Tsukahagi, the Poisonous Mayakashi (P2 Monster Zone"), out + d.describe_decision()


def test_tsukahagi_activates_for_a_mayakashi_destroyed_in_the_hand_or_deck():
    # FAQ 22064
    d, out = _w_run({'hand': ['Yasha, the Skeletal Mayakashi'], 'graveyard': ['Tsukahagi, the Poisonous Mayakashi'], 'deck': ['Yasha, the Skeletal Mayakashi', 'Mystical Shine Ball'], 'deck_filler': 10},
                  {'monsters': [{'card': 'Sangan', 'position': 'attack'}], 'spells_traps': [{'card': 'Crush Card Virus', 'face_up': False}], 'deck_filler': 10},
                  ['Activate Crush Card Virus', '#0', '#0'], seed=1)
    seen, more = _w_seen(d, 'Tsukahagi, the Poisonous Mayakashi')
    assert seen or "activates Tsukahagi, the Poisonous Mayakashi" in out, out + more + d.describe_decision()


def test_tsukahagi_destroyed_at_the_same_time_cannot_activate():
    # FAQ 22065
    d, out = _w_run({'hand': ['Mystical Shine Ball'], 'monsters': [{'card': 'Hajun, the Winged Mayakashi', 'position': 'attack'}, {'card': 'Tsukahagi, the Poisonous Mayakashi', 'position': 'attack'}], 'deck_filler': 10},
                  {'spells_traps': [{'card': 'Torrential Tribute', 'face_up': False}], 'deck_filler': 10},
                  ['@1', 'Normal Summon', '#0', 'Activate Torrential'], seed=1)
    assert "Tsukahagi, the Poisonous Mayakashi: P1 Monster Zone" in out, out
    seen, more = _w_seen(d, 'Tsukahagi, the Poisonous Mayakashi')
    assert not seen and "activates Tsukahagi, the Poisonous Mayakashi" not in out + more, out + more + d.describe_decision()


def test_red_eyes_retro_dragon_additional_summon_only_once_per_turn():
    # FAQ 16083
    d, out = _w_run({'hand': ['Red-Eyes Black Dragon', 'Red-Eyes Black Dragon'], 'monsters': [{'card': 'Red-Eyes Retro Dragon', 'zone': 1, 'position': 'attack'}, {'card': 'Red-Eyes Retro Dragon', 'zone': 2, 'position': 'attack'}], 'deck_filler': 10},
                  {'hand': [], 'deck_filler': 10},
                  ['@1', 'Activate Red-Eyes Retro'], seed=1)
    out += _until(d, lambda d: d.decision.kind == "idle")
    assert not _offered(d, "Activate Red-Eyes Retro Dragon"), out + d.describe_decision()


def test_red_eyes_retro_dragon_activates_with_one_free_zone():
    # FAQ 16089
    d, out = _w_run({'hand': ['Red-Eyes Retro Dragon'], 'monsters': [{'card': 'Red-Eyes Wyvern', 'zone': 1, 'position': 'defense'}, {'card': 'Mystical Elf', 'zone': 2}, {'card': 'Mystical Elf', 'zone': 3}, {'card': 'Mystical Elf', 'zone': 4}, {'card': 'Mystical Elf', 'zone': 5}], 'deck_filler': 10},
                  {'hand': ['Shield Crush'], 'deck_filler': 10},
                  ['@2', 'Activate Shield Crush', '#0'], seed=1)
    seen, more = _w_seen(d, 'Red-Eyes Retro Dragon')
    assert seen or "activates Red-Eyes Retro Dragon" in out, out + more + d.describe_decision()


# ---------------------------------------------------------------- Q&As of cards with a trigger effect in the GY (wideX)


def test_destiny_hero_dreamer_is_asked_before_the_opponent_responds():
    # FAQ 13064
    d, out = _w_run({'monsters': [{'card': 'Destiny HERO - Dasher', 'position': 'attack', 'zone': 1}], 'graveyard': ['Destiny HERO - Dreamer'], 'deck_filler': 10},
                    {'monsters': [{'card': 'Beast King Barbaros', 'position': 'attack', 'zone': 1}], 'hand': ['Forbidden Scripture'], 'deck_filler': 10},
                    ['@2', 'Enter the Battle', 'Attack with', '#0'], seed=1)
    assert "effect of Destiny HERO - Dreamer" in d.describe_decision(), out + d.describe_decision()


def test_destiny_hero_dreamer_cannot_be_chained_to_forbidden_scripture():
    # FAQ 13064
    d, out = _w_run({'monsters': [{'card': 'Destiny HERO - Dasher', 'position': 'attack', 'zone': 1}], 'graveyard': ['Destiny HERO - Dreamer'], 'deck_filler': 10},
                    {'monsters': [{'card': 'Beast King Barbaros', 'position': 'attack', 'zone': 1}], 'hand': ['Forbidden Scripture'], 'deck_filler': 10},
                    ['@2', 'Enter the Battle', 'Attack with', '#0', 'No', 'Activate Forbidden Scripture', '#0'], seed=1)
    assert "activates Forbidden Scripture" in out, out
    seen, more = _w_seen(d, 'Destiny HERO - Dreamer')
    assert not seen and "activates Destiny HERO - Dreamer" not in out + more, out + more + d.describe_decision()


def test_cross_debug_cannot_target_a_link_monster_with_0_atk():
    # FAQ 22608
    d, out = _w_run({'monsters': [{'card': 'Link Spider', 'zone': 'EMZ left', 'position': 'attack', 'summoned': 'link', 'properly_summoned': True}], 'graveyard': ['Cross Debug', {'card': 'Salamangreat Almiraj', 'properly_summoned': True}, {'card': 'Link Spider', 'properly_summoned': True}], 'deck_filler': 10},
                    {'monsters': [{'card': 'Link Spider', 'zone': 'EMZ left', 'position': 'attack', 'summoned': 'link', 'properly_summoned': True}], 'deck_filler': 10},
                    ['@3', 'Enter the Battle', 'Attack with Link Spider', '#0', '#0'], seed=1)
    assert "Targets: Link Spider (P1 GY)" in out and not _offered(d, "Salamangreat Almiraj"), out + d.describe_decision()


def test_cyber_emergency_negated_by_the_opponent_returns_for_either_player():
    # FAQ 21900
    d, out = _w_run({'hand': ['Mystical Shine Ball'], 'spells_traps': [{'card': 'Cyber Emergency', 'face_up': False}], 'deck': ['Cyber Dragon'], 'deck_filler': 10},
                    {'monsters': [{'card': 'Light and Darkness Dragon', 'zone': 1, 'summoned': 'normal'}], 'deck_filler': 10},
                    ['@1', 'Activate Cyber Emergency'], seed=1)
    out += _until(d, lambda d: d.decision.kind == "idle" or "effect of Cyber Emergency (P1 GY)" in d.describe_decision())
    assert "effect of Cyber Emergency (P1 GY)" in d.describe_decision(), out + d.describe_decision()


# ---------------------------------------------------------------- core fixes for uniqueness and Pendulum Scales, and Decoy Dragon
def _w_step(d, goals):
    """Play each goal on the current decision without passing: "#i" = option i, "P" = pass, other = option label prefix."""
    out = ""
    for g in goals:
        if g == "P":
            out += d.play([P])
        elif g.startswith("#"):
            out += d.play([int(g[1:])])
        else:
            labels = [o.label for o in d.decision.options]
            hit = next((l for l in labels if l.startswith(g)), None)
            assert hit, out + d.describe_decision() + " -- missing " + g
            out += d.play([hit])
    return out


def test_earthbound_immortals_turned_face_up_together_let_the_player_choose():
    # FAQ 8792
    d, out = _w_run({'hand': ['Swords of Revealing Light'], 'field_spell': {'card': 'Necrovalley'}, 'deck_filler': 10},
                    {'monsters': [{'card': 'Earthbound Immortal Ccapac Apu', 'position': 'set', 'zone': 1, 'summoned': 'tribute'}, {'card': 'Earthbound Immortal Uru', 'position': 'set', 'zone': 2}], 'deck_filler': 10},
                    ['@1', 'Activate Swords', '#0'], seed=1)
    assert "Select the card(s) to keep on the field" in d.describe_decision(), out + d.describe_decision()
    assert _offered(d, "Earthbound Immortal Ccapac Apu") and _offered(d, "Earthbound Immortal Uru"), d.describe_decision()


def test_earthbound_immortal_turned_face_up_after_another_is_destroyed():
    # FAQ 8792
    d, out = _w_run({'hand': ['Swords of Revealing Light'], 'field_spell': {'card': 'Necrovalley'}, 'deck_filler': 10},
                    {'monsters': [{'card': 'Earthbound Immortal Ccapac Apu', 'position': 'attack', 'zone': 1, 'summoned': 'tribute'}, {'card': 'Earthbound Immortal Uru', 'position': 'set', 'zone': 2}], 'deck_filler': 10},
                    ['@1', 'Activate Swords', '#0'], seed=1)
    assert "Earthbound Immortal Uru: P2 Monster Zone 2 → P2 GY — destroyed, by rule" in out, out + d.describe_decision()


def test_stargazer_keeps_the_pendulum_shift_scale_when_its_condition_is_met_later():
    # FAQ 14394
    d, out = _w_run({'hand': ['Pendulum Shift', 'Mystical Space Typhoon', 'Ignis Phoenix, the Dracoslayer', 'Blue-Eyes White Dragon', 'Archfiend of Gilfer'], 'pendulum_zones': ['Stargazer Magician', 'Timegazer Magician'], 'deck_filler': 10},
                    {'deck_filler': 10},
                    ['@1', 'Activate Pendulum Shift', '#0', '#0', '#8', 'Activate Mystical Space Typhoon', '#0', 'Timegazer', 'Activate Ignis Phoenix', '#0'], seed=1)
    assert _offered(d, "Select Blue-Eyes White Dragon"), out + d.describe_decision()


def test_stargazer_scale_becomes_4_without_another_magician():
    # FAQ 14394
    d, out = _w_run({'hand': ['Mystical Space Typhoon', 'Ignis Phoenix, the Dracoslayer', 'Blue-Eyes White Dragon', 'Archfiend of Gilfer'], 'pendulum_zones': ['Stargazer Magician', 'Timegazer Magician'], 'deck_filler': 10},
                    {'deck_filler': 10},
                    ['@1', 'Activate Mystical Space Typhoon', '#0', 'Timegazer', 'Activate Ignis Phoenix', '#0'], seed=1)
    assert _offered(d, "Select Archfiend of Gilfer") and not _offered(d, "Select Blue-Eyes White Dragon"), out + d.describe_decision()


def test_stargazer_keeps_the_dharma_eye_scale_after_dharma_eye_leaves():
    # FAQ 16043
    d = start({'hand': ['Timegazer Magician', 'Performapal Pendulum Sorcerer', 'Mystical Space Typhoon', 'Red-Eyes Black Dragon', 'Dark Magician Girl'], 'pendulum_zones': ['Dharma-Eye Magician', 'Stargazer Magician'], 'deck_filler': 10}, {'hand': [], 'deck_filler': 10})
    out = _w_turn(d, 1)
    out += _w_step(d, ["Activate Dharma-Eye", "#0", "#1", "P", "#0", "#0", "Dharma-Eye", "P", "Activate Performapal Pendulum Sorcerer",
                       "Special Summon Performapal"])
    assert _offered(d, "Select Red-Eyes Black Dragon") and _offered(d, "Select Dark Magician Girl"), out + d.describe_decision()


def test_decoy_dragon_calculates_damage_before_malefic_blue_eyes_destroys_itself():
    # FAQ 9227
    d, out = _w_run({'monsters': [{'card': 'Decoy Dragon', 'position': 'attack', 'zone': 1}], 'graveyard': [{'card': 'Malefic Blue-Eyes White Dragon', 'properly_summoned': True, 'summoned': 'special', 'summoned_from': 'hand'}], 'deck_filler': 10},
                    {'monsters': [{'card': 'Gazelle the King of Mythical Beasts', 'position': 'attack', 'zone': 1}], 'deck_filler': 10},
                    ['@2', 'Enter the Battle', 'Attack', '#0', '#0', '#0'], seed=1)
    after = out.split("Malefic Blue-Eyes White Dragon is Special Summoned")[-1]
    assert "Damage calculation: Gazelle the King of Mythical Beasts" in after, out
    assert after.index("Damage calculation") < after.index("Malefic Blue-Eyes White Dragon: P1 Monster Zone 2 → P1 GY — destroyed by an effect"), out


# ---------------------------------------------------------------- the remaining Q&As ("this turn's" Battle Phase, Labrynth, Gymir, merged chain triggers)


def test_the_unhappy_maiden_also_ends_a_second_battle_phase():
    # FAQ 6059
    d, out = _w_run({'hand': ['Offerings to the Doomed', 'Ages of Stars and Frost'], 'monsters': [{'card': 'Mystical Shine Ball', 'zone': 1}, {'card': 'Battle Ox', 'zone': 2}], 'deck_filler': 10},
                    {'monsters': [{'card': 'The Unhappy Maiden', 'zone': 1, 'position': 'attack'}, {'card': 'Mystical Shine Ball', 'zone': 2, 'position': 'attack'}], 'deck_filler': 10},
                    ['@3', 'Activate Offerings', '#0', '#0', '#0', '#0', 'Enter the Battle', 'Attack with Battle Ox', '#0'], seed=1)
    assert "activates The Unhappy Maiden" in out, out
    assert "Main Phase 2: choose an action" in d.describe_decision(), out + d.describe_decision()


def test_ages_of_stars_and_frost_still_gives_a_second_battle_phase():
    # FAQ 6059
    d, out = _w_run({'hand': ['Offerings to the Doomed', 'Ages of Stars and Frost'], 'monsters': [{'card': 'Mystical Shine Ball', 'zone': 1}, {'card': 'Battle Ox', 'zone': 2}], 'deck_filler': 10},
                    {'monsters': [{'card': 'The Unhappy Maiden', 'zone': 1, 'position': 'attack'}, {'card': 'Mystical Shine Ball', 'zone': 2, 'position': 'attack'}], 'deck_filler': 10},
                    ['@3', 'Activate Offerings', '#0', '#0', '#0', '#0', 'Enter the Battle', 'Go to Main Phase 2'], seed=1)
    assert "Conduct another Battle Phase" in d.describe_decision(), out + d.describe_decision()


def test_labrynth_labyrinth_adds_destruction_after_durendal_replaces_the_effect():
    # FAQ 24185
    d = start({'hand': [], 'field_spell': {'card': 'Labrynth Labyrinth'}, 'spells_traps': [{'card': 'Welcome Labrynth', 'face_up': False}, {'card': 'Mirror Force', 'face_up': False}], 'deck': ['Arianna the Labrynth Servant'], 'deck_filler': 10},
              {'monsters': [{'card': 'Artifact Durendal', 'zone': 1, 'materials': ['Cyber Dragon', 'Cyber Dragon']}], 'deck_filler': 10, 'spells_traps': [{'card': 'Mirror Force', 'face_up': False}]}, seed=1)
    out = _w_turn(d, 1)
    out += _w_step(d, ['Activate Welcome', '#0', '#0'])
    assert "Mirror Force: P2 Spell & Trap Zone 1 → P2 GY — destroyed by an effect" in out, out
    assert "Add the" in d.describe_decision() and "destroy 1 card on the field" in d.describe_decision(), out + d.describe_decision()


def test_gymir_uses_the_name_at_resolution_of_a_card_set_face_down_where_it_activated():
    # FAQ 23907
    d = start({'hand': [], 'monsters': [{'card': 'Icejade Gymir Aegirine', 'zone': 1, 'position': 'attack', 'summoned': 'synchro', 'properly_summoned': True}], 'deck_filler': 10, 'spells_traps': [{'card': 'Book of Moon', 'face_up': False}]},
              {'hand': ['Cyber Dragon Core'], 'spells_traps': [{'card': 'Cyber Dragon Core', 'face_up': True}], 'graveyard': ['Cyber Dragon Core'], 'deck': ['Mystical Shine Ball', 'Cyber Emergency'], 'deck_filler': 10}, seed=1)
    out = _w_turn(d, 2)
    out += _w_step(d, ['Normal Summon Cyber', '#0', 'Activate Icejade', 'Activate Book', '#0', 'Yes'])
    assert "Cyber Dragon Core: P2 Spell & Trap Zone 1 → P2 banished" in out, out
    assert "Cyber Dragon Core: P2 GY → P2 banished" not in out, out


def test_gymir_uses_the_name_at_activation_of_a_card_that_left():
    # FAQ 23907
    d = start({'monsters': [{'card': 'Icejade Gymir Aegirine', 'zone': 1, 'position': 'attack', 'summoned': 'synchro', 'properly_summoned': True}], 'deck_filler': 10},
              {'hand': ['Wightprincess'], 'monsters': [{'card': 'Wightprincess', 'zone': 1}], 'graveyard': ['Wightprincess'], 'deck_filler': 10}, seed=1)
    out = _w_turn(d, 2)
    out += _w_step(d, ['#0', 'Activate Icejade', 'P', 'Yes'])
    assert "Wightprincess: P2 Monster Zone 1 → P2 banished" in out, out
    assert "P2 GY → P2 banished" not in out, out


def test_red_eyes_retro_dragon_summons_monsters_destroyed_in_different_chain_links():
    # FAQ 16090
    d, out = _w_run({'hand': ['Red-Eyes Retro Dragon'], 'monsters': [{'card': 'Red-Eyes Black Dragon', 'zone': 1, 'position': 'attack'}, {'card': 'Red-Eyes Wyvern', 'zone': 2, 'position': 'attack'}], 'deck_filler': 10},
                    {'hand': ['Fissure', 'Mystical Shine Ball'], 'spells_traps': [{'card': 'Raigeki Break', 'face_up': False}], 'deck_filler': 10},
                    ['@2', 'Activate Fissure', '#0', 'Activate Raigeki', '#0', '#1', 'Activate Red-Eyes Retro', '#0', '#0', '#0', '#0', '#0'], seed=1)
    assert "Red-Eyes Black Dragon is Special Summoned" in out and "Red-Eyes Wyvern is Special Summoned" in out, out


def test_titanic_galaxy_activates_once_and_chooses_from_every_destroyed_xyz():
    # FAQ 17974
    d = start({'monsters': [{'card': 'Number 38: Hope Harbinger Dragon Titanic Galaxy', 'position': 'defense', 'materials': ['Blue-Eyes White Dragon', 'Blue-Eyes White Dragon']}, {'card': 'Thunder End Dragon', 'position': 'attack'}, {'card': 'Number 62: Galaxy-Eyes Prime Photon Dragon', 'position': 'attack'}, {'card': 'Galaxy-Eyes Full Armor Photon Dragon', 'position': 'attack'}], 'deck_filler': 10},
              {'monsters': [{'card': 'Marshmallon', 'position': 'attack'}], 'hand': ['Mystical Shine Ball'], 'spells_traps': [{'card': 'Mirror Force', 'face_up': False}, {'card': 'Raigeki Break', 'face_up': False}], 'deck_filler': 10}, seed=1)
    out = _w_turn(d, 3)
    out += _w_step(d, ['Enter the Battle', 'P', 'P', 'Attack with Thunder End', '#0', 'Activate Mirror', 'Activate Raigeki', '#0', '#3', 'P', 'Yes', 'P'])
    for name in ["Number 62: Galaxy-Eyes Prime Photon Dragon", "Thunder End Dragon", "Galaxy-Eyes Full Armor Photon Dragon"]:
        assert _offered(d, name), out + d.describe_decision()


# ---------------------------------------------------------------- "once more" attack effects
def test_dmz_dragon_gives_no_third_attack_to_a_monster_that_already_attacked_twice():
    # FAQ 22561: the equips are destroyed, but Borrelsword Dragon cannot attack a third time
    d, out = _w_run({'monsters': [{'card': 'Borrelsword Dragon', 'zone': 'EMZ left', 'position': 'attack', 'summoned': 'link', 'properly_summoned': True}, {'card': 'DMZ Dragon', 'zone': 2}], 'graveyard': ['DMZ Dragon', 'Anesthrokket Dragon'], 'deck_filler': 10},
                    {'monsters': [{'card': 'Battle Ox', 'zone': 1}, {'card': 'Battle Ox', 'zone': 2}, {'card': 'Battle Ox', 'zone': 3}], 'deck_filler': 10},
                    ['@3', 'Activate DMZ', '#0', '#1', '#1', '#0', 'Activate Borrelsword', '#1', 'Enter the Battle', 'Attack with Borrelsword', '#1', '#1', '#1', '#1', '#0', '#1', '#0'], seed=1)
    assert "Anesthrokket Dragon: P1 Spell & Trap Zone 1 → P1 GY — destroyed by an effect" in out, out
    assert not _offered(d, "Attack with Borrelsword Dragon"), out + d.describe_decision()


# ---------------------------------------------------------------- Q&As of cards whose scripts differ from their peers (wideY)


def test_big_shield_gardna_cannot_negate_after_ceasefire_flipped_it():
    # FAQ 7432
    d, out = _w_run({'monsters': [{'card': 'Big Shield Gardna', 'position': 'set'}], 'deck_filler': 10},
                    {'hand': ['Mind Control'], 'spells_traps': [{'card': 'Ceasefire', 'face_up': False}], 'deck_filler': 10},
                    ['@2', 'Activate Mind Control', '#0', 'Activate Ceasefire'], seed=1)
    out += _until(d, lambda d: d.decision.kind == "idle" or "choose a zone" in d.describe_decision())
    assert "Big Shield Gardna (P1 Monster Zone 1) changes to face-up Defense Position" in out, out
    assert "its activation is negated" not in out and "choose a zone" in d.describe_decision(), out + d.describe_decision()


def test_light_ruler_tosses_the_coin_after_leaving_the_field():
    # FAQ 6882
    d, out = _w_run({'hand': ['Arcana Force EX - The Light Ruler'], 'monsters': [{'card': 'Battle Ox'}, {'card': 'Axe Raider'}, {'card': 'Giant Soldier of Stone'}], 'deck_filler': 10},
                    {'spells_traps': [{'card': 'Compulsory Evacuation Device', 'face_up': False}], 'deck_filler': 10},
                    ['@1', 'Special Summon Arcana', '#0', '#0', '#0', '#0', '#0', 'Activate Compulsory', '#0'], seed=1)
    out += _until(d, lambda d: d.decision.kind == "idle" or d.turn >= 2)
    after = out.split("The Light Ruler: P1 Monster Zone 1 → P1 hand")[-1]
    assert "The Light Ruler: P1 Monster Zone 1 → P1 hand" in out and "Coin toss for P1" in after, out


def test_royal_command_stops_flip_monster_effects_from_being_activated():
    # FAQ 24209
    d = start({'hand': ['Proto Enneacraft - "orgIA"', 'Battle Ox'], 'spells_traps': [{'card': 'Royal Command', 'face_up': False}], 'deck_filler': 10},
              {'deck_filler': 10}, seed=1)
    out = _w_turn(d, 1)
    out += _w_step(d, ['Activate Royal', 'P'])
    assert not _offered(d, 'Activate Proto Enneacraft - "orgIA" (P1 hand): "Special Summon'), d.describe_decision()
    assert _offered(d, 'Activate Proto Enneacraft - "orgIA" (P1 hand): "Activate it as a Pendulum Spell'), d.describe_decision()


def test_flip_monster_effects_can_be_activated_without_royal_command():
    # FAQ 24209
    d = start({'hand': ['Proto Enneacraft - "orgIA"', 'Battle Ox'], 'deck_filler': 10},
              {'deck_filler': 10}, seed=1)
    out = _w_turn(d, 1)
    out += _w_step(d, [])
    assert _offered(d, 'Activate Proto Enneacraft - "orgIA" (P1 hand): "Special Summon'), d.describe_decision()


# ---------------------------------------------------------------- ATK/DEF changes skip a target turned face-down (peer scan of 428 functions)
def test_dragonmaid_tinkhec_does_not_raise_the_atk_of_a_target_turned_face_down():
    # FAQ 19425 and 13844 (same rule): no ATK/DEF change if the target is face-down at resolution
    d = start({"hand": ["Dragonmaid Tinkhec"], "monsters": [{"card": "Laundry Dragonmaid", "position": "attack", "zone": 1, "summoned": "normal"}],
               "deck_filler": 10},
              {"spells_traps": [{"card": "Book of Moon", "face_up": False}], "deck_filler": 10}, seed=1)
    out = d.play(["Activate Dragonmaid Tinkhec", "Activate Book of Moon", "Change the battle"])
    assert "Laundry Dragonmaid (P1 Monster Zone 1) changes to face-down Defense Position" in out, out
    assert "P1 Flip Summons Laundry Dragonmaid" in out, out
    assert "Laundry Dragonmaid, face-up Attack, ATK 500/DEF 1600" in d.board(), d.board()


def test_garbage_collector_does_not_return_a_target_that_was_destroyed():
    # FAQ 20869 (same rule): nothing happens to a target that has left the field
    d = start({"monsters": [{"card": "Garbage Collector", "zone": 1, "summoned": "normal"}, {"card": "Cyberse Gadget", "zone": 2, "summoned": "special"}],
               "deck": ["Cyberse Wizard"], "deck_filler": 10},
              {"spells_traps": [{"card": "Ring of Destruction", "face_up": False}], "deck_filler": 10}, seed=1)
    out = d.play(["Pass (don't respond)", "Pass (don't respond)", "Activate Garbage Collector", "Activate Ring of Destruction", "Cyberse Gadget"])
    assert "Cyberse Gadget: P1 Monster Zone 2 → P1 GY" in out, out
    assert "P1 GY → P1 hand" not in out and "choose a zone" not in d.describe_decision(), out + d.describe_decision()


def test_flying_red_carp_cannot_raise_its_atk_after_damage_calculation():
    # FAQ 157 and the Damage Step rule: ATK/DEF changes only from the start of the Damage Step until before damage calculation
    d = start({"hand": ["Penguin Soldier"], "monsters": [{"card": "Flying Red Carp", "position": "attack", "zone": 1, "summoned": "normal"}],
               "deck_filler": 10},
              {"monsters": [{"card": "Big Shield Gardna", "position": "defense", "zone": 1, "summoned": "normal"}], "deck_filler": 10}, seed=1)
    out = _w_turn(d, 3)
    out += d.play(["Enter the Battle Phase"])
    out += _until(d, lambda d: _offered(d, "Attack with Flying Red Carp"))
    out += d.play(["Attack with Flying Red Carp"])
    before = after = 0
    for _ in range(30):
        if _offered(d, "Go to Main Phase 2"):
            break
        if "Damage calculation:" in out:
            after += _offered(d, "Activate Flying Red Carp")
        else:
            before += _offered(d, "Activate Flying Red Carp")
        labels = [o.label for o in d.decision.options]
        out += d.play([P if P in labels else next(l for l in labels if not l.startswith("Activate"))])
    assert "Damage calculation:" in out, out
    assert before > 0 and after == 0, (before, after, out)


def test_trap_reactor_cannot_respond_to_a_trap_in_the_damage_step():
    # card FAQ of Trap Reactor・RR: it cannot be activated in the Damage Step
    d = start({"monsters": [{"card": "Battle Ox", "zone": 1, "summoned": "normal"}, {"card": "Trap Reactor ・Y FI", "zone": 2, "summoned": "normal"}],
               "deck_filler": 10},
              {"monsters": [{"card": "Mystical Shine Ball", "zone": 1, "summoned": "normal"}],
               "spells_traps": [{"card": "Reinforcements", "face_up": False}], "deck_filler": 10}, seed=1)
    out = _w_turn(d, 3)
    out += d.play(["Enter the Battle Phase"])
    out += _until(d, lambda d: _offered(d, "Attack with Battle Ox"))
    out += d.play(["Attack with Battle Ox"])
    out += _until(d, lambda d: "Damage Step" in d.describe_decision() and _offered(d, "Activate Reinforcements"))
    out += d.play(["Activate Reinforcements", 0])
    assert "Chain Link 1: P2 activates Reinforcements" in out, out
    assert not _offered(d, "Activate Trap Reactor"), d.describe_decision()


# ---------------------------------------------------------------- Q&As of staples and cards users asked about (wideW)
def test_great_gallant_bandit_counts_a_double_tribute_monster_from_the_hand_as_two():
    # FAQ 24367
    d = start({"hand": ["The Great Gallant Bandit", "Gaia the Fierce Knight Origin"], "deck_filler": 10}, {"deck_filler": 10}, seed=1)
    out = _w_turn(d, 1)
    out += d.play(["Normal Summon The Great Gallant Bandit"])
    assert "Gaia the Fierce Knight Origin (P1 hand) [2]" in d.describe_decision(), d.describe_decision()
    out += d.play([0])
    assert "Gaia the Fierce Knight Origin: P1 hand → P1 GY — Tributed" in out, out


def test_quick_summon_can_fetch_a_monster_that_tribute_summons_itself_from_the_hand_and_the_opponents_field():
    # FAQ 24374 (B)
    d = start({"hand": ["Battle Ox"], "graveyard": ["Quick Summon"], "deck": ["The Great Gallant Bandit"], "deck_filler": 10},
              {"monsters": [{"card": "Axe Raider", "zone": 1, "summoned": "normal"}], "deck_filler": 10}, seed=1)
    out = _w_turn(d, 1)
    out += d.play(["Activate Quick Summon (P1 GY)"])
    out += _until(d, lambda d: "Tribute" in d.describe_decision())
    assert "The Great Gallant Bandit: P1 Deck → P1 hand" in out and "Axe Raider (P2 Monster Zone 1)" in d.describe_decision(), out


def test_an_effect_negated_by_forbidden_chalice_stays_negated_after_book_of_moon():
    # FAQ 24426
    d = start({"spells_traps": [{"card": "The Sun God's Protector - Egyptian God Slime", "face_up": False}], "deck": ["Sun God Unification"],
               "deck_filler": 10},
              {"spells_traps": [{"card": "Book of Moon", "face_up": False}, {"card": "Forbidden Chalice", "face_up": False}], "deck_filler": 10}, seed=1)
    out = d.play([0, 0, 0, 0, 0, 0])
    assert "Resolving Chain Link 2 (Book of Moon)" in out, out
    assert "Chain Link 1 (The Sun God's Protector - Egyptian God Slime): its effect is negated" in out, out
    assert "Sun God Unification: P1 Deck → P1 hand" not in out, out


def _utopia_attacks(dice):
    d = start({"monsters": [{"card": "Number S39: Utopia the Lightning", "zone": 1, "materials": ["Mystical Shine Ball"] * 3}], "deck_filler": 10},
              {"graveyard": ["Speedroid Tri-Eyed Dice"] if dice else [], "spells_traps": [{"card": "Mirror Force", "face_up": False}],
               "deck_filler": 10}, seed=1)
    out = _w_turn(d, 3)
    out += d.play(["Enter the Battle Phase"])
    for _ in range(10):
        if _offered(d, "Attack with Number S39"):
            break
        labels = [o.label for o in d.decision.options]
        pick = next((l for l in labels if l.startswith(("Activate Speedroid", "Enter the Battle Phase"))), P if P in labels else 0)
        out += d.play([pick])
    out += d.play(["Attack with Number S39"])
    for _ in range(10):
        if _offered(d, "Activate Mirror Force") or d.decision.kind == "idle" or _offered(d, "Go to Main Phase 2"):
            break
        labels = [o.label for o in d.decision.options]
        out += d.play([P if P in labels else 0])
    return d, out


def test_utopia_the_lightning_stops_locking_activations_once_its_attack_is_negated():
    # FAQ 23595
    d, out = _utopia_attacks(dice=True)
    assert "(Speedroid Tri-Eyed Dice's effect applies)" in out and _offered(d, "Activate Mirror Force"), out + d.describe_decision()
    d, out = _utopia_attacks(dice=False)
    assert not _offered(d, "Activate Mirror Force"), out + d.describe_decision()
