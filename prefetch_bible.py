#!/usr/bin/env python3
"""
Pre-fetch all New Testament Bible data and cache it as JSON files.

Usage:
    python prefetch_bible.py                  # Fetch everything
    python prefetch_bible.py NIV              # Fetch only NIV
    python prefetch_bible.py KJV ESV          # Fetch KJV and ESV
    python prefetch_bible.py --hebrew-only    # Fetch only Hebrew
    python prefetch_bible.py --migrate        # Export hardcoded data to cache

This populates  static/data/bible/{translation}/{book}/{chapter}.json
so that the web app can serve verses instantly without live fetching.
"""

import sys
import time
import logging

from bible_data import NT_BOOKS, NT_TRANSLATIONS
import bible_fetcher

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def prefetch(translations=None):
    """Fetch and cache all chapters for the given translations."""
    if translations is None:
        translations = NT_TRANSLATIONS

    total_chapters = sum(info["chapters"] for info in NT_BOOKS.values())
    total = total_chapters * len(translations)
    done = 0
    cached = 0
    fetched = 0
    errors = 0

    for translation in translations:
        print(f"\n{'=' * 60}")
        print(f"  Fetching: {translation}")
        print(f"{'=' * 60}")

        for book, info in NT_BOOKS.items():
            for chapter in range(1, info["chapters"] + 1):
                done += 1
                label = f"[{done}/{total}] {translation} — {book} {chapter}"

                # Check if already cached
                existing = bible_fetcher.get_cached(translation, book, chapter)
                if existing:
                    print(f"{label} … cached ({len(existing)} verses)")
                    cached += 1
                    continue

                print(f"{label} … fetching", end="", flush=True)
                verses = bible_fetcher.get_verses(translation, book, chapter)

                if verses:
                    print(f" ✓ ({len(verses)} verses)")
                    fetched += 1
                else:
                    print(" ✗ FAILED")
                    errors += 1

                # Rate-limit between external requests
                if translation == "Hebrew":
                    time.sleep(0.2)   # Hebrew already has per-verse delays
                else:
                    time.sleep(1.0)   # Be respectful to BibleHub / bible-api

    print(f"\n{'=' * 60}")
    print(f"  Done!")
    print(f"  Already cached : {cached}")
    print(f"  Newly fetched  : {fetched}")
    print(f"  Errors         : {errors}")
    print(f"  Total          : {done}")
    print(f"{'=' * 60}\n")


def migrate_hardcoded():
    """Export the existing hardcoded translations.py data to JSON cache."""
    print("Exporting hardcoded data from translations.py to JSON cache …")
    bible_fetcher.export_hardcoded_to_cache()
    print("Done!")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--migrate" in args:
        migrate_hardcoded()
        sys.exit(0)

    if "--hebrew-only" in args:
        prefetch(["Hebrew"])
    elif args:
        # Treat remaining args as translation codes
        valid = [t for t in args if t in bible_fetcher.TRANSLATION_SOURCES]
        if not valid:
            print(f"Unknown translations: {args}")
            print(f"Available: {', '.join(NT_TRANSLATIONS)}")
            sys.exit(1)
        prefetch(valid)
    else:
        prefetch()
