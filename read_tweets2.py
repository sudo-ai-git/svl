import openpyxl
wb = openpyxl.load_workbook('/home/sudosudo/.openclaw/workspace/ArweaveP_tweets.xlsx')
ws = wb['tweets']
# Print all tweets to find puzzle-10-related ones (the wallet addr bkjJGw3NLxs8OAyRxgTL or "puzzle 10" / "#10")
for row in ws.iter_rows(min_row=2, values_only=True):
    tid, text, name, screen, utc, created = row[0], row[1], row[2], row[3], row[4], row[5]
    t = str(text) if text else ""
    low = t.lower()
    if ('puzzle' in low and ('10' in low or '#10' in low)) or 'bkjJGw3' in t or 'order 66' in low or 'order66' in low:
        print("=====", created, "=====")
        print(t)
        print()
