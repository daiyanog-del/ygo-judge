"""A small HTTP API over the ygo-judge tools, for callers that are not MCP clients.

Added for JudgemanAI on 2026-11-21 (AGPL-3.0-or-later, like the rest of ygo-judge).
The API keeps duels in memory and listens on HTTP_API_HOST:HTTP_API_PORT (default 127.0.0.1:8765).

- POST /call   {"tool": "...", "args": {...}}  ->  {"output": "..."}   (errors: 400 {"error": "..."})
- GET  /schema ->  {"output": <JSON Schema of the board setup>}
- GET  /health ->  {"output": "ok"}

Tools: find_card, find_card_ja, start_duel, choose, get_state, undo, card_script.
get_rulings is not exposed. find_card_ja looks cards up by their Japanese name (the first comment
line of each card script) and get_state returns only the last LOG_TAIL log lines unless full=true.
"""
import json
import os
import re
import sys
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import server
from .scenario import Setup

ALLOWED = {"find_card", "find_card_ja", "start_duel", "choose", "get_state", "undo", "card_script"}
LOG_TAIL = 30

JA_INDEX: list[tuple[str, str]] = []  # (Japanese name, passcode), built once at startup


def build_ja_index() -> None:
    root = os.path.join(os.environ["YGO_DATA"], "CardScripts")
    for sub in ("official", "pre-release"):
        d = os.path.join(root, sub)
        for fn in sorted(os.listdir(d)):
            m = re.fullmatch(r"c(\d+)\.lua", fn)
            if m:
                with open(os.path.join(d, fn), encoding="utf-8", errors="replace") as f:
                    JA_INDEX.append((f.readline().strip().lstrip("-").strip(), m.group(1)))


def _norm(s: str) -> str:
    """Ignore width (NFKC), spaces, middle dots and the different dashes."""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\s・･]", "", s)
    return re.sub(r"[‐‑‒–—―−ー－-]", "-", s).lower()


def find_card_ja(query: str, limit: int = 5) -> str:
    q = _norm(query)
    hits = [(ja, code) for ja, code in JA_INDEX if q in _norm(ja)]
    hits.sort(key=lambda t: (_norm(t[0]) != q, len(t[0])))
    if not hits:
        return f"「{query}」を日本語名に含むカードは見つかりません。"
    return "\n\n".join(f"日本語名: {ja}\n" + server.find_card(code, 1) for ja, code in hits[:limit])


def get_state_short(duel_id: str, full: bool = False) -> str:
    out = server.get_state(duel_id)
    if full or "\n\nLog:\n" not in out:
        return out
    head, rest = out.split("\n\nLog:\n", 1)
    log, _, decision = rest.partition("\n\n")
    lines = log.splitlines()
    if len(lines) > LOG_TAIL:
        lines = [f"  …（前の {len(lines) - LOG_TAIL} 行は省略。全部見るときは full: true）"] + lines[-LOG_TAIL:]
    return f"{head}\n\nLog:\n" + "\n".join(lines) + f"\n\n{decision}"


def call(tool: str, args: dict) -> str:
    if tool not in ALLOWED:
        raise ValueError(f"{tool} is not available (available: {sorted(ALLOWED)})")
    if tool == "find_card_ja":
        return find_card_ja(**args)
    if tool == "get_state":
        return get_state_short(**args)
    if tool == "start_duel":
        args = {"setup": Setup.model_validate(args["setup"] if "setup" in args else args)}
    return getattr(server, tool)(**args)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"output": "ok"})
        elif self.path == "/schema":
            self._send(200, {"output": Setup.model_json_schema()})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/call":
            self._send(404, {"error": "not found"})
            return
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8-sig"))
            self._send(200, {"output": call(req["tool"], req.get("args", {}))})
        except Exception as e:  # bad arguments come back as text so the caller can fix them; the server keeps running
            self._send(400, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt: str, *a) -> None:
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % a))


def main() -> None:
    build_ja_index()
    host = os.environ.get("HTTP_API_HOST", "127.0.0.1")
    port = int(os.environ.get("HTTP_API_PORT", "8765"))
    print(f"{len(JA_INDEX)} Japanese card names. Listening on {host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
