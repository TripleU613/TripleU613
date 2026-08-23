#!/usr/bin/env python3
"""Render the profile stats as one pixel-art terminal SVG.

Every glyph is drawn as raw pixel rectangles from a hand-made 5x7 bitmap font —
no vector fonts, no third-party widget service, nothing to rate-limit or 404.
The output is committed to the repo; a failed refresh keeps the last good file.

Usage:
    python3 scripts/gen_cards.py                  # fetch live, write assets/
    python3 scripts/gen_cards.py --fixture        # render sample data (offline)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

USER = os.environ.get("PROFILE_USER", "TripleU613")
API = "https://api.github.com"

# ---------------------------------------------------------------------------
# Palette — sampled from the omarchy sunset wallpaper
# ---------------------------------------------------------------------------

BG = "#16112b"      # deep indigo night
BORDER = "#4a3a7a"  # muted violet
FG = "#e8dcff"      # pale lavender
MUTED = "#8a7ab0"   # dusk violet
PINK = "#ff4fa3"    # hot pink ridge-light
PURPLE = "#9d6bff"  # violet
ORANGE = "#ffa057"  # sunset road glow
YELLOW = "#ffcc66"  # sun
CORAL = "#ff6673"   # horizon red
BLUE = "#7d8cff"    # far-hills blue

LANG_COLORS = {
    "Python": PURPLE,
    "Rust": ORANGE,
    "TypeScript": BLUE,
    "JavaScript": YELLOW,
    "Kotlin": PINK,
    "Shell": CORAL,
    "C": FG,
    "HTML": "#c85aff",
}
FALLBACK = [PINK, ORANGE, PURPLE, YELLOW, BLUE, CORAL]


def lang_color(name: str, i: int) -> str:
    return LANG_COLORS.get(name, FALLBACK[i % len(FALLBACK)])


# ---------------------------------------------------------------------------
# 5x7 pixel font (uppercase only; input is uppercased before lookup)
# ---------------------------------------------------------------------------

F = {
"A": ["_XXX_","X___X","X___X","XXXXX","X___X","X___X","X___X"],
"B": ["XXXX_","X___X","X___X","XXXX_","X___X","X___X","XXXX_"],
"C": ["_XXX_","X___X","X____","X____","X____","X___X","_XXX_"],
"D": ["XXXX_","X___X","X___X","X___X","X___X","X___X","XXXX_"],
"E": ["XXXXX","X____","X____","XXXX_","X____","X____","XXXXX"],
"F": ["XXXXX","X____","X____","XXXX_","X____","X____","X____"],
"G": ["_XXX_","X___X","X____","X_XXX","X___X","X___X","_XXX_"],
"H": ["X___X","X___X","X___X","XXXXX","X___X","X___X","X___X"],
"I": ["XXXXX","__X__","__X__","__X__","__X__","__X__","XXXXX"],
"J": ["____X","____X","____X","____X","____X","X___X","_XXX_"],
"K": ["X___X","X__X_","X_X__","XX___","X_X__","X__X_","X___X"],
"L": ["X____","X____","X____","X____","X____","X____","XXXXX"],
"M": ["X___X","XX_XX","X_X_X","X_X_X","X___X","X___X","X___X"],
"N": ["X___X","XX__X","XX__X","X_X_X","X__XX","X__XX","X___X"],
"O": ["_XXX_","X___X","X___X","X___X","X___X","X___X","_XXX_"],
"P": ["XXXX_","X___X","X___X","XXXX_","X____","X____","X____"],
"Q": ["_XXX_","X___X","X___X","X___X","X_X_X","X__X_","_XX_X"],
"R": ["XXXX_","X___X","X___X","XXXX_","X_X__","X__X_","X___X"],
"S": ["_XXXX","X____","X____","_XXX_","____X","____X","XXXX_"],
"T": ["XXXXX","__X__","__X__","__X__","__X__","__X__","__X__"],
"U": ["X___X","X___X","X___X","X___X","X___X","X___X","_XXX_"],
"V": ["X___X","X___X","X___X","X___X","X___X","_X_X_","__X__"],
"W": ["X___X","X___X","X___X","X_X_X","X_X_X","XX_XX","X___X"],
"X": ["X___X","X___X","_X_X_","__X__","_X_X_","X___X","X___X"],
"Y": ["X___X","X___X","_X_X_","__X__","__X__","__X__","__X__"],
"Z": ["XXXXX","____X","___X_","__X__","_X___","X____","XXXXX"],
"0": ["_XXX_","X___X","X__XX","X_X_X","XX__X","X___X","_XXX_"],
"1": ["__X__","_XX__","__X__","__X__","__X__","__X__","XXXXX"],
"2": ["_XXX_","X___X","____X","___X_","__X__","_X___","XXXXX"],
"3": ["XXXX_","____X","____X","_XXX_","____X","____X","XXXX_"],
"4": ["___X_","__XX_","_X_X_","X__X_","XXXXX","___X_","___X_"],
"5": ["XXXXX","X____","XXXX_","____X","____X","X___X","_XXX_"],
"6": ["_XXX_","X____","X____","XXXX_","X___X","X___X","_XXX_"],
"7": ["XXXXX","____X","___X_","__X__","__X__","__X__","__X__"],
"8": ["_XXX_","X___X","X___X","_XXX_","X___X","X___X","_XXX_"],
"9": ["_XXX_","X___X","X___X","_XXXX","____X","____X","_XXX_"],
" ": ["_____"]*7,
".": ["_____","_____","_____","_____","_____","_XX__","_XX__"],
",": ["_____","_____","_____","_____","_XX__","_XX__","_X___"],
"-": ["_____","_____","_____","_XXX_","_____","_____","_____"],
"_": ["_____","_____","_____","_____","_____","_____","XXXXX"],
"/": ["____X","____X","___X_","__X__","_X___","X____","X____"],
"%": ["XX__X","XX__X","___X_","__X__","_X___","X__XX","X__XX"],
":": ["_____","_XX__","_XX__","_____","_XX__","_XX__","_____"],
"@": ["_XXX_","X___X","X_XXX","X_X_X","X_XX_","X____","_XXX_"],
"#": ["_X_X_","_X_X_","XXXXX","_X_X_","XXXXX","_X_X_","_X_X_"],
"+": ["_____","__X__","__X__","XXXXX","__X__","__X__","_____"],
"'": ["__X__","__X__","_____","_____","_____","_____","_____"],
"~": ["_____","_____","_XX_X","X_XX_","_____","_____","_____"],
"!": ["__X__","__X__","__X__","__X__","__X__","_____","__X__"],
"?": ["_XXX_","X___X","____X","___X_","__X__","_____","__X__"],
"=": ["_____","_____","XXXXX","_____","XXXXX","_____","_____"],
"[": ["_XXX_","_X___","_X___","_X___","_X___","_X___","_XXX_"],
"]": ["_XXX_","___X_","___X_","___X_","___X_","___X_","_XXX_"],
"(": ["___X_","__X__","_X___","_X___","_X___","__X__","___X_"],
")": ["_X___","__X__","___X_","___X_","___X_","__X__","_X___"],
"$": ["__X__","_XXXX","X_X__","_XXX_","__X_X","XXXX_","__X__"],
"·": ["_____","_____","_____","_XX__","_XX__","_____","_____"],
"★": ["__X__","__X__","XXXXX","_XXX_","_XXX_","_X_X_","X___X"],
"❯": ["X____","XX___","_XX__","__XX_","_XX__","XX___","X____"],
"|": ["__X__"]*7,
">": ["X____","_X___","__X__","___X_","__X__","_X___","X____"],
}

# characters we normalise before lookup; anything else unknown is dropped
TRANSLATE = {"—": "-", "–": "-", "&": "+", "’": "'", "“": "'", "”": "'"}


def norm(text: str) -> str:
    out = []
    for ch in str(text).upper():
        ch = TRANSLATE.get(ch, ch)
        if ch in F:
            out.append(ch)
        elif ch == "\t":
            out.append(" ")
        # unknown glyphs are dropped rather than rendered wrong
    return "".join(out)


class Painter:
    """Collects pixel rects and emits them as per-colour <path> elements."""

    def __init__(self) -> None:
        self.ops: list[tuple[str, str, str]] = []  # (color, seg, extra)

    def block(self, x: float, y: float, w: float, h: float, color: str, extra: str = "") -> None:
        self.ops.append((color, f"M{x:g} {y:g}h{w:g}v{h:g}h{-w:g}z", extra))

    def text(self, x: float, y: float, s: str, color: str, sc: int = 2) -> float:
        """Draw text, return the x just past the last glyph."""
        cx = x
        for ch in norm(s):
            rows = F[ch]
            for ry, row in enumerate(rows):
                run = 0
                for rx in range(6):
                    on = rx < 5 and row[rx] == "X"
                    if on:
                        run += 1
                    elif run:
                        self.block(cx + (rx - run) * sc, y + ry * sc, run * sc, sc, color)
                        run = 0
            cx += 6 * sc
        return cx

    @staticmethod
    def width(s: str, sc: int = 2) -> int:
        return len(norm(s)) * 6 * sc

    def emit(self, w: int, h: int) -> str:
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img">',
            f'<rect width="{w}" height="{h}" fill="{BG}"/>',
            '<g shape-rendering="crispEdges">',
        ]
        # merge consecutive same-colour plain ops into one path
        i = 0
        while i < len(self.ops):
            color, seg, extra = self.ops[i]
            if extra:
                parts.append(f'<path fill="{color}" d="{seg}">{extra}</path>')
                i += 1
                continue
            segs = [seg]
            j = i + 1
            while j < len(self.ops) and self.ops[j][0] == color and not self.ops[j][2]:
                segs.append(self.ops[j][1])
                j += 1
            parts.append(f'<path fill="{color}" d="{"".join(segs)}"/>')
            i = j
        parts.append("</g></svg>")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def api(path: str) -> object:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{USER}-profile-cards",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def paged(path: str) -> list:
    out: list = []
    page = 1
    while page <= 10:
        sep = "&" if "?" in path else "?"
        batch = api(f"{path}{sep}per_page=100&page={page}")
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def collect() -> dict:
    user = api(f"/users/{USER}")
    repos = paged(f"/users/{USER}/repos?type=owner&sort=pushed")
    # Public non-forks only. The default Actions token can't see private repos,
    # but this is a public README — filter explicitly so a broader PAT could
    # never leak a private repo name into it.
    own = [r for r in repos if not r.get("fork") and not r.get("private")]

    totals: dict[str, int] = {}
    for r in own:
        try:
            for lang, n in (api(f"/repos/{USER}/{r['name']}/languages") or {}).items():
                totals[lang] = totals.get(lang, 0) + n
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
            print(f"  ! languages for {r['name']}: {exc}", file=sys.stderr)

    top = sorted(
        (r for r in own if not r.get("archived")),
        key=lambda r: (r.get("stargazers_count", 0), r.get("pushed_at", "")),
        reverse=True,
    )[:4]

    return {
        "repos": len(own),
        "stars": sum(r.get("stargazers_count", 0) for r in own),
        "forks": sum(r.get("forks_count", 0) for r in own),
        "followers": user.get("followers", 0),
        "languages": sorted(totals.items(), key=lambda kv: kv[1], reverse=True),
        "top": [
            {
                "name": r["name"],
                "desc": r.get("description") or r.get("language") or "",
                "stars": r.get("stargazers_count", 0),
            }
            for r in top
        ],
    }


FIXTURE = {
    "repos": 17,
    "stars": 49,
    "forks": 5,
    "followers": 21,
    "languages": [
        ("Python", 1_120_000),
        ("Kotlin", 640_000),
        ("Shell", 430_000),
        ("JavaScript", 390_000),
        ("Rust", 260_000),
        ("HTML", 210_000),
    ],
    "top": [
        {"name": "TripleUMDM_Public", "desc": "Public landing page for TripleUMDM", "stars": 25},
        {"name": "Unitree-Go1-Pro-Almost-Full-Backup-", "desc": "Unitree Go1 Pro backup (Pi + both Jetsons)", "stars": 3},
        {"name": "claude-teleport", "desc": "Move a Claude Code session to another machine", "stars": 2},
        {"name": "mirrorbot-gplay", "desc": "Google Play APK downloader for MirrorBot", "stars": 2},
    ],
}


# ---------------------------------------------------------------------------
# The terminal
# ---------------------------------------------------------------------------

W = 880
MX = 32          # content left margin
SC = 2           # font scale: glyph 10x14, advance 12
ADV = 6 * SC
LINE = 14


def clip_cols(text: str, cols: int) -> str:
    t = norm(text)
    return t if len(t) <= cols else t[: max(0, cols - 1)].rstrip(" ,.-_") + "."


def render(d: dict) -> str:
    p = Painter()
    y = 44

    def prompt(cmd: str) -> None:
        nonlocal y
        x = p.text(MX, y, "❯ ", PINK)
        p.text(x, y, cmd, ORANGE)
        y += LINE + 10

    # --- stats ---
    prompt("tripleu stats")
    x = MX
    for label, value in [
        ("REPOS", d["repos"]),
        ("STARS", d["stars"]),
        ("FORKS", d["forks"]),
        ("FOLLOWERS", d["followers"]),
    ]:
        x = p.text(x, y, f"{label} ", MUTED)
        x = p.text(x, y, str(value), FG)
        x += 3 * ADV
    y += LINE + 20

    # --- languages ---
    prompt("tripleu langs")
    langs = d["languages"][:6]
    total = sum(n for _, n in d["languages"]) or 1
    # defrag-style cell bar
    cell, gap = 10, 2
    ncells = (W - 2 * MX + gap) // (cell + gap)
    shares = [n / total * ncells for _, n in langs]
    counts = [int(s) for s in shares]
    for _ in range(ncells - sum(counts)):
        k = max(range(len(shares)), key=lambda i: shares[i] - counts[i])
        counts[k] += 1
    ci = 0
    for i, cnt in enumerate(counts):
        for _ in range(cnt):
            p.block(MX + ci * (cell + gap), y, cell, cell, lang_color(langs[i][0], i))
            ci += 1
    y += cell + 14
    # legend: 3 columns
    for i, (name, n) in enumerate(langs):
        lx = MX + (i % 3) * 272
        ly = y + (i // 3) * (LINE + 8)
        p.block(lx, ly + 3, 8, 8, lang_color(name, i))
        x = p.text(lx + 16, ly, clip_cols(name, 12), FG)
        p.text(x + ADV, ly, f"{100 * n / total:.1f}%", MUTED)
    y += ((len(langs) + 2) // 3) * (LINE + 8) + 16

    # --- top repos ---
    prompt("tripleu ship")
    for r in d["top"][:4]:
        star = f"★ {r['stars']}"
        star_x = W - MX - Painter.width(star)
        p.text(star_x, y, star, YELLOW)
        name = clip_cols(r["name"], 34)
        x = p.text(MX, y, name, PURPLE)
        avail = (star_x - x - 3 * ADV) // ADV
        if avail > 4 and r["desc"]:
            p.text(x + 2 * ADV, y, clip_cols(r["desc"], avail), MUTED)
        y += LINE + 8
    y += 10

    # --- idle prompt with blinking cursor ---
    x = p.text(MX, y, "❯ ", PINK)
    p.block(
        x, y, 10, LINE, FG,
        extra='<animate attributeName="opacity" values="1;1;0;0" '
              'keyTimes="0;0.5;0.5;1" dur="1.2s" repeatCount="indefinite"/>',
    )
    y += LINE + 22

    H = y + 10
    # window border (2px) with a title gap in the top run
    title = " TRIPLEU@OMARCHY:~ "
    tw = Painter.width(title)
    p.block(10, 8, 20, 2, BORDER)                       # top-left stub
    p.text(34, 1, title, MUTED)
    p.block(34 + tw + 4, 8, W - 10 - (34 + tw + 4) - 2, 2, BORDER)  # top run
    p.block(10, H - 12, W - 22, 2, BORDER)              # bottom
    p.block(10, 8, 2, H - 18, BORDER)                   # left
    p.block(W - 12, 8, 2, H - 18, BORDER)               # right

    return p.emit(W, H)


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", action="store_true")
    ap.add_argument("--out", default="assets")
    args = ap.parse_args()

    if args.fixture:
        data = FIXTURE
    else:
        try:
            data = collect()
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError) as exc:
            print(f"fetch failed, keeping existing card: {exc}", file=sys.stderr)
            return 1
        print(f"fetched {data['repos']} repos, {data['stars']} stars")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "tty.svg").write_text(render(data) + "\n")
    print(f"  wrote {out / 'tty.svg'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
