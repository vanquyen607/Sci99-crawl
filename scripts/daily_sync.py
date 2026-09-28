# -*- coding: utf-8 -*-
"""Daily orchestrator: login sci99 → update 27 tabs → verify.
Run by Windows Task Scheduler (see daily_sync.bat).
"""
import sys, io, os, subprocess, time, traceback
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, f'daily_{datetime.now():%Y%m%d_%H%M%S}.log')

def log(msg):
    line = f'[{datetime.now():%H:%M:%S}] {msg}'
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def run(step, args, timeout=600):
    log(f'=== STEP: {step} ===')
    t0 = time.time()
    try:
        r = subprocess.run(
            [sys.executable, '-X', 'utf8'] + args,
            cwd=HERE, timeout=timeout,
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        out = (r.stdout or '') + (r.stderr or '')
        # keep last 80 lines in log
        tail = '\n'.join(out.splitlines()[-80:])
        log(tail)
        elapsed = time.time() - t0
        if r.returncode != 0:
            log(f'FAIL {step} rc={r.returncode} ({elapsed:.0f}s)')
            return False
        log(f'OK {step} ({elapsed:.0f}s)')
        return True
    except subprocess.TimeoutExpired:
        log(f'TIMEOUT {step} after {timeout}s')
        return False
    except Exception as e:
        log(f'ERROR {step}: {e}')
        traceback.print_exc(file=sys.stdout)
        return False

def main():
    log(f'DAILY SYNC START pid={os.getpid()}')
    results = {}

    # 1) Refresh sci99 cookies (headless login)
    results['login'] = run('login_sci99', ['login_sci99_daily.py'], timeout=180)
    if not results['login']:
        log('login failed — trying with existing cookies anyway')

    # 2) Fetch fresh article sources (amino + MCP Cjj + MCP SW table)
    results['fetch_sources'] = run('fetch_daily_sources.py', ['fetch_daily_sources.py'], timeout=420)

    # 3) Detail-page products (赖氨酸/苏氨酸/色氨酸/磷酸氢钙/蛋氨酸/维生素/棕榈油)
    results['detail_pages'] = run('update_from_detail_pages.py', ['update_from_detail_pages.py'], timeout=600)

    # 4) Amino articles (缬氨酸/精氨酸/异亮氨酸)
    results['amino_articles'] = run('update_amino_from_articles.py', ['update_amino_from_articles.py'], timeout=300)

    # 5) MCP 磷酸二氢钙 2 blocks
    results['mcp'] = run('update_mcp_two_blocks.py', ['update_mcp_two_blocks.py'], timeout=180)

    # 5b) Choline 60% from echemi (headed Chrome window flashes ~20s; non-core)
    results['choline_echemi'] = run('update_choline_echemi.py', ['update_choline_echemi.py'], timeout=300)

    # 5c) 磷酸一二钙 weekly report (requests + PDF; non-core, skips when no new report)
    results['mdcph_weekly'] = run('update_mdcph_weekly.py', ['update_mdcph_weekly.py'], timeout=240)

    # 5d) 乳清粉 weekly (sci99 search, needs login cookies; early-stops on first known date)
    results['whey'] = run('update_whey_sci99.py', ['update_whey_sci99.py'], timeout=600)

    # 5e) 肌醇 99% 湖北 (100ppi, playwright; early-stops once pages fall behind sheet)
    results['inositol'] = run('update_inositol_100ppi.py', ['update_inositol_100ppi.py'], timeout=420)

    # 5f) 发酵豆粕 50% 营口 (mysteel chart API, 1y daily)
    results['fsb'] = run('update_fsb_mysteel.py', ['update_fsb_mysteel.py'], timeout=180)

    # 6) FX rates (shibor 历史数据): 汇率 sheet 25 pairs + USD col (汇率/USD) of all sheets
    #    (runs AFTER the updaters above so new rows get their K column healed)
    results['fx_sheet'] = run('update_fx_sheet.py', ['update_fx_sheet.py'], timeout=120)
    results['fx_usd_cols'] = run('update_fx_rate.py', ['update_fx_rate.py'], timeout=600)

    # 7) Verify (best-effort; may 429 — needs backoff headroom)
    results['verify'] = run('verify_all_status.py', ['verify_all_status.py'], timeout=600)

    ok = sum(1 for v in results.values() if v)
    log(f'DAILY SYNC DONE {ok}/{len(results)} steps OK: {results}')
    print('RESULTS', results, flush=True)
    # exit 0 if core steps ok (detail + mcp), else 1
    core = results.get('detail_pages') and results.get('mcp')
    return 0 if core else 1

if __name__ == '__main__':
    sys.exit(main())
