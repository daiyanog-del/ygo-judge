#!/bin/sh
# Fetches (or updates) EDOPro's rules engine source, card scripts, card databases and strings.
# Usage: scripts/fetch-data.sh [dir]
set -eu
DIR=${1:-vendor}
mkdir -p "$DIR"

get() {  # get <github repo> <folder> [extra clone flags]
	if [ -d "$DIR/$2/.git" ]; then
		git -C "$DIR/$2" checkout -q -- .  # drop the patches applied last time; they are applied again below
		git -C "$DIR/$2" pull -q --ff-only
		git -C "$DIR/$2" submodule -q update --init --depth 1
	else
		git clone -q --depth 1 ${3:-} "https://github.com/$1.git" "$DIR/$2"
	fi
}
get edo9300/ygopro-core ygopro-core "--recurse-submodules --shallow-submodules"
get ProjectIgnis/CardScripts CardScripts
get ProjectIgnis/BabelCDB BabelCDB
curl -fsSL -o "$DIR/strings.conf" https://raw.githubusercontent.com/ProjectIgnis/Distribution/master/config/strings.conf
# JudgemanAI (2026-11-23): apply patches/<folder>/*.patch to the fetched sources, so the engine follows Konami's
# rulings where the original differs (each patch names the official Q&A it follows; tests/test_judgeman_rulings.py
# checks them). A patch that no longer applies to a newer upstream stops the fetch, and with it the image build.
PATCHES=$(dirname "$0")/../patches
for folder in ygopro-core CardScripts; do
	for p in "$PATCHES/$folder"/*.patch; do
		[ -e "$p" ] || continue
		git -C "$DIR/$folder" apply --whitespace=nowarn "$(cd "$(dirname "$p")" && pwd)/$(basename "$p")"
		echo "applied $folder/$(basename "$p")"
	done
done
echo "data in $DIR"
