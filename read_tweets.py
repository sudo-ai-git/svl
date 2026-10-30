import openpyxl
wb = openpyxl.load_workbook('/home/sudosudo/.openclaw/workspace/ArweaveP_tweets.xlsx')
for ws in wb.worksheets:
    print("SHEET:", ws.title, "rows:", ws.max_row, "cols:", ws.max_column)
    hdr = [c.value for c in ws[1]]
    print("HEADER:", hdr)
    print("---")
