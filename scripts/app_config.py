# -*- coding: utf-8 -*-
"""Load/save app_settings.json + apply schedule to Windows Task Scheduler."""
import os, json, subprocess, re

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(HERE, 'app_settings.json')
DEFAULT_DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

def load_settings():
    if not os.path.exists(SETTINGS_PATH):
        return {}
    with open(SETTINGS_PATH, encoding='utf-8') as f:
        return json.load(f)

def save_settings(data):
    with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return SETTINGS_PATH

def apply_login_to_scripts(settings):
    """Write username/password into login_sci99_daily.py + login_sci99.py."""
    user = settings.get('sci99_username', '')
    pwd = settings.get('sci99_password', '')
    for name in ('login_sci99_daily.py', 'login_sci99.py'):
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            src = f.read()
        src2 = re.sub(r"USERNAME\s*=\s*['\"][^'\"]*['\"]", f"USERNAME = {user!r}", src, count=1)
        src2 = re.sub(r"PASSWORD\s*=\s*['\"][^'\"]*['\"]", f"PASSWORD = {pwd!r}", src2, count=1)
        if src2 != src:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(src2)
    return True

def get_schedule_status(task_name='sci99-sheets-daily'):
    """Query schtasks. Return dict or None."""
    try:
        r = subprocess.run(
            ['schtasks', '/query', '/tn', task_name, '/fo', 'LIST', '/v'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20
        )
        out = (r.stdout or '') + (r.stderr or '')
        if r.returncode != 0 and 'cannot find' in out.lower():
            return {'exists': False, 'raw': out}
        status = {'exists': True, 'raw': out}
        m = re.search(r'Status:\s+(.+)', out)
        if m: status['status'] = m.group(1).strip()
        m = re.search(r'Next Run Time:\s+(.+)', out)
        if m: status['next_run'] = m.group(1).strip()
        m = re.search(r'Start Time:\s+(.+)', out)
        if m: status['start_time'] = m.group(1).strip()
        m = re.search(r'Schedule Type:\s+(.+)', out)
        if m: status['schedule_type'] = m.group(1).strip()
        m = re.search(r'Days:\s+(.+)', out)
        if m: status['days'] = m.group(1).strip()
        m = re.search(r'Task To Run:\s+(.+)', out)
        if m: status['task_to_run'] = m.group(1).strip()
        m = re.search(r'Scheduled Task State:\s+(.+)', out)
        if m: status['enabled'] = 'Enabled' in m.group(1)
        return status
    except Exception as e:
        return {'exists': False, 'error': str(e)}

def apply_schedule(settings, task_name=None):
    """Create or change Windows scheduled task from settings.schedule."""
    sch = settings.get('schedule', {})
    name = task_name or settings.get('task_name', 'sci99-sheets-daily')
    enabled = sch.get('enabled', True)
    hour = int(sch.get('hour', 18))
    minute = int(sch.get('minute', 30))
    days = sch.get('days') or DEFAULT_DAYS
    # normalize day names for schtasks: MON,TUE,...
    day_csv = ','.join(d.upper()[:3] for d in days)
    st = f'{hour:02d}:{minute:02d}'
    bat = os.path.join(HERE, 'daily_sync.bat')
    if not os.path.exists(bat):
        return False, f'bat not found: {bat}'

    # delete existing
    subprocess.run(['schtasks', '/delete', '/tn', name, '/f'],
                   capture_output=True, text=True, timeout=15)

    if not enabled:
        return True, f'task {name} deleted/disabled (enabled=false)'

    # weekly with days
    cmd = ['schtasks', '/create', '/tn', name, '/tr', bat,
           '/sc', 'weekly', '/d', day_csv, '/st', st, '/f']
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=20)
    out = ((r.stdout or '') + (r.stderr or '')).strip()
    if r.returncode != 0:
        # fallback daily
        cmd = ['schtasks', '/create', '/tn', name, '/tr', bat,
               '/sc', 'daily', '/st', st, '/f']
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=20)
        out = ((r.stdout or '') + (r.stderr or '')).strip()
    ok = r.returncode == 0 or 'SUCCESS' in out.upper() or 'exists' in out.lower()
    return ok, out or f'schedule applied {st} days={day_csv}'

def run_task_now(task_name='sci99-sheets-daily'):
    r = subprocess.run(['schtasks', '/run', '/tn', task_name],
                       capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=20)
    return r.returncode == 0, ((r.stdout or '') + (r.stderr or '')).strip()

def enable_task(task_name='sci99-sheets-daily', enable=True):
    flag = '/en' if enable else '/di'
    r = subprocess.run(['schtasks', '/change', '/tn', task_name, flag],
                       capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=15)
    return r.returncode == 0, ((r.stdout or '') + (r.stderr or '')).strip()

if __name__ == '__main__':
    s = load_settings()
    print('settings keys:', list(s.keys()))
    print('schedule status:', get_schedule_status(s.get('task_name', 'sci99-sheets-daily')))
