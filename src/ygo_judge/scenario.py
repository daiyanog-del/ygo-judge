"""Board setups: the structured scenario the agent writes, turned into an EDOPro puzzle script.

The same Lua runs in the headless engine and opens in EDOPro's Puzzle mode, where one person
controls both players (no DUEL_SIMPLE_AI) and the duel goes on past the first turn (no
aux.BeginPuzzle).
"""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .cards import (
    EXTRA_DECK_TYPES,
    TYPE_FUSION,
    TYPE_LINK,
    TYPE_MONSTER,
    TYPE_PENDULUM,
    TYPE_RITUAL,
    TYPE_SPSUMMON,
    TYPE_SYNCHRO,
    TYPE_TRAP,
    TYPE_XYZ,
    Card,
    CardDB,
    normalize,
)

CardRef = str | int

SUMMON_TYPES = {
    "normal": "SUMMON_TYPE_NORMAL",
    "tribute": "SUMMON_TYPE_TRIBUTE",
    "flip": "SUMMON_TYPE_FLIP",
    "special": "SUMMON_TYPE_SPECIAL",
    "fusion": "SUMMON_TYPE_FUSION",
    "ritual": "SUMMON_TYPE_RITUAL",
    "synchro": "SUMMON_TYPE_SYNCHRO",
    "xyz": "SUMMON_TYPE_XYZ",
    "pendulum": "SUMMON_TYPE_PENDULUM",
    "link": "SUMMON_TYPE_LINK",
}
SUMMON_FROM = {
    "hand": "LOCATION_HAND",
    "deck": "LOCATION_DECK",
    "extra deck": "LOCATION_EXTRA",
    "graveyard": "LOCATION_GRAVE",
    "banished": "LOCATION_REMOVED",
}
POSITIONS = {"attack": "POS_FACEUP_ATTACK", "defense": "POS_FACEUP_DEFENSE", "set": "POS_FACEDOWN_DEFENSE"}


class ScenarioModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StoredCard(ScenarioModel):
    card: CardRef
    properly_summoned: bool | None = Field(
        None, description="Whether its required summon procedure was completed before it left the field. Required for revival-restricted monsters."
    )
    summoned: Literal[tuple(SUMMON_TYPES)] | None = Field(None, description="Previous summon type, if relevant to the question.")
    summoned_from: Literal[tuple(SUMMON_FROM)] | None = None


class Monster(ScenarioModel):
    card: CardRef = Field(description="Card name or passcode.")
    zone: int | Literal["EMZ left", "EMZ right"] | None = Field(
        None,
        description="Main Monster Zone 1-5 (left to right as its controller sees it) or an Extra Monster Zone. Default: next free zone.",
    )
    position: Literal["attack", "defense", "set"] = Field("attack", description='"set" = face-down Defense Position.')
    summoned: Literal[tuple(SUMMON_TYPES)] | None = Field(
        None, description="How it was summoned. Default: its Extra Deck summon type for Extra Deck monsters, otherwise Normal Summon (Special Summon for Special Summon-only monsters)."
    )
    summoned_from: Literal[tuple(SUMMON_FROM)] | None = Field(
        None, description='Where it was summoned from. Default: "extra deck" for Extra Deck monsters, otherwise "hand".'
    )
    properly_summoned: bool | None = Field(
        None, description="Whether its required summon procedure was completed. Inferred for the natural Fusion/Ritual/Synchro/Xyz/Link summon; otherwise specify it for revival-restricted monsters."
    )
    materials: list[CardRef] = Field(default_factory=list, description="Xyz Materials attached to it.")
    counters: dict[str, int] = Field(default_factory=dict, description='Counters on it, e.g. {"Spell Counter": 2}; a counter only one card uses goes by the name of that card.')


class SpellTrap(ScenarioModel):
    card: CardRef = Field(description="Card name or passcode.")
    zone: int | None = Field(None, description="Spell & Trap Zone 1-5. Default: next free zone.")
    face_up: bool = Field(False, description="false = Set (face-down). Set cards can be activated right away.")
    equipped_to: str | None = Field(
        None, description='The monster it is equipped to: a card name on the field, prefixed with "p1:" or "p2:" if needed.'
    )
    targets: list[str] = Field(
        default_factory=list, description="Cards it continuously targets (e.g. Call of the Haunted's monster), same format as equipped_to."
    )
    counters: dict[str, int] = Field(default_factory=dict)


class FieldSpell(ScenarioModel):
    card: CardRef
    face_up: bool = True
    counters: dict[str, int] = Field(default_factory=dict)


class PlayerSetup(ScenarioModel):
    lp: int = Field(8000, ge=1, le=0x7FFFFFFF)
    hand: list[CardRef] = Field(default_factory=list)
    deck: list[CardRef] = Field(default_factory=list, description="Main Deck, top card first. Empty unless listed.")
    extra_deck: list[CardRef] = Field(default_factory=list)
    graveyard: list[CardRef | StoredCard] = Field(default_factory=list)
    banished: list[CardRef | StoredCard] = Field(default_factory=list, description="Face-up banished cards.")
    banished_facedown: list[CardRef] = Field(default_factory=list, description="Face-down banished cards.")
    extra_deck_faceup: list[CardRef] = Field(default_factory=list, description="Face-up Pendulum Monsters in the Extra Deck.")
    monsters: list[Monster] = Field(default_factory=list)
    spells_traps: list[SpellTrap] = Field(default_factory=list)
    field_spell: FieldSpell | None = None
    pendulum_zones: list[CardRef] = Field(default_factory=list, description="Up to 2 Pendulum Scales: [left, right].")
    deck_filler: int = Field(
        0, ge=0, description="Extra vanilla cards (Mystical Shine Ball) under the listed deck, for effects that draw, mill or need a deck."
    )


class Setup(ScenarioModel):
    """A board to test on. P1 is the turn player: the duel starts on turn 1 and stops at the first legal decision (usually Main Phase 1),
    with no Battle Phase or Main Phase 2 on that turn. Both players are controlled by you.
    For later turns, use choose to end turns: P2 plays turn 2, P1 plays turn 3, and so on."""

    p1: PlayerSetup = Field(default_factory=PlayerSetup)
    p2: PlayerSetup = Field(default_factory=PlayerSetup)
    title: str = Field("", description="Short description of what is being tested.")
    seed: int = Field(1, description="Random seed (shuffles, coin tosses, dice, random selections).")


FILLER = 39552864  # Mystical Shine Ball: vanilla, no archetype


def _lua_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


class _Builder:
    def __init__(self, cards: CardDB):
        self.cards = cards
        self.lines: list[str] = []
        self.placed: list[tuple[int, str, Card]] = []  # (player, variable, card) on the field
        self.zones: dict[str, tuple[str, int]] = {}  # variable -> (location, sequence)
        self.count = 0

    def card(self, ref: CardRef) -> Card:
        return self.cards.resolve(ref)

    def add(self, card: Card, player: int, location: str, seq: int, position: str, proc: bool = False) -> str:
        self.count += 1
        var = f"c{self.count}"
        extra = ",true" if proc else ""
        self.lines.append(f"local {var}=Debug.AddCard({card.code},{player},{player},{location},{seq},{position}{extra}) --{card.name}")
        self.zones[var] = (location, seq)
        return var

    def counters(self, var: str, counters: dict[str, int]) -> None:
        for name, count in counters.items():
            counter = self.cards.counter_by_name.get(normalize(name))
            if counter is None:
                words = set(normalize(name).split()) - {"counter"}
                near = sorted({v for v in self.cards.counters.values() if words & set(normalize(v).split())})[:8]
                raise ValueError(f'Unknown counter "{name}".' + (f" Similar: {', '.join(near)}." if near else ""))
            self.lines.append(f"Debug.PreAddCounter({var},{counter:#x},{count})")

    def placed_at(self, var: str) -> tuple[int, Card]:
        """(controller, card) of a variable from `placed`."""
        return next((p, c) for p, v, c in self.placed if v == var)

    def find(self, ref: str, player: int) -> str:
        """Variable of a card on the field from "name", "p1:name" or "p2:name"."""
        side = None
        if m := re.match(r"\s*p([12])\s*:\s*(.+)", ref, re.IGNORECASE):
            side, ref = int(m[1]) - 1, m[2]
        key = normalize(ref)
        matches = [v for p, v, c in self.placed if normalize(c.name) == key and side in (None, p)]
        if len(matches) != 1:
            where = "on the field" if not matches else "more than once; prefix it with p1: or p2:"
            raise ValueError(f'"{ref}" is {"not " if not matches else ""}{where}.')
        return matches[0]


@dataclass
class StartActivation:
    """A face-up Trap the duel activates when it starts (see build_duel_script)."""

    player: int
    card: Card
    zone: int  # Spell & Trap Zone sequence
    targets: list[tuple[int, int, Card]]  # (controller, Monster Zone sequence, card)


def build_puzzle(setup: Setup, cards: CardDB) -> str:
    """EDOPro puzzle script for a setup; raises ValueError on an invalid setup."""
    return _build(setup, cards, activate=False)[0]


def build_duel_script(setup: Setup, cards: CardDB) -> tuple[str, list[StartActivation]]:
    """The script the engine runs. Unlike the exported puzzle, a face-up Trap whose activation only targets or
    equips to monsters (replays_activation) is Set, and the duel activates it on them when it starts, so the
    effects its activation applies exist (Rare Metalmorph's negation, an Equip Trap's ATK gain...).
    Debug.ResetTurnRecords (patches/ygopro-core) then forgets that activation in this turn's records."""
    return _build(setup, cards, activate=True)


def _build(setup: Setup, cards: CardDB, activate: bool) -> tuple[str, list[StartActivation]]:
    b = _Builder(cards)
    activations: list[StartActivation] = []
    b.lines += [
        f"--YGO Judge scenario{': ' + setup.title.splitlines()[0] if setup.title else ''}",
        "--Both players are yours: play P2's responses too.",
        'Debug.SetAIName("P2")',
        "--Normal first-turn rules: no Battle Phase or Main Phase 2 on turn 1.",
        "Debug.ReloadFieldBegin(0,5)",
        f"Debug.SetPlayerInfo(0,{setup.p1.lp},0,1)",
        f"Debug.SetPlayerInfo(1,{setup.p2.lp},0,1)",
    ]
    links: list[tuple[int, str, SpellTrap, bool]] = []
    emz_owner: dict[str, str] = {}  # the 2 Extra Monster Zones are shared: P1's left is P2's right
    for player, ps in enumerate((setup.p1, setup.p2)):
        tag = f"P{player + 1}"
        b.lines.append(f"--{tag}")
        for _ in range(ps.deck_filler):
            b.add(cards.get(FILLER), player, "LOCATION_DECK", 0, "POS_FACEDOWN")
        for ref in reversed(ps.deck):  # each card added goes on top, so the first listed ends up on top
            card = b.card(ref)
            if card.is_(TYPE_MONSTER) and card.is_(EXTRA_DECK_TYPES):
                raise ValueError(f"{card.name} is an Extra Deck monster; list it in extra_deck.")
            b.add(card, player, "LOCATION_DECK", 0, "POS_FACEDOWN")
        for ref in ps.extra_deck:
            card = b.card(ref)
            if not (card.is_(TYPE_MONSTER) and card.is_(EXTRA_DECK_TYPES)):
                raise ValueError(f"{card.name} is not an Extra Deck monster.")
            b.add(card, player, "LOCATION_EXTRA", 0, "POS_FACEDOWN")
        for ref in ps.extra_deck_faceup:
            card = b.card(ref)
            if not (card.is_(TYPE_MONSTER) and card.is_(TYPE_PENDULUM)):
                raise ValueError(f"{card.name} is not a Pendulum Monster; only those can be face-up in the Extra Deck.")
            b.add(card, player, "LOCATION_EXTRA", 0, "POS_FACEUP")
        for ref in ps.hand:
            card = b.card(ref)
            if card.is_(TYPE_MONSTER) and card.is_(EXTRA_DECK_TYPES):
                raise ValueError(f"{card.name} is an Extra Deck monster and can't be in the hand.")
            b.add(card, player, "LOCATION_HAND", 0, "POS_FACEDOWN")
        for location, entries in (("LOCATION_GRAVE", ps.graveyard), ("LOCATION_REMOVED", ps.banished)):
            for entry in entries:
                history = entry if isinstance(entry, StoredCard) else StoredCard(card=entry)
                card = b.card(history.card)
                if _needs_procedure(card) and history.properly_summoned is None:
                    raise ValueError(f"{card.name}: specify properly_summoned true or false in its GY/banished entry.")
                var = b.add(card, player, location, 0, "POS_FACEUP", proc=bool(history.properly_summoned))
                if history.summoned or history.properly_summoned or history.summoned_from:
                    summoned = history.summoned or _natural_summon(card)
                    source = history.summoned_from or ("extra deck" if card.is_(EXTRA_DECK_TYPES) else "hand")
                    b.lines.append(f"Debug.PreSummon({var},{SUMMON_TYPES[summoned]},{SUMMON_FROM[source]})")

        for ref in ps.banished_facedown:
            b.add(b.card(ref), player, "LOCATION_REMOVED", 0, "POS_FACEDOWN")

        used = set()
        for m in ps.monsters:
            card = b.card(m.card)
            if not card.is_(TYPE_MONSTER):
                raise ValueError(f"{card.name} is not a monster; put it in spells_traps.")
            if m.zone in ("EMZ left", "EMZ right"):
                seq = 5 if m.zone == "EMZ left" else 6
                # JudgemanAI 2026-11-23: two monsters in one shared Extra Monster Zone crashed the engine
                slot = m.zone if player == 0 else ("EMZ right" if m.zone == "EMZ left" else "EMZ left")
                if slot in emz_owner and emz_owner[slot] != tag:
                    raise ValueError(f"{tag}'s {m.zone} is {emz_owner[slot]}'s {slot}, already used by {emz_owner[slot]}: "
                                     "the 2 Extra Monster Zones are shared (P1's left is P2's right). Use the other one.")
                emz_owner[slot] = tag
            elif m.zone is None:
                seq = next((s for s in range(5) if s not in used), None)
                if seq is None:
                    raise ValueError(f"{tag} has no free Main Monster Zone for {card.name}.")
            elif 1 <= m.zone <= 5:
                seq = m.zone - 1
            else:
                raise ValueError(f"Monster zone {m.zone} doesn't exist; use 1-5, 'EMZ left' or 'EMZ right'.")
            if seq in used:
                raise ValueError(f"{tag} Monster Zone {m.zone} is used twice.")
            used.add(seq)
            summoned = m.summoned or _natural_summon(card)
            proper = m.properly_summoned
            if proper is None:
                natural_procedure = summoned in ("fusion", "ritual", "synchro", "xyz", "link") and summoned == _natural_summon(card)
                if _needs_procedure(card) and not natural_procedure:
                    raise ValueError(f"{card.name}: specify properly_summoned true or false for this summon history.")
                proper = natural_procedure
            var = b.add(card, player, "LOCATION_MZONE", seq, POSITIONS[m.position], proc=proper)
            b.placed.append((player, var, card))
            source = m.summoned_from or ("extra deck" if card.is_(EXTRA_DECK_TYPES) else "hand")
            b.lines.append(f"Debug.PreSummon({var},{SUMMON_TYPES[summoned]},{SUMMON_FROM[source]})")
            for ref in m.materials:
                material = b.card(ref)
                b.lines.append(
                    f"Debug.AddCard({material.code},{player},{player},LOCATION_MZONE,{seq},POS_FACEUP) --{material.name} (material)"
                )
            b.counters(var, m.counters)

        pendulum = [b.card(ref) for ref in ps.pendulum_zones]
        if len(pendulum) > 2:
            raise ValueError(f"{tag} has only 2 Pendulum Zones.")
        used = {0, 4} if len(pendulum) == 2 else ({0} if pendulum else set())  # Pendulum Zones are S/T zones 1 and 5
        for index, card in enumerate(pendulum):
            b.placed.append((player, b.add(card, player, "LOCATION_PZONE", index, "POS_FACEUP"), card))
        for st in ps.spells_traps:
            card = b.card(st.card)
            if st.zone is None:
                seq = next((s for s in range(5) if s not in used), None)
                if seq is None:
                    raise ValueError(f"{tag} has no free Spell & Trap Zone for {card.name}.")
            elif 1 <= st.zone <= 5:
                seq = st.zone - 1
            else:
                raise ValueError(f"Spell & Trap Zone {st.zone} doesn't exist; use 1-5.")
            if seq in used:
                raise ValueError(f"{tag} Spell & Trap Zone {seq + 1} is already used.")
            used.add(seq)
            replay = activate and st.face_up and bool(st.targets or st.equipped_to) and replays_activation(card, cards)
            var = b.add(card, player, "LOCATION_SZONE", seq, "POS_FACEUP" if st.face_up and not replay else "POS_FACEDOWN")
            b.placed.append((player, var, card))
            links.append((player, var, st, replay))
        if ps.field_spell:
            card = b.card(ps.field_spell.card)
            var = b.add(card, player, "LOCATION_FZONE", 0, "POS_FACEUP" if ps.field_spell.face_up else "POS_FACEDOWN")
            b.placed.append((player, var, card))
            b.counters(var, ps.field_spell.counters)

    for player, var, st, replay in links:  # equips and targets can point at either player's cards
        if replay:
            targets = []
            for ref in ([st.equipped_to] if st.equipped_to else []) + st.targets:
                target = b.find(ref, player)
                location, seq = b.zones[target]
                controller, card = b.placed_at(target)
                if location != "LOCATION_MZONE":
                    raise ValueError(f"{b.placed_at(var)[1].name} can only target monsters, not {card.name}.")
                targets.append((controller, seq, card))
            activations.append(StartActivation(player, b.placed_at(var)[1], b.zones[var][1], targets))
        else:
            if st.equipped_to:
                b.lines.append(f"Debug.PreEquip({var},{b.find(st.equipped_to, player)})")
            for ref in st.targets:
                b.lines.append(f"Debug.PreSetTarget({var},{b.find(ref, player)})")
        b.counters(var, st.counters)
    if activations:
        b.lines += [
            "--The Set Traps above are activated when the duel starts; afterwards, forget those activations.",
            "local reset=Effect.GlobalEffect()",
            "reset:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)",
            "reset:SetCode(EVENT_CHAIN_END)",
            f"reset:SetLabel({len(activations)})",
            "reset:SetOperation(function(e) Debug.ResetTurnRecords() e:SetLabel(e:GetLabel()-1) if e:GetLabel()==0 then e:Reset() end end)",
            "Duel.RegisterEffect(reset,0)",
        ]
    b.lines.append("Debug.ReloadFieldEnd()")
    if setup.title:
        b.lines.append(f"Debug.ShowHint({_lua_string(setup.title)})")
    return "\n".join(b.lines) + "\n", activations


# Duel functions an activation may call and still be rebuilt by activating it again on the same monsters.
_REPLAYABLE_CALL = re.compile(r"(Get|Is|Check)\w*|Equip|EquipComplete|Hint|HintSelection|SetOperationInfo|RegisterEffect|RegisterFlagEffect|AdjustInstantly")


def replays_activation(card: Card, cards: CardDB) -> bool:
    """Whether a Trap's activation only targets or equips to monsters (and may apply effects to itself or to them),
    so activating it again on those monsters rebuilds it exactly. Traps whose activation does more, such as
    Special Summoning the target (Call of the Haunted), keep their target set directly."""
    if not card.is_(TYPE_TRAP):
        return False
    source = (cards.script(f"c{card.code}.lua") or b"").decode("utf-8", errors="replace")
    funcs = {m[1]: m[0] for m in re.finditer(r"^function s\.(\w+)\(.*?^end", source, re.S | re.M)}
    init = funcs.get("initial_effect", "")
    todo = [  # the operations of activations that always target (Seal of Wickedness targets only sometimes)
        op
        for var in re.findall(r"(\w+):SetType\(EFFECT_TYPE_ACTIVATE\)", init)
        if re.search(var + r":SetProperty\([^)\n]*EFFECT_FLAG_CARD_TARGET", init)
        for op in re.findall(var + r":SetOperation\(s\.(\w+)\)", init)
    ]
    persistent = re.search(r"aux\.AddPersistentProcedure\(([^\n]*)\)", init)
    if persistent:  # its 11th argument is the operation; the procedure itself sets the target
        args = [a.strip() for a in persistent[1].split(",")]
        todo += [args[10][2:]] if len(args) > 10 and args[10].startswith("s.") else []
    body, seen = "", set()
    while todo:
        name = todo.pop()
        if name in seen or name not in funcs:
            continue
        seen.add(name)
        body += funcs[name]
        todo += re.findall(r"s\.(\w+)\(", funcs[name])
    if not (persistent or "SetCardTarget" in body or re.search(r"Duel\.Equip\(\w+,\s*(c|e:GetHandler\(\))", body)):
        return False
    return all(_REPLAYABLE_CALL.fullmatch(call) for call in re.findall(r"Duel\.(\w+)\(", body))


def _needs_procedure(card: Card) -> bool:
    return card.is_(TYPE_MONSTER) and card.is_(EXTRA_DECK_TYPES | TYPE_RITUAL | TYPE_SPSUMMON)


def _natural_summon(card: Card) -> str:
    for bit, kind in ((TYPE_LINK, "link"), (TYPE_XYZ, "xyz"), (TYPE_SYNCHRO, "synchro"), (TYPE_FUSION, "fusion"), (TYPE_RITUAL, "ritual")):
        if card.is_(bit):
            return kind
    return "special" if card.is_(TYPE_SPSUMMON) else "normal"
