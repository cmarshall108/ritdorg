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
python app.py    # serves on http://localhost:80
```

Set `SECRET_KEY` and `ADMIN_PASS_HASH` environment variables before
serving production traffic — see `set_admin_password.py`.

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
