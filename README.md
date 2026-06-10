# RITDorg — Interactive Bible Reader

[RITDorg](https://www.ritd.org/) is a free, open Bible-study web app from
**Rivers In The Desert, Inc. (RITD)** — a non-profit ministry dedicated to
making the Word of God more accessible in the original Hebrew and Greek.

## Features

- **200+ Bible translations** served from XML sources, with on-demand
  fetching and a local cache.
- **Parallel reading** — view multiple translations side-by-side, verse by
  verse.
- **Interactive Hebrew & Greek lexicon** with Strong's numbers, occurrence
  counts and cross-translation concordance.
- **Verse-by-verse audio** (text-to-speech) for any chapter in any
  supported language.
- **Free Hebrew lessons** — alphabet, vocabulary and grammar taught
  straight from Genesis.
- **Bible study tools** — bookmarks, highlights, notes, reading plans,
  outlines, tags and exportable notebooks.
- **Newsletters, Q&A, video library and downloads** for ongoing teaching
  from RITD.
- **Mobile + offline-friendly** progressive web app (Capacitor iOS /
  Android wrapper supported).

## Tech stack

- Python 3 + Flask
- SQLite (users, sessions, newsletters, study tools)
- Vanilla JS / CSS frontend with a service worker
- XML Bible sources under `bible_data/`

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m ritdorg.app    # serves on http://localhost:8080 (non-root port)
# or: python ritdorg/app.py
# or: flask --app ritdorg.app run --port 8080 --debug
```

A `.env` file (see `.env.example`) is now loaded automatically via
`python-dotenv` if present; this is the easiest way to provide
`SECRET_KEY` / `ADMIN_PASS_HASH` for both dev and the production paths.

Set `SECRET_KEY` and `ADMIN_PASS_HASH` environment variables (or use
`.env`) before serving production traffic — see `ritdorg/set_admin_password.py`.

## Keeping the server online + automatic log capture

- Use `./scripts/auto_redeploy.sh` (run under `screen`, `tmux`, or `nohup … &`) for a
  self-healing runner: it watches the git branch for updates (every 3 h by
  default) and, more importantly, keeps a restart-forever "keeper" subshell
  around the uvicorn process. If the web server crashes for *any* reason
  (exception, OOM, import error, etc.) it is automatically restarted within
  ~5 seconds.
- **All logs are captured automatically** to `data/server.log` (rotated at
  ~10 MiB, keeping 5 backups). This includes:
  - uvicorn access/error logs
  - every `logger.*`, `app.logger.*`, `print()` and traceback from the
    application and all imported modules (`bible_fetcher`, `auth`, study
    tools, …)
  - start/stop banners with timestamps so you can see restart history
- The Python side (`ritdorg/app.py`) also forces a `RotatingFileHandler` on the root
  logger at import time, so even a direct `python ritdorg/app.py` or `python -m ritdorg.app`
  run will persist its logs.
- `./scripts/deploy.sh` also tees its output into the same log file for consistency.
- Override `CHECK_INTERVAL_SECONDS`, `APP_PORT`, `APP_HOST` via the
  environment if needed. On first run (or after a pull) it installs deps.
- A `.env` file is loaded automatically (python-dotenv). The deploy
  scripts set `RITD_NO_CONSOLE_LOG=1` internally to avoid duplicate log
  lines in `data/server.log` (RotatingFileHandler is authoritative).

Example persistent launch (as root for port 80):

    sudo nohup ./scripts/auto_redeploy.sh >> data/auto_redeploy.out 2>&1 &

Then `tail -f data/server.log` to watch everything the server ever emitted.

## SEO / search-engine indexing

- `/sitemap.xml` is generated dynamically from the live newsletter list
  plus all public pages.
- `/robots.txt` allows everything except `/admin`, `/api/` and uploaded
  videos, and points to the sitemap.
- All public templates emit `<meta name="description">`, canonical URL,
  Open Graph and Twitter card tags via `templates/_seo.html`.
- The home page also exposes JSON-LD structured data describing the
  `WebSite` (with a `SearchAction`) and the `Organization`.

## License & contact

© Rivers In The Desert, Inc. — Cameron, NC.
Email: <hebrew@ritd.org>
