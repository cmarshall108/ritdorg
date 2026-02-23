import subprocess
import re

# Verse counts for Mark 1-16
verse_counts = {
    1: 45,
    2: 28,
    3: 35,
    4: 41,
    5: 43,
    6: 56,
    7: 37,
    8: 38,
    9: 50,
    10: 52,
    11: 33,
    12: 44,
    13: 37,
    14: 72,
    15: 47,
    16: 20
}

hebrew_texts = {}

for chapter in range(1, 17):
    hebrew_texts[chapter] = {}
    for verse in range(1, verse_counts[chapter] + 1):
        url = f"https://biblehub.com/text/mark/{chapter}-{verse}.htm"
        try:
            result = subprocess.run(['curl', '-s', url], capture_output=True, text=True, timeout=10)
            html = result.stdout
            # Extract Hebrew text
            match = re.search(r'<span class="heb">([^<]*)</span>', html)
            if match:
                hebrew_text = match.group(1)
                hebrew_texts[chapter][verse] = hebrew_text
            else:
                hebrew_texts[chapter][verse] = "NOT FOUND"
        except Exception as e:
            hebrew_texts[chapter][verse] = f"ERROR: {str(e)}"

# Now print the dictionary
print('"Mark": {')
for chapter in range(1, 17):
    print(f"    {chapter}: {{")
    for verse in range(1, verse_counts[chapter] + 1):
        text = hebrew_texts[chapter][verse]
        print(f'        {verse}: "{text}",')
    print("    },")
print("},")