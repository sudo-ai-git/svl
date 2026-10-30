import openpyxl
from datetime import datetime
wb = openpyxl.load_workbook('/home/sudosudo/.openclaw/workspace/ArweaveP_tweets.xlsx')
ws = wb['tweets']
rows = []
for row in ws.iter_rows(min_row=2, values_only=True):
    created = row[5]
    text = str(row[1]) if row[1] else ""
    try:
        d = datetime.strptime(str(created), "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        continue
    rows.append((d, text))
rows.sort()
# search for length/char hints and puzzle-10 references
print("===== TWEETS WITH 'chars' or 'char' =====")
for d, text in rows:
    if 'char' in text.lower():
        print(f"[{d.strftime('%Y-%m-%d')}] {text}")
        print()
print("===== TWEETS MENTIONING puzzle + 10 =====")
for d, text in rows:
    low = text.lower()
    if 'puzzle' in low and ('10' in text or '#10' in text):
        print(f"[{d.strftime('%Y-%m-%d')}] {text}")
        print()
