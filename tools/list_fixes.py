"""List every Konami FAQ fix in patches/ as CSV, so the fixes can be sorted by kind.

Each added line that mentions "FAQ" becomes one row: patch, file, FAQ numbers, kind, comment.
The kind comes from a tag in the comment:
  [general:faq]      a general rule, applied where a Konami FAQ rules on that card or case
  [general:analogy]  the same general rule, applied by analogy to a card with the same text but no FAQ of its own
  [exception]        an exception to a rule the engine applies elsewhere (for example a flag that only some cards opt into)
  [card]             a fix to one card's own handling
Lines without a tag have an empty kind; older fixes were written before the tags and can be sorted later.

Usage: python tools/list_fixes.py > fixes.csv
"""
import csv
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "patches"
FAQ = re.compile(r"FAQ\s*([\d,\s/]+(?:and\s+\d+)?)")
TAG = re.compile(r"\[(general:faq|general:analogy|exception|card)\]")


def rows():
    for patch in sorted(ROOT.glob("*/*.patch")):
        current = ""
        for line in patch.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("diff --git "):
                current = line.split(" b/", 1)[-1]
                continue
            if not line.startswith("+") or line.startswith("+++") or "FAQ" not in line:
                continue
            numbers = sorted({int(n) for m in FAQ.finditer(line) for n in re.findall(r"\d{3,5}", m.group(1))})
            tag = TAG.search(line)
            comment = re.sub(r"^\+\s*", "", line)
            comment = comment.split("--", 1)[-1].split("//", 1)[-1].strip() if ("--" in comment or "//" in comment) else comment.strip()
            yield {
                "patch": f"{patch.parent.name}/{patch.name}",
                "file": current,
                "faq": " ".join(map(str, numbers)),
                "kind": tag.group(1) if tag else "",
                "comment": comment,
            }


def main():
    writer = csv.DictWriter(sys.stdout, fieldnames=["patch", "file", "faq", "kind", "comment"], lineterminator="\n")
    writer.writeheader()
    for row in rows():
        writer.writerow(row)


if __name__ == "__main__":
    main()
