# -*- coding: utf-8 -*-
"""Parallel-lane test harness for daily_sync (TEST ONLY - daily_sync.py untouched).

Default is a dry plan. --live runs the same scripts daily_sync.py runs, split
into 4 lanes that run concurrently. A per-host lock keeps two steps that hit
the same site (sci99/100ppi/echemi/...) from overlapping, because the old
sequential flow is what those sites expect.

    python -X utf8 scripts/_test_parallel/run_parallel_test.py            # plan only
    python -X utf8 scripts/_test_parallel/run_parallel_test.py --live     # real run
    python -X utf8 scripts/_test_parallel/run_parallel_test.py --live --only sci99
    python -X utf8 scripts/_test_parallel/run_parallel_test.py --live --no-host-lock
    python -X utf8 scripts/_test_parallel/run_parallel_test.py --live --skip-final

Exit code 0 only when detail_pages and mcp both succeed (same core as daily_sync).
"""
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
LOG_DIR = os.path.join(HERE, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, f'parallel_{datetime.now():%Y%m%d_%H%M%S}.log')
LOCK_FILE = os.path.join(HERE, 'run.lock')

_log_lock = threading.Lock()


def log(msg):
    line = f'[{datetime.now():%H:%M:%S}] {msg}'
    with _log_lock:
        print(line, flush=True)
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


# --------------------------------------------------------------------------- #
# step table: same scripts + timeouts as daily_sync.py
# host = site the step talks to; two steps with the same host never overlap
# --------------------------------------------------------------------------- #
STEPS = {
    'login':          dict(script='login_sci99_daily.py',      timeout=180,  host='sci99'),
    'fetch_sources':  dict(script='fetch_daily_sources.py',    timeout=420,  host='sci99'),
    'detail_pages':   dict(script='update_from_detail_pages.py', timeout=600, host='sci99'),
    'amino':          dict(script='update_amino_from_articles.py', timeout=300, host='sci99'),
    'mcp':            dict(script='update_mcp_two_blocks.py',  timeout=180,  host='sheets'),
    'choline':        dict(script='update_choline_echemi.py',  timeout=300,  host='echemi'),
    'mdcph':          dict(script='update_mdcph_weekly.py',    timeout=240,  host='sci99'),
    'whey':           dict(script='update_whey_sci99.py',      timeout=600,  host='sci99'),
    'inositol':       dict(script='update_inositol_100ppi.py', timeout=420,  host='100ppi'),
    'fsb':            dict(script='update_fsb_mysteel.py',     timeout=180,  host='mysteel'),
    'raw_100ppi':     dict(script='update_raw_100ppi.py',      timeout=900,  host='100ppi'),
    'raw_echemi':     dict(script='update_raw_echemi.py',      timeout=1800, host='echemi'),
    'raw_sci99':      dict(script='update_raw_sci99.py',       timeout=600,  host='sci99'),
    'raw_sci99_pdf':  dict(script='update_raw_sci99_pdf.py',   timeout=300,  host='sci99'),
    'raw_cnbg':       dict(script='update_raw_cnbg.py',        timeout=180,  host='cnbg'),
    'fx_sheet':       dict(script='update_fx_sheet.py',        timeout=120,  host='shibor'),
    'fx_usd_cols':    dict(script='update_fx_rate.py',         timeout=600,  host='shibor'),
    'verify':         dict(script='verify_all_status.py',      timeout=600,  host='sheets'),
}

LANES = {
    'sci99':   ['detail_pages', 'whey', 'mdcph', 'raw_sci99', 'raw_sci99_pdf'],
    '100ppi':  ['inositol', 'raw_100ppi', 'fsb', 'raw_cnbg'],
    'echemi':  ['choline', 'raw_echemi'],
    'articles': ['fetch_sources', 'amino', 'mcp'],
}
FINAL = ['fx_sheet', 'fx_usd_cols', 'verify']

_host_locks = {}
_host_lock_enabled = True


def _host_lock(host):
    if not _host_lock_enabled or not host:
        return None
    with _log_lock:
        return _host_locks.setdefault(host, threading.Lock())


def _kill_tree(pid):
    try:
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(pid)],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def run_step(name, prefix):
    step = STEPS[name]
    lock = _host_lock(step['host'])
    if lock:
        log(f'{prefix} wait for host {step["host"]}: {name}')
        lock.acquire()
    t0 = time.time()
    log(f'{prefix} >>> {name} ({step["script"]}, timeout {step["timeout"]}s)')
    try:
        p = subprocess.Popen(
            [sys.executable, '-X', 'utf8', step['script']], cwd=SCRIPTS,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1)

        def _pump():
            try:
                for ln in p.stdout:
                    log(f'{prefix}   {ln.rstrip(chr(10))}')
            except Exception:
                pass

        th = threading.Thread(target=_pump, daemon=True)
        th.start()
        while p.poll() is None and time.time() - t0 < step['timeout']:
            time.sleep(0.5)
        if p.poll() is None:
            _kill_tree(p.pid)
            th.join(5)
            log(f'{prefix} TIMEOUT {name} after {step["timeout"]}s')
            return False, time.time() - t0
        th.join(10)
        elapsed = time.time() - t0
        if p.returncode != 0:
            log(f'{prefix} FAIL {name} rc={p.returncode} ({elapsed:.0f}s)')
            return False, elapsed
        log(f'{prefix} OK {name} ({elapsed:.0f}s)')
        return True, elapsed
    except Exception as e:
        log(f'{prefix} ERROR {name}: {e}')
        traceback.print_exc(file=sys.stdout)
        return False, time.time() - t0
    finally:
        if lock:
            lock.release()


def run_lane(lane, names, results, durations):
    t0 = time.time()
    for i, name in enumerate(names):
        if i == 0:
            ok, el = run_step(name, f'[{lane}]')
            results[name] = ok
            durations[name] = el
        else:
            # stop the lane on failure, like a shell &&
            prev = names[i - 1]
            if not results.get(prev):
                log(f'[{lane}] skip {name} (previous step failed)')
                results[name] = False
                continue
            ok, el = run_step(name, f'[{lane}]')
            results[name] = ok
            durations[name] = el
    log(f'[{lane}] lane done in {time.time() - t0:.0f}s')


def acquire_instance_lock():
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        with open(LOCK_FILE, encoding='utf-8') as f:
            pid = f.read().strip()
        log(f'another test run is active (pid {pid}); remove {LOCK_FILE} if stale')
        return False
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(str(os.getpid()))
    return True


def main():
    global _host_lock_enabled
    live = '--live' in sys.argv
    _host_lock_enabled = '--no-host-lock' not in sys.argv
    skip_final = '--skip-final' in sys.argv
    only = None
    if '--only' in sys.argv:
        idx = sys.argv.index('--only')
        if idx + 1 < len(sys.argv):
            only = sys.argv[idx + 1]

    lanes = dict(LANES)
    if only:
        if only not in lanes:
            print(f'unknown lane {only!r}; lanes: {", ".join(lanes)}')
            return 2
        lanes = {only: lanes[only]}

    log(f'PARALLEL TEST START pid={os.getpid()} live={live} '
        f'host_lock={_host_lock_enabled} lanes={list(lanes)}')
    if not live:
        log('DRY PLAN (pass --live to execute):')
        log('  step order per lane (host lock serializes same-site steps)')
        for lane, names in lanes.items():
            for name in names:
                s = STEPS[name]
                log(f'    [{lane}] {name:<14} {s["script"]:<32} '
                    f'timeout={s["timeout"]:>4}s host={s["host"]}')
        if not skip_final:
            for name in FINAL:
                s = STEPS[name]
                log(f'    [final] {name:<12} {s["script"]:<32} '
                    f'timeout={s["timeout"]:>4}s host={s["host"]}')
        log('DONE dry')
        return 0

    if not acquire_instance_lock():
        return 2

    t_start = time.time()
    results, durations = {}, {}
    try:
        log('phase 0: login (all lanes depend on fresh sci99 cookies)')
        ok, el = run_step('login', '[login]')
        results['login'] = ok
        durations['login'] = el
        if not ok:
            log('login failed - lanes still run with existing cookies')

        threads = []
        for lane, names in lanes.items():
            th = threading.Thread(target=run_lane, args=(lane, names, results, durations),
                                  name=lane, daemon=False)
            th.start()
            threads.append((lane, th))
        for lane, th in threads:
            th.join()
            log(f'[{lane}] joined')

        if not skip_final:
            log('phase final: fx + verify (after every sheet writer)')
            for name in FINAL:
                ok, el = run_step(name, '[final]')
                results[name] = ok
                durations[name] = el
                if not ok and name != 'verify':
                    log(f'[final] continue after failure of {name}')

        wall = time.time() - t_start
        ok_n = sum(1 for v in results.values() if v)
        log(f'PARALLEL TEST DONE {ok_n}/{len(results)} steps OK in {wall:.0f}s '
            f'({wall / 60:.1f} min)')
        for name, el in sorted(durations.items(), key=lambda kv: -kv[1]):
            log(f'  {name:<14} {el:>6.0f}s  {"OK" if results.get(name) else "FAIL"}')
        core = results.get('detail_pages') and results.get('mcp')
        return 0 if core else 1
    finally:
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass


if __name__ == '__main__':
    sys.exit(main())
