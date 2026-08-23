#!/usr/bin/env python3
"""Render the profile stat cards as static SVGs.

Everything the README displays is generated here and committed to the repo, so
the cards are plain files on a CDN we control. No third-party widget service
sits between a visitor and the page, which means there is nothing to rate-limit,
nothing to 404, and nothing that needs hiding when someone else's quota runs
out. If the API call fails, the previous cards simply stay in place.

Usage:
    python3 scripts/gen_cards.py                  # fetch live, write assets/
    python3 scripts/gen_cards.py --fixture        # render sample data (offline)
    python3 scripts/gen_cards.py --out some/dir   # write elsewhere

Requires no third-party packages: stdlib only, so CI needs no install step.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from html import escape
from pathlib import Path

USER = os.environ.get("PROFILE_USER", "TripleU613")
API = "https://api.github.com"

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,"
    "'Noto Sans',Arial,sans-serif"
)
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace"

THEMES = {
    "dark": {
        "bg": "#08090c",
        "panel": "#0d1117",
        "border": "#1f2530",
        "title": "#f0f6fc",
        "text": "#c9d1d9",
        "muted": "#6e7681",
        "value": "#ffffff",
        "accent": "#0066ff",
        "accent2": "#22d3ee",
        "track": "#161b22",
    },
    "light": {
        "bg": "#ffffff",
        "panel": "#ffffff",
        "border": "#d8dee4",
        "title": "#1f2328",
        "text": "#3d444d",
        "muted": "#818b98",
        "value": "#0a0c10",
        "accent": "#0053d6",
        "accent2": "#0891b2",
        "track": "#eef1f4",
    },
}

# GitHub linguist colours for the languages that actually show up here, with a
# fallback for anything new.
LANG_COLORS = {
    "Rust": "#dea584",
    "Python": "#3572A5",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "Kotlin": "#A97BFF",
    "Shell": "#89e051",
    "C": "#555555",
    "C++": "#f34b7d",
    "Java": "#b07219",
    "Go": "#00ADD8",
    "HTML": "#e34c26",
    "CSS": "#663399",
    "Dockerfile": "#384d54",
    "Makefile": "#427819",
    "Nix": "#7e7eff",
    "Lua": "#000080",
    "Swift": "#F05138",
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "Vue": "#41b883",
    "Svelte": "#ff3e00",
    "Astro": "#ff5a03",
    "Zig": "#ec915c",
    "Assembly": "#6E4C13",
    "SCSS": "#c6538c",
    "Smali": "#4a5f7a",
    "Batchfile": "#C1F12E",
    "PowerShell": "#012456",
}
FALLBACK_COLORS = ["#58a6ff", "#ff7b72", "#7ee787", "#d2a8ff", "#ffa657", "#79c0ff"]


def lang_color(name: str, index: int) -> str:
    return LANG_COLORS.get(name, FALLBACK_COLORS[index % len(FALLBACK_COLORS)])


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
    while page <= 10:  # 1000 repos is far past anything we need
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
    """Pull the numbers the cards need. Raises on any API failure."""
    user = api(f"/users/{USER}")
    repos = paged(f"/users/{USER}/repos?type=owner&sort=pushed")
    # Drop private repos explicitly. The default Actions token only ever sees
    # public ones, but these cards are committed to a public README — so if this
    # is ever run with a broader PAT, a private repo name still can't leak out.
    own = [r for r in repos if not r.get("fork") and not r.get("private")]

    stars = sum(r.get("stargazers_count", 0) for r in own)
    forks = sum(r.get("forks_count", 0) for r in own)

    # Bytes-per-language across every non-fork repo, so the breakdown reflects
    # what was actually written rather than one label per repo.
    totals: dict[str, int] = {}
    for r in own:
        try:
            for lang, count in (api(f"/repos/{USER}/{r['name']}/languages") or {}).items():
                totals[lang] = totals.get(lang, 0) + count
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
            print(f"  ! languages for {r['name']}: {exc}", file=sys.stderr)

    top = sorted(
        (r for r in own if not r.get("archived")),
        key=lambda r: (r.get("stargazers_count", 0), r.get("pushed_at", "")),
        reverse=True,
    )[:4]

    return {
        "name": user.get("name") or USER,
        "since": (user.get("created_at") or "")[:4],
        "repos": len(own),
        "stars": stars,
        "forks": forks,
        "followers": user.get("followers", 0),
        "languages": sorted(totals.items(), key=lambda kv: kv[1], reverse=True),
        "top": [
            {
                "name": r["name"],
                "desc": r.get("description") or "",
                "stars": r.get("stargazers_count", 0),
                "lang": r.get("language") or "",
            }
            for r in top
        ],
    }


FIXTURE = {
    "name": "TripleU",
    "since": "2023",
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
        {
            "name": "TripleUMDM_Public",
            "desc": "Public landing page for TripleUMDM",
            "stars": 25,
            "lang": "HTML",
        },
        {
            "name": "Unitree-Go1-Pro-Almost-Full-Backup-",
            "desc": "Near-complete Unitree Go1 Pro backup (Pi + both Jetson Nanos)",
            "stars": 3,
            "lang": "Python",
        },
        {
            "name": "claude-teleport",
            "desc": "A Claude Code skill that moves your conversation to another machine",
            "stars": 2,
            "lang": "Shell",
        },
        {
            "name": "mirrorbot-gplay",
            "desc": "Google Play APK downloader server for MirrorBot",
            "stars": 2,
            "lang": "Python",
        },
    ],
}


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------


def human(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".0k", "k")
    return str(n)


def clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,.;:-") + "…"


def head(width: int, height: int, t: dict, uid: str) -> str:
    """Card shell: rounded panel, hairline border, accent rule along the top."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
     viewBox="0 0 {width} {height}" role="img" fill="none">
  <defs>
    <linearGradient id="accent-{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{t['accent']}"/>
      <stop offset="100%" stop-color="{t['accent2']}"/>
    </linearGradient>
    <clipPath id="card-{uid}">
      <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12"/>
    </clipPath>
  </defs>
  <g clip-path="url(#card-{uid})">
    <rect width="{width}" height="{height}" fill="{t['panel']}"/>
    <rect width="{width}" height="3" fill="url(#accent-{uid})"/>
  </g>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12"
        stroke="{t['border']}"/>
"""


def label(x: int, y: int, text: str, t: dict) -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="10" font-weight="600"'
        f' letter-spacing="1.1" fill="{t["muted"]}">{escape(text.upper())}</text>'
    )


def title(x: int, y: int, text: str, t: dict) -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="15" font-weight="700"'
        f' fill="{t["title"]}">{escape(text)}</text>'
    )


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

W = 430
H = 195


def card_stats(d: dict, t: dict, uid: str) -> str:
    s = [head(W, H, t, uid)]
    s.append(title(24, 40, "Build log", t))
    s.append(label(24, 58, f"github.com/{USER} · since {d['since']}", t))

    cells = [
        ("Public repos", human(d["repos"])),
        ("Stars earned", human(d["stars"])),
        ("Forks", human(d["forks"])),
        ("Followers", human(d["followers"])),
    ]
    # 2x2 grid. Each cell gets a hairline left rule in the accent colour so the
    # numbers read as a set rather than four loose labels.
    for i, (name, value) in enumerate(cells):
        cx = 24 + (i % 2) * 200
        cy = 92 + (i // 2) * 54
        s.append(
            f'<rect x="{cx}" y="{cy - 14}" width="2" height="34" rx="1"'
            f' fill="url(#accent-{uid})" opacity="0.75"/>'
        )
        s.append(
            f'<text x="{cx + 14}" y="{cy + 6}" font-family="{MONO}" font-size="22"'
            f' font-weight="700" fill="{t["value"]}">{escape(value)}</text>'
        )
        s.append(
            f'<text x="{cx + 14}" y="{cy + 20}" font-family="{FONT}" font-size="10"'
            f' font-weight="500" fill="{t["muted"]}">{escape(name)}</text>'
        )

    s.append("</svg>")
    return "\n".join(s)


def card_languages(d: dict, t: dict, uid: str) -> str:
    s = [head(W, H, t, uid)]
    s.append(title(24, 40, "What I actually write", t))
    s.append(label(24, 58, "by bytes · public non-fork repos", t))

    langs = d["languages"][:6]
    total = sum(v for _, v in d["languages"]) or 1

    # Stacked bar. Segments below ~1.2% are dropped rather than rendered as a
    # sliver too thin to see or click.
    bar_x, bar_y, bar_w = 24, 76, W - 48
    s.append(
        f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="9" rx="4.5"'
        f' fill="{t["track"]}"/>'
    )
    s.append(f'<g clip-path="url(#langbar-{uid})">')
    s.append(
        f'<defs><clipPath id="langbar-{uid}"><rect x="{bar_x}" y="{bar_y}"'
        f' width="{bar_w}" height="9" rx="4.5"/></clipPath></defs>'
    )
    offset = 0.0
    for i, (name, value) in enumerate(langs):
        seg = bar_w * value / total
        if seg < bar_w * 0.012:
            continue
        s.append(
            f'<rect x="{bar_x + offset:.1f}" y="{bar_y}" width="{seg:.1f}" height="9"'
            f' fill="{lang_color(name, i)}"/>'
        )
        offset += seg
    s.append("</g>")

    # Legend, two columns of three.
    for i, (name, value) in enumerate(langs):
        pct = 100.0 * value / total
        lx = 24 + (i % 2) * 205
        ly = 110 + (i // 2) * 26
        s.append(
            f'<circle cx="{lx + 4}" cy="{ly - 4}" r="4.5"'
            f' fill="{lang_color(name, i)}"/>'
        )
        s.append(
            f'<text x="{lx + 16}" y="{ly}" font-family="{FONT}" font-size="12"'
            f' font-weight="500" fill="{t["text"]}">{escape(clip(name, 14))}</text>'
        )
        s.append(
            f'<text x="{lx + 178}" y="{ly}" text-anchor="end" font-family="{MONO}"'
            f' font-size="11" fill="{t["muted"]}">{pct:.1f}%</text>'
        )

    s.append("</svg>")
    return "\n".join(s)


TW = 880
TH = 196


def card_top(d: dict, t: dict, uid: str) -> str:
    s = [head(TW, TH, t, uid)]
    s.append(title(24, 40, "Currently shipping", t))
    s.append(label(24, 58, "most-starred active repositories", t))

    for i, r in enumerate(d["top"][:4]):
        rx = 24 + (i % 2) * 424
        ry = 86 + (i // 2) * 56
        s.append(
            f'<rect x="{rx}" y="{ry - 18}" width="408" height="46" rx="8"'
            f' fill="{t["track"]}" stroke="{t["border"]}"/>'
        )
        s.append(
            f'<text x="{rx + 14}" y="{ry}" font-family="{MONO}" font-size="12.5"'
            f' font-weight="700" fill="{t["title"]}">{escape(clip(r["name"], 30))}</text>'
        )
        s.append(
            f'<text x="{rx + 394}" y="{ry}" text-anchor="end" font-family="{MONO}"'
            f' font-size="11" fill="{t["muted"]}">★ {r["stars"]}</text>'
        )
        s.append(
            f'<text x="{rx + 14}" y="{ry + 17}" font-family="{FONT}" font-size="10.5"'
            f' fill="{t["muted"]}">{escape(clip(r["desc"] or r["lang"] or "—", 62))}</text>'
        )

    s.append("</svg>")
    return "\n".join(s)


CARDS = {"stats": card_stats, "languages": card_languages, "top-repos": card_top}


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", action="store_true", help="render sample data offline")
    ap.add_argument("--out", default="assets", help="output directory")
    args = ap.parse_args()

    if args.fixture:
        data = FIXTURE
        print("rendering from fixture")
    else:
        try:
            data = collect()
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError) as exc:
            # Leave the committed cards untouched. A failed refresh shows the
            # last good numbers rather than a broken image.
            print(f"fetch failed, keeping existing cards: {exc}", file=sys.stderr)
            return 1
        print(
            f"fetched {data['repos']} repos, {data['stars']} stars, "
            f"{len(data['languages'])} languages"
        )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, render in CARDS.items():
        for theme_name, theme in THEMES.items():
            path = out / f"{name}-{theme_name}.svg"
            path.write_text(render(data, theme, f"{name}-{theme_name}") + "\n")
            print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
