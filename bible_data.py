"""
Bible book metadata for dynamic Bible loading.
Defines all 66 books (39 OT + 27 NT) with chapter counts and URL slugs.
"""

# All Old Testament books with metadata (Protestant canon, matches Károli)
OT_BOOKS = {
    "Genesis":          {"chapters": 50, "slug": "genesis"},
    "Exodus":           {"chapters": 40, "slug": "exodus"},
    "Leviticus":        {"chapters": 27, "slug": "leviticus"},
    "Numbers":          {"chapters": 36, "slug": "numbers"},
    "Deuteronomy":      {"chapters": 34, "slug": "deuteronomy"},
    "Joshua":           {"chapters": 24, "slug": "joshua"},
    "Judges":           {"chapters": 21, "slug": "judges"},
    "Ruth":             {"chapters":  4, "slug": "ruth"},
    "1 Samuel":         {"chapters": 31, "slug": "1_samuel"},
    "2 Samuel":         {"chapters": 24, "slug": "2_samuel"},
    "1 Kings":          {"chapters": 22, "slug": "1_kings"},
    "2 Kings":          {"chapters": 25, "slug": "2_kings"},
    "1 Chronicles":     {"chapters": 29, "slug": "1_chronicles"},
    "2 Chronicles":     {"chapters": 36, "slug": "2_chronicles"},
    "Ezra":             {"chapters": 10, "slug": "ezra"},
    "Nehemiah":         {"chapters": 13, "slug": "nehemiah"},
    "Esther":           {"chapters": 10, "slug": "esther"},
    "Job":              {"chapters": 42, "slug": "job"},
    "Psalms":           {"chapters": 150, "slug": "psalms"},
    "Proverbs":         {"chapters": 31, "slug": "proverbs"},
    "Ecclesiastes":     {"chapters": 12, "slug": "ecclesiastes"},
    "Song of Solomon":  {"chapters":  8, "slug": "song_of_solomon"},
    "Isaiah":           {"chapters": 66, "slug": "isaiah"},
    "Jeremiah":         {"chapters": 52, "slug": "jeremiah"},
    "Lamentations":     {"chapters":  5, "slug": "lamentations"},
    "Ezekiel":          {"chapters": 48, "slug": "ezekiel"},
    "Daniel":           {"chapters": 12, "slug": "daniel"},
    "Hosea":            {"chapters": 14, "slug": "hosea"},
    "Joel":             {"chapters":  3, "slug": "joel"},
    "Amos":             {"chapters":  9, "slug": "amos"},
    "Obadiah":          {"chapters":  1, "slug": "obadiah"},
    "Jonah":            {"chapters":  4, "slug": "jonah"},
    "Micah":            {"chapters":  7, "slug": "micah"},
    "Nahum":            {"chapters":  3, "slug": "nahum"},
    "Habakkuk":         {"chapters":  3, "slug": "habakkuk"},
    "Zephaniah":        {"chapters":  3, "slug": "zephaniah"},
    "Haggai":           {"chapters":  2, "slug": "haggai"},
    "Zechariah":        {"chapters": 14, "slug": "zechariah"},
    "Malachi":          {"chapters":  4, "slug": "malachi"},
}

# All New Testament books with metadata
NT_BOOKS = {
    "Matthew":          {"chapters": 28, "slug": "matthew"},
    "Mark":             {"chapters": 16, "slug": "mark"},
    "Luke":             {"chapters": 24, "slug": "luke"},
    "John":             {"chapters": 21, "slug": "john"},
    "Acts":             {"chapters": 28, "slug": "acts"},
    "Romans":           {"chapters": 16, "slug": "romans"},
    "1 Corinthians":    {"chapters": 16, "slug": "1_corinthians"},
    "2 Corinthians":    {"chapters": 13, "slug": "2_corinthians"},
    "Galatians":        {"chapters":  6, "slug": "galatians"},
    "Ephesians":        {"chapters":  6, "slug": "ephesians"},
    "Philippians":      {"chapters":  4, "slug": "philippians"},
    "Colossians":       {"chapters":  4, "slug": "colossians"},
    "1 Thessalonians":  {"chapters":  5, "slug": "1_thessalonians"},
    "2 Thessalonians":  {"chapters":  3, "slug": "2_thessalonians"},
    "1 Timothy":        {"chapters":  6, "slug": "1_timothy"},
    "2 Timothy":        {"chapters":  4, "slug": "2_timothy"},
    "Titus":            {"chapters":  3, "slug": "titus"},
    "Philemon":         {"chapters":  1, "slug": "philemon"},
    "Hebrews":          {"chapters": 13, "slug": "hebrews"},
    "James":            {"chapters":  5, "slug": "james"},
    "1 Peter":          {"chapters":  5, "slug": "1_peter"},
    "2 Peter":          {"chapters":  3, "slug": "2_peter"},
    "1 John":           {"chapters":  5, "slug": "1_john"},
    "2 John":           {"chapters":  1, "slug": "2_john"},
    "3 John":           {"chapters":  1, "slug": "3_john"},
    "Jude":             {"chapters":  1, "slug": "jude"},
    "Revelation":       {"chapters": 22, "slug": "revelation"},
}

# Available translations (English + Hebrew)
NT_TRANSLATIONS = ["NIV", "NKJV", "KJV", "ESV", "NASB1995", "Hungarian", "Hungarian-Revised", "Hebrew"]

# Combined map of every Bible book (OT first, then NT) used by the
# fetcher / app / prefetch routines.
ALL_BOOKS = {**OT_BOOKS, **NT_BOOKS}

# Total chapters in the New Testament
NT_TOTAL_CHAPTERS = sum(info["chapters"] for info in NT_BOOKS.values())  # 260
OT_TOTAL_CHAPTERS = sum(info["chapters"] for info in OT_BOOKS.values())  # 929
TOTAL_CHAPTERS = NT_TOTAL_CHAPTERS + OT_TOTAL_CHAPTERS                   # 1189
