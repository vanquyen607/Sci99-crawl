# -*- coding: utf-8 -*-
"""One-off repair: remove/fix rows that the 100ppi fallback wrote from a
DIFFERENT trader than the tab's 备注 names (see update_raw_100ppi.py, which
now skips instead of mixing).

Every row listed here was checked against the source pages:
  - REMOVE: the named trader has no quote that day, another trader does, and
            the stored price is that stranger's (玉米淀粉 2900 -> 3860).
  - FIX:    the named trader did quote that day and the stored price is a
            stranger's (丙酸 6400 stored as 6900).

Removing rows shrinks the block; write_all clears the stale tail rows left
behind by the previous, longer block when old_end says the block shrank.
"""
import io
import os
import sys

if __name__ == '__main__' and __package__ is None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import newsheet_lib as NS
import raw_lib as RL

REMOVE = {
    '玉米淀粉_100ppi': {'10/2/2026', '9/28/2026'},
    '乳酸_100ppi': {'10/2/2026', '9/26/2026'},
    '丙酸_国产_100ppi': {'9/30/2026'},
    '磷酸_100ppi': {'9/30/2026'},
}
FIX = {
    '丙酸_国产_100ppi': {'9/29/2026': 6400},
    '磷酸_100ppi': {'9/29/2026': 11000},
}


def main():
    sh = RL.open_sh()
    titles = sorted(set(REMOVE) | set(FIX))
    grid = RL.read_grid(sh, titles)
    blocks, first, ends = {}, {}, {}
    for t in titles:
        rows = grid[t]
        meta = RL.analyze(rows)
        if meta is None:
            print(f'  FAIL {t}: no header')
            continue
        old = RL.data_rows(rows, meta)
        old_end = meta['first'] + len(old) - 1
        width = meta['width']
        remove, fix = REMOVE.get(t, set()), FIX.get(t, {})
        g2 = [list(r) for r in rows]
        nrem = nfix = 0
        for i, r in enumerate(g2):
            if not r:
                continue
            d = NS.date_text(r[0])
            if d in remove:
                p = RL._plain(r[meta['price_col']]) if meta['price_col'] < len(r) else None
                g2[i] = [''] * max(len(r), width)
                print(f'  {t}: drop {d} (price {p})')
                nrem += 1
            elif d in fix:
                old_p = r[meta['price_col']] if meta['price_col'] < len(r) else None
                while len(r) <= meta['price_col']:
                    r.append('')
                r[meta['price_col']] = fix[d]
                print(f'  {t}: {d} price {old_p} -> {fix[d]}')
                nfix += 1
        if not nrem and not nfix:
            print(f'  {t}: nothing to repair')
            continue
        built, meta2, err = RL.build(g2, [], meta)
        if err:
            print(f'  FAIL {t}: {err}')
            continue
        new_end = meta['first'] + len(built) - 1
        blocks[t] = built
        first[t] = meta['first']
        ends[t] = old_end
        note = f'{len(old)} -> {len(built)} rows'
        if new_end < old_end:
            note += f', clear A{new_end + 1}:*{old_end}'
        print(f'  {t}: {note}')
    if not blocks:
        print('nothing to do')
        print('DONE repair_100ppi_leaks')
        return
    if '--dry' in sys.argv:
        print(f'[dry] would write {sorted(blocks)}')
        print('DONE repair_100ppi_leaks')
        return
    n = RL.write_all(sh, blocks, first, old_end=ends)
    print(f'wrote {n} tabs in 1 call')
    print('DONE repair_100ppi_leaks')


if __name__ == '__main__':
    main()
