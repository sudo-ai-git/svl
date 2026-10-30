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
# Puzzle 10 was posted Apr 14 2020. Look at Apr-May 2020 window.
for d, text in rows:
    if d.year == 2020 and 4 <= d.month <= 6:
        print(f"[{d.strftime('%Y-%m-%d')}] {text}")
        print()
