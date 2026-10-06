# -*- coding: utf-8 -*-
"""Shared read/write helpers for the '原料' spreadsheet (51 data tabs).

Quota-friendly by design: one values_batch_get reads every tab we touch and
one values_batch_update writes them all back, so a full updater run costs
2-3 API calls against the Sheets quota instead of 4+ per tab.

Layout facts this lib relies on (verified 2026-10-05):
- row 1 = source URL, header row = first row containing '日期' (row 2, row 3 on
  三甲胺_鲁西化工_cnbg / 三甲胺_国产_cnbg where rows 4-6 are blank), data starts
  at the first dated row.
- width varies per tab: 9 (cnbg), 10 (棕榈油×3), 11 (most), 17 (维E/氯化胆碱/
  磷酸一铵/磷酸二铵/玉米淀粉 - the last keeps 备注 at col K, FX block at L..Q).
- 涨跌/比例 live on the 平均价 column (H everywhere, F on cnbg) and read
  downward: '={L}{R}-{L}{R+1}' on every row including the newest.
"""
import re
import time

import gspread
from google.oauth2.service_account import Credentials

import newsheet_lib as NS

SID2 = '1pnDkBjLjfXgNE-Qv7rU7risEfcM3y4f4nd-OTN9XEu0'
CRED = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
INDEX_TABS = {'ECHEMI', 'SCI99', '100PPI'}
RANGE_COLS = 26          # read up to col Z
CHUNK = 30               # ranges per values_batch_get
RETRY_WAITS = (25, 60)   # seconds on 429


def open_sh():
    creds = Credentials.from_service_account_file(
        CRED, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return gspread.authorize(creds).open_by_key(SID2)


def retry(fn, *args, **kwargs):
    waits = list(RETRY_WAITS)
    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e)
            if ('429' in msg or 'quota' in msg.lower()) and waits:
                w = waits.pop(0)
                print(f'    quota hit, waiting {w}s...', flush=True)
                time.sleep(w)
                continue
            raise


def all_titles(sh):
    return [w.title for w in sh.worksheets() if w.title not in INDEX_TABS]


def read_grid(sh, titles):
    """{title: raw rows} - header rows included, formulas preserved, dates as
    serial numbers. 2 API calls regardless of how many tabs are requested."""
    meta = {w.title: w for w in sh.worksheets()}
    order, ranges = [], []
    col = gspread.utils.rowcol_to_a1(1, RANGE_COLS)[:-1]
    for t in titles:
        ws = meta.get(t)
        if ws is None:
            print(f'  WARN no such tab: {t}')
            continue
        order.append(t)
        ranges.append(f"'{t}'!A1:{col}{max(ws.row_count, 50)}")
    grid = {}
    for i in range(0, len(ranges), CHUNK):
        res = retry(sh.values_batch_get, ranges[i:i + CHUNK],
                    params={'valueRenderOption': 'FORMULA'})
        for t, v in zip(order[i:i + CHUNK], res['valueRanges']):
            grid[t] = v.get('values', [])
    return grid


def _width(rows):
    w = 0
    for r in rows:
        for i, c in enumerate(r):
            if str(c if c is not None else '').strip():
                w = max(w, i + 1)
    return w


def analyze(rows):
    """-> dict(header_row, first, width, price_col, delta_col, ratio_col, fx_col)
    1-based row numbers; column indexes are 0-based; -1 when absent."""
    hi = -1
    for i, r in enumerate(rows[:6]):
        if '日期' in [str(x).strip() for x in r]:
            hi = i
            break
    if hi < 0:
        return None
    header = [str(x).strip() for x in rows[hi]]
    first = -1
    for i in range(hi + 1, len(rows)):
        if NS.date_text(rows[i][0] if rows[i] else ''):
            first = i + 1
            break
    if first < 0:
        first = hi + 3

    def col_of(pred, default=-1):
        for j, c in enumerate(header):
            if pred(c):
                return j
        return default

    price_col = col_of(lambda c: '平均价' in c, 7)
    delta_col = col_of(lambda c: c.startswith('涨跌'))
    ratio_col = col_of(lambda c: c.startswith('比例'))
    fx_col = col_of(lambda c: '汇率' in c)
    return {
        'header_row': hi + 1,
        'header': header,
        'first': first,
        'width': _width(rows) or len(header),
        'price_col': price_col,
        'delta_col': delta_col,
        'ratio_col': ratio_col,
        'fx_col': fx_col,
    }


def data_rows(rows, meta):
    """Existing data block as raw padded lists (formulas kept)."""
    out = []
    for r in rows[meta['first'] - 1:]:
        rr = list(r) + [''] * (meta['width'] - len(r))
        rr = rr[:meta['width']]
        if not any(str(x).strip() for x in rr):
            continue
        out.append(rr)
    return out


def scan(rows, meta, width):
    """Template formula per column (first hit) + constant value templates.

    Skips 涨跌/比例 (regenerated from the price column) and never synthesizes
    the average itself. Values count for col K onward so a constant 备注 can
    fill new rows when the fetcher left it blank. The original cell type is
    kept: a constant 10 must fill as the number 10, not as the text '10'."""
    hi = meta['header_row'] - 1
    first = meta['first']
    skip = {meta['delta_col'], meta['ratio_col'], meta['price_col']}
    tpl, vcount, vorig, vtot = {}, {}, {}, {}
    for ri, r in enumerate(rows[hi:]):
        R = hi + ri + 1
        if R < first:
            continue
        rr = list(r) + [''] * (width - len(r))
        for c in range(width):
            if c in skip:
                continue
            v = rr[c]
            if isinstance(v, str) and v.startswith('='):
                if c not in tpl:
                    tpl[c] = (v, R)
            elif c >= 10:
                vv = str(v).strip() if v is not None else ''
                if vv:
                    vtot[c] = vtot.get(c, 0) + 1
                    vcount[(c, vv)] = vcount.get((c, vv), 0) + 1
                    vorig.setdefault((c, vv), v)
    vt = {}
    for c in range(10, width):
        tot = vtot.get(c, 0)
        if not tot:
            continue
        best = max(((v, n) for (cc, v), n in vcount.items() if cc == c),
                   key=lambda kv: kv[1], default=None)
        if best and best[1] / tot >= 0.6:
            vt[c] = vorig.get((c, best[0]), best[0])
    return tpl, vt


def _single_row_tpl(s):
    rows_ref = set(NS.RE_SAMEROW.findall(s))
    return len(rows_ref) <= 1


TEXT_HEADER_CELLS = ('产品名称', '规格型号', '市场', '数据类型', '备注')
RE_PLAINNUM = re.compile(r'^-?\d+(?:\.\d+)?$')


def _unpercent(v, header, c):
    """Undo a USER_ENTERED round-trip: writing the text '85%' stores the number
    0.85 with a percent format. Text columns never hold a ratio, so a float in
    (0, 1] there is always a mangled 规格型号/备注."""
    if c >= len(header) or header[c] not in TEXT_HEADER_CELLS:
        return v
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and 0 < v <= 1:
        return f'{round(v * 100, 6):g}%'
    return v


def _numeric_cols(ded, meta, width):
    """Columns >= 10 whose values are mostly plain numbers (拉柜费, 海运费).
    A text '10' there would break =M3+N3+O3."""
    out = set()
    for c in range(10, width):
        if c in (meta['delta_col'], meta['ratio_col'], meta['price_col']):
            continue
        num = tot = 0
        for rr in ded:
            v = rr[c] if c < len(rr) else None
            if isinstance(v, str) and (not v.strip() or v.startswith('=')):
                continue
            if isinstance(v, bool):
                continue
            tot += 1
            if isinstance(v, (int, float)):
                num += 1
        if tot and num / tot >= 0.6:
            out.add(c)
    return out


def _formula_cols(ded, meta, width):
    """Columns that are mostly formulas (the FX block K..Q). An empty cell there
    is a hole, not a choice, so they are refilled for every row - not just the
    fetched ones - because dedupe_sorted reorders rows and an index-based
    fresh/old split would miss rows that moved."""
    out = set()
    for c in range(width):
        if c in (meta['delta_col'], meta['ratio_col'], meta['price_col']):
            continue
        tot = fml = 0
        for rr in ded:
            v = rr[c] if c < len(rr) else None
            if isinstance(v, str) and v.startswith('='):
                tot += 1
                fml += 1
            elif isinstance(v, str) and v.strip():
                tot += 1
        if tot >= 3 and fml / tot >= 0.6:
            out.add(c)
    return out


def stamp(ded, meta, tpl, vt, fresh_dates=None):
    """Re-point / regenerate every formula so the block stays valid after new
    rows are pushed in at the top (self-heals #REF! 涨跌 cells too).

    fresh_dates: dates that came from the fetch. Constant values (vt) are only
    copied into those rows - an existing row may legitimately have an empty
    备注. Formula holes are filled everywhere (see _formula_cols)."""
    fresh_dates = fresh_dates or set()
    width = meta['width']
    price_col, delta_col, ratio_col = meta['price_col'], meta['delta_col'], meta['ratio_col']
    L = gspread.utils.rowcol_to_a1(1, price_col + 1)[0] if price_col >= 0 else 'H'
    numeric = _numeric_cols(ded, meta, width)
    formula_cols = _formula_cols(ded, meta, width)
    for i, rr in enumerate(ded):
        R = meta['first'] + i
        while len(rr) < width:
            rr.append('')
        for c in range(width):
            rr[c] = _unpercent(rr[c], meta['header'], c)
        price = rr[price_col] if price_col >= 0 else ''
        has_price = str(price).strip() not in ('', '0')
        if delta_col >= 0 and has_price:
            rr[delta_col] = f'={L}{R}-{L}{R + 1}'
        if ratio_col >= 0 and has_price:
            rr[ratio_col] = f'=({L}{R}-{L}{R + 1})/{L}{R + 1}'
        is_fresh = NS.date_text(rr[0]) in fresh_dates
        for c in range(width):
            if c in (delta_col, ratio_col):
                continue
            v = rr[c]
            if isinstance(v, str) and v.startswith('='):
                rr[c] = NS.normalize_single(v, R)
            elif v is None or (isinstance(v, str) and not v.strip()):
                t = tpl.get(c)
                filled = False
                if (t and c != price_col and _single_row_tpl(t[0])
                        and (c in formula_cols or is_fresh)):
                    rr[c] = NS.normalize_single(t[0], R)
                    filled = True
                if not filled and c in vt and (is_fresh or c in numeric):
                    rr[c] = vt[c]
        for c in numeric:
            v = rr[c]
            if isinstance(v, str) and RE_PLAINNUM.match(v.strip()):
                f = float(v)
                rr[c] = int(f) if f == int(f) else f


def build(rows, fresh, meta=None):
    """existing grid rows + fetched rows -> (final block, meta, error).

    Fetched rows come first so they win the date collision; within the old
    block duplicates of a date (a few tabs were pasted twice) collapse to the
    first occurrence, and a price mismatch is reported."""
    meta = meta or analyze(rows)
    if meta is None:
        return None, None, 'no header row'
    width = meta['width']
    existing = data_rows(rows, meta)
    pc = meta['price_col']
    old_by_date = {}
    for r in existing:
        d = NS.date_text(r[0])
        if d and d not in old_by_date:
            old_by_date[d] = r
    nchanged = 0
    for r in fresh:
        d = NS.date_text(r[0])
        old = old_by_date.get(d)
        if old is None or pc < 0:
            continue
        po = _plain(old[pc]) if pc < len(old) else None
        pn = _plain(r[pc]) if pc < len(r) else None
        if po is not None and pn is not None and abs(po - pn) > 1e-9:
            nchanged += 1
            if nchanged <= 8:
                print(f'  WARN {d}: fetched price {pn} replaces sheet value {po}')
    if nchanged > 8:
        print(f'  WARN {nchanged} fetched prices replace existing sheet values')
    merged = [list(r) for r in fresh] + existing
    ded = NS.dedupe_sorted(merged, width)
    if existing:
        by_date = {}
        for r in existing:
            d = NS.date_text(r[0])
            if d:
                by_date.setdefault(d, r)
        kept = {NS.date_text(r[0]) for r in ded}
        for r in existing:
            d = NS.date_text(r[0])
            if not d or d not in kept:
                continue
            k = by_date[d]
            if k is r:
                continue
            pk = _plain(k[meta['price_col']]) if meta['price_col'] < len(k) else None
            pi = _plain(r[meta['price_col']]) if meta['price_col'] < len(r) else None
            if pk is not None and pi is not None and abs(pk - pi) > 1e-9:
                print(f'  WARN {d}: duplicate date with different price kept={pk} dropped={pi}')
    tpl, vt = scan(rows, meta, width)
    fdates = set()
    for r in fresh:
        d = NS.date_text(r[0])
        if d:
            fdates.add(d)
    stamp(ded, meta, tpl, vt, fresh_dates=fdates)
    return ded, meta, None


def _plain(v):
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return None


def _runs(cols):
    runs = []
    for c in cols:
        if runs and runs[-1][1] == c - 1:
            runs[-1][1] = c
        else:
            runs.append([c, c])
    return runs


def _column_kinds(rows, width):
    """(formula columns, plain columns). A plain column is written back with
    RAW so that the text '99%' stays text instead of turning into 0.99."""
    has_f = [False] * width
    has_t = [False] * width
    for r in rows:
        for c in range(min(width, len(r))):
            v = r[c]
            if isinstance(v, str) and v.startswith('='):
                has_f[c] = True
            elif isinstance(v, str) and v.strip():
                has_t[c] = True
    return has_f, has_t


def write_all(sh, blocks, first_by_title, date_col=0, old_end=None):
    """{title: rows} -> values:batchUpdate, twice.

    Pass 1 (USER_ENTERED) parses dates and formulas over the whole block.
    Pass 2 (RAW) rewrites every column that holds no formula - dates excluded -
    as-is, so text that looks like a number or a percentage survives.

    old_end = {title: last row the block occupied before this write}. When the
    block shrank (duplicate dates collapsed) those rows keep their old values
    unless they are cleared, so pass it and the tail is cleared in the same
    batch.
    """
    full, raw, tails = [], [], []
    for title, rows in blocks.items():
        if not rows:
            continue
        width = max(len(r) for r in rows)
        vals = [list(r) + [''] * (width - len(r)) for r in rows]
        first = first_by_title[title]
        end = first + len(vals) - 1
        # rowcol_to_a1(1, width) is e.g. 'Q1' -> keep the column letter
        col = gspread.utils.rowcol_to_a1(1, width)[:-1]
        full.append({'range': f"'{title}'!A{first}:{col}{end}", 'values': vals})
        if old_end:
            oe = old_end.get(title)
            if oe and oe > end:
                # whole stale rows: clear to the last column any tab uses
                tails.append(f"'{title}'!A{end + 1}:AZ{oe}")
        has_f, has_t = _column_kinds(vals, width)
        for c in range(width):
            if has_f[c] and has_t[c]:
                print(f'  WARN {title}: col {c + 1} mixes formulas and text; '
                      f'text cells go through USER_ENTERED')
        plain = [c for c in range(width) if c != date_col and not has_f[c]]
        for a, b in _runs(plain):
            ca = gspread.utils.rowcol_to_a1(1, a + 1)[0]
            cb = gspread.utils.rowcol_to_a1(1, b + 1)[0]
            raw.append({'range': f"'{title}'!{ca}{first}:{cb}{end}",
                        'values': [r[a:b + 1] for r in vals]})
    if not full:
        return 0
    retry(sh.values_batch_update, body={'valueInputOption': 'USER_ENTERED', 'data': full})
    if raw:
        retry(sh.values_batch_update, body={'valueInputOption': 'RAW', 'data': raw})
    if tails:
        retry(sh.values_batch_clear, body={'ranges': tails})
        for t in tails:
            print(f'  cleared tail {t}')
    return len(full)
