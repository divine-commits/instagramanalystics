#!/usr/bin/env python3
"""Reel maker: turns your own clips into silent 9:16 reels with text on top.

Every reel is:
  - 1080x1920 (9:16), 30 fps, H.264 MP4
  - 7 seconds or less
  - no audio track at all (so you can add music in Instagram)
  - up to two text beats: text1 shows first, text2 takes over halfway

How to use:
  1. Put your clips in reels/clips/
  2. Fill in reels/plan.csv (one row per reel)
  3. Run:  python reels/make_reels.py            (all rows)
           python reels/make_reels.py 1-5        (rows with id 1 to 5)
           python reels/make_reels.py --preview  (also saves a still per reel)
  Finished reels land in reels/out/

plan.csv columns:
  id        number used in the output file name
  date      posting date (YYYY-MM-DD), only used in the file name
  slot      AM or PM, only used in the file name
  clip      file name inside reels/clips/
  start     second in the clip to start from (blank = 0)
  length    reel length in seconds (blank = 7, never more than 7)
  text1     hook text, shown from the start
  text2     second text, shown from the halfway point (blank = keep text1)
  caption   your post caption (not put on the video, just kept with the plan)

Needs Python 3.9+, Pillow (pip install pillow) and ffmpeg on your PATH.
"""

import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CLIPS = HERE / "clips"
OUT = HERE / "out"
PLAN = HERE / "plan.csv"

W, H, FPS = 1080, 1920, 30
MAX_LEN = 7.0

# Instagram covers the top ~220px (account bar) and bottom ~420px (caption,
# buttons), plus the right edge (like/comment/share). Text stays inside this box.
SAFE_TOP, SAFE_BOTTOM = 260, H - 480
SAFE_LEFT, SAFE_RIGHT = 90, W - 150

FONT_SIZE = 76
LINE_GAP = 14
PAD_X, PAD_Y = 34, 18
MAX_TEXT_W = SAFE_RIGHT - SAFE_LEFT - 2 * PAD_X

FONT_CANDIDATES = [
    HERE / "fonts" / "font.ttf",
    HERE / "fonts" / "font.otf",
    Path("/usr/share/fonts/opentype/inter/InterDisplay-ExtraBold.otf"),
    Path("/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"),
    Path("C:/Windows/Fonts/seguibl.ttf"),      # Segoe UI Black
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def load_font():
    for p in FONT_CANDIDATES:
        if p.exists():
            return ImageFont.truetype(str(p), FONT_SIZE)
    sys.exit("No bold font found. Put a .ttf at reels/fonts/font.ttf")


def wrap(draw, text, font):
    """Split text into lines that fit MAX_TEXT_W. A '|' forces a line break."""
    lines = []
    for para in text.split("|"):
        words, line = para.split(), ""
        for word in words:
            test = f"{line} {word}".strip()
            if draw.textlength(test, font=font) <= MAX_TEXT_W or not line:
                line = test
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
    return lines


def text_card(text, font, path):
    """Transparent 1080x1920 PNG: white text on rounded dark pills, centred."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    lines = wrap(draw, text, font)
    asc, desc = font.getmetrics()
    line_h = asc + desc + 2 * PAD_Y
    block_h = len(lines) * line_h + (len(lines) - 1) * LINE_GAP
    # Sit the block a little above the middle of the safe zone.
    y = SAFE_TOP + int((SAFE_BOTTOM - SAFE_TOP - block_h) * 0.42)
    cx = (SAFE_LEFT + SAFE_RIGHT) // 2
    for line in lines:
        tw = draw.textlength(line, font=font)
        x0 = int(cx - tw / 2 - PAD_X)
        x1 = int(cx + tw / 2 + PAD_X)
        draw.rounded_rectangle([x0, y, x1, y + line_h], radius=22,
                               fill=(0, 0, 0, 165))
        draw.text((cx, y + PAD_Y), line, font=font, fill="white", anchor="mt")
        y += line_h + LINE_GAP
    img.save(path)


def clip_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def render(row, font, tmp, preview):
    rid = row["id"].strip()
    if not (row.get("clip") or "").strip():
        return False                    # slot not filled in yet
    clip = CLIPS / row["clip"].strip()
    if not clip.exists():
        print(f"  #{rid}: clip not found: {clip.name} (skipped)")
        return False

    start = float(row.get("start") or 0)
    length = min(float(row.get("length") or MAX_LEN), MAX_LEN)
    have = clip_duration(clip) - start
    if have <= 0.5:
        print(f"  #{rid}: start {start}s is past the end of {clip.name} (skipped)")
        return False
    length = min(length, have)

    text1 = (row.get("text1") or "").strip()
    text2 = (row.get("text2") or "").strip()
    half = round(length / 2, 2)

    inputs = ["-ss", str(start), "-t", str(length), "-i", str(clip)]
    # Scale to fill 9:16, centre-crop, lock frame rate and pixel format.
    chain = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
             f"crop={W}:{H},fps={FPS},setsar=1,format=yuv420p[v0]")
    last = "v0"
    beats = []
    if text1:
        beats.append((text1, 0, half if text2 else length))
    if text2:
        beats.append((text2, half, length))
    for i, (text, t0, t1) in enumerate(beats, start=1):
        png = Path(tmp) / f"{rid}_{i}.png"
        text_card(text, font, png)
        inputs += ["-loop", "1", "-t", str(length), "-i", str(png)]
        fade_in = f"fade=t=in:st={t0}:d=0.25:alpha=1"
        chain += (f";[{i}:v]format=rgba,{fade_in}[t{i}]"
                  f";[{last}][t{i}]overlay=0:0:"
                  f"enable='between(t,{t0},{t1})'[v{i}]")
        last = f"v{i}"

    name = f"{int(rid):02d}"
    if row.get("date"):
        name += f"_{row['date'].strip()}"
    if row.get("slot"):
        name += f"_{row['slot'].strip().upper()}"
    out = OUT / f"reel_{name}.mp4"

    cmd = ["ffmpeg", "-y", "-v", "error", *inputs,
           "-filter_complex", chain, "-map", f"[{last}]",
           "-an",                      # no audio track
           "-t", str(length),
           "-c:v", "libx264", "-preset", "slow", "-crf", "19",
           "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)

    if preview:
        still = OUT / "previews" / f"reel_{name}.jpg"
        still.parent.mkdir(exist_ok=True)
        at = half + 0.6 if text2 else 1.0
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(min(at, length - 0.1)),
                        "-i", str(out), "-frames:v", "1", "-q:v", "3", str(still)],
                       check=True)
    print(f"  #{rid}: {out.name}  ({length:.1f}s)")
    return True


def parse_range(arg):
    if "-" in arg:
        a, b = arg.split("-", 1)
        return set(range(int(a), int(b) + 1))
    return {int(x) for x in arg.split(",")}


def main():
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is not installed or not on your PATH.")
    args = sys.argv[1:]
    preview = "--preview" in args
    args = [a for a in args if a != "--preview"]
    wanted = parse_range(args[0]) if args else None

    with PLAN.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("id") or "").strip()]
    if wanted:
        rows = [r for r in rows if int(r["id"]) in wanted]

    OUT.mkdir(exist_ok=True)
    font = load_font()
    done = 0
    with tempfile.TemporaryDirectory() as tmp:
        for row in rows:
            done += render(row, font, tmp, preview)
    print(f"Made {done} of {len(rows)} reels in {OUT}")


if __name__ == "__main__":
    main()
