import openpyxl
wb = openpyxl.load_workbook('/home/sudosudo/.openclaw/workspace/ArweaveP_tweets.xlsx')
ws = wb['tweets']
# Print all tweets after Apr 2020 (puzzle 10 was Apr 14 2020) to see hints
rows = []
for row in ws.iter_rows(min_row=2, values_only=True):
    created = row[5]
    text = str(row[1]) if row[1] else ""
    rows.append((created, text))
# Sort by date
import re
def keyf(r):
    return str(r[0])
rows.sort(key=keyf)
for created, text in rows:
    print(f"[{created}] {text[:400]}")
