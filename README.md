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
