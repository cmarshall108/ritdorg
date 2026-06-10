#!/usr/bin/env python3
"""
OCR pipeline: extract Bible text from the scanned-image Hungarian PDF
('Teljes 210587_Kerszteny_misszio_BIBLIA_BELIV 2.pdf') and write it
to the JSON cache as a new translation called 'Hungarian-Revised'.

Stages (each is resumable / idempotent):
  1. RENDER : pdftoppm renders pages 1..N to JPEG at 200 DPI
  2. OCR    : tesseract -l hun on every page, output stored as text
  3. PARSE  : merge per-page text into book/chapter/verse JSON files

Usage:
    python tools/ocr_hungarian_pdf.py            # do everything
    python tools/ocr_hungarian_pdf.py render     # render-only
    python tools/ocr_hungarian_pdf.py ocr        # ocr-only
    python tools/ocr_hungarian_pdf.py parse      # parse-only
"""
from __future__ import annotations
import os, re, sys, json, glob, subprocess, shutil
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_PATH   = os.path.join(ROOT, "Teljes 210587_Kerszteny_misszio_BIBLIA_BELIV 2.pdf")
WORK_DIR   = "/tmp/bible_ocr"
IMG_DIR    = os.path.join(WORK_DIR, "pages")
TXT_DIR    = os.path.join(WORK_DIR, "text")
OUT_DIR    = os.path.join(ROOT, "static", "data", "bible", "hungarian-revised")
DPI        = 200
WORKERS    = 6
TOTAL_PAGES_HINT = 1272   # informational only

# ---------------------------------------------------------------------------
# Hungarian header  -> English book name (must match keys in bible_data)
# ---------------------------------------------------------------------------
BOOK_HEADER_MAP = {
    # Pentateuch
    "MÓZES I. KÖNYVE":        "Genesis",
    "MÓZESI. KÖNYVE":         "Genesis",   # OCR glue
    "MÓZES ELSŐ KÖNYVE":      "Genesis",
    "MÓZES II. KÖNYVE":       "Exodus",
    "MÓZESII. KÖNYVE":        "Exodus",
    "MÓZES MÁSODIK KÖNYVE":   "Exodus",
    "MÓZES III. KÖNYVE":      "Leviticus",
    "MÓZESIII. KÖNYVE":       "Leviticus",
    "MÓZES HARMADIK KÖNYVE":  "Leviticus",
    "MÓZES IV. KÖNYVE":       "Numbers",
    "MÓZESIV. KÖNYVE":        "Numbers",
    "MÓZES NEGYEDIK KÖNYVE":  "Numbers",
    "MÓZES V. KÖNYVE":        "Deuteronomy",
    "MÓZESV. KÖNYVE":         "Deuteronomy",
    "MÓZES ÖTÖDIK KÖNYVE":    "Deuteronomy",
    # History
    "JÓZSUÉ KÖNYVE":          "Joshua",
    "BÍRÁK KÖNYVE":           "Judges",
    "RUTH KÖNYVE":            "Ruth",
    "RÚTH KÖNYVE":            "Ruth",
    "SÁMUEL I. KÖNYVE":       "1 Samuel",
    "SÁMUELI. KÖNYVE":        "1 Samuel",   # OCR glue
    "I. SÁMUEL":              "1 Samuel",
    "SÁMUEL II. KÖNYVE":      "2 Samuel",
    "SÁMUELII. KÖNYVE":       "2 Samuel",
    "II. SÁMUEL":             "2 Samuel",
    "KIRÁLYOK I. KÖNYVE":     "1 Kings",
    "KIRÁLYOKI. KÖNYVE":      "1 Kings",
    "I. KIRÁLYOK":            "1 Kings",
    "A KIRÁLYOKRÓL ÍROTT ELSŐ KÖNYV":   "1 Kings",
    "KIRÁLYOK II. KÖNYVE":    "2 Kings",
    "KIRÁLYOKII. KÖNYVE":     "2 Kings",
    "II. KIRÁLYOK":           "2 Kings",
    "A KIRÁLYOKRÓL ÍROTT MÁSODIK KÖNYV":"2 Kings",
    "KRÓNIKÁK I. KÖNYVE":     "1 Chronicles",
    "KRÓNIKÁKI. KÖNYVE":      "1 Chronicles",
    "I. KRÓNIKÁK":            "1 Chronicles",
    "KRÓNIKÁK II. KÖNYVE":    "2 Chronicles",
    "KRÓNIKÁKII. KÖNYVE":     "2 Chronicles",
    "II. KRÓNIKÁK":           "2 Chronicles",
    "EZSDRÁS KÖNYVE":         "Ezra",
    "NEHÉMIÁS KÖNYVE":        "Nehemiah",
    "ESZTER KÖNYVE":          "Esther",
    # Wisdom / Poetry
    "JÓB KÖNYVE":             "Job",
    "ZSOLTÁROK KÖNYVE":       "Psalms",
    "PÉLDABESZÉDEK KÖNYVE":   "Proverbs",
    "PÉLDABESZÉDEK":          "Proverbs",
    "BÖLCS SALAMON PÉLDABESZÉDEI": "Proverbs",
    "PRÉDIKÁTOR KÖNYVE":      "Ecclesiastes",
    "A PRÉDIKÁTOR SALAMON KÖNYVE": "Ecclesiastes",
    "ÉNEKEK ÉNEKE":           "Song of Solomon",
    # Major prophets
    "ÉSAIÁS KÖNYVE":          "Isaiah",
    "ÉZSAIÁS KÖNYVE":         "Isaiah",
    "JEREMIÁS KÖNYVE":        "Jeremiah",
    "JEREMIÁS SIRALMAI":      "Lamentations",
    "EZÉKIEL KÖNYVE":         "Ezekiel",
    "DÁNIEL KÖNYVE":          "Daniel",
    # Minor prophets
    "HÓSEÁS KÖNYVE":          "Hosea",
    "HÓSEÁS PRÓFÉTA KÖNYVE":  "Hosea",
    "JÓEL KÖNYVE":            "Joel",
    "JÓEL PRÓFÉTA KÖNYVE":    "Joel",
    "ÁMÓS KÖNYVE":            "Amos",
    "ÁMÓS PRÓFÉTA KÖNYVE":    "Amos",
    "ABDIÁS KÖNYVE":          "Obadiah",
    "ABDIÁS PRÓFÉTA KÖNYVE":  "Obadiah",
    "JÓNÁS KÖNYVE":           "Jonah",
    "JÓNÁS PRÓFÉTA KÖNYVE":   "Jonah",
    "MIKEÁS KÖNYVE":          "Micah",
    "MIKEÁS PRÓFÉTA KÖNYVE":  "Micah",
    "MIKHEÁS KÖNYVE":         "Micah",
    "NÁHUM KÖNYVE":           "Nahum",
    "NAHUM KÖNYVE":           "Nahum",
    "HABAKUK KÖNYVE":         "Habakkuk",
    "HABAKUK PRÓFÉTA KÖNYVE": "Habakkuk",
    "SOFÓNIÁS KÖNYVE":        "Zephaniah",
    "SOFONIÁS KÖNYVE":        "Zephaniah",
    "AGGEUS KÖNYVE":          "Haggai",
    "ZAKARIÁS KÖNYVE":        "Zechariah",
    "MALAKIÁS KÖNYVE":        "Malachi",
    # New Testament
    "MÁTÉ EVANGÉLIUMA":       "Matthew",
    "MÁRK EVANGÉLIUMA":       "Mark",
    "LUKÁCS EVANGÉLIUMA":     "Luke",
    "JÁNOS EVANGÉLIUMA":      "John",
    "AZ APOSTOLOK CSELEKEDETEI": "Acts",
    "AZ APOSTOLOK CSELEKEDEIEI":  "Acts",   # OCR variant
    "AZ APOSTOLOK CSELEKEDETIEI": "Acts",   # OCR variant
    "APOSTOLOK CSELEKEDETEI":     "Acts",
    "PÁL LEVELE A RÓMABELIEKHEZ":     "Romans",
    "PÁLLEVELE A RÓMABELIEKHEZ":      "Romans",  # OCR glue
    "RÓMAI LEVÉL":                    "Romans",
    "PÁL LEVELE A RÓMAIAKHOZ":        "Romans",
    "RÓMABELIEKHEZ":                  "Romans",
    "RÓMAIAKHOZ":                     "Romans",
    "RÓMABELIEKHEZ ÍRT LEVÉL":        "Romans",
    "PÁL I. LEVELE A KORINTHUSBELIEKHEZ": "1 Corinthians",
    "PÁLI. LEVELE A KORINTHUSBELIEKHEZ":  "1 Corinthians",  # OCR glue
    "I. KORINTHUSI LEVÉL":                "1 Corinthians",
    "KORINTHUSBELIEKHEZ I.":              "1 Corinthians",
    "KORINTHUSIAKHOZ I.":                 "1 Corinthians",
    "I. KORINTHUSBELIEKHEZ":              "1 Corinthians",
    "PÁL II. LEVELE A KORINTHUSBELIEKHEZ":"2 Corinthians",
    "PÁLII. LEVELE A KORINTHUSBELIEKHEZ": "2 Corinthians",  # OCR glue
    "II. KORINTHUSI LEVÉL":               "2 Corinthians",
    "KORINTHUSBELIEKHEZ II.":             "2 Corinthians",
    "KORINTHUSIAKHOZ II.":                "2 Corinthians",
    "II. KORINTHUSBELIEKHEZ":             "2 Corinthians",
    "PÁL LEVELE A GALATÁKHOZ":            "Galatians",
    "GALATA LEVÉL":                       "Galatians",
    "GALÁCZIABELIEKHEZ":                  "Galatians",
    "GALATÁKHOZ":                         "Galatians",
    "PÁL LEVELE AZ EFÉZUSIAKHOZ":         "Ephesians",
    "EFÉZUSI LEVÉL":                      "Ephesians",
    "EFÉZUSBELIEKHEZ":                    "Ephesians",
    "EFEZUSIAKHOZ":                       "Ephesians",
    "PÁL LEVELE A FILIPPIBELIEKHEZ":      "Philippians",
    "PÁLLEVELE A FILIPPIBELIEKHEZ":       "Philippians",
    "FILIPPI LEVÉL":                      "Philippians",
    "FILIPPIBELIEKHEZ":                   "Philippians",
    "FILIPPIEKHEZ":                       "Philippians",
    "PÁL LEVELE A KOLOSSÉBELIEKHEZ":      "Colossians",
    "PÁLLEVELE A KOLOSSÉBELIEKHEZ":       "Colossians",
    "KOLOSSÉI LEVÉL":                     "Colossians",
    "KOLOSSÉBELIEKHEZ":                   "Colossians",
    "KOLOSSÉIAKHOZ":                      "Colossians",
    "PÁL I. LEVELE A THESSALONIKABELIEKHEZ": "1 Thessalonians",
    "PÁLI. LEVELE A THESSALONIKABELIEKHEZ":  "1 Thessalonians",
    "I. THESSALONIKAI LEVÉL":                "1 Thessalonians",
    "THESSALONIKABELIEKHEZ I.":               "1 Thessalonians",
    "THESSZALONIKAIAKHOZ I.":                 "1 Thessalonians",
    "I. THESSALONIKABELIEKHEZ":               "1 Thessalonians",
    "PÁL II. LEVELE A THESSALONIKABELIEKHEZ": "2 Thessalonians",
    "PÁLII. LEVELE A THESSALONIKABELIEKHEZ":  "2 Thessalonians",
    "II. THESSALONIKAI LEVÉL":                "2 Thessalonians",
    "THESSALONIKABELIEKHEZ II.":              "2 Thessalonians",
    "THESSZALONIKAIAKHOZ II.":                "2 Thessalonians",
    "II. THESSALONIKABELIEKHEZ":              "2 Thessalonians",
    "PÁL I. LEVELE TIMÓTHEUSHOZ":  "1 Timothy",
    "PÁLI. LEVELE TIMÓTHEUSHOZ":   "1 Timothy",
    "I. TIMÓTHEUS":                "1 Timothy",
    "TIMÓTHEUSHOZ I.":             "1 Timothy",
    "I. TIMÓTHEUSHOZ":             "1 Timothy",
    "PÁL II. LEVELE TIMÓTHEUSHOZ": "2 Timothy",
    "PÁLII. LEVELE TIMÓTHEUSHOZ":  "2 Timothy",
    "II. TIMÓTHEUS":               "2 Timothy",
    "TIMÓTHEUSHOZ II.":            "2 Timothy",
    "II. TIMÓTHEUSHOZ":            "2 Timothy",
    "TITUSHOZ ÍRT LEVÉL":          "Titus",
    "PÁL LEVELE TITUSHOZ":         "Titus",
    "TITUSHOZ":                    "Titus",
    "FILEMONHOZ ÍRT LEVÉL":        "Philemon",
    "FILEMONHOZÍRT LEVÉL":         "Philemon",  # OCR glue
    "FILEMONHCZ ÍRT LEVÉL":        "Philemon",  # OCR variant
    "PÁL LEVELE FILEMONHOZ":       "Philemon",
    "FILEMONHOZ":                  "Philemon",
    "A ZSIDÓKHOZ ÍRT LEVÉL":       "Hebrews",
    "AZ SIDÓKHOZ ÍRT LEVÉL":       "Hebrews",  # OCR variant
    "AZSIDÓKHOZ ÍRT LEVÉL":        "Hebrews",  # OCR glue
    "AZSIDÓKHOZÍRT LEVÉL":         "Hebrews",  # OCR glue
    "A ZSIDÓKHOZÍRT LEVÉL":        "Hebrews",  # OCR glue
    "ZSIDÓKHOZ ÍRT LEVÉL":         "Hebrews",
    "ZSIDÓKHOZ":                   "Hebrews",
    "JAKAB LEVELE":                "James",
    "JAKAB APOSTOL LEVELE":        "James",
    "PÉTER APOSTOL ELSŐ LEVELE":   "1 Peter",
    "PÉTER ELSŐ LEVELE":           "1 Peter",
    "PÉTER I. LEVELE":             "1 Peter",
    "I. PÉTER LEVELE":             "1 Peter",
    "I. PÉTER":                    "1 Peter",
    "PÉTER APOSTOL MÁSODIK LEVELE":"2 Peter",
    "PÉTER MÁSODIK LEVELE":        "2 Peter",
    "PÉTER II. LEVELE":            "2 Peter",
    "II. PÉTER LEVELE":            "2 Peter",
    "II. PÉTER":                   "2 Peter",
    "JÁNOS APOSTOL ELSŐ LEVELE":   "1 John",
    "JÁNOS ELSŐ LEVELE":           "1 John",
    "JÁNOS I. LEVELE":             "1 John",
    "I. JÁNOS LEVELE":             "1 John",
    "I. JÁNOS":                    "1 John",
    "JÁNOS APOSTOL MÁSODIK LEVELE":"2 John",
    "JÁNOS MÁSODIK LEVELE":        "2 John",
    "JÁNOS II. LEVELE":            "2 John",
    "II. JÁNOS LEVELE":            "2 John",
    "II. JÁNOS":                   "2 John",
    "JÁNOS APOSTOL HARMADIK LEVELE":"3 John",
    "JÁNOS HARMADIK LEVELE":       "3 John",
    "JÁNOS III. LEVELE":           "3 John",
    "III. JÁNOS LEVELE":           "3 John",
    "III. JÁNOS":                  "3 John",
    "JÚDÁS LEVELE":                "Jude",
    "JÚDÁS APOSTOL LEVELE":        "Jude",
    "JELENÉSEK KÖNYVE":            "Revelation",
    "A JELENÉSEK KÖNYVE":          "Revelation",
    # Bare/short header forms used on transition pages
    "I. KORINTHUS":                "1 Corinthians",
    "II. KORINTHUS":               "2 Corinthians",
    "I. THESSALONIKA":             "1 Thessalonians",
    "II. THESSALONIKA":            "2 Thessalonians",
    "I. TIMÓTHEUS":                "1 Timothy",
    "II. TIMÓTHEUS":               "2 Timothy",
    "FILIPPI":                     "Philippians",
    "EFÉZUS":                      "Ephesians",
    "GALATA":                      "Galatians",
    "KOLOSSÉ":                     "Colossians",
    "TITUS":                       "Titus",
    "FILEMON":                     "Philemon",
    "JAKAB":                       "James",
    "ZSIDÓK":                      "Hebrews",
    # Multi-line book-opening titles (joined with single space)
    "MÓZES ELSŐ KÖNYVE A TEREMTÉSRŐL":                                "Genesis",
    "MÓZES MÁSODIK KÖNYVE A ZSIDOKNAK EGYIPTOMBOL VALÓ KIJÖVETELERŐL":"Exodus",
    "MÓZES MÁSODIK KÖNYVE":                                           "Exodus",
    "MÓZES NEGYEDIK KÖNYVE AZ IZRAELITÁK MEGSZÁMLÁLÁSÁRÓL VALÓ KÖNYV":"Numbers",
    "MÓZES NEGYEDIK KÖNYVE":                                          "Numbers",
    "MÓZES ÖTÖDIK KÖNYVE A TÖRVÉNY SUMMAJA":                          "Deuteronomy",
    "MÓZES ÖTÖDIK KÖNYVE":                                            "Deuteronomy",
    "SÁMUEL MÁSODIK KÖNYVE":                                          "2 Samuel",
    "ÉSAIÁS PRÓFÉTA KÖNYVE":                                          "Isaiah",
    "EZÉKIEL PRÓFÉTA KÖNYVE":                                         "Ezekiel",
    "DÁNIEL PRÓFÉTA KÖNYVE":                                          "Daniel",
    "ABDIÁS PRÓFÉTA KÖNYVE":                                          "Obadiah",
    "JÓNÁS PRÓFÉTA KÖNYVE":                                           "Jonah",
    "MIKEÁS PRÓFÉTA KÖNYVE":                                          "Micah",
    "AGGEUS PRÓFÉTA KÖNYVE":                                          "Haggai",
    "MALAKIÁS PRÓFÉTA KÖNYVE":                                        "Malachi",
    "MÁTÉ ÍRÁSA SZERINT VALÓ SZENT EVANGÉLIUM":                       "Matthew",
    "MÁRK ÍRÁSA SZERINT VALÓ SZENT EVANGÉLIUM":                       "Mark",
    "LUKÁCS ÍRÁSA SZERINT VALÓ SZENT EVANGÉLIUM":                     "Luke",
    "JÁNOS ÍRÁSA SZERINT VALÓ SZENT EVANGÉLIUM":                      "John",
    "PÁL APOSTOLNAK A RÓMABELIEKHEZ ÍRT LEVELE":                      "Romans",
    "PÁL APOSTOLNAK A KORINTHUSBELIEKHEZ ÍRT ELSŐ LEVELE":            "1 Corinthians",
    "PÁL APOSTOLNAK A KORINTHUSBELIEKHEZ ÍRT MÁSODIK LEVELE":         "2 Corinthians",
    "PÁL APOSTOLNAK A GALÁCZIABELIEKHEZ ÍRT LEVELE":                  "Galatians",
    "PÁL APOSTOLNAK A GALATÁKHOZ ÍRT LEVELE":                         "Galatians",
    "PÁL APOSTOLNAK AZ EFÉZUSBELIEKHEZ ÍRT LEVELE":                   "Ephesians",
    "PÁL APOSTOLNAK AZ EFÉZUSIAKHOZ ÍRT LEVELE":                      "Ephesians",
    "PÁL APOSTOLNAK A FILIPPIBELIEKHEZ ÍRT LEVELE":                   "Philippians",
    "PÁL APOSTOLNAK A KOLOSSÉBELIEKHEZ ÍRT LEVELE":                   "Colossians",
    "PÁL APOSTOLNAK A THESSALONIKABELIEKHEZ ÍRT ELSŐ LEVELE":         "1 Thessalonians",
    "PÁL APOSTOLNAK A THESSALONIKABELIEKHEZ ÍRT MÁSODIK LEVELE":      "2 Thessalonians",
    "PÁL APOSTOLNAK TIMÓTHEUSHOZ ÍRT ELSŐ LEVELE":                    "1 Timothy",
    "PÁL APOSTOLNAK TIMÓTHEUSHOZ ÍRT MÁSODIK LEVELE":                 "2 Timothy",
    "PÁL APOSTOLNAK TITUSHOZ ÍRT LEVELE":                             "Titus",
    "PÁL APOSTOLNAK FILEMONHOZ ÍRT LEVELE":                           "Philemon",
    "PÁL APOSTOLNAK A ZSIDÓKHOZ ÍRT LEVELE":                          "Hebrews",
    "JAKAB APOSTOLNAK KÖZÖNSÉGES LEVELE":                             "James",
    "PÉTER APOSTOLNAK ELSŐ LEVELE":                                   "1 Peter",
    "PÉTER APOSTOLNAK MÁSODIK LEVELE":                                "2 Peter",
    "JÁNOS APOSTOLNAK ELSŐ LEVELE":                                   "1 John",
    "JÁNOS APOSTOLNAK MÁSODIK LEVELE":                                "2 John",
    "JÁNOS APOSTOLNAK HARMADIK LEVELE":                               "3 John",
    "JÚDÁS APOSTOLNAK LEVELE":                                        "Jude",
    "JÉZUS KRISZTUS JELENÉSEI":                                       "Revelation",
}

# Sort longest first so we match the most specific header
HEADER_KEYS = sorted(BOOK_HEADER_MAP.keys(), key=len, reverse=True)

# Lazy import (so script is usable even without bible_data)
def _book_slug(book: str) -> str:
    sys.path.insert(0, ROOT)
    from ritdorg.ritdorg.bible_data import ALL_BOOKS
    info = ALL_BOOKS.get(book)
    return info["slug"] if info else book.lower().replace(" ", "_")


# ---------------------------------------------------------------------------
# Stage 1: render
# ---------------------------------------------------------------------------
def render_all() -> int:
    os.makedirs(IMG_DIR, exist_ok=True)
    existing = sorted(glob.glob(os.path.join(IMG_DIR, "p-*.jpg")))
    if existing:
        # Get total pages from pdfinfo
        info = subprocess.check_output(["pdfinfo", PDF_PATH], text=True)
        m = re.search(r"^Pages:\s+(\d+)", info, re.M)
        total = int(m.group(1)) if m else TOTAL_PAGES_HINT
        if len(existing) >= total:
            print(f"[render] {len(existing)} pages already rendered, skipping.")
            return total

    print(f"[render] Rendering PDF at {DPI} DPI to {IMG_DIR} ...")
    # Render in chunks of 200 to allow recovery if interrupted
    info = subprocess.check_output(["pdfinfo", PDF_PATH], text=True)
    m = re.search(r"^Pages:\s+(\d+)", info, re.M)
    total = int(m.group(1)) if m else TOTAL_PAGES_HINT

    chunk = 100
    for first in range(1, total + 1, chunk):
        last = min(first + chunk - 1, total)
        # Skip if already done
        sample = os.path.join(IMG_DIR, f"p-{last:04d}.jpg")
        if os.path.exists(sample):
            continue
        print(f"[render]   pages {first}..{last}")
        subprocess.run([
            "pdftoppm", "-r", str(DPI),
            "-f", str(first), "-l", str(last),
            "-jpeg", PDF_PATH,
            os.path.join(IMG_DIR, "p"),
        ], check=True)
    rendered = len(glob.glob(os.path.join(IMG_DIR, "p-*.jpg")))
    print(f"[render] done. {rendered} pages on disk.")
    return total


# ---------------------------------------------------------------------------
# Stage 2: ocr (parallel)
# ---------------------------------------------------------------------------
def _ocr_one(img_path: str) -> tuple[str, bool]:
    page_id = os.path.splitext(os.path.basename(img_path))[0]   # p-0025
    out_base = os.path.join(TXT_DIR, page_id)
    txt_path = out_base + ".txt"
    if os.path.exists(txt_path) and os.path.getsize(txt_path) > 50:
        return page_id, True
    # On macOS /tmp is a symlink to /private/tmp; tesseract fails to open
    # files via /tmp paths.  Resolve to the real path before invoking it.
    real_img = os.path.realpath(img_path)
    real_out = os.path.realpath(os.path.dirname(out_base))
    real_out_base = os.path.join(real_out, os.path.basename(out_base))
    try:
        subprocess.run(
            ["tesseract", real_img, real_out_base, "-l", "hun", "--psm", "1"],
            check=True, capture_output=True,
        )
        return page_id, True
    except subprocess.CalledProcessError:
        return page_id, False


def ocr_all():
    os.makedirs(TXT_DIR, exist_ok=True)
    images = sorted(glob.glob(os.path.join(IMG_DIR, "p-*.jpg")))
    print(f"[ocr] {len(images)} images to process with {WORKERS} workers")
    done, failed = 0, 0
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(_ocr_one, img): img for img in images}
        for i, fut in enumerate(as_completed(futures), 1):
            page_id, ok = fut.result()
            if ok:
                done += 1
            else:
                failed += 1
            if i % 50 == 0 or i == len(images):
                print(f"[ocr]   {i}/{len(images)} done={done} failed={failed}")
    print(f"[ocr] complete. done={done} failed={failed}")


# ---------------------------------------------------------------------------
# Stage 3: parse
# ---------------------------------------------------------------------------
PAGE_HEADER_RE = re.compile(r"^[A-ZÁÉÍÓÖŐÚÜŰ.\s\d]+$")
VERSE_LINE_RE  = re.compile(r"^(\d{1,3})\.\s+(.*)$")
CHAPTER_RE     = re.compile(r"^(\d{1,3})\s+(.*)$")
# Cross-reference suffix: e.g. "Ján. 10,17. 18.", "1Sám. 15,22. Róm. 8,32."
XREF_SUFFIX_RE = re.compile(
    r"\s+(?:[1-3]?\s*[A-ZÉÁÍÓÖŐÚÜŰ][a-zéáíóöőúüű]+\.)"
    r"(?:\s*\d+[,\.]\s*\d+[a-z]?\.?(?:\s*\d+[a-z]?\.?)*)+"
    r"(?:\s+(?:[1-3]?\s*[A-ZÉÁÍÓÖŐÚÜŰ][a-zéáíóöőúüű]+\.)"
    r"(?:\s*\d+[,\.]\s*\d+[a-z]?\.?(?:\s*\d+[a-z]?\.?)*)+)*\s*$"
)


def _strip_xref(text: str) -> str:
    # Repeatedly strip cross-reference suffix(es) at the end of a verse
    for _ in range(3):
        new = XREF_SUFFIX_RE.sub("", text).rstrip()
        if new == text:
            break
        text = new
    return text


def _normalize_book_header(line: str) -> tuple[str | None, list[int]]:
    """If `line` is a book/chapter page header, return (english_book, [chapter_nums]).

    Headers look like:
        "MÓZES I. KÖNYVE 22. 23. 25"      (right page: page# at END)
        "20 MÓZES I. KÖNYVE 17. 18."      (left page: page# at START)
    """
    s = re.sub(r"\s+", " ", line.strip())
    if not s:
        return None, []
    # Strip leading page-number token (left pages); also tolerate stray dot.
    s = re.sub(r"^\d{1,4}\.?\s+", "", s)
    # Strip trailing tokens that look like page-numbers OR OCR-mangled
    # page-numbers (e.g. 'B7i', '347', '811'). Try multiple patterns.
    # Page numbers are bare digits with NO trailing dot (chapter tokens have
    # a trailing dot like "23.").
    s = re.sub(r"\s+\d{1,4}\s*$", "", s)
    # Mangled page-number with at least one letter, e.g. 'B7i'
    s = re.sub(r"\s+(?=\S*[A-Za-z])(?=\S*\d)\S{1,5}\s*$", "", s)
    # Now extract trailing chapter list "MÓZES I. KÖNYVE 22. 23."
    chapters: list[int] = []
    while True:
        m = re.search(r"\s+(\d{1,3})\.\s*$", s)
        if not m:
            break
        chapters.insert(0, int(m.group(1)))
        s = s[:m.start()].rstrip()
    if not s:
        return None, []
    s_up = s.upper()
    for key in HEADER_KEYS:
        if s_up == key or s_up.endswith(key) or s_up.endswith(" " + key):
            # Single-chapter books / book-start pages may not list a chapter
            # number — default to chapter 1.
            return BOOK_HEADER_MAP[key], chapters or [1]
    # Some pages have just BOOK NAME (no chapters listed) on a section divider
    return None, []


def _parse_header_line(line: str):
    """Return list[(book, chapters)] for a page header line.

    Handles transition pages like
       "JÁNOS EVANGÉLIUMA 21. — APOSTOLOK CSELEKEDETEI 1."
       "I. JÁNOS 5. — II. JÁNOS"
       "RÓMAI LEVÉL 16. —I. KORINTHUSI LEVÉL 1."
    by splitting on em-/en-/hyphen-dashes that are surrounded by spaces or
    glued to the next book name.
    """
    # Normalize dash characters
    norm = re.sub(r"\s*[—–-]\s*", " — ", line)
    # Split on em-dash separator
    parts = [p.strip() for p in norm.split(" — ") if p.strip()]
    out = []
    for part in parts:
        bk, ch = _normalize_book_header(part)
        if bk:
            out.append((bk, ch))
    return out


def parse_all():
    text_files = sorted(glob.glob(os.path.join(TXT_DIR, "p-*.txt")))
    if not text_files:
        print("[parse] no text files; run OCR first.")
        return

    bible: dict[str, dict[int, dict[int, str]]] = {}
    cur_book: str | None = None
    cur_chapter: int | None = None
    cur_verse: int | None = None
    pending: list[str] = []

    def flush():
        nonlocal pending
        if cur_book and cur_chapter and cur_verse is not None and pending:
            text = " ".join(pending)
            text = re.sub(r"-\s+", "", text)
            text = re.sub(r"\s+", " ", text).strip()
            text = _strip_xref(text)
            if text:
                bible.setdefault(cur_book, {}).setdefault(cur_chapter, {})[cur_verse] = text
        pending.clear()

    pages_processed = 0
    book_changes = 0
    for tf in text_files:
        with open(tf, "r", encoding="utf-8") as fh:
            raw = fh.read()
        lines = [ln.rstrip() for ln in raw.split("\n")]

        # Find a book-header line within the first 8 non-empty lines.
        # Also try concatenating consecutive uppercase lines for multi-line
        # title-page headers like "MÁTÉ ÍRÁSA SZERINT VALÓ SZENT EVANGÉLIUM".
        header_parts: list[tuple[str, list[int]]] = []
        body_start = 0
        nonempty_indices = [i for i, ln in enumerate(lines) if ln.strip()]
        for k, i in enumerate(nonempty_indices[:8]):
            # Try single line first
            parts = _parse_header_line(lines[i])
            if parts:
                header_parts = parts
                body_start = i + 1
                break
            # Try joined 2-line and 3-line concatenations
            for span in (2, 3):
                if k + span <= len(nonempty_indices):
                    joined = " ".join(lines[nonempty_indices[k + j]].strip()
                                      for j in range(span))
                    parts = _parse_header_line(joined)
                    if parts:
                        header_parts = parts
                        body_start = nonempty_indices[k + span - 1] + 1
                        break
            if header_parts:
                break

        if not header_parts:
            # Title/blank page — emit nothing
            pages_processed += 1
            continue

        header_book, header_chapters = header_parts[0]
        # Optional transition: a second book starts somewhere on this page
        trans_book: str | None = None
        trans_chapters: list[int] = []
        if len(header_parts) > 1:
            trans_book, trans_chapters = header_parts[1]

        if header_book != cur_book:
            flush()
            cur_book = header_book
            cur_chapter = None
            cur_verse = None
            book_changes += 1

        # Build a chapter queue: chapters listed in header that are NOT yet started.
        chapter_queue = [c for c in header_chapters if c != cur_chapter]
        # If cur_chapter isn't listed on this page, the page's content begins
        # with the first queued chapter (continuation from previous page or
        # opening of a new chapter that we missed).
        if header_chapters and cur_chapter not in header_chapters and chapter_queue:
            flush()
            cur_chapter = chapter_queue.pop(0)
            cur_verse = 1   # OCR drop-cap is unreliable; assume verse 1 begins

        for ln in lines[body_start:]:
            stripped = ln.strip()
            if not stripped:
                continue
            # Page footer (page number alone)
            if re.fullmatch(r"\d{1,4}", stripped):
                continue

            # Verse line:  "12. És monda: ..."
            mv = VERSE_LINE_RE.match(stripped)
            if mv:
                vn = int(mv.group(1))
                # Heuristic: verse number went backward AND there are unstarted
                # chapters on this page → drop-cap was missed; advance chapter.
                if (chapter_queue and cur_verse is not None
                    and vn <= cur_verse and vn <= 3):
                    flush()
                    cur_chapter = chapter_queue.pop(0)
                # Or transition to next book on same page
                elif (not chapter_queue and trans_book and trans_chapters
                      and cur_verse is not None and vn <= cur_verse and vn <= 3):
                    flush()
                    cur_book = trans_book
                    book_changes += 1
                    chapter_queue = list(trans_chapters)
                    trans_book = None
                    trans_chapters = []
                    cur_chapter = chapter_queue.pop(0)
                else:
                    flush()
                cur_verse = vn
                pending.append(mv.group(2).strip())
                continue

            # Drop-cap chapter start:  "1 Megjelenék pedig őnéki az Úr a"
            mc = CHAPTER_RE.match(stripped)
            if mc and len(stripped.split()) >= 3:
                ch_num = int(mc.group(1))
                rest = mc.group(2).strip()
                # Drop-caps almost always represent verse 1.  We trust the
                # chapter_queue (chapters listed in this page header) over the
                # OCR'd digit, because the OCR digit can also just be "1" for
                # any chapter.
                if ch_num == 1 and chapter_queue:
                    new_chapter = chapter_queue.pop(0)
                    flush()
                    cur_chapter = new_chapter
                    cur_verse = 1
                    pending.append(rest)
                    continue
                # Transition into a second book on the same page
                if (ch_num == 1 and not chapter_queue
                    and trans_book and trans_chapters):
                    flush()
                    cur_book = trans_book
                    book_changes += 1
                    chapter_queue = list(trans_chapters)
                    trans_book = None
                    trans_chapters = []
                    new_chapter = chapter_queue.pop(0)
                    cur_chapter = new_chapter
                    cur_verse = 1
                    pending.append(rest)
                    continue
                # Otherwise: standalone numbered line that may be a chapter
                # heading (e.g. Psalm number alone on a line).
                if ch_num in chapter_queue:
                    new_chapter = ch_num
                    chapter_queue = [c for c in chapter_queue if c != ch_num]
                    flush()
                    cur_chapter = new_chapter
                    cur_verse = 1
                    pending.append(rest)
                    continue

            # Initial chapter: if cur_chapter is None and we haven't yet
            # committed a verse, this might be body of chapter that began on
            # previous page, OR the first chapter of this book.
            if cur_chapter is None and chapter_queue:
                cur_chapter = chapter_queue.pop(0)
                cur_verse = 1
                pending.append(stripped)
                continue
            if cur_chapter is None:
                # No chapter known — skip (likely book introduction)
                continue

            # Section heading heuristic: short, no digits, no terminal
            # punctuation, only between verses (pending empty).
            words = stripped.split()
            if (not pending
                and len(words) <= 8
                and not re.search(r"\d", stripped)
                and not stripped.endswith((".", "?", "!", '"', '”', "’", ":"))):
                continue

            # Continuation of current verse
            if cur_verse is not None:
                pending.append(stripped)

        pages_processed += 1
    flush()

    # Write JSON
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)
    written = 0
    for book, chapters in bible.items():
        slug = _book_slug(book)
        bdir = os.path.join(OUT_DIR, slug)
        os.makedirs(bdir, exist_ok=True)
        for ch, verses in chapters.items():
            data = {str(k): v for k, v in sorted(verses.items())}
            with open(os.path.join(bdir, f"{ch}.json"), "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            written += 1
    print(f"[parse] pages={pages_processed} book_changes={book_changes} "
          f"books={len(bible)} chapters_written={written}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("all", "render"):
        render_all()
    if stage in ("all", "ocr"):
        ocr_all()
    if stage in ("all", "parse"):
        parse_all()

if __name__ == "__main__":
    main()
