# -*- coding: utf-8 -*-
"""Shared read/write helpers for the '2026.09.25' sheet (new single-tab format).

- read_formula_rows(): rows kept as raw cells (formula strings preserved),
  date serials converted to 'M/D/YYYY' text, padded to width.
- write_tab(): sort desc + re-point formulas to their final rows
  (col8/col9 by per-sheet detected pattern, cols10-16 single-row refs) +
  fill template formulas for empty cells of newly appended rows.
"""
import re
from datetime import datetime, timedelta

import gspread

RE_SAMEROW = re.compile(r'\$?[A-Z]{1,3}\$?(\d+)')
RE_C8 = re.compile(r'^=\+?\(?(H(\d+)-H(\d+))\)?$')
RE_C9 = re.compile(r'^=\(H(\d+)-H(\d+)\)/H(\d+)$')

# Standard 17-col header (same as 氯化胆碱_echemi / 87% tabs)
STD_HEADER = ['日期', '产品名称', '规格型号', '市场', '数据类型', '最低价', '最高价',
              '平均价 （元/吨）', '涨跌', '比例', '汇率\nUSD', '折成美金',
              '退税后\n（-13%）', '拉柜+报关费', '海运费', 'CIF 估算', '备注']


def serial_to_date(v):
    try:
        return datetime(1899, 12, 30) + timedelta(days=float(v))
    except (TypeError, ValueError):
        return None


def date_text(v):
    """Cell -> 'M/D/YYYY' when it is a date (serial or text), else ''."""
    if isinstance(v, str) and re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', v.strip()):
        return v.strip()
    d = serial_to_date(v)
    if d and 1990 < d.year < 2100:
        return f'{d.month}/{d.day}/{d.year}'
    return ''


def date_key(s):
    try:
        return datetime.strptime(s, '%m/%d/%Y')
    except Exception:
        return datetime(1900, 1, 1)


def carry_over(new_rows, old_rows, cols=(10, 16)):
    """Copy cols (K 汇率, Q 备注 by default) from old_rows to new_rows for the
    same date when the new cell is empty. Writers put fetched rows first (they
    win on price), which would otherwise drop K/remark for every overlapped
    date on each rewrite."""
    old_by_date = {}
    for r in old_rows:
        d = date_text(r[0])
        if d:
            old_by_date[d] = r
    for r in new_rows:
        o = old_by_date.get(date_text(r[0]))
        if not o:
            continue
        for c in cols:
            v_new = r[c] if c < len(r) else ''
            v_old = o[c] if c < len(o) else ''
            if not str(v_new).strip() and str(v_old).strip():
                while len(r) <= c:
                    r.append('')
                r[c] = v_old
    return new_rows


def dedupe_sorted(rows, width):
    """Pad to width, normalize date text, keep first row per date, sort desc."""
    seen, ded = set(), []
    for r in rows:
        rr = list(r[:width]) + [''] * max(0, width - len(r))
        if isinstance(rr[0], str):
            rr[0] = rr[0].strip()
        d = date_text(rr[0])
        if d:
            if d in seen:
                continue
            seen.add(d)
            rr[0] = d
        ded.append(rr)
    ded.sort(key=lambda r: date_key(date_text(r[0])), reverse=True)
    return ded


def stamp_formulas(ded, first_data_row=3, factor='87%'):
    """For narrow/legacy tabs being upgraded to the 17-col layout: assign
    col8/col9 (above-self delta), col11/col12/col15 formulas and col13/col14
    constants. Rows must already be dedupe_sorted (so row numbers are final).
    Top row gets col8/col9 cleared (no previous day to diff against)."""
    for i, rr in enumerate(ded):
        R = first_data_row + i
        while len(rr) < 17:
            rr.append('')
        h = rr[7]
        if str(h).strip() in ('', '0'):
            continue
        if i > 0:
            rr[8] = f'=H{R - 1}-H{R}'
            rr[9] = f'=(H{R - 1}-H{R})/H{R}'
        else:
            for c in (8, 9):
                if isinstance(rr[c], str) and rr[c].startswith('='):
                    rr[c] = ''
        for c, val in ((11, f'=H{R}/K{R}'), (12, f'=L{R}*{factor}'),
                       (13, 10), (14, 30), (15, f'=M{R}+N{R}+O{R}')):
            if not (isinstance(rr[c], str) and rr[c].strip()):
                rr[c] = val


def normalize_single(s, R):
    """If all letter-row-refs share one row number, point them at R."""
    rows = set(RE_SAMEROW.findall(s))
    if len(rows) == 1:
        p = next(iter(rows))
        if p != str(R):
            return re.sub(r'(\$?[A-Z]{1,3}\$?)' + p + r'(?![0-9])',
                          lambda m: m.group(1) + str(R), s)
    return s


def _rng(ws, first, width):
    end = max(ws.row_count, first + 50)
    col2 = gspread.utils.rowcol_to_a1(1, width)[1:]
    return f'A{first}:{col2}{end}'


def read_formula_rows(ws, first_data_row=3, width=17):
    """Raw rows (formulas preserved); date cells as 'M/D/YYYY' text."""
    f = ws.get(_rng(ws, first_data_row, width), value_render_option='FORMULA')
    out = []
    for r in f:
        rr = list(r[:width]) + [''] * max(0, width - len(r))
        if not any(str(x).strip() for x in rr):
            continue
        d = date_text(rr[0])
        if d:
            rr[0] = d
        out.append(rr)
    return out


def _scan(ws, first, width):
    """Scan the sheet for:
    - col8/col9 offset patterns: majority vote of (ref_row - own_row)
    - template formula per col 7..16: (formula_str, own_row) first hit
    - value template per col 11..16: most common non-empty non-formula value
      when it appears in >= 60% of such cells (constant columns like
      col13/col14 fees or col16 remark). col10 (汇率) excluded — it varies
      per date and legacy tabs may hold other content there.
    """
    f = ws.get(_rng(ws, first, width), value_render_option='FORMULA')
    off8, off9 = {}, {}
    tpl = {}
    vcount = {c: {} for c in range(11, width)}
    vtot = {c: 0 for c in range(11, width)}
    for ri, r in enumerate(f):
        R = first + ri
        rr = list(r) + [''] * (width - len(r))
        for c in range(7, width):
            v = rr[c]
            is_f = isinstance(v, str) and v.startswith('=')
            if is_f:
                if c not in tpl:
                    tpl[c] = (v, R)
                if c == 8:
                    m = RE_C8.match(v.strip())
                    if m:
                        k = (int(m.group(2)) - R, int(m.group(3)) - R)
                        off8[k] = off8.get(k, 0) + 1
                elif c == 9:
                    m = RE_C9.match(v.strip())
                    if m:
                        k = (int(m.group(1)) - R, int(m.group(2)) - R, int(m.group(3)) - R)
                        off9[k] = off9.get(k, 0) + 1
            elif c >= 11:
                vv = str(v).strip() if v is not None else ''
                if vv:
                    vtot[c] += 1
                    vcount[c][vv] = vcount[c].get(vv, 0) + 1
    p8 = max(off8, key=off8.get) if off8 else None
    p9 = max(off9, key=off9.get) if off9 else None
    vt = {}
    for c, cnt in vcount.items():
        if not cnt:
            continue
        val, n = max(cnt.items(), key=lambda kv: kv[1])
        if vtot[c] and n / vtot[c] >= 0.6:
            vt[c] = val
    return p8, p9, tpl, vt


def write_tab(ws, rows, first_data_row=3, width=17):
    """Sort desc + repair/fill formulas + write the full block.

    rows: complete final block (existing rows carry their raw formula cells;
    new rows carry data cols; cells intended for generation left as '').
    Returns (n_written, had_changes).
    """
    ded = dedupe_sorted(rows, width)

    p8, p9, tpl, vt = _scan(ws, first_data_row, width)

    def refs_ok(offsets, R):
        return all(R + o >= first_data_row for o in offsets)

    for i, rr in enumerate(ded):
        R = first_data_row + i
        h = rr[7]
        has_h = str(h).strip() not in ('', '0')
        # col8 / col9: values kept; empty + detected pattern + H present -> generate
        if p8 and refs_ok(p8, R):
            v = rr[8]
            if (not (isinstance(v, str) and v.strip())) and has_h:
                rr[8] = f'=H{R + p8[0]}-H{R + p8[1]}'
            elif isinstance(v, str) and v.startswith('='):
                rr[8] = f'=H{R + p8[0]}-H{R + p8[1]}'
        if p9 and refs_ok(p9, R):
            v = rr[9]
            if (not (isinstance(v, str) and v.strip())) and has_h:
                rr[9] = f'=(H{R + p9[0]}-H{R + p9[1]})/H{R + p9[2]}'
            elif isinstance(v, str) and v.startswith('='):
                rr[9] = f'=(H{R + p9[0]}-H{R + p9[1]})/H{R + p9[2]}'
        # other formula cols
        for c in range(width):
            if c in (8, 9):
                continue
            v = rr[c]
            if isinstance(v, str) and v.startswith('='):
                rr[c] = normalize_single(v, R)
            elif v is None or (isinstance(v, str) and not v.strip()):
                # empty cell of a new row -> template formula (single-row refs)
                t = tpl.get(c)
                filled = False
                if t and c != 7:   # never synthesize avg (col7)
                    rows_ref = set(RE_SAMEROW.findall(t[0]))
                    if len(rows_ref) <= 1:
                        rr[c] = normalize_single(t[0], R) if rows_ref else t[0]
                        filled = True
                if not filled and c in vt:
                    rr[c] = vt[c]

    n_old = len(ws.get(_rng(ws, first_data_row, width)))
    col2 = gspread.utils.rowcol_to_a1(1, width)[1:]
    end = max(first_data_row + max(n_old, len(ded)) + 10, first_data_row + len(ded) + 10)
    ws.batch_clear([f'A{first_data_row}:{col2}{end}'])
    if ded:
        ws.update(ded, f'A{first_data_row}', value_input_option='USER_ENTERED')
    return len(ded), len(ded) != n_old
