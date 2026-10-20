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
           python reels/make_reels.py --source "G:/My Drive/Vlog"
                 (finds each clip by file name anywhere in that folder)
  Finished reels land in reels/out/

plan.csv columns:
  id        number used in the output file name
  date      posting date (YYYY-MM-DD), only used in the file name
  slot      AM or PM, only used in the file name
  pillar    story / talent / clients (just for planning)
  vibe      the kind of clip that suits this reel (just for planning)
  clip      file name, in reels/clips/ or anywhere under a --source folder
  start     second in the clip to start from (blank = 0)
  length    reel length in seconds (blank = 7, never more than 7)
  text1     hook text, shown from the start
  text2     punchline, shown from 2.5s (blank = text1 stays for the whole reel)
  split     optional: second the punchline appears (default 2.5)
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
    # Long hooks: step the size down so they stay within 4 lines.
    size = FONT_SIZE
    while len(lines) > 4 and size > 58 and hasattr(font, "font_variant"):
        size -= 4
        font = font.font_variant(size=size)
        lines = wrap(draw, text, font)
    asc, desc = font.getmetrics()
    line_h = asc + desc + 2 * PAD_Y
    block_h = len(lines) * line_h + (len(lines) - 1) * LINE_GAP
    # Centre the block in the lower-middle (around 61% down) so it sits under
    # faces in selfie clips but stays clear of Instagram's caption area.
    y = min(int(H * 0.61 - block_h / 2), SAFE_BOTTOM - block_h)
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


IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def find_clip(name, sources):
    """Look for the clip in reels/clips/ first, then anywhere under each --source folder."""
    direct = CLIPS / name
    if direct.exists():
        return direct
    for src in sources:
        for hit in Path(src).rglob(name):
            return hit
    return None


def color_transfer(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=color_transfer", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True)
    return out.stdout.strip()


def has_filter(name):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                         capture_output=True, text=True)
    return f" {name} " in out.stdout


def render(row, font, tmp, preview, sources=()):
    rid = row["id"].strip()
    name_in_plan = (row.get("clip") or "").strip()
    if not name_in_plan:
        return False                    # slot not filled in yet
    clip = find_clip(name_in_plan, sources)
    if clip is None:
        print(f"  #{rid}: clip not found: {name_in_plan} (skipped)")
        return False
    is_image = clip.suffix.lower() in IMAGE_EXT

    start = float(row.get("start") or 0)
    length = min(float(row.get("length") or MAX_LEN), MAX_LEN)
    if not is_image:
        have = clip_duration(clip) - start
        if have <= 0.5:
            print(f"  #{rid}: start {start}s is past the end of {clip.name} (skipped)")
            return False
        length = min(length, have)

    text1 = (row.get("text1") or "").strip()
    text2 = (row.get("text2") or "").strip()
    # The second line comes in early (2.5s) so the punchline lands before the loop.
    half = round(min(float(row.get("split") or 2.5), length / 2), 2)

    if is_image:
        # A still (used for previews): slow push-in so it still feels like video.
        frames = int(length * FPS)
        inputs = ["-loop", "1", "-t", str(length), "-i", str(clip)]
        chain = (f"[0:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
                 f"crop={W*2}:{H*2},zoompan=z='1+0.06*on/{frames}':d=1:"
                 f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
                 f"setsar=1,format=yuv420p[v0]")
    else:
        inputs = ["-ss", str(start), "-t", str(length), "-i", str(clip)]
        # iPhone/Android "HDR" video looks washed out unless it's converted to normal colour.
        tonemap = ""
        if color_transfer(clip) in ("arib-std-b67", "smpte2084") and has_filter("zscale"):
            tonemap = ("zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,"
                       "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,")
        # Scale to fill 9:16, centre-crop, lock frame rate and pixel format.
        chain = (f"[0:v]{tonemap}scale={W}:{H}:force_original_aspect_ratio=increase,"
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
    sources = []
    while "--source" in args:
        i = args.index("--source")
        sources.append(args[i + 1])
        del args[i:i + 2]
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
            done += render(row, font, tmp, preview, sources)
    print(f"Made {done} of {len(rows)} reels in {OUT}")


if __name__ == "__main__":
    main()
