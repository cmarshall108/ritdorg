"""
New Testament book metadata for dynamic Bible loading.
Defines all 27 NT books with chapter counts and URL slugs for various sources.
"""

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
NT_TRANSLATIONS = ["NIV", "NKJV", "KJV", "ESV", "NASB1995", "Hungarian", "Hebrew"]

# Total chapters in the New Testament
NT_TOTAL_CHAPTERS = sum(info["chapters"] for info in NT_BOOKS.values())  # 260
