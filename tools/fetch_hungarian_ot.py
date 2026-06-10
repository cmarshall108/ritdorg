#!/usr/bin/env python3
"""One-shot: fetch Hungarian Karoli OT chapters into the JSON cache."""
import os, sys, time, logging

# Make ritdorg package importable when running this tool from repo root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from ritdorg.bible_data import OT_BOOKS
import ritdorg.bible_fetcher as bible_fetcher

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

TRANSLATION = "Hungarian"
DELAY = 0.4  # seconds between requests

total = sum(info["chapters"] for info in OT_BOOKS.values())
done = cached = fetched = errors = 0
failed = []

for book, info in OT_BOOKS.items():
    for ch in range(1, info["chapters"] + 1):
        done += 1
        existing = bible_fetcher.get_cached(TRANSLATION, book, ch)
        if existing:
            cached += 1
            continue
        verses = bible_fetcher.get_verses(TRANSLATION, book, ch)
        label = f"[{done}/{total}] {book} {ch}"
        if verses:
            print(f"{label} ✓ ({len(verses)} verses)")
            fetched += 1
        else:
            print(f"{label} ✗ FAILED")
            errors += 1
            failed.append((book, ch))
        time.sleep(DELAY)

print(f"\nDone. cached={cached} fetched={fetched} errors={errors}")
if failed:
    print("Failed:")
    for b, c in failed:
        print(f"  {b} {c}")
    sys.exit(1)
