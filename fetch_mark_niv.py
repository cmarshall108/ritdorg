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

niv_texts = {}

for chapter in range(1, 17):
    niv_texts[chapter] = {}
    for verse in range(1, verse_counts[chapter] + 1):
        url = f"https://biblehub.com/niv/mark/{chapter}-{verse}.htm"
        try:
            result = subprocess.run(['curl', '-s', url], capture_output=True, text=True, timeout=10)
            html = result.stdout
            # Extract NIV text - look for the verse content
            # Try different patterns
            patterns = [
                r'<span class="text">([^<]*)</span>',
                r'<div class="verse[^"]*">([^<]*)</div>',
                r'<p class="[^"]*">([^<]*)</p>'
            ]

            text = "NOT FOUND"
            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    text = match.group(1).strip()
                    break

            niv_texts[chapter][verse] = text
        except Exception as e:
            niv_texts[chapter][verse] = f"ERROR: {str(e)}"

# Now print the dictionary
print('"Mark": {')
for chapter in range(1, 17):
    print(f"    {chapter}: {{")
    for verse in range(1, verse_counts[chapter] + 1):
        text = niv_texts[chapter][verse]
        # Escape quotes
        text = text.replace('"', '\\"')
        print(f'        {verse}: "{text}",')
    print("    },")
print("},")