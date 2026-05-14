#!/usr/bin/env python3
"""
OCR pipeline: extract Bible text from the scanned-image Kenyah New
Testament PDF ('Kenyah-New-Testament-(print).pdf') and write it to the
JSON cache as a new translation called 'Kenyah'.

Stages (each is resumable / idempotent):
  1. RENDER : pdftoppm renders pages 1..N to JPEG at 250 DPI
  2. OCR    : tesseract -l ind on every page (Indonesian model handles
              the Latin script + Indonesian-style spelling well)
  3. PARSE  : merge per-page text into book/chapter/verse JSON files

Usage:
    python tools/ocr_kenyah_pdf.py            # do everything
    python tools/ocr_kenyah_pdf.py render     # render-only
    python tools/ocr_kenyah_pdf.py ocr        # ocr-only
    python tools/ocr_kenyah_pdf.py parse      # parse-only
"""
from __future__ import annotations
import os, re, sys, json, glob, subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_PATH   = os.path.join(ROOT, "Kenyah-New-Testament-(print).pdf")
WORK_DIR   = "/tmp/kenyah_ocr"
IMG_DIR    = os.path.join(WORK_DIR, "pages")
TXT_DIR    = os.path.join(WORK_DIR, "text")
OUT_DIR    = os.path.join(ROOT, "static", "data", "bible", "kenyah")
DPI        = 250
WORKERS    = 6
TOTAL_PAGES_HINT = 745

# ---------------------------------------------------------------------------
# Kenyah-style book header  -> English book name.  Includes the
# specific spellings used in this NT print edition:
#   PEMUYAN     = Acts ("doings/works")
#   PUYAN LUHA' = Revelation
#   RUM         = Romans
#   YAYA        = John (1/2/3 YAYA = 1/2/3 John)
#   KURINTUS    = Corinthians
#   IPESUS      = Ephesians
#   PILIPI      = Philippians
#   KULUSE      = Colossians
#   TESALUNIKA  = Thessalonians
#   TIMUTIUS    = Timothy
#   PILIMUN     = Philemon
#   IBERANI     = Hebrews
#   YAKUP       = James
#   PETERUS     = Peter
#   YAHUDA      = Jude
# Some Indonesian-style aliases are kept as fallbacks just in case the
# OCR slips on a few headers.
# ---------------------------------------------------------------------------
BOOK_HEADER_MAP = {
    # Gospels
    "MATIUS": "Matthew", "MATTIUS": "Matthew", "MATEUS": "Matthew",
    "MARKUS": "Mark", "MARK": "Mark",
    "LUKAS": "Luke", "LUKA": "Luke", "LUKE": "Luke",
    "YAYA": "John", "YAHYA": "John", "YOHANES": "John", "YOH": "John",

    # Acts (Pemuyan = "Acts/Doings")
    "PEMUYAN": "Acts",
    "PEMUYAN RASUL": "Acts",
    "KISAH RASUL": "Acts",
    "KISAH PARA RASUL": "Acts",

    # Pauline epistles
    "RUM": "Romans", "ROMA": "Romans", "ROMANS": "Romans",

    "1 KURINTUS": "1 Corinthians", "I KURINTUS": "1 Corinthians",
    "1KURINTUS": "1 Corinthians", "KURINTUS 1": "1 Corinthians",
    "2 KURINTUS": "2 Corinthians", "II KURINTUS": "2 Corinthians",
    "2KURINTUS": "2 Corinthians", "KURINTUS 2": "2 Corinthians",
    "1 KORINTUS": "1 Corinthians", "2 KORINTUS": "2 Corinthians",

    "GALATIA": "Galatians",
    "IPESUS": "Ephesians", "EFESUS": "Ephesians", "EPESUS": "Ephesians",
    "PILIPI": "Philippians", "FILIPI": "Philippians",
    "KULUSE": "Colossians", "KOLOSE": "Colossians",

    "1 TESALUNIKA": "1 Thessalonians", "I TESALUNIKA": "1 Thessalonians",
    "1TESALUNIKA": "1 Thessalonians", "TESALUNIKA 1": "1 Thessalonians",
    "2 TESALUNIKA": "2 Thessalonians", "II TESALUNIKA": "2 Thessalonians",
    "2TESALUNIKA": "2 Thessalonians", "TESALUNIKA 2": "2 Thessalonians",
    "1 TESALONIKA": "1 Thessalonians", "2 TESALONIKA": "2 Thessalonians",

    "1 TIMUTIUS": "1 Timothy", "I TIMUTIUS": "1 Timothy",
    "1TIMUTIUS": "1 Timothy", "TIMUTIUS 1": "1 Timothy",
    "2 TIMUTIUS": "2 Timothy", "II TIMUTIUS": "2 Timothy",
    "2TIMUTIUS": "2 Timothy", "TIMUTIUS 2": "2 Timothy",
    "1 TIMOTIUS": "1 Timothy", "2 TIMOTIUS": "2 Timothy",

    "TITUS": "Titus",
    "PILIMUN": "Philemon", "FILEMON": "Philemon",
    "IBERANI": "Hebrews", "IBRANI": "Hebrews",

    # General epistles
    "YAKUP": "James", "YAKOBUS": "James", "YAK": "James",

    "1 PETERUS": "1 Peter", "I PETERUS": "1 Peter",
    "1PETERUS": "1 Peter", "PETERUS 1": "1 Peter",
    "2 PETERUS": "2 Peter", "II PETERUS": "2 Peter",
    "2PETERUS": "2 Peter", "PETERUS 2": "2 Peter",
    "1 PETRUS": "1 Peter", "2 PETRUS": "2 Peter",

    "1 YAYA": "1 John", "I YAYA": "1 John",
    "1YAYA": "1 John", "YAYA 1": "1 John",
    "2 YAYA": "2 John", "II YAYA": "2 John",
    "2YAYA": "2 John", "YAYA 2": "2 John",
    "3 YAYA": "3 John", "III YAYA": "3 John",
    "3YAYA": "3 John", "YAYA 3": "3 John",
    "1 YOHANES": "1 John", "2 YOHANES": "2 John", "3 YOHANES": "3 John",

    "YAHUDA": "Jude", "YUDAS": "Jude", "YUDA": "Jude",

    # Revelation: "PUYAN LUHA'" — note the trailing apostrophe.
    "PUYAN LUHA'": "Revelation",
    "PUYAN LUHA": "Revelation",
    "WAHYU": "Revelation",
}

# Sorted keys longest-first so e.g. "1 KORINTUS" matches before "1".
SORTED_HEADERS = sorted(BOOK_HEADER_MAP.keys(), key=len, reverse=True)

# Slugify map for filesystem layout — must match bible_data.NT_BOOKS slugs.
BOOK_SLUGS = {
    "Matthew": "matthew",          "Mark": "mark",
    "Luke": "luke",                "John": "john",
    "Acts": "acts",                "Romans": "romans",
    "1 Corinthians": "1_corinthians", "2 Corinthians": "2_corinthians",
    "Galatians": "galatians",      "Ephesians": "ephesians",
    "Philippians": "philippians",  "Colossians": "colossians",
    "1 Thessalonians": "1_thessalonians", "2 Thessalonians": "2_thessalonians",
    "1 Timothy": "1_timothy",      "2 Timothy": "2_timothy",
    "Titus": "titus",              "Philemon": "philemon",
    "Hebrews": "hebrews",          "James": "james",
    "1 Peter": "1_peter",          "2 Peter": "2_peter",
    "1 John": "1_john",            "2 John": "2_john",
    "3 John": "3_john",            "Jude": "jude",
    "Revelation": "revelation",
}

# Expected NT chapter counts per book (sanity bounds for parser).
NT_CHAPTER_COUNT = {
    "Matthew": 28, "Mark": 16, "Luke": 24, "John": 21, "Acts": 28,
    "Romans": 16, "1 Corinthians": 16, "2 Corinthians": 13,
    "Galatians": 6, "Ephesians": 6, "Philippians": 4, "Colossians": 4,
    "1 Thessalonians": 5, "2 Thessalonians": 3,
    "1 Timothy": 6, "2 Timothy": 4, "Titus": 3, "Philemon": 1,
    "Hebrews": 13, "James": 5, "1 Peter": 5, "2 Peter": 3,
    "1 John": 5, "2 John": 1, "3 John": 1, "Jude": 1, "Revelation": 22,
}


# ---------------------------------------------------------------------------
# Stage 1: render PDF -> JPEG
# ---------------------------------------------------------------------------

def stage_render() -> int:
    """pdftoppm pages → /tmp/kenyah_ocr/pages/p-NNN.jpg.

    Resumable: skips work if all expected pages already exist.
    """
    os.makedirs(IMG_DIR, exist_ok=True)
    existing = sorted(glob.glob(os.path.join(IMG_DIR, "p-*.jpg")))
    if len(existing) >= TOTAL_PAGES_HINT:
        print(f"[render] skip — {len(existing)} pages already rendered")
        return len(existing)

    print(f"[render] pdftoppm -r {DPI} → {IMG_DIR}/p-NNN.jpg")
    cmd = [
        "pdftoppm", "-r", str(DPI), "-jpeg",
        PDF_PATH, os.path.join(IMG_DIR, "p"),
    ]
    subprocess.run(cmd, check=True)
    pages = sorted(glob.glob(os.path.join(IMG_DIR, "p-*.jpg")))
    print(f"[render] done — {len(pages)} pages")
    return len(pages)


# ---------------------------------------------------------------------------
# Stage 2: OCR each page → /tmp/kenyah_ocr/text/p-NNN.txt
# ---------------------------------------------------------------------------

def _ocr_one(args):
    img_path, txt_path = args
    if os.path.exists(txt_path) and os.path.getsize(txt_path) > 0:
        return (img_path, True, "cached")
    # On macOS, leptonica sometimes fails on absolute /tmp paths
    # (symlink to /private/tmp). Run tesseract from the image dir
    # using a relative input filename to dodge that quirk.
    img_dir = os.path.dirname(img_path)
    img_name = os.path.basename(img_path)
    out_base = txt_path[:-4]  # strip .txt — tesseract appends it
    try:
        subprocess.run(
            ["tesseract", img_name, out_base, "-l", "ind", "--psm", "1"],
            check=True,
            cwd=img_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return (img_path, True, "ok")
    except subprocess.CalledProcessError as e:
        return (img_path, False, str(e))


def stage_ocr() -> int:
    os.makedirs(TXT_DIR, exist_ok=True)
    pages = sorted(glob.glob(os.path.join(IMG_DIR, "p-*.jpg")))
    if not pages:
        print("[ocr] no rendered pages — run render first")
        return 0

    tasks = []
    for img in pages:
        name = os.path.splitext(os.path.basename(img))[0]
        tasks.append((img, os.path.join(TXT_DIR, f"{name}.txt")))

    done = sum(1 for _, t in tasks if os.path.exists(t) and os.path.getsize(t) > 0)
    print(f"[ocr] {done}/{len(tasks)} already OCRed; running on remainder")

    completed = done
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(_ocr_one, t) for t in tasks]
        for fut in as_completed(futures):
            img, ok, msg = fut.result()
            completed += 1 if ok and msg != "cached" else 0
            if completed % 25 == 0 and msg != "cached":
                print(f"[ocr] progress: {completed}/{len(tasks)}")
    txts = sorted(glob.glob(os.path.join(TXT_DIR, "p-*.txt")))
    print(f"[ocr] done — {len(txts)} text files")
    return len(txts)


# ---------------------------------------------------------------------------
# Stage 3: parse OCR text into book/chapter/verse JSON
# ---------------------------------------------------------------------------

# Page running header forms we want to recognise:
#   "MATIUS 15"
#   "LUKAS 9, 10"          (page spans two chapters)
#   "1 KURINTUS 6"
#   "1 TIMUTIUS5"          (chapter glued to book name)
#   "PUYAN LUHA' 9, 10"
# Allow any leading garbage (the OCR sometimes prefixes "|" etc.).
HEADER_CHAPTER_RE = re.compile(
    r"^[^A-Za-z0-9]*"
    r"((?:[123IVX]+\s+)?[A-Z][A-Z' .\-]{0,30}?)"  # optional 1/2/3/I prefix + book
    r"\s*"
    r"(\d{1,3})"                              # first chapter
    r"(?:\s*[,\-]\s*(\d{1,3}))?"              # optional second chapter
    r"\s*$"
)
# Title-only header (book on its own line, e.g. "MATIUS" or "YAHUDA"
# or "2 PETERUS").
TITLE_ONLY_RE = re.compile(
    r"^[^A-Za-z0-9]*((?:[123IVX]+\s+)?[A-Z][A-Z' \-]{1,30}?)\s*$"
)

# Bare page number (footer).
PAGE_NUM_RE = re.compile(r"^\s*\d{1,4}\s*$")

# Combined verse/chapter marker matched in flat text.
#   group 1 (chap): optional chapter prefix, e.g. "10 " in "10 1U'o"
#   group 2 (vrs):  verse number
#   group 3 (lead): first character of the verse text
# `(?<=\s)|^` makes sure the chapter number is not part of an earlier
# word (avoids matching the trailing digits of e.g. "ada111Foo").
CHAP_VERSE_RE = re.compile(
    r"(?:(?<=\s)|^)"
    r"(?:(\d{1,3})\s+)?"
    r"(\d{1,3})\s*"
    r"([A-Za-z\u00C0-\u017F\"'“‘])"
)


def _normalize_header(line: str) -> str:
    """Uppercase + collapse spaces. Keep apostrophe (PUYAN LUHA')."""
    s = line.strip()
    # strip leading non-letter junk like "|"
    s = re.sub(r"^[^A-Za-z0-9]+", "", s)
    # keep word chars, spaces, hyphens, apostrophes
    s = re.sub(r"[^\w '\-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).upper()
    return s


def _match_book(token: str):
    """Return canonical English book name for a normalized header token."""
    if not token:
        return None
    if token in BOOK_HEADER_MAP:
        return BOOK_HEADER_MAP[token]
    # Try longest-prefix match (e.g., "1 KURINTUS6" -> "1 KURINTUS").
    for key in SORTED_HEADERS:
        if token.startswith(key) or token.endswith(key):
            return BOOK_HEADER_MAP[key]
    return None


def _detect_header(lines: list[str]):
    """Inspect the first non-empty lines for a book header.

    Returns (body_lines, book_or_None, chapter_list_or_None).
    chapter_list is a list of ints (the chapter numbers the page covers).
    """
    body = []
    book = None
    chapters = None
    seen_header = False

    # Keep a tiny lookahead so we can pair "SURAT CEN" / "SURAT KATU…"
    # intro lines with the book name on the next non-empty line.
    pending_intro = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            if not seen_header:
                continue  # ignore blanks before header
            body.append(line)
            continue
        if PAGE_NUM_RE.match(line):
            continue  # drop bare page-number footer

        if not seen_header:
            # Skip introductory phrases that precede a title page.
            if re.match(r"^\s*SURAT\b", line, re.IGNORECASE):
                pending_intro = True
                continue

            tok = _normalize_header(line)
            # "MATIUS 15" or "LUKAS 9, 10"
            m = HEADER_CHAPTER_RE.match(line.strip())
            if m:
                # Try to peel a glued trailing chapter from the book token.
                book_tok = _normalize_header(m.group(1))
                # Sometimes the token has digits glued, e.g. "1 TIMUTIUS5"
                # -> book group already excludes the digits via the
                # \d capture, but be defensive.
                book_tok = re.sub(r"\d+$", "", book_tok).strip()
                cand_book = _match_book(book_tok)
                if cand_book:
                    book = cand_book
                    ch1 = int(m.group(2))
                    chs = [ch1]
                    if m.group(3):
                        try:
                            chs.append(int(m.group(3)))
                        except ValueError:
                            pass
                    chapters = chs
                    seen_header = True
                    pending_intro = False
                    continue
            # "MATIUS" / "YAHUDA" (title page; chapter is 1)
            m2 = TITLE_ONLY_RE.match(line)
            if m2 and len(line.strip()) >= 2:
                cand_book = _match_book(tok)
                if cand_book:
                    book = cand_book
                    chapters = [1]
                    seen_header = True
                    pending_intro = False
                    continue
            # If we were waiting for a book-title following "SURAT…"
            # and this line doesn't look like a header, swallow it but
            # don't register a header — the book may be on a later
            # line still.
            if pending_intro:
                continue

            # No header recognised: this page is a continuation of the
            # previous page's book/chapter — start collecting body.
            seen_header = True
            body.append(line)
        else:
            body.append(line)

    return body, book, chapters


def _extract_verses(text_block: str, chapter_list: list[int]):
    """Yield (chapter, verse, text) triples from a flowing text blob.

    ``chapter_list`` lists the chapters this page covers, in order. We
    advance through it whenever we encounter an explicit chapter prefix
    in the OCR (e.g. "10 1U'o ...") that matches the next chapter, OR
    when the verse number resets back to 1.
    """
    if not chapter_list:
        return
    flat = re.sub(r"\s+", " ", text_block).strip()
    if not flat:
        return

    matches = list(CHAP_VERSE_RE.finditer(flat))
    if not matches:
        return

    ci = 0
    cur_chapter = chapter_list[ci]
    last_verse = 0

    parsed = []  # (chapter, verse, start_of_text)
    for m in matches:
        ch_str, vs_str, _lead = m.group(1), m.group(2), m.group(3)
        try:
            verse = int(vs_str)
        except ValueError:
            continue
        if not (1 <= verse <= 200):
            continue

        # Explicit chapter prefix — only honour it if it matches the
        # next chapter we expect on this page.
        if ch_str is not None:
            try:
                ch_int = int(ch_str)
            except ValueError:
                ch_int = None
            if ch_int is not None and ch_int != cur_chapter:
                # Advance the chapter pointer if this is the next
                # planned chapter. Otherwise, ignore the prefix —
                # it might be a stray two-digit verse.
                if ci + 1 < len(chapter_list) and ch_int == chapter_list[ci + 1]:
                    ci += 1
                    cur_chapter = ch_int
                    last_verse = 0
                # else: keep current chapter, treat ch_str as junk
        else:
            # Implicit chapter rollover: verse number drops back to 1
            # (or a small number) after we've already collected verses.
            if (
                verse == 1
                and last_verse >= 5
                and ci + 1 < len(chapter_list)
            ):
                ci += 1
                cur_chapter = chapter_list[ci]

        parsed.append((cur_chapter, verse, m.start(3)))
        last_verse = verse

    # Build text spans between consecutive markers.
    for i, (chap, verse, start) in enumerate(parsed):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(flat)
        # However, a verse text shouldn't include a trailing "10 " that
        # actually belongs to the next chapter prefix. The next match's
        # `m.start()` already accounts for that since the next regex
        # match would have consumed the chapter-prefix digits.
        text = flat[start:end].strip(" .,;:")
        # Drop a stray trailing page-number footer that survived line
        # joining (e.g. " 200" at end of last verse on a page).
        text = re.sub(r"\s+\d{1,4}\s*$", "", text).strip()
        if text:
            yield (chap, verse, text)


def stage_parse():
    os.makedirs(OUT_DIR, exist_ok=True)
    txts = sorted(glob.glob(os.path.join(TXT_DIR, "p-*.txt")))
    if not txts:
        print("[parse] no OCR output to parse")
        return

    # Aggregate: { book: { chapter: { verse: text } } }
    book_data: dict[str, dict[int, dict[int, str]]] = {}

    current_book = None
    current_chapter_list: list[int] | None = None

    for txt_path in txts:
        with open(txt_path, "r", encoding="utf-8", errors="ignore") as fh:
            raw_lines = fh.read().splitlines()

        body, det_book, det_chapters = _detect_header(raw_lines)
        if det_book:
            current_book = det_book
        if det_chapters:
            current_chapter_list = det_chapters
        elif current_chapter_list:
            # Continuation page: keep last known chapter as a singleton
            # so verse rollover doesn't accidentally bump.
            current_chapter_list = [current_chapter_list[-1]]

        if not current_book or not current_chapter_list:
            continue

        text_block = "\n".join(body)
        for ch, vs, text in _extract_verses(text_block, current_chapter_list):
            chapters = book_data.setdefault(current_book, {})
            verses = chapters.setdefault(ch, {})
            if vs in verses:
                # Prefer the longer/more complete capture if duplicated
                # across page boundaries.
                if len(text) > len(verses[vs]):
                    verses[vs] = text
            else:
                verses[vs] = text

    # Write per-chapter JSON files matching cache layout.
    written_chapters = 0
    for book in sorted(book_data.keys()):
        chapters = book_data[book]
        slug = BOOK_SLUGS.get(book)
        if not slug:
            print(f"[parse] WARN unknown book slug for {book!r}, skipping")
            continue
        max_ch = NT_CHAPTER_COUNT.get(book, 200)
        book_dir = os.path.join(OUT_DIR, slug)
        os.makedirs(book_dir, exist_ok=True)
        kept = 0
        for ch, verses in chapters.items():
            if not (1 <= ch <= max_ch):
                continue
            data = {str(k): v for k, v in sorted(verses.items())}
            with open(os.path.join(book_dir, f"{ch}.json"), "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            kept += 1
            written_chapters += 1
        print(f"[parse] {book}: {kept}/{max_ch} chapters, "
              f"{sum(len(v) for v in chapters.values())} verses")
    print(f"[parse] done — wrote {written_chapters} chapter files to {OUT_DIR}")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main():
    stages = sys.argv[1:] or ["render", "ocr", "parse"]
    if "render" in stages:
        stage_render()
    if "ocr" in stages:
        stage_ocr()
    if "parse" in stages:
        stage_parse()


if __name__ == "__main__":
    main()
