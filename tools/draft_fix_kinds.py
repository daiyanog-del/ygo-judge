"""Draft a kind for each FAQ fix that has no tag yet, into docs/fix_kinds.csv (review it by hand afterwards).

Rules for the draft (the "basis" column says which one applied):
  core file (.cpp/.h)                              -> general:faq
  script fix whose FAQ number appears in 2+ card scripts:
      the card is named in that FAQ                -> general:faq
      the card is not named in that FAQ            -> general:analogy
  script fix in one card only                      -> card
Rows already in docs/fix_kinds.csv keep their kind (a hand review is not overwritten).

Usage: python tools/draft_fix_kinds.py <qa.json> <cards.json> <CardScripts/official folder>
The card of a script is found from the Japanese name on the first line of the script.
"""
import csv
import json
import pathlib
import re
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from list_fixes import rows  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "fix_kinds.csv"
FIELDS = ["patch", "file", "faq", "kind", "basis", "comment"]


def norm(s):
    return re.sub(r"[\s　・]", "", unicodedata.normalize("NFKC", s))


def main():
    qa = {int(q["fid"]): q for q in json.load(open(sys.argv[1], encoding="utf-8"))}
    cards = json.load(open(sys.argv[2], encoding="utf-8"))
    official = pathlib.Path(sys.argv[3])
    cid_by_name = {norm(v["name"]): int(k) for k, v in cards.items()}

    def cid_of(path):
        p = official / pathlib.Path(path).name
        if not p.exists():
            return None
        first = p.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0].lstrip("-").strip()
        return cid_by_name.get(norm(first))

    def cards_of(fid):
        q = qa.get(fid)
        if not q:
            return set()
        return set(json.loads(q["cards"]) if isinstance(q["cards"], str) else q["cards"])

    old = {}
    if OUT.exists():
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            old[(r["patch"], r["file"], r["faq"], r["comment"])] = r
    all_rows = list(rows())
    files_by_faq = {}
    for r in all_rows:
        if r["file"].startswith("official/"):
            for f in r["faq"].split():
                files_by_faq.setdefault(int(f), set()).add(r["file"])
    out = []
    for r in all_rows:
        if r["kind"]:
            continue
        key = (r["patch"], r["file"], r["faq"], r["comment"])
        if key in old:
            out.append(old[key])
            continue
        faqs = [int(f) for f in r["faq"].split()]
        if r["file"].endswith((".cpp", ".h")):
            kind, basis = "general:faq", "core"
        elif not r["file"].startswith("official/") or not faqs:
            kind, basis = "", "not a card script or no FAQ number"
        elif any(len(files_by_faq.get(f, ())) >= 2 for f in faqs):
            cid = cid_of(r["file"])
            named = cid is not None and any(cid in cards_of(f) for f in faqs)
            kind, basis = ("general:faq", "shared FAQ, card named") if named else ("general:analogy", "shared FAQ, card not named")
        else:
            kind, basis = "card", "one card"
        out.append({"patch": r["patch"], "file": r["file"], "faq": r["faq"], "kind": kind, "basis": "draft: " + basis, "comment": r["comment"]})
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print(len(out), "rows ->", OUT)


if __name__ == "__main__":
    main()
