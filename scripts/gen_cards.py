#!/usr/bin/env python3
"""Render the profile stats as one pixel-art terminal SVG.

Every glyph is drawn as raw pixel rectangles from a hand-made 5x7 bitmap font —
no vector fonts, no third-party widget service, nothing to rate-limit or 404.
The output is committed to the repo; a failed refresh keeps the last good file.

Data comes from the GitHub GraphQL API when a token is available (a PAT in the
STATS_TOKEN secret sees private repositories too, so the numbers cover
everything, not just public work), with a REST fallback for tokenless runs.
Only aggregates are rendered — repo names never appear in the output, so a
broad token cannot leak anything private into the public README.

Usage:
    python3 scripts/gen_cards.py                  # fetch live, write assets/
    python3 scripts/gen_cards.py --data d.json    # render from a data file
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

USER = os.environ.get("PROFILE_USER", "TripleU613")

# ---------------------------------------------------------------------------
# Palette — black / dark blue / electric blue
# ---------------------------------------------------------------------------

BG = "#04070d"
BORDER = "#16335f"
FG = "#d9e8ff"
MUTED = "#4e6b9e"
ELEC = "#00a8ff"
BLUE = "#0066ff"
CYAN = "#22d3ee"
ICE = "#7dd3fc"
ROYAL = "#3d5eff"
PALE = "#b7d3ff"

LANG_RANK = [ELEC, BLUE, CYAN, ICE, ROYAL, PALE]
HEAT = ["#0b1a33", "#10407e", "#0066ff", "#00a8ff", "#8be2ff"]

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

TRANSLATE = {"—": "-", "–": "-", "&": "+", "’": "'", "“": "'", "”": "'"}


def norm(text: str) -> str:
    out = []
    for ch in str(text).upper():
        ch = TRANSLATE.get(ch, ch)
        if ch in F:
            out.append(ch)
        # unknown glyphs are dropped rather than rendered wrong
    return "".join(out)


class Painter:
    """Collects pixel rects and emits them as per-colour <path> elements."""

    def __init__(self) -> None:
        self.ops: list[tuple[str, str, str]] = []  # (color, seg, extra)

    def block(self, x: float, y: float, w: float, h: float, color: str, extra: str = "") -> None:
        self.ops.append((color, f"M{x:g} {y:g}h{w:g}v{h:g}h{-w:g}z", extra))

    def text(self, x: float, y: float, s: str, color: str, sc: int = 2) -> float:
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
# Data — GraphQL first (sees private repos with a PAT), REST fallback
# ---------------------------------------------------------------------------


def token() -> str | None:
    return os.environ.get("STATS_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def http(url: str, body: bytes | None = None) -> object:
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{USER}-profile-cards",
            "Content-Type": "application/json",
        },
    )
    if token():
        req.add_header("Authorization", f"Bearer {token()}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


GQL = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        forkCount
        languages(first: 10) { edges { size node { name } } }
      }
    }
  }
}
"""


def gql(cursor: str | None) -> dict:
    body = json.dumps({"query": GQL, "variables": {"login": USER, "cursor": cursor}}).encode()
    out = http("https://api.github.com/graphql", body)
    if not isinstance(out, dict) or out.get("errors") or not out.get("data", {}).get("user"):
        raise ValueError(f"graphql: {json.dumps(out)[:300]}")
    return out["data"]["user"]


def collect_graphql() -> dict:
    stars = forks = 0
    langs: dict[str, int] = {}
    cursor = None
    first = None
    while True:
        u = gql(cursor)
        if first is None:
            first = u
        repos = u["repositories"]
        for r in repos["nodes"]:
            stars += r["stargazerCount"]
            forks += r["forkCount"]
            for e in r["languages"]["edges"]:
                langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    cc = first["contributionsCollection"]
    days = {
        d["date"]: d["contributionCount"]
        for w in cc["contributionCalendar"]["weeks"]
        for d in w["contributionDays"]
    }
    return {
        "repos": first["repositories"]["totalCount"],
        "stars": stars,
        "forks": forks,
        "followers": first["followers"]["totalCount"],
        "langs": sorted(langs.items(), key=lambda kv: -kv[1]),
        "contrib_total": cc["contributionCalendar"]["totalContributions"],
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "reviews": cc["totalPullRequestReviewContributions"],
        "days": days,
    }


def collect_rest() -> dict:
    user = http(f"https://api.github.com/users/{USER}")
    repos: list = []
    page = 1
    while page <= 10:
        batch = http(f"https://api.github.com/users/{USER}/repos?type=owner&per_page=100&page={page}")
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    own = [r for r in repos if not r.get("fork")]
    langs: dict[str, int] = {}
    for r in own:
        try:
            for lang, n in (http(f"https://api.github.com/repos/{USER}/{r['name']}/languages") or {}).items():
                langs[lang] = langs.get(lang, 0) + n
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
            pass
    return {
        "repos": len(own),
        "stars": sum(r.get("stargazers_count", 0) for r in own),
        "forks": sum(r.get("forks_count", 0) for r in own),
        "followers": user.get("followers", 0),
        "langs": sorted(langs.items(), key=lambda kv: -kv[1]),
    }


def collect() -> dict:
    try:
        return collect_graphql()
    except Exception as exc:  # noqa: BLE001 - fall back to public REST data
        print(f"graphql unavailable ({exc}), falling back to REST", file=sys.stderr)
        return collect_rest()


# ---------------------------------------------------------------------------
# The terminal
# ---------------------------------------------------------------------------

W = 880
MX = 32
ADV = 12          # glyph advance at scale 2
LINE = 14


def clip_cols(text: str, cols: int) -> str:
    t = norm(text)
    return t if len(t) <= cols else t[: max(0, cols - 1)].rstrip(" ,.-_") + "."


def heat_level(count: int, q: list[int]) -> int:
    if count <= 0:
        return 0
    for i, threshold in enumerate(q, start=1):
        if count <= threshold:
            return i
    return 4


def streaks(days: dict[str, int]) -> tuple[int, int]:
    if not days:
        return 0, 0
    dates = sorted(days)
    start = dt.date.fromisoformat(dates[0])
    end = dt.date.fromisoformat(dates[-1])
    best = run = 0
    cur = start
    current = 0
    while cur <= end:
        if days.get(cur.isoformat(), 0) > 0:
            run += 1
            best = max(best, run)
        else:
            run = 0
        cur += dt.timedelta(days=1)
    # current streak counts back from the last recorded day
    cur = end
    while cur >= start and days.get(cur.isoformat(), 0) > 0:
        current += 1
        cur -= dt.timedelta(days=1)
    return current, best


def render(d: dict) -> str:
    p = Painter()
    y = 44

    def prompt(cmd: str) -> None:
        nonlocal y
        x = p.text(MX, y, "❯ ", ELEC)
        p.text(x, y, cmd, CYAN)
        y += LINE + 10

    def statline(items: list[tuple[str, object]]) -> None:
        nonlocal y
        x = MX
        for label, value in items:
            x = p.text(x, y, f"{label} ", MUTED)
            x = p.text(x, y, str(value), FG)
            x += 3 * ADV
        y += LINE + 8

    # --- stats ---
    prompt("tripleu stats")
    statline([
        ("REPOS", d["repos"]),
        ("STARS", d["stars"]),
        ("FORKS", d["forks"]),
        ("FOLLOWERS", d["followers"]),
    ])
    extra = [(k.upper(), d[k]) for k in ("commits", "prs", "issues", "reviews") if d.get(k) is not None]
    if extra:
        statline(extra)
    y += 12

    # --- contribution graph ---
    days: dict[str, int] = d.get("days") or {}
    if days:
        prompt("tripleu graph")
        dates = sorted(days)
        end = dt.date.fromisoformat(dates[-1])
        start = end - dt.timedelta(days=end.weekday() + 1 + 51 * 7)  # 52 sunday-aligned weeks
        nonzero = sorted(v for v in days.values() if v > 0)
        q = [nonzero[int(len(nonzero) * f)] for f in (0.25, 0.5, 0.75)] if nonzero else [1, 2, 3]
        cell, gap = 12, 3
        cur = start
        col = 0
        while cur <= end:
            for row in range(7):
                if cur > end:
                    break
                lvl = heat_level(days.get(cur.isoformat(), 0), q)
                p.block(MX + col * (cell + gap), y + row * (cell + gap), cell, cell, HEAT[lvl])
                cur += dt.timedelta(days=1)
            col += 1
        y += 7 * (cell + gap) - gap + 14

        total = d.get("contrib_total", sum(days.values()))
        cur_streak, best_streak = streaks(days)
        x = p.text(MX, y, f"{total} ", FG)
        x = p.text(x, y, "CONTRIBUTIONS/YR", MUTED)
        x = p.text(x + 2 * ADV, y, "· STREAK ", MUTED)
        x = p.text(x, y, f"{cur_streak}D", FG)
        x = p.text(x + 2 * ADV, y, "· BEST ", MUTED)
        x = p.text(x, y, f"{best_streak}D", FG)
        mix = d.get("mix")
        if mix:
            x = p.text(x + 2 * ADV, y, "· ", MUTED)
            x = p.text(x, y, f"{mix['commits_pct']}%", FG)
            x = p.text(x, y, " COMMITS ", MUTED)
            x = p.text(x, y, f"{mix['prs_pct']}%", FG)
            p.text(x, y, " PRS", MUTED)
        y += LINE + 20

    # --- languages ---
    prompt("tripleu langs")
    langs = d["langs"][:6]
    total_b = sum(n for _, n in d["langs"]) or 1
    cell, gap = 10, 2
    ncells = (W - 2 * MX + gap) // (cell + gap)
    shares = [n / total_b * ncells for _, n in langs]
    counts = [int(s) for s in shares]
    for _ in range(ncells - sum(counts)):
        k = max(range(len(shares)), key=lambda i: shares[i] - counts[i])
        counts[k] += 1
    ci = 0
    for i, cnt in enumerate(counts):
        for _ in range(cnt):
            p.block(MX + ci * (cell + gap), y, cell, cell, LANG_RANK[i % len(LANG_RANK)])
            ci += 1
    y += cell + 14
    for i, (name, n) in enumerate(langs):
        lx = MX + (i % 3) * 272
        ly = y + (i // 3) * (LINE + 8)
        p.block(lx, ly + 3, 8, 8, LANG_RANK[i % len(LANG_RANK)])
        x = p.text(lx + 16, ly, clip_cols(name, 12), FG)
        p.text(x + ADV, ly, f"{100 * n / total_b:.1f}%", MUTED)
    y += ((len(langs) + 2) // 3) * (LINE + 8) + 14

    # --- idle prompt with blinking cursor ---
    x = p.text(MX, y, "❯ ", ELEC)
    p.block(
        x, y, 10, LINE, FG,
        extra='<animate attributeName="opacity" values="1;1;0;0" '
              'keyTimes="0;0.5;0.5;1" dur="1.2s" repeatCount="indefinite"/>',
    )
    y += LINE + 22

    H = y + 10
    title = " TRIPLEU@OMARCHY:~ "
    tw = Painter.width(title)
    p.block(10, 8, 20, 2, BORDER)
    p.text(34, 1, title, MUTED)
    p.block(34 + tw + 4, 8, W - 10 - (34 + tw + 4) - 2, 2, BORDER)
    p.block(10, H - 12, W - 22, 2, BORDER)
    p.block(10, 8, 2, H - 18, BORDER)
    p.block(W - 12, 8, 2, H - 18, BORDER)
    return p.emit(W, H)


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="render from a JSON data file instead of fetching")
    ap.add_argument("--out", default="assets")
    args = ap.parse_args()

    if args.data:
        data = json.load(open(args.data))
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
