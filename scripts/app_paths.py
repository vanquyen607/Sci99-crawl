# -*- coding: utf-8 -*-
"""Single source of truth for the service-account file and the 2 spreadsheet IDs.

Everything reads scripts/app_settings.json (written by the GUI ⚙ Cài đặt tab).
Missing keys fall back to the historical hardcoded defaults, so an existing
machine and a fresh clone keep working unchanged.

Reconfigure a machine by editing app_settings.json (or the GUI) only:
    service_account_json  -> path to the Google service-account JSON
    spreadsheet_id        -> OLD sheet (33 tabs)
    raw_spreadsheet_id    -> RAW sheet (51 data tabs + 3 index tabs)
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(HERE, 'app_settings.json')

DEFAULT_SERVICE_ACCOUNT = r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json'
DEFAULT_OLD_SID = '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU'
DEFAULT_RAW_SID = '1pnDkBjLjfXgNE-Qv7rU7risEfcM3y4f4nd-OTN9XEu0'

_settings = None


def _load():
    global _settings
    if _settings is None:
        try:
            with open(SETTINGS_PATH, encoding='utf-8') as f:
                _settings = json.load(f)
        except (OSError, ValueError):
            _settings = {}
    return _settings


def _get(key):
    v = _load().get(key)
    return v.strip() if isinstance(v, str) else ''


def service_account_path():
    return _get('service_account_json') or DEFAULT_SERVICE_ACCOUNT


def old_spreadsheet_id():
    return _get('spreadsheet_id') or DEFAULT_OLD_SID


def raw_spreadsheet_id():
    return _get('raw_spreadsheet_id') or DEFAULT_RAW_SID
