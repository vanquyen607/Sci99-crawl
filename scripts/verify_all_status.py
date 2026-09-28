# -*- coding: utf-8 -*-
"""Verify recent rows + status of all data tabs in the 2026.09.25 sheet."""
import sys, io, re, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

NEW_SID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'

creds = Credentials.from_service_account_file(
    r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json',
    scopes=['https://www.googleapis.com/auth/spreadsheets'])
sh = gspread.authorize(creds).open_by_key(NEW_SID)

def with_retry(fn, tries=3, wait=60):
    """Retry on Google 429 quota (read requests per minute)."""
    for i in range(tries):
        try:
            return fn()
        except gspread.exceptions.APIError as e:
            if '429' in str(e) and i < tries - 1:
                print(f'  429 quota — wait {wait}s then retry ({i + 1}/{tries - 1})', flush=True)
                time.sleep(wait)
            else:
                raise

def wsheet(name):
    return with_retry(lambda: sh.worksheet(name))

SHEETS = [
    '汇率',
    '赖氨酸70_河北_sci99', '赖氨酸70_山东_sci99',
    '赖氨酸98_河北_sci99', '赖氨酸98_山东_sci99',
    '苏氨酸_河北_sci99', '苏氨酸_山东_sci99',
    '缬氨酸_sci99_search', '色氨酸_sci99',
    '精氨酸', '异亮氨酸',
    '氯化胆碱_echemi', '磷酸氢钙_sci99', '磷酸一二钙_pdf_sci99',
    '磷酸二氢钙_云南_sci99_search', '磷酸二氢钙_西南_sci99',
    '蛋氨酸_山东_sci99', '蛋氨酸_河南_sci99',
    '维生素A_sci99', '维生素B1_sci99', '维生素B2_sci99',
    '维生素C_sci99', '维生素D3_sci99', '维生素E_sci99',
    '玉米蛋白粉_sci99', 'DDGS_sci', '鱼粉_sci99',
    '乳清粉_sci99', '肌醇_国产_100ppi', '发酵豆粕_mysteel',
    '棕榈油_天津24_sci99', '棕榈油_张家港52_sci99', '棕榈油_张家港24_sci99',
]

def dk(s):
    try:
        return datetime.strptime(s, '%m/%d/%Y')
    except Exception:
        return datetime(1900, 1, 1)

print('=== STATUS ALL (new sheet) ===')
for name in SHEETS:
    try:
        ws = wsheet(name)
    except Exception as e:
        print(f'{name}: MISSING ({e})')
        continue
    rows = with_retry(ws.get_all_values)
    # data starts row 3 (header row 2); 汇率 starts row 2
    start = 1 if name == '汇率' else 2
    sample = rows[start:start + 13]
    date_cols = {}
    for r in sample:
        for i, v in enumerate(r):
            v = str(v).strip()
            if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', v):
                if i not in date_cols:
                    date_cols[i] = v
    if not date_cols:
        print(f'{name}: NO DATES rows={len(rows)}')
        continue
    best = max(date_cols.values(), key=dk)
    nblocks = len(date_cols)
    print(f'{name}: latest={best} date_cols={nblocks} rows={len(rows)} cols={list(date_cols.items())[:4]}')
    time.sleep(0.4)

# Format samples: top 3 data rows of a few representative tabs
print('\n=== FORMAT SAMPLES (R3-R5, cols 0-11) ===')
for name in ('维生素B1_sci99', '赖氨酸70_河北_sci99', '玉米蛋白粉_sci99', 'DDGS_sci', '鱼粉_sci99'):
    try:
        ws = wsheet(name)
        rows = with_retry(ws.get_all_values)
    except Exception as e:
        print(f'{name}: {e}')
        continue
    print(f'--- {name}')
    for r in rows[2:5]:
        print(' ', r[0:12])
    time.sleep(0.4)
