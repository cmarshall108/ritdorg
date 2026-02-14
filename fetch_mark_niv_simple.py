#!/usr/bin/env python3
import subprocess
import re
import html

def get_niv_chapter(book, chapter):
    url = f"https://biblehub.com/niv/{book}/{chapter}.htm"
    try:
        result = subprocess.run(['curl', '-s', url], capture_output=True, text=True, timeout=15)
        html_content = result.stdout

        # Extract verses using regex
        pattern = r'<span class="reftext"><a href="http://biblehub.com/{book}/\d+-(\d+)\.htm"><b>\d+</b></a></span>(.*?)(?=<span class="reftext">|<p class="sectionhead">|<hr|$|<div id="botbox">)'
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
        print(f"Error fetching {book} chapter {chapter}: {e}")
        return {}

# Verse counts for Mark 1-16
verse_counts = {
    1: 45, 2: 28, 3: 35, 4: 41, 5: 43, 6: 56, 7: 37, 8: 38, 9: 50,
    10: 52, 11: 33, 12: 44, 13: 37, 14: 72, 15: 47, 16: 20
}

# Get all chapters
niv_texts = {}
for chapter in range(1, 17):
    print(f"Fetching Mark {chapter}...")
    chapter_data = get_niv_chapter("mark", chapter)
    niv_texts[chapter] = chapter_data
    print(f"Found {len(chapter_data)} verses")

# Print the dictionary
print('"Mark": {')
for chapter in range(1, 17):
    print(f"    {chapter}: {{")
    for verse in range(1, verse_counts[chapter] + 1):
        if verse in niv_texts[chapter]:
            text = niv_texts[chapter][verse]
            # Escape quotes
            text = text.replace('"', '\\"')
            print(f'        {verse}: "{text}",')
        else:
            print(f'        {verse}: "NOT FOUND",')
    print("    },")
print("},")