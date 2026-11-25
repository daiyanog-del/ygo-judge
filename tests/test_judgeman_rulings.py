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
