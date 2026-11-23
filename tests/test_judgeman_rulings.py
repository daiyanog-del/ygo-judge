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
