#!/usr/bin/env python3
import subprocess
import re
import html

def get_niv_chapter(chapter):
    url = f"https://biblehub.com/niv/matthew/{chapter}.htm"
    try:
        result = subprocess.run(['curl', '-s', url], capture_output=True, text=True, timeout=15)
        html_content = result.stdout

        # Extract verses using regex
        pattern = r'<span class="reftext"><a href="http://biblehub.com/matthew/\d+-(\d+)\.htm"><b>\d+</b></a></span>(.*?)(?=<span class="reftext">|<p class="sectionhead">|<hr|$|<div id="botbox">)'
        matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)

        chapter_dict = {}
        for match in matches:
            verse_num = int(match[0])
            text = match[1].strip()
            # Clean text: remove HTML tags
            text = re.sub(r'<[^>]+>', '', text)
            # Decode HTML entities
            text = html.unescape(text)
            # Remove extra spaces
            text = re.sub(r'\s+', ' ', text).strip()
            # Remove footnotes
            text = re.sub(r'\s+[a-z]\s+.*?$', '', text)
            text = text.strip()
            if text:
                chapter_dict[verse_num] = text

        return chapter_dict
    except Exception as e:
        print(f"Error fetching chapter {chapter}: {e}")
        return {}

# Verse counts for Matthew 13-28
verse_counts = {
    13: 58, 14: 36, 15: 39, 16: 28, 17: 27, 18: 35, 19: 30,
    20: 34, 21: 46, 22: 46, 23: 39, 24: 51, 25: 46, 26: 75, 27: 66, 28: 20
}

# Get all chapters
niv_texts = {}
for chapter in range(13, 29):
    print(f"Fetching Matthew {chapter}...")
    chapter_data = get_niv_chapter(chapter)
    niv_texts[chapter] = chapter_data
    print(f"Found {len(chapter_data)} verses")

# Output in the format needed for translations.py
print("\n# NIV Matthew 13-28")
print("niv_matthew_13_28 = {")
for chapter in range(13, 29):
    print(f"    {chapter}: {{")
    for verse in range(1, verse_counts[chapter] + 1):
        if verse in niv_texts[chapter]:
            text = niv_texts[chapter][verse]
            # Escape quotes for Python string
            text = text.replace('"', '\\"').replace("'", "\\'")
            print(f'        {verse}: "{text}",')
        else:
            print(f'        {verse}: "NOT FOUND",')
    print("    },")
print("}")