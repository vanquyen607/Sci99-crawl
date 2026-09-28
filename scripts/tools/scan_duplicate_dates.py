# -*- coding: utf-8 -*-
"""Scan all 15 sheets: find duplicate dates per block. Option --fix to remove dups."""
import sys, io, re, argparse
from datetime import datetime
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
import gspread
from google.oauth2.service_account import Credentials

CREDS = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
SID = '1hmDLpYOALH8-Fu4pxG-VJZURDtz3Z2UzWwTPAOs230I'

SHEETS = [
    '汇率',
    '赖氨酸70 (规格型号)', '赖氨酸98', '苏氨酸', '缬氨酸', '精氨酸', '色氨酸',
    '氯化胆碱', '磷酸氢钙', '磷酸一二钙-每周', '磷酸二氢钙', '蛋氨酸',
    '异亮氨酸', '维生素', '棕榈油',
]

# known widths by sheet (default 17); vitamin/palm special handled via date-col detection
DEFAULT_WIDTH = 17
# 汇率: dates start row 2 (0-based idx 1), 26 cols, footer 2 last rows
FX_START_RI = 1
FX_WIDTH = 26

def parse_date(s):
    s = str(s or '').strip()
    if not s:
        return None
    for fmt in ('%m/%d/%Y', '%Y/%m/%d', '%Y-%m-%d', '%m/%d/%y', '%Y.%m.%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None

def to_mdY(d):
    return f'{d.month}/{d.day}/{d.year}'

def find_date_cols(rows, sample_rows=12, start_ri=3):
    """Find columns that look like date headers/data starts."""
    date_cols = {}
    for r in rows[start_ri:start_ri + sample_rows]:
        for i, v in enumerate(r):
            v = str(v).strip()
            if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', v) or re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', v):
                if i not in date_cols:
                    date_cols[i] = v
    return sorted(date_cols.keys())

def block_width_for(sheet, start, date_cols):
    """Infer width: next date col - start, or default."""
    later = [c for c in date_cols if c > start]
    if later:
        return later[0] - start - 1  # often 1 col gap? actually blocks abut: 0 and 18 => width 17
        # for 0 and 18: width = 18 - 0 = 18? No, cols 0-16 width 17, col17 empty, col18 next
        # so width = next_start - start - gap. gap usually 0 or 1.
        # safer: next_start - start, then shrink trailing empties later.
    # special cases
    if sheet == '维生素':
        if start == 109:
            return 18
        return 17
    if sheet == '棕榈油':
        return 10
    if sheet == '氯化胆碱':
        # B2 starts at 19
        return 17
    return DEFAULT_WIDTH

def infer_width(sheet, start, all_date_cols, rows):
    if sheet == '汇率':
        return FX_WIDTH
    later = [c for c in all_date_cols if c > start]
    if later:
        gap = later[0] - start
        # typical: width 17 with gap 1 (0..16, empty 17, next 18) => gap=18
        # or abutting width 10: 0..9 next 12? palm has gap
        # try width = gap - 1 if col at gap-1 empty-ish else gap
        cand = gap - 1
        if cand >= 5:
            # check that cand doesn't cut into next date col content
            return cand
        return gap
    # last block
    if sheet == '维生素' and start == 109:
        return 18
    if sheet == '棕榈油':
        return 10
    return DEFAULT_WIDTH

def scan_sheet(ws, rows, fix=False):
    start_ri = FX_START_RI if ws.title == '汇率' else 3
    date_cols = find_date_cols(rows, start_ri=start_ri)
    if not date_cols:
        return {'name': ws.title, 'error': 'no date cols', 'dups': []}
    results = []
    for start in date_cols:
        width = infer_width(ws.title, start, date_cols, rows)
        # collect rows with dates
        entries = []  # (row_idx0, date, row_slice, nonempty_count)
        for ri in range(start_ri, len(rows)):
            r = list(rows[ri]) + [''] * (start + width + 2 - len(rows[ri]))
            cell = r[start]
            d = parse_date(cell)
            if not d:
                # only count if block has some content
                block = r[start:start + width]
                if any(str(x).strip() for x in block):
                    # non-date content in date col — skip as non-date row
                    pass
                continue
            block = r[start:start + width]
            nonempty = sum(1 for x in block if str(x).strip())
            entries.append({
                'ri': ri,  # 0-based into rows
                'd': d,
                'block': block,
                'nonempty': nonempty,
                'raw_date': str(cell).strip(),
            })
        # group by date
        by_date = defaultdict(list)
        for e in entries:
            by_date[e['d']].append(e)
        dups = {d: lst for d, lst in by_date.items() if len(lst) > 1}
        results.append({
            'start': start,
            'width': width,
            'n_rows': len(entries),
            'n_unique': len(by_date),
            'dup_dates': len(dups),
            'dup_detail': sorted(
                [(d, [(x['ri'] + 1, x['nonempty'], x['raw_date']) for x in lst])
                 for d, lst in dups.items()],
                reverse=True
            )[:20],  # cap detail
            'dup_total_extra': sum(len(lst) - 1 for lst in dups.values()),
            'entries': entries,
            'by_date': by_date,
        })
    return {'name': ws.title, 'blocks': results, 'date_cols': date_cols}


def fix_sheet(ws, rows, scan):
    """Rewrite each block without duplicate dates (keep richest row per date)."""
    date_cols = scan['date_cols']
    is_fx = ws.title == '汇率'
    start_row = FX_START_RI + 1  # 1-based
    total_kept = 0
    total_removed = 0
    for blk in scan['blocks']:
        start, width = blk['start'], blk['width']
        by_date = blk['by_date']
        if not blk['dup_dates']:
            continue
        # keep best row per date: max nonempty, then earliest ri (stable)
        kept = []
        for d, lst in sorted(by_date.items(), reverse=True):
            best = max(lst, key=lambda x: (x['nonempty'], -x['ri']))
            kept.append((d, list(best['block'][:width])))
        removed = blk['dup_total_extra']
        # clear and write
        col1 = start + 1
        old_n = blk['n_rows']
        if is_fx:
            # data starts row 2; footer 2 last rows must be preserved
            first_data_ri = min(e['ri'] for e in blk['entries']) if blk['entries'] else FX_START_RI
            last_data_ri = max(e['ri'] for e in blk['entries']) if blk['entries'] else FX_START_RI
            end_row = max(last_data_ri + 1, first_data_ri + len(kept))
            rng = f'{gspread.utils.rowcol_to_a1(first_data_ri + 1, col1)}:{gspread.utils.rowcol_to_a1(end_row, col1 + width - 1)}'
            ws.batch_clear([rng])
            if kept:
                grid = [row for _, row in kept]
                ws.update(values=grid, range_name=gspread.utils.rowcol_to_a1(first_data_ri + 1, col1), value_input_option='RAW')
        else:
            end_row = max(4 + old_n, 4 + len(kept))
            rng = f'{gspread.utils.rowcol_to_a1(4, col1)}:{gspread.utils.rowcol_to_a1(end_row, col1 + width - 1)}'
            ws.batch_clear([rng])
            if kept:
                grid = [row for _, row in kept]
                ws.update(values=grid, range_name=gspread.utils.rowcol_to_a1(4, col1), value_input_option='RAW')
        total_kept += len(kept)
        total_removed += removed
        print(f"  fixed col{start}: kept={len(kept)} removed_extra={removed}")
    return total_kept, total_removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fix', action='store_true', help='remove duplicate dates')
    args = ap.parse_args()

    creds = Credentials.from_service_account_file(CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sh = gspread.authorize(creds).open_by_key(SID)

    total_dup_dates = 0
    total_extra = 0
    sheets_with_dups = []

    for name in SHEETS:
        ws = sh.worksheet(name)
        rows = ws.get_all_values()
        scan = scan_sheet(ws, rows, fix=args.fix)
        if 'error' in scan:
            print(f"{name}: ERROR {scan['error']}")
            continue
        sheet_dups = sum(b['dup_dates'] for b in scan['blocks'])
        sheet_extra = sum(b['dup_total_extra'] for b in scan['blocks'])
        total_dup_dates += sheet_dups
        total_extra += sheet_extra
        flag = ' ** DUPS **' if sheet_dups else ''
        print(f"{name}: blocks={len(scan['blocks'])} dup_dates={sheet_dups} extra_rows={sheet_extra}{flag}")
        for b in scan['blocks']:
            if b['dup_dates']:
                print(f"  col{b['start']} w={b['width']}: n={b['n_rows']} unique={b['n_unique']} dup={b['dup_dates']} extra={b['dup_total_extra']}")
                for d, locs in b['dup_detail'][:8]:
                    loc_s = ', '.join(f"R{ri}(ne={ne},{rd})" for ri, ne, rd in locs)
                    print(f"    {d}: {loc_s}")
                if b['dup_dates'] > 8:
                    print(f"    ... +{b['dup_dates'] - 8} more dup dates")
                sheets_with_dups.append(name)

        if args.fix and sheet_dups:
            kept, removed = fix_sheet(ws, rows, scan)
            # re-scan to verify
            rows2 = ws.get_all_values()
            scan2 = scan_sheet(ws, rows2)
            dups2 = sum(b['dup_dates'] for b in scan2.get('blocks', []))
            print(f"  FIXED: kept={kept} removed_extra~{removed} verify_dup={dups2}")

    print(f'\n=== TOTAL dup_dates={total_dup_dates} extra_rows={total_extra} sheets_with_dups={len(set(sheets_with_dups))} ===')
    if sheets_with_dups:
        print('sheets:', sorted(set(sheets_with_dups)))
    if not args.fix and total_dup_dates:
        print('Run with --fix to remove duplicates (keep richest row per date).')


if __name__ == '__main__':
    main()
