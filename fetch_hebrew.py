import subprocess
import re

# Verse counts for Matthew 13-28
verse_counts = {
    13: 58,
    14: 36,
    15: 39,
    16: 28,
    17: 27,
    18: 35,
    19: 30,
    20: 34,
    21: 46,
    22: 46,
    23: 39,
    24: 51,
    25: 46,
    26: 75,
    27: 66,
    28: 20
}

hebrew_texts = {}

for chapter in range(13, 29):
    hebrew_texts[chapter] = {}
    for verse in range(1, verse_counts[chapter] + 1):
        url = f"https://biblehub.com/text/matthew/{chapter}-{verse}.htm"
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
print("hebrew_matthew = {")
for chapter in range(13, 29):
    print(f"    {chapter}: {{")
    for verse in range(1, verse_counts[chapter] + 1):
        text = hebrew_texts[chapter][verse]
        print(f"        {verse}: \"{text}\",")
    print("    },")
print("}")