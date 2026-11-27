import json

import pytest

from ygo_judge import server
from ygo_judge.scenario import Setup


def test_saved_duel_keeps_normal_first_turn_rules_after_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "STATE", tmp_path)
    store = server.Duels()
    duel = store.create(Setup())
    duel.play([])
    store.save(duel)
    restored = server.Duels().get(duel.id)
    assert restored.board() == duel.board()
    assert restored.log == duel.log
    assert "Enter the Battle Phase" not in restored.describe_decision()


def test_old_saved_duel_requires_a_fresh_test(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "STATE", tmp_path)
    store = server.Duels()
    duel = store.create(Setup())
    store.save(duel)
    path = store._path(duel.id)
    saved = json.loads(path.read_text())
    saved.pop("rules_version")  # Original unversioned format, with first-turn Battle Phase enabled.
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="Start a new duel with start_duel"):
        server.Duels().get(duel.id)


@pytest.mark.parametrize("fingerprint", [None, "different-engine-and-card-scripts"])
def test_saved_duel_rejects_different_or_unknown_assets(tmp_path, monkeypatch, fingerprint):
    monkeypatch.setattr(server, "STATE", tmp_path)
    store = server.Duels()
    duel = store.create(Setup())
    store.save(duel)
    path = store._path(duel.id)
    saved = json.loads(path.read_text())
    if fingerprint is None:
        saved.pop("simulation_fingerprint")
    else:
        saved["simulation_fingerprint"] = fingerprint
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="different engine/card assets"):
        server.Duels().get(duel.id)


def test_failed_live_duel_cannot_return_a_clean_state_or_be_saved(tmp_path, monkeypatch):
    from ygo_judge.engine import EngineError

    monkeypatch.setattr(server, "STATE", tmp_path)
    store = server.Duels()
    monkeypatch.setattr(server, "duels", store)
    duel = store.create(Setup())
    duel.errors.append("broken card effect")
    with pytest.raises(EngineError, match="Simulation invalid"):
        store.save(duel)
    assert "Simulation invalid" in server.get_state(duel.id)
    assert "Simulation invalid" in server.choose(duel.id, [])
    assert "Simulation invalid" in server.undo(duel.id)


def test_asset_fingerprint_changes_for_each_input(tmp_path):
    from ygo_judge.compatibility import simulation_fingerprint

    data = tmp_path / "data"
    (data / "CardScripts" / "official").mkdir(parents=True)
    (data / "BabelCDB").mkdir()
    library = tmp_path / "engine.so"
    inputs = [library, data / "strings.conf", data / "BabelCDB" / "cards.cdb", data / "CardScripts" / "official" / "c1.lua"]
    for path in inputs:
        path.write_bytes(b"initial")
    previous = simulation_fingerprint(data, library)
    for path in inputs:
        path.write_bytes(b"updated")
        simulation_fingerprint.cache_clear()  # a new server process after an asset update
        current = simulation_fingerprint(data, library)
        assert current != previous
        previous = current


def _ja_index(monkeypatch):
    from ygo_judge import http_api
    monkeypatch.setattr(http_api, "JA_INDEX", [])
    http_api.build_ja_index()
    return http_api


@pytest.mark.parametrize("query, code", [
    ("スプリガンズ・メリーメイカー", "48285768"),  # the script's name had lost its last character
    ("グレイドル・コブラ", "93445074"),  # the script carried Graydle Alligator's name
    ("夢魔鏡の魔獣－パンタス", "99792080"),
    ("未界域のネッシー", "70711847"),  # the script's name had furigana mixed in
    ('"罪宝狩りの悪魔"', "80845034"),  # plain quotation marks match the official “ ”
])
def test_find_card_ja_finds_the_card_by_its_official_name(monkeypatch, query, code):
    out = _ja_index(monkeypatch).find_card_ja(query, 1)
    assert f"[{code}]" in out, out


def test_no_two_official_scripts_share_a_japanese_name():
    # The first line of each script is the Japanese name find_card_ja searches. Alternate versions of one card share
    # its name on purpose; "JP name" marks scripts whose Japanese name is not known yet.
    import os
    import re
    allowed = {"融合", "覇王天龍オッドアイズ・アークレイ・ドラゴン", "ビッグ・シールド・ガードナー", "JP name", "JPname", "Japanese name"}
    d = os.path.join(os.environ["YGO_DATA"], "CardScripts", "official")
    seen = {}
    for fn in sorted(os.listdir(d)):
        if re.fullmatch(r"c\d+\.lua", fn):
            with open(os.path.join(d, fn), encoding="utf-8", errors="replace") as f:
                seen.setdefault(f.readline().strip().lstrip("-").strip(), []).append(fn)
    dup = {ja: files for ja, files in seen.items() if len(files) > 1 and ja not in allowed}
    assert not dup, dup
