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

`reels/plan.csv` has all 60 reels (2 a day from 2026-10-20 to 2026-11-18): AM = your story (@thenotsodivine voice: lowercase hooks, no on-screen CTA), PM = alternating Filipino talent / clients (Staffed). Each row has the hook text, a caption with CTA, and the clip picked for it from your Google Drive (`folder` and `clip` file name).

On Windows, if Google Drive for desktop is installed, point it at the two shared folders:

```
reels --source "G:\My Drive\Vlog" --source "G:\My Drive\Divine Personal Brand"
```

It finds each clip by file name, cuts 7 seconds from the `start` second, crops to 9:16, fixes HDR phone colours, adds the text and removes the audio. Add reel numbers to make just some (`reels 1-5 --source ...`) and `--preview` for a still of each. Finished reels go in `reels/out/`.

Needs Python, Pillow (installed automatically) and ffmpeg (`winget install Gyan.FFmpeg`). On Mac: `python3 reels/make_reels.py --source ...`.
