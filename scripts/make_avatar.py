#!/usr/bin/env python3
"""Build the circular animated avatar (APNG) for the README.

The README is plain markdown, so there is no way to script a delay before an
animation starts — the timing has to live inside the image. This writes an APNG
whose first frame is the still profile picture held for HOLD_SECONDS, followed
by the video frames at FPS, looping forever. It reads as a static portrait that
bursts into life every few seconds.

APNG rather than GIF because GIF only has 1-bit transparency, which leaves a
jagged staircase on a circular crop; APNG carries a full alpha channel, so the
circle stays smooth against both the light and dark GitHub themes.

Getting 12.5s of full-frame animation into a sane file size took some measuring.
Frame differencing is useless here (the glow changes nearly every pixel) and
dithering costs more than it saves. What works is quantising to a fixed adaptive
palette shared by every frame — no dither, so no noise for the compressor to
carry — and then running oxipng, which reduces the palettised frames far harder
than Pillow can. At the display size, 64 colours is indistinguishable from full
colour, so the savings go into framerate instead.

Usage:
    python3 scripts/make_avatar.py --video profile-video.mp4 --still pic.png
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 170          # matches the README's display width, so no resampling
FPS = 12
COLORS = 64
HOLD_SECONDS = 10


def ffmpeg_bin() -> str:
    """Prefer a system ffmpeg; imageio-ffmpeg ships one if there isn't any."""
    for candidate in ("ffmpeg", "ffmpeg-linux"):
        found = shutil.which(candidate)
        if found:
            return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("no ffmpeg found; pip install imageio-ffmpeg")


def circle_mask(size: int) -> Image.Image:
    """Anti-aliased circular alpha mask, drawn 4x and downsampled."""
    scale = 4
    big = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(big).ellipse((0, 0, size * scale - 1, size * scale - 1), fill=255)
    return big.resize((size, size), Image.LANCZOS)


def decode(video: Path, size: int, fps: int) -> list[Image.Image]:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(video),
                "-vf", f"fps={fps},scale={size}:{size}:flags=lanczos",
                f"{tmp}/f%04d.png",
            ],
            check=True,
        )
        return [Image.open(p).convert("RGBA").copy() for p in sorted(Path(tmp).glob("*.png"))]


def shared_palette(frames: list[Image.Image], size: int, colors: int) -> Image.Image:
    """One palette for every frame, so the colours don't flicker between them."""
    sample = [f.convert("RGB") for f in frames[::6]] or [frames[0].convert("RGB")]
    montage = Image.new("RGB", (size * len(sample), size))
    for i, f in enumerate(sample):
        montage.paste(f, (i * size, 0))
    return montage.quantize(colors=colors, method=Image.MEDIANCUT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--still", required=True)
    ap.add_argument("--out", default="assets/avatar.png")
    ap.add_argument("--size", type=int, default=SIZE)
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--colors", type=int, default=COLORS)
    ap.add_argument("--hold", type=float, default=HOLD_SECONDS)
    args = ap.parse_args()

    raw = decode(Path(args.video), args.size, args.fps)
    if not raw:
        sys.exit("no frames decoded from video")

    mask = circle_mask(args.size)
    palette = shared_palette(raw, args.size, args.colors)

    def prepare(img: Image.Image) -> Image.Image:
        img = img.convert("RGBA").resize((args.size, args.size), Image.LANCZOS)
        rgb = img.convert("RGB").quantize(palette=palette, dither=Image.NONE).convert("RGB")
        # Multiply the source alpha by the circle, so a still that already has
        # transparency doesn't get its corners painted back in.
        alpha = Image.new("L", img.size, 0)
        alpha.paste(mask, (0, 0), img.getchannel("A"))
        return Image.merge("RGBA", (*rgb.split(), alpha))

    still = prepare(Image.open(args.still))
    frames = [prepare(f) for f in raw]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    per_frame = round(1000 / args.fps)
    still.save(
        out,
        format="PNG",
        save_all=True,
        append_images=frames,
        duration=[int(args.hold * 1000)] + [per_frame] * len(frames),
        loop=0,
        disposal=1,   # restore to background, so alpha doesn't accumulate
        blend=0,      # each frame replaces the last rather than compositing
        optimize=True,
    )
    before = out.stat().st_size / 1024

    try:
        import oxipng

        oxipng.optimize(out, level=6, optimize_alpha=True)
    except ImportError:
        print("note: pip install pyoxipng to shrink this by ~55%", file=sys.stderr)

    after = out.stat().st_size / 1024
    print(
        f"wrote {out}: still held {args.hold:g}s + {len(frames)} frames @ {args.fps}fps, "
        f"{args.colors} colors, {before:.0f} -> {after:.0f} KB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
