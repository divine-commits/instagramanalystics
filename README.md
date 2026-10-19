# Post lab fetcher

Pulls your Instagram post Insights with the official Instagram API (Instagram Login, `graph.instagram.com`) so you can paste them into your post lab.

No scraping and no Instagram password. Your access token lives only in `.env` on your computer, and that file is never committed.

## Phase 1 commands

| Command | What it does |
|---|---|
| `lab setup` | Paste your access token (hidden) and save it to `.env` |
| `lab check` | Confirm the token works; shows account type (Creator/Business) and token expiry |
| `lab refresh` | Renew the token for another 60 days (token must be at least 24 hours old and not yet expired) |
| `lab recent` | List your 10 most recent posts |
| `lab test <link>` | Test one post: is it in the media list, which Insights metrics come back |

On Windows type `lab …`; on Mac type `./lab …` from inside this folder.

Requires Python 3.9 or newer. Nothing else to install.

## Reel maker

Turns your own clips into silent 9:16 reels (1080x1920, 7 seconds max, no audio track) with text on top, ready for you to add music in Instagram.

1. Put your clips in `reels/clips/`
2. `reels/plan.csv` already has all 60 reels written (2 a day from 2026-10-20 to 2026-11-18): AM = your story, PM = alternating Filipino talent / clients, each with text, a caption and a `shot_idea`. Fill in the `clip` column with the file name for each one. Optional: where to start in it, the hook text (`text1`) and the second line (`text2`, shown from the halfway point). Use `|` inside text to force a line break.
3. Run `python reels/make_reels.py` (or `python reels/make_reels.py 1-10 --preview` for a few, plus still previews)

Finished reels go in `reels/out/`. Needs Pillow (`pip install pillow`) and ffmpeg.
