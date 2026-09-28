# -*- coding: utf-8 -*-
"""
SCI99 → Google Sheets — Desktop GUI (Light / Pro theme)
Double-click Mo app.bat (or run: python -X utf8 sci99_gui.py)
"""
import sys, os, re, json, ast, subprocess, threading, time, glob, queue
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import app_config as cfg

# ---------- palettes: Light / Pro (default) + Dark ----------
LIGHT = {
    'bg':       '#f4f6fa',   # app background
    'surface':  '#ffffff',   # cards
    'surface2': '#eef2f7',   # nested / input bg
    'border':   '#dce3ec',
    'text':     '#0f172a',   # primary
    'muted':    '#64748b',   # secondary
    'accent':   '#2563eb',   # blue primary
    'accent_h': '#1d4ed8',
    'ok':       '#16a34a',
    'ok_h':     '#15803d',
    'warn':     '#d97706',
    'err':      '#dc2626',
    'info':     '#0284c7',
    'tab_bg':   '#e8edf4',
    'tab_sel':  '#ffffff',
    'head_bg':  '#f1f5f9',
    'row_alt':  '#f8fafc',
    'sel':      '#dbeafe',
    'sel_run':  '#bfdbfe',
    'console':  '#0f172a',
    'console_f':'#e2e8f0',
}
DARK = {
    'bg':       '#0b1120',
    'surface':  '#111a2e',
    'surface2': '#1a2438',
    'border':   '#24314a',
    'text':     '#e5eaf3',
    'muted':    '#8ea0bd',
    'accent':   '#3b82f6',
    'accent_h': '#2563eb',
    'ok':       '#22c55e',
    'ok_h':     '#16a34a',
    'warn':     '#f59e0b',
    'err':      '#f87171',
    'info':     '#38bdf8',
    'tab_bg':   '#0f172a',
    'tab_sel':  '#111a2e',
    'head_bg':  '#16203a',
    'row_alt':  '#0f182b',
    'sel':      '#1e3a8a',
    'sel_run':  '#1d4ed8',
    'console':  '#080d18',
    'console_f':'#dbe6f7',
}
C = dict(LIGHT)
FONT   = ('Segoe UI', 10)
FONT_S = ('Segoe UI', 9)
FONT_B = ('Segoe UI', 10, 'bold')
FONT_H = ('Segoe UI', 15, 'bold')
FONT_H2= ('Segoe UI', 12, 'bold')
FONT_NUM = ('Segoe UI', 18, 'bold')

# (STEP marker key in daily_sync output, display name, results key, core?)
STEPS = [
    ('login_sci99',                  'Đăng nhập sci99',         'login',            False),
    ('fetch_daily_sources.py',       'Tải nguồn (articles+MCP)', 'fetch_sources',   False),
    ('update_from_detail_pages.py',  'Trang chi tiết sản phẩm', 'detail_pages',     True),
    ('update_amino_from_articles.py','Bài viết amino (3 sp)',   'amino_articles',   False),
    ('update_mcp_two_blocks.py',     'MCP 磷酸二氢钙 2 block',  'mcp',              True),
    ('update_choline_echemi.py',     '氯化胆碱 60% (echemi)',   'choline_echemi',   False),
    ('update_mdcph_weekly.py',       '磷酸一二钙-每周',         'mdcph_weekly',     False),
    ('update_whey_sci99.py',         '乳清粉 (sci99 tuần)',      'whey',             False),
    ('update_inositol_100ppi.py',    '肌醇 100ppi',              'inositol',         False),
    ('update_fsb_mysteel.py',        '发酵豆粕 (mysteel)',       'fsb',              False),
    ('update_fx_sheet.py',           '汇率 sheet 25 cặp',       'fx_sheet',         False),
    ('update_fx_rate.py',            'Cột 汇率/USD (all)',      'fx_usd_cols',      False),
    ('verify_all_status.py',         'Verify 33 sheet',         'verify',           False),
]
_TS = r'^\[\d{2}:\d{2}:\d{2}\] '


class ToolTip:
    """Hover tooltip cho nút bấm (desktop-app feel)."""
    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self._after = None
        self.tw = None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')

    def _schedule(self, event=None):
        try:
            self._after = self.widget.after(500, self._show)
        except Exception:
            pass

    def _show(self):
        if not self.widget.winfo_exists():
            return
        try:
            self.tw = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            tw.wm_geometry(f'+{x}+{y}')
            tk.Label(tw, text=self.text, justify='left', background=C['console'],
                     foreground=C['console_f'], relief='solid', borderwidth=1,
                     font=('Segoe UI', 9), padx=8, pady=4, wraplength=340).pack()
        except Exception:
            self.tw = None

    def _hide(self, event=None):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
        if self.tw:
            try:
                self.tw.destroy()
            except Exception:
                pass
            self.tw = None

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

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('SCI99 Sheets Autosync')
        self.geometry('1160x860')
        self.minsize(1040, 760)
        self.configure(bg=C['bg'])
        self.settings = cfg.load_settings() or self._default_settings()
        self.sheets = self._merge_sheets()
        self.running = False
        self.proc = None
        self._stop_requested = False
        self._single_running = False
        self._ui_q = queue.Queue()
        self._status_rows = []
        self._status_gids = {}
        self._data_rows = []
        self._history_rows = []
        self._theme = self.settings.get('theme', 'light')
        self._build_styles()
        self._build_header()
        self._build_body()
        self._build_footer()
        self.after(50, self._poll_ui_q)
        # phím tắt desktop: F5 refresh, F6 chạy sync, Esc dừng
        self.bind('<F5>', lambda e: self.refresh_all())
        self.bind('<F6>', lambda e: self.run_sync())
        self.bind('<Escape>', lambda e: self.stop_sync())
        if self._theme == 'dark':
            self._apply_theme('dark')
        self.refresh_schedule_status()
        self.refresh_sheet_status()
        self.refresh_history()

    def _merge_sheets(self):
        """33 tab chuẩn = nguồn sự thật; đồng bộ về app_settings.json nếu lệch."""
        merged = list(SHEETS)
        if (self.settings.get('sheets') or []) != merged:
            self.settings['sheets'] = merged
            try:
                cfg.save_settings(self.settings)
            except Exception:
                pass
        return merged

    def _subtitle(self):
        sch = self.settings.get('schedule', {})
        try:
            t = f"{int(sch.get('hour', 18)):02d}:{int(sch.get('minute', 30)):02d}"
        except Exception:
            t = '18:30'
        return f'{len(self.sheets)} sheet · sci99.com → Google Sheets · daily {t}'

    # ---------- theme (Light / Dark) ----------
    _REMAP_OPTS = ('bg', 'fg', 'activebackground', 'activeforeground', 'selectcolor',
                   'highlightbackground', 'highlightcolor', 'insertbackground',
                   'buttonbackground')

    def toggle_theme(self):
        self._apply_theme('dark' if self._theme == 'light' else 'light')
        self.settings['theme'] = self._theme
        try:
            cfg.save_settings(self.settings)
        except Exception:
            pass

    def _apply_theme(self, theme):
        new = DARK if theme == 'dark' else LIGHT
        old = dict(C)
        self._theme = theme
        if old != new:
            C.clear()
            C.update(new)
            self._build_styles()
            self._remap_widgets(self, {old[k]: new[k] for k in old if old[k] != new[k]})
            if hasattr(self, 'tree_hist'):
                for tag, color in (('ok', C['ok']), ('warn', C['warn']),
                                   ('err', C['err']), ('run', C['info'])):
                    self.tree_hist.tag_configure(tag, foreground=color)
        if hasattr(self, 'btn_theme'):
            self.btn_theme.config(text='☀️  Light' if theme == 'dark' else '🌙  Dark')

    def _remap_widgets(self, w, mapping):
        if not mapping:
            return
        for opt in self._REMAP_OPTS:
            try:
                v = w.cget(opt)
            except Exception:
                continue
            if v in mapping:
                try:
                    w.config(**{opt: mapping[v]})
                except Exception:
                    pass
        for ch in w.winfo_children():
            self._remap_widgets(ch, mapping)

    # ---------- helpers: styles / widgets ----------
    def _post(self, fn, *args):
        self._ui_q.put((fn, args))

    def _poll_ui_q(self):
        try:
            while True:
                fn, args = self._ui_q.get_nowait()
                try:
                    fn(*args)
                except Exception as e:
                    print('ui callback error:', e)
        except queue.Empty:
            pass
        self.after(50, self._poll_ui_q)

    def _default_settings(self):
        return {
            'sci99_username': '',
            'sci99_password': '',
            'spreadsheet_id': '1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU',
            'service_account_json': r'C:\Users\DELL\.openclaw\workspace\secrets\service_account.json',
            'task_name': 'sci99-sheets-daily',
            'schedule': {'enabled': True, 'hour': 18, 'minute': 30,
                         'days': ['MON','TUE','WED','THU','FRI','SAT','SUN']},
            'sheets': SHEETS[:],
        }

    def _build_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        # Notebook tabs
        style.configure('TNotebook', background=C['bg'], borderwidth=0, padding=0)
        style.configure('TNotebook.Tab', background=C['tab_bg'], foreground=C['muted'],
                        padding=(16, 9), font=FONT_B, borderwidth=0)
        style.map('TNotebook.Tab',
                  background=[('selected', C['tab_sel'])],
                  foreground=[('selected', C['accent'])])
        # Frames
        style.configure('TFrame', background=C['bg'])
        style.configure('Card.TFrame', background=C['surface'], relief='solid', borderwidth=1,
                        bordercolor=C['border'])
        style.configure('Inner.TFrame', background=C['surface'])
        # Labels
        style.configure('TLabel', background=C['bg'], foreground=C['text'], font=FONT)
        style.configure('Card.TLabel', background=C['surface'], foreground=C['text'], font=FONT)
        style.configure('Muted.TLabel', background=C['bg'], foreground=C['muted'], font=FONT_S)
        style.configure('CardMuted.TLabel', background=C['surface'], foreground=C['muted'], font=FONT_S)
        style.configure('H1.TLabel', background=C['bg'], foreground=C['text'], font=FONT_H)
        style.configure('H2.TLabel', background=C['surface'], foreground=C['text'], font=FONT_H2)
        # Buttons
        style.configure('TButton', font=FONT_B, padding=(10, 6),
                        background=C['surface2'], foreground=C['text'], borderwidth=1,
                        bordercolor=C['border'], relief='flat')
        style.map('TButton', background=[('active', C['surface2'])])
        style.configure('Accent.TButton', font=FONT_B, padding=(14, 8),
                        background=C['accent'], foreground='#fff', borderwidth=0)
        style.map('Accent.TButton', background=[('active', C['accent_h'])])
        style.configure('Ok.TButton', font=FONT_B, padding=(14, 8),
                        background=C['ok'], foreground='#fff', borderwidth=0)
        style.map('Ok.TButton', background=[('active', C['ok_h'])])
        style.configure('Warn.TButton', font=FONT_B, padding=(12, 8),
                        background=C['warn'], foreground='#fff', borderwidth=0)
        style.map('Warn.TButton', background=[('active', '#b45309')])
        style.configure('Danger.TButton', font=FONT_B, padding=(12, 8),
                        background=C['err'], foreground='#fff', borderwidth=0)
        style.map('Danger.TButton', background=[('active', '#b91c1c')])
        style.configure('Ghost.TButton', font=FONT_S, padding=(10, 5),
                        background=C['surface'], foreground=C['muted'], borderwidth=1,
                        bordercolor=C['border'])
        style.map('Ghost.TButton', background=[('active', C['surface2'])])
        # Treeview
        style.configure('Treeview', background=C['surface'], foreground=C['text'],
                        fieldbackground=C['surface'], font=FONT, rowheight=28, borderwidth=0)
        style.configure('Treeview.Heading', background=C['head_bg'], foreground=C['text'],
                        font=FONT_B, relief='flat', padding=(6, 6))
        style.map('Treeview',
                  background=[('selected', C['sel'])],
                  foreground=[('selected', C['text'])],
                  fieldbackground=[('selected', C['sel'])])
        style.map('Treeview.Heading', background=[('active', C['surface2'])])
        # Entry / Spinbox / Check
        style.configure('TEntry', fieldbackground=C['surface'], foreground=C['text'],
                        insertcolor=C['text'], borderwidth=1, bordercolor=C['border'], padding=4)
        style.map('TEntry', bordercolor=[('focus', C['accent'])])
        style.configure('TCheckbutton', background=C['surface'], foreground=C['text'], font=FONT)
        style.map('TCheckbutton', background=[('active', C['surface'])])
        # Progress
        style.configure('Horizontal.TProgressbar', background=C['accent'],
                        troughcolor=C['surface2'], bordercolor=C['border'], lightcolor=C['accent'],
                        darkcolor=C['accent'])
        # Combobox
        style.configure('TCombobox', fieldbackground=C['surface'], foreground=C['text'],
                        background=C['surface'], bordercolor=C['border'], arrowcolor=C['muted'],
                        padding=4, font=FONT)
        style.map('TCombobox', fieldbackground=[('readonly', C['surface'])],
                  foreground=[('readonly', C['text'])],
                  bordercolor=[('focus', C['accent'])])

    # ---------- custom light widgets ----------
    def card(self, parent, title=None, pad=14):
        outer = tk.Frame(parent, bg=C['border'], highlightthickness=0)
        body = tk.Frame(outer, bg=C['surface'])
        body.pack(fill='both', expand=True, padx=1, pady=1)
        if title:
            hr = tk.Frame(body, bg=C['surface'])
            hr.pack(fill='x', padx=pad, pady=(pad, 6))
            tk.Label(hr, text=title, bg=C['surface'], fg=C['text'],
                     font=FONT_H2).pack(side='left')
            outer._hdr = hr
        outer._body = body
        return outer

    def btn(self, parent, text, command, kind='ghost', **kw):
        style = {
            'primary': 'Accent.TButton',
            'ok': 'Ok.TButton',
            'warn': 'Warn.TButton',
            'danger': 'Danger.TButton',
            'ghost': 'Ghost.TButton',
        }.get(kind, 'TButton')
        b = ttk.Button(parent, text=text, command=command, style=style, **kw)
        return b

    def label(self, parent, text, kind='text', font=None, **kw):
        colors = {
            'text': C['text'], 'muted': C['muted'], 'ok': C['ok'],
            'warn': C['warn'], 'err': C['err'], 'accent': C['accent'],
        }
        bg = kw.pop('bg', C['surface'] if parent.cget('bg') == C['surface'] else C['bg'])
        return tk.Label(parent, text=text, bg=bg, fg=colors.get(kind, C['text']),
                        font=font or FONT, **kw)

    def entry(self, parent, width=36, show=None, **kw):
        e = tk.Entry(parent, width=width, font=FONT, bg=C['surface'], fg=C['text'],
                     insertbackground=C['text'], relief='solid', bd=1,
                     highlightthickness=1, highlightcolor=C['accent'],
                     highlightbackground=C['border'], **kw)
        if show is not None:
            e.config(show=show)
        return e

    def _build_header(self):
        hdr = tk.Frame(self, bg=C['surface'], highlightthickness=1,
                       highlightbackground=C['border'])
        hdr.pack(fill='x', padx=16, pady=(16, 0))

        left = tk.Frame(hdr, bg=C['surface'])
        left.pack(side='left', padx=16, pady=12)
        tk.Label(left, text='📊  SCI99 Sheets Autosync', bg=C['surface'],
                 fg=C['text'], font=FONT_H).pack(anchor='w')
        self.lbl_sub = tk.Label(left, text=self._subtitle(), bg=C['surface'],
                                fg=C['muted'], font=FONT_S)
        self.lbl_sub.pack(anchor='w', pady=(2, 0))

        right = tk.Frame(hdr, bg=C['surface'])
        right.pack(side='right', padx=16, pady=12)
        self.btn_theme = self.btn(right, '🌙  Dark', self.toggle_theme, kind='ghost')
        self.btn_theme.pack(side='right', padx=(10, 0))
        ToolTip(self.btn_theme, 'Chuyển Light / Dark theme (lưu vào cài đặt)')
        self.lbl_sched_hdr = tk.Label(right, text='', bg=C['surface'], fg=C['ok'],
                                      font=FONT_B)
        self.lbl_sched_hdr.pack(anchor='e')
        self.lbl_clock = tk.Label(right, text='', bg=C['surface'], fg=C['muted'],
                                  font=FONT_S)
        self.lbl_clock.pack(anchor='e', pady=(2, 0))
        self.after(1000, self._tick_clock)

    def _tick_clock(self):
        self.lbl_clock.config(text=datetime.now().strftime('%A · %d/%m/%Y · %H:%M:%S'))
        self.after(1000, self._tick_clock)

    def _build_body(self):
        wrap = tk.Frame(self, bg=C['bg'])
        wrap.pack(fill='both', expand=True, padx=16, pady=12)

        self.nb = ttk.Notebook(wrap)
        self.nb.pack(fill='both', expand=True)
        self.tab_home = ttk.Frame(self.nb)
        self.tab_data = ttk.Frame(self.nb)
        self.tab_run  = ttk.Frame(self.nb)
        self.tab_set  = ttk.Frame(self.nb)
        self.tab_logs = ttk.Frame(self.nb)
        self.nb.add(self.tab_home, text='  🏠  Dashboard  ')
        self.nb.add(self.tab_data, text='  📁  Dữ liệu  ')
        self.nb.add(self.tab_run,  text='  ▶  Chạy sync  ')
        self.nb.add(self.tab_set,  text='  ⚙  Cài đặt  ')
        self.nb.add(self.tab_logs, text='  📜  Logs  ')
        self._build_home()
        self._build_data()
        self._build_run()
        self._build_settings()
        self._build_logs()

    def _build_footer(self):
        ft = tk.Frame(self, bg=C['bg'])
        ft.pack(fill='x', padx=16, pady=(0, 12))
        self.lbl_status = tk.Label(ft, text='● Sẵn sàng', bg=C['bg'], fg=C['ok'],
                                   font=FONT_S, anchor='w')
        self.lbl_status.pack(side='left', fill='x', expand=True)
        btn_ref = self.btn(ft, '🔄  Làm mới tất cả', self.refresh_all, kind='ghost')
        btn_ref.pack(side='right')
        ToolTip(btn_ref, f'Tải lại trạng thái schedule + {len(self.sheets)} sheet + logs (F5)')
        tk.Label(ft, text='F5 làm mới · F6 chạy sync · Esc dừng', bg=C['bg'],
                 fg=C['muted'], font=('Segoe UI', 8)).pack(side='right', padx=12)

    # ---------------- Dashboard ----------------
    def _build_home(self):
        f = self.tab_home

        # --- schedule card ---
        c1 = self.card(f, '⏰  Lịch chạy tự động')
        c1.pack(fill='x', pady=(12, 8))
        inner = c1._body
        row = tk.Frame(inner, bg=C['surface'])
        row.pack(fill='x', padx=16, pady=(0, 14))
        self.lbl_sched = tk.Label(row, text='…', bg=C['surface'], fg=C['muted'],
                                  font=FONT, justify='left')
        self.lbl_sched.pack(side='left', fill='x', expand=True)
        bb = tk.Frame(row, bg=C['surface'])
        bb.pack(side='right')
        self.btn_home_run = self.btn(bb, '▶  Chạy ngay', self.run_sync, kind='ok')
        self.btn_home_run.pack(side='left', padx=4)
        ToolTip(self.btn_home_run, f'Chạy full pipeline {len(STEPS)} bước ngay trong app (F6) — tab "Chạy sync" hiện tiến trình')
        self.btn(bb, '⏸  Tạm dừng', self.pause_schedule, kind='warn').pack(side='left', padx=4)
        self.btn(bb, '▶  Bật lại', self.resume_schedule, kind='primary').pack(side='left', padx=4)

        # --- stats cards ---
        stats = tk.Frame(f, bg=C['bg'])
        stats.pack(fill='x', pady=4)
        self.card_vars = {}
        for i, (key, title, sub) in enumerate([
            ('sheets',     '📄  Tổng sheet',          'đang theo dõi'),
            ('latest924',  '🕐  Latest = hôm nay',     f'trong {len(self.sheets)} sheet'),
            ('rows',       '📊  Tổng dòng dữ liệu',   'tất cả sheet'),
            ('last_run',   '💾  Lần chạy gần nhất',    'từ logs/'),
            ('cookies',    '🍪  Cookie sci99',         'session hiện tại'),
        ]):
            box = self.card(stats)
            box.pack(side='left', fill='both', expand=True, padx=(0 if i==0 else 8, 0))
            body = box._body
            tk.Label(body, text=title, bg=C['surface'], fg=C['muted'],
                     font=FONT_S).pack(anchor='w', padx=14, pady=(12, 0))
            v = tk.Label(body, text='—', bg=C['surface'], fg=C['accent'], font=FONT_NUM)
            v.pack(anchor='w', padx=14, pady=(2, 0))
            tk.Label(body, text=sub, bg=C['surface'], fg=C['muted'],
                     font=('Segoe UI', 8)).pack(anchor='w', padx=14, pady=(0, 4))
            self.card_vars[key] = v

        # --- status table ---
        c3 = self.card(f, f'📋  Trạng thái {len(self.sheets)} sheet')
        c3.pack(fill='both', expand=True, pady=(8, 6))
        body = c3._body
        hdr = tk.Frame(body, bg=C['surface'])
        hdr.pack(fill='x', padx=14, pady=(0, 6))
        self.btn(hdr, '⟳ Refresh', self.refresh_sheet_status, kind='ghost').pack(side='right')
        self.lbl_status_count = tk.Label(hdr, text='', bg=C['surface'], fg=C['muted'],
                                         font=FONT_S)
        self.lbl_status_count.pack(side='right', padx=(0, 10))
        self.var_bad = tk.BooleanVar(value=False)
        tk.Checkbutton(hdr, text='Chỉ hiện lỗi', variable=self.var_bad,
                       command=self._render_status, bg=C['surface'], fg=C['text'],
                       selectcolor=C['surface2'], activebackground=C['surface'],
                       font=FONT_S).pack(side='right', padx=(0, 10))
        self.ent_filter = self.entry(hdr, width=18)
        self.ent_filter.pack(side='right', padx=(0, 6))
        self.ent_filter.insert(0, '')
        self.ent_filter.bind('<KeyRelease>', lambda e: self._render_status())
        tk.Label(hdr, text='Lọc:', bg=C['surface'], fg=C['muted'], font=FONT_S
                 ).pack(side='right', padx=(0, 4))

        cols = ('sheet', 'latest', 'rows', 'blocks', 'note')
        self.tree_status = ttk.Treeview(body, columns=cols, show='headings', height=6)
        for c, w, t in [('sheet', 220, 'Sheet'), ('latest', 110, 'Latest'),
                        ('rows', 70, 'Rows'), ('blocks', 70, 'Blocks'),
                        ('note', 300, 'Note')]:
            self.tree_status.heading(c, text=t)
            self.tree_status.column(c, width=w, anchor='w')
        vsb = ttk.Scrollbar(body, orient='vertical', command=self.tree_status.yview)
        self.tree_status.configure(yscrollcommand=vsb.set)
        self.tree_status.pack(side='left', fill='both', expand=True, padx=(14, 0), pady=(0, 14))
        vsb.pack(side='right', fill='y', padx=(0, 8), pady=(0, 14))
        self.tree_status.bind('<Double-1>', self._open_status_sheet)

        # --- run history ---
        c4 = self.card(f, '📜  Lịch sử chạy gần đây')
        c4.pack(fill='x', pady=(0, 12))
        hbody = c4._body
        hhdr = tk.Frame(hbody, bg=C['surface'])
        hhdr.pack(fill='x', padx=14, pady=(0, 6))
        self.btn(hhdr, '⟳ Refresh', self.refresh_history, kind='ghost').pack(side='right')
        self.lbl_hist = tk.Label(hhdr, text='đọc logs/daily_*.log', bg=C['surface'],
                                 fg=C['muted'], font=FONT_S)
        self.lbl_hist.pack(side='left')
        hcols = ('when', 'dur', 'detail', 'state')
        self.tree_hist = ttk.Treeview(hbody, columns=hcols, show='headings', height=4)
        for c, w, t in [('when', 150, 'Thời gian'), ('dur', 90, 'Thời lượng'),
                        ('detail', 560, 'Chi tiết'), ('state', 130, 'Trạng thái')]:
            self.tree_hist.heading(c, text=t)
            self.tree_hist.column(c, width=w, anchor='w')
        for tag, color in (('ok', C['ok']), ('warn', C['warn']), ('err', C['err']),
                           ('run', C['info'])):
            self.tree_hist.tag_configure(tag, foreground=color)
        hsb2 = ttk.Scrollbar(hbody, orient='vertical', command=self.tree_hist.yview)
        self.tree_hist.configure(yscrollcommand=hsb2.set)
        self.tree_hist.pack(side='left', fill='both', expand=True, padx=(14, 0), pady=(0, 14))
        hsb2.pack(side='right', fill='y', padx=(0, 8), pady=(0, 14))

    # ---------------- status helpers ----------------
    @staticmethod
    def _status_bad(row):
        latest = str(row[1]) if len(row) > 1 else ''
        note = str(row[4]) if len(row) > 4 else ''
        return (latest in ('ERR', 'NO DATE') or note.startswith('⚠')
                or note.startswith('ERROR') or str(row[0]) == 'ERROR')

    def _render_status(self, event=None):
        tree = self.tree_status
        for i in tree.get_children():
            tree.delete(i)
        try:
            q = self.ent_filter.get().strip().lower()
        except Exception:
            q = ''
        only_bad = bool(self.var_bad.get()) if hasattr(self, 'var_bad') else False
        shown = 0
        for row in self._status_rows:
            if q and q not in str(row[0]).lower():
                continue
            if only_bad and not self._status_bad(row):
                continue
            tree.insert('', 'end', values=[str(x) for x in row[:5]])
            shown += 1
        if hasattr(self, 'lbl_status_count'):
            self.lbl_status_count.config(text=f'{shown}/{len(self._status_rows)} sheet')
        if not self._status_rows:
            tree.insert('', 'end', values=('—', 'chưa tải', '', '', ''))

    def _open_status_sheet(self, event=None):
        sel = self.tree_status.selection()
        if not sel:
            return
        name = str(self.tree_status.item(sel[0], 'values')[0])
        if name in ('ERROR', '—'):
            return
        sid = self.settings.get('spreadsheet_id', '')
        gid = self._status_gids.get(name)
        url = f'https://docs.google.com/spreadsheets/d/{sid}'
        if gid is not None:
            url += f'#gid={gid}'
        import webbrowser
        webbrowser.open(url)

    def refresh_history(self):
        self._history_rows = []
        if hasattr(self, 'tree_hist'):
            for i in self.tree_hist.get_children():
                self.tree_hist.delete(i)
            self.tree_hist.insert('', 'end',
                                  values=('…', '', 'đang đọc logs/', ''))
        threading.Thread(target=self._history_worker, daemon=True).start()

    def _history_worker(self):
        rows = []
        logs = sorted(glob.glob(os.path.join(HERE, 'logs', 'daily_*.log')), reverse=True)
        for p in logs[:10]:
            try:
                with open(p, encoding='utf-8', errors='replace') as f:
                    f.seek(0, 2)
                    size = f.tell()
                    f.seek(max(0, size - 300000))
                    txt = f.read()
            except Exception:
                continue
            m = re.search(r'daily_(\d{8})_(\d{6})', os.path.basename(p))
            when = (f'{m.group(1)[6:8]}/{m.group(1)[4:6]}/{m.group(1)[0:4]} '
                    f'{m.group(2)[0:2]}:{m.group(2)[2:4]}') if m else \
                   os.path.basename(p)
            done = re.search(r'DAILY SYNC DONE (\d+)/(\d+) steps OK', txt)
            fails = re.findall(r'\] FAIL (\S+) rc=', txt)
            ts = re.findall(r'^\[(\d{2}):(\d{2}):(\d{2})\]', txt, re.M)
            dur = ''
            if ts:
                a = int(ts[0][0]) * 3600 + int(ts[0][1]) * 60 + int(ts[0][2])
                b = int(ts[-1][0]) * 3600 + int(ts[-1][1]) * 60 + int(ts[-1][2])
                if b < a:
                    b += 86400
                dur = f'{(b - a) // 60}m {(b - a) % 60}s'
            detail_parts = []
            if done:
                detail_parts.append(f"{done.group(1)}/{done.group(2)} bước OK")
            if fails:
                detail_parts.append('FAIL: ' + ', '.join(fails))
            detail = ' · '.join(detail_parts) or 'không có DONE/FAIL'
            if done:
                state, tag = ('✅ OK', 'ok') if not fails else ('⚠ PARTIAL', 'warn')
            else:
                age = time.time() - os.path.getmtime(p)
                if age < 300:
                    state, tag = '⏳ đang chạy', 'run'
                else:
                    state, tag = '❌ chưa xong', 'err'
            rows.append((when, dur, detail, state, tag))
        def ui():
            self._history_rows = rows
            if not hasattr(self, 'tree_hist'):
                return
            for i in self.tree_hist.get_children():
                self.tree_hist.delete(i)
            for r in rows:
                self.tree_hist.insert('', 'end', values=r[:4], tags=(r[4],))
            self.lbl_hist.config(
                text=(f'{len(rows)} lần gần nhất · ✅ {sum(1 for r in rows if r[4] == "ok")}'
                      f' · ⚠ {sum(1 for r in rows if r[4] == "warn")}'
                      f' · ❌ {sum(1 for r in rows if r[4] == "err")}'),
                fg=C['muted'])
        self._post(ui)

    def refresh_schedule_status(self):
        st = cfg.get_schedule_status(self.settings.get('task_name', 'sci99-sheets-daily'))
        if not st.get('exists'):
            txt = 'Chưa có Task Scheduler — vào tab Cài đặt → "Lưu & áp dụng lịch"'
            color = C['err']
            self.lbl_sched_hdr.config(text='●  Chưa schedule', fg=C['err'])
        else:
            days = st.get('days', '')
            next_run = st.get('next_run', '?')
            start = st.get('start_time', '?')
            state = 'ON' if st.get('enabled', True) else 'PAUSED'
            color = C['ok'] if st.get('enabled', True) else C['warn']
            txt = (f"Task: {self.settings.get('task_name')}\n"
                   f"Trạng thái: {st.get('status', '?')}  ·  {state}\n"
                   f"Giờ chạy: {start}  ·  Days: {days}\n"
                   f"Next run: {next_run}")
            self.lbl_sched_hdr.config(text=f'●  {start} daily  ·  {state}', fg=color)
        self.lbl_sched.config(text=txt, fg=color)
        self.card_vars['last_run'].config(text=self._last_log_time() or '—')
        if hasattr(self, 'lbl_sub'):
            self.lbl_sub.config(text=self._subtitle())

    def _last_log_time(self):
        logs = sorted(glob.glob(os.path.join(HERE, 'logs', 'daily_*.log')))
        if not logs:
            return None
        base = os.path.basename(logs[-1])
        m = re.search(r'daily_(\d{8})_(\d{6})', base)
        if m:
            return f"{m.group(1)} {m.group(2)[:2]}:{m.group(2)[2:4]}"
        return base

    def refresh_sheet_status(self):
        self.card_vars['sheets'].config(text=str(len(self.sheets)))
        self.card_vars['rows'].config(text='…')
        ck = os.path.join(HERE, 'sci99_cookies.json')
        if os.path.exists(ck):
            try:
                n = len(json.load(open(ck, encoding='utf-8')))
                self.card_vars['cookies'].config(text=f'{n}')
            except Exception:
                self.card_vars['cookies'].config(text='corrupt')
        else:
            self.card_vars['cookies'].config(text='missing')
        self.card_vars['latest924'].config(text='…')
        self.lbl_status.config(text='● Đang kiểm tra sheet…', fg=C['info'])
        threading.Thread(target=self._fetch_status_worker, daemon=True).start()

    def _status_progress(self, text, color):
        self.lbl_status.config(text=text, fg=color)

    def _fetch_status_worker(self):
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            creds = Credentials.from_service_account_file(
                self.settings['service_account_json'],
                scopes=['https://www.googleapis.com/auth/spreadsheets'])
            sh = gspread.authorize(creds).open_by_key(self.settings['spreadsheet_id'])
            now = datetime.now()
            today_variants = {
                f'{now.month}/{now.day}/{now.year}',
                f'{now.month:02d}/{now.day:02d}/{now.year}',
            }
            n_today = 0
            total_rows = 0
            rows_out = []
            total = len(self.sheets)
            for idx, name in enumerate(self.sheets, 1):
                ws, vals, err = None, None, ''
                for attempt in range(4):        # 429 quota: backoff thay vì hiện ERR oan
                    try:
                        ws = sh.worksheet(name)
                        vals = ws.get_all_values()
                        err = ''
                        break
                    except Exception as e:
                        err = str(e)
                        if '429' in err or 'quota' in err.lower() or 'Rate Limit' in err:
                            self._post(self._status_progress,
                                       f'● 429 — đợi quota ({idx}/{total})…', C['warn'])
                            # 15+30+45 = 90s > cửa sổ quota 60s/100 read
                            time.sleep(min(60, 15 * (attempt + 1)))
                            continue
                        break
                if vals is None:
                    rows_out.append((name, 'ERR', '', '', err[:80]))
                    continue
                self._status_gids[name] = getattr(ws, 'id', None)
                total_rows += len(vals)
                if idx % 5 == 0 or idx == total:
                    self._post(self._status_progress,
                               f'● Đang tải sheet {idx}/{total}…', C['info'])
                date_cols = {}
                # new format: row0 URL, row1 header, row2 first data
                sample = vals[1:12] if name == '汇率' else vals[2:12]
                for r in sample:
                    for i, v in enumerate(r):
                        v = str(v).strip()
                        if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', v):
                            date_cols.setdefault(i, v)
                def dk(s):
                    try:
                        return datetime.strptime(s, '%m/%d/%Y')
                    except Exception:
                        return datetime(1900, 1, 1)
                if not date_cols:
                    rows_out.append((name, 'NO DATE', str(len(vals)), '0', ''))
                    continue
                best = max(date_cols.values(), key=dk)
                nblocks = len(date_cols)
                is_today = best in today_variants or best == f'{now.month}/{now.day}/{now.year}'
                if is_today:
                    n_today += 1
                note = '✅ hôm nay' if is_today else ('📅 ngày khác' if dk(best).year >= 2026 else '⚠ cũ')
                rows_out.append((name, best, str(len(vals)), str(nblocks), note))

            def ui():
                self._status_rows = rows_out
                self._render_status()
                self.card_vars['latest924'].config(text=f'{n_today}/{len(rows_out)}')
                self.card_vars['rows'].config(text=f'{total_rows:,}')
                self.lbl_status.config(text=f'● Đã tải {len(rows_out)} sheet status', fg=C['ok'])
            self._post(ui)
        except Exception as e:
            def ui_err():
                self._status_rows = [('ERROR', '', '', '', str(e)[:120])]
                self._render_status()
                self.lbl_status.config(text=f'● Lỗi: {e}', fg=C['err'])
            self._post(ui_err)

    def refresh_all(self):
        self.refresh_schedule_status()
        self.refresh_sheet_status()
        self.refresh_logs_list()
        self.refresh_history()
        if hasattr(self, 'lbl_sub'):
            self.lbl_sub.config(text=self._subtitle())

    # ---------------- Data viewer ----------------
    def _build_data(self):
        f = self.tab_data
        top = tk.Frame(f, bg=C['bg'])
        top.pack(fill='x', pady=(12, 8))

        tk.Label(top, text='Sheet:', bg=C['bg'], fg=C['muted'],
                 font=FONT_S).pack(side='left')
        self.cmb_sheet = ttk.Combobox(top, values=self.sheets, state='readonly',
                                      width=26, font=FONT)
        self.cmb_sheet.set(self.sheets[0])
        self.cmb_sheet.pack(side='left', padx=(6, 12))

        self.btn(top, '📂  Mở Google Sheet', self.open_sheet_url, kind='ghost').pack(side='left', padx=4)
        self.btn(top, '🔍  Tải dữ liệu', self.load_sheet_data, kind='primary').pack(side='left', padx=4)
        self.btn(top, '⬇  Export CSV', self.export_csv, kind='ghost').pack(side='left', padx=4)

        top2 = tk.Frame(f, bg=C['bg'])
        top2.pack(fill='x', pady=(0, 8))
        self.lbl_find = tk.Label(top2, text='Tìm trong sheet:', bg=C['bg'], fg=C['muted'],
                                 font=FONT_S)
        self.lbl_find.pack(side='left', padx=(2, 6))
        self.ent_find = self.entry(top2, width=30)
        self.ent_find.pack(side='left')
        self.ent_find.bind('<KeyRelease>', self._apply_data_filter)
        ToolTip(self.ent_find, 'Lọc dòng theo nội dung bất kỳ (không phân biệt hoa thường)')
        self.lbl_data_info = tk.Label(top2, text='', bg=C['bg'], fg=C['muted'], font=FONT_S)
        self.lbl_data_info.pack(side='right')

        box = self.card(f)
        box.pack(fill='both', expand=True, pady=(0, 12))
        body = box._body
        self.data_cols = []
        self.tree_data = ttk.Treeview(body, show='headings')
        vsb = ttk.Scrollbar(body, orient='vertical', command=self.tree_data.yview)
        hsb = ttk.Scrollbar(body, orient='horizontal', command=self.tree_data.xview)
        self.tree_data.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree_data.grid(row=0, column=0, sticky='nsew', padx=(1, 0), pady=1)
        vsb.grid(row=0, column=1, sticky='ns', pady=1)
        hsb.grid(row=1, column=0, sticky='ew', pady=(0, 1))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self._raw_vals = []

    def open_sheet_url(self):
        sid = self.settings.get('spreadsheet_id', '')
        import webbrowser
        webbrowser.open(f'https://docs.google.com/spreadsheets/d/{sid}')

    def load_sheet_data(self):
        name = self.cmb_sheet.get()
        if not name:
            return
        self.lbl_data_info.config(text='⏳ Đang tải…', fg=C['info'])
        threading.Thread(target=self._load_data_worker, args=(name,), daemon=True).start()

    def _load_data_worker(self, name):
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            creds = Credentials.from_service_account_file(
                self.settings['service_account_json'],
                scopes=['https://www.googleapis.com/auth/spreadsheets'])
            sh = gspread.authorize(creds).open_by_key(self.settings['spreadsheet_id'])
            ws = sh.worksheet(name)
            vals = ws.get_all_values()
            def ui():
                self._raw_vals = vals
                n_cols = max((len(r) for r in vals), default=0)
                self._data_base_info = f'{name}: {len(vals)} rows × {n_cols} cols'
                if self.ent_find.get():
                    self.ent_find.delete(0, 'end')
                self._render_grid(vals)
            self._post(ui)
        except Exception as e:
            def ui():
                self._data_base_info = f'ERROR: {e}'
                self.lbl_data_info.config(text=self._data_base_info, fg=C['err'])
            self._post(ui)

    def _render_grid(self, vals):
        """Render full sheet: header row as column headings + data rows below."""
        for c in self.tree_data.get_children():
            self.tree_data.delete(c)
        self._data_rows = []
        if not vals:
            return 0
        # header detection: prefer row containing '日期', else densest in first 6
        # rows with earliest-wins tie-break (n >= best wrongly picked later data rows)
        header_idx = None
        for i in range(min(6, len(vals))):
            if any(str(x).strip() == '日期' for x in vals[i]):
                header_idx = i
                break
        if header_idx is None:
            header_idx = 0
            best = -1
            for i in range(min(6, len(vals))):
                n = sum(1 for x in vals[i] if str(x).strip())
                if n > best:
                    best = n
                    header_idx = i
        header = [str(x).replace('\n', ' ').strip()[:32] or f'col{j}' for j, x in enumerate(vals[header_idx])]
        seen = {}
        cols = []
        for j, h in enumerate(header):
            if h in seen:
                seen[h] += 1
                h = f'{h}_{seen[h]}'
            else:
                seen[h] = 1
            cols.append(h)
        self.data_cols = cols
        self.tree_data.configure(columns=cols, show='headings')
        for c in cols:
            self.tree_data.heading(c, text=c)
            self.tree_data.column(c, width=110, anchor='w', minwidth=60)
        # ALL data rows (no cap) — header stays as headings; filter applied after
        for r in vals[header_idx + 1:]:
            rr = list(r) + [''] * (len(cols) - len(r))
            self._data_rows.append([str(x)[:80] for x in rr[:len(cols)]])
        self._apply_data_filter()
        return len(self._data_rows)

    def _apply_data_filter(self, event=None):
        """Redraw Data tab rows, keeping only those matching the search box."""
        tree = self.tree_data
        for c in tree.get_children():
            tree.delete(c)
        try:
            q = self.ent_find.get().strip().lower()
        except Exception:
            q = ''
        n = 0
        for r in self._data_rows:
            if q and not any(q in str(x).lower() for x in r):
                continue
            tree.insert('', 'end', values=r)
            n += 1
        if hasattr(self, 'lbl_data_info') and getattr(self, '_data_base_info', ''):
            self.lbl_data_info.config(
                text=(self._data_base_info +
                      (f' · khớp {n}/{len(self._data_rows)} dòng' if q else
                       f' · {n} dòng')),
                fg=C['ok'] if n else C['warn'])

    def export_csv(self):
        if not self._raw_vals:
            messagebox.showinfo('Export', 'Hãy Tải dữ liệu trước')
            return
        name = self.cmb_sheet.get().replace(' ', '_')
        path = filedialog.asksaveasfilename(
            defaultextension='.csv',
            initialfile=f'{name}_{datetime.now():%Y%m%d}.csv',
            filetypes=[('CSV', '*.csv')])
        if not path:
            return
        import csv
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerows(self._raw_vals)
        messagebox.showinfo('Export', f'Đã lưu:\n{path}')

    # ---------------- Run sync ----------------
    def _build_run(self):
        f = self.tab_run
        top = tk.Frame(f, bg=C['bg'])
        top.pack(fill='x', pady=(12, 8))
        self.btn_run = self.btn(top, '▶   CHẠY SYNC NGAY', self.run_sync, kind='ok')
        self.btn_run.pack(side='left')
        self.btn_stop = self.btn(top, '⏹ Dừng', self.stop_sync, kind='danger', state='disabled')
        self.btn_stop.pack(side='left', padx=6)
        self.btn_task_run = self.btn(top, '📅 Qua Task Scheduler', self.run_via_task, kind='primary')
        self.btn_task_run.pack(side='left', padx=6)
        self.btn_verify = self.btn(top, '✔  Verify nhanh', self.run_verify, kind='primary')
        self.btn_verify.pack(side='left', padx=6)
        ToolTip(self.btn_run, 'Chạy trực tiếp daily_sync.py trong app — xem tiến trình từng bước bên dưới (F6)')
        ToolTip(self.btn_stop, 'Dừng toàn bộ tiến trình sync (kể cả step đang chạy) — phím Esc')
        ToolTip(self.btn_task_run, 'Chạy qua Windows Task Scheduler (chạy nền, không hiện console)')
        ToolTip(self.btn_verify, 'Chạy riêng verify_all_status.py — kiểm tra '
                                 f'{len(self.sheets)} tab mà không chạy pipeline')

        right = tk.Frame(top, bg=C['bg'])
        right.pack(side='right')
        self.lbl_step_now = tk.Label(right, text=f'Bước — / {len(STEPS)}', bg=C['bg'], fg=C['muted'],
                                     font=FONT_B)
        self.lbl_step_now.pack(side='right', padx=(10, 0))
        self.progress = ttk.Progressbar(right, mode='determinate', maximum=len(STEPS), length=260)
        self.progress.pack(side='right')

        # --- tiến trình N bước (2 cột × 7) ---
        c0 = self.card(f, f'Tiến trình {len(STEPS)} bước')
        c0.pack(fill='x', pady=(4, 4))
        self.lbl_run_state = tk.Label(c0._hdr, text='Sẵn sàng', bg=C['surface'],
                                      fg=C['muted'], font=FONT_B)
        self.lbl_run_state.pack(side='right')
        grid = tk.Frame(c0._body, bg=C['surface'])
        grid.pack(fill='x', padx=14, pady=(2, 12))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self.step_rows = []
        for i, (key, name, rk, core) in enumerate(STEPS):
            col, rowi = divmod(i, 7)
            rf = tk.Frame(grid, bg=C['surface'], highlightthickness=1,
                          highlightbackground=C['border'])
            rf.grid(row=rowi, column=col, sticky='ew', padx=(0, 6), pady=2)
            badge = tk.Label(rf, text=f' {i + 1} ', width=3, bg=C['surface2'], fg=C['muted'],
                             font=('Segoe UI', 9, 'bold'))
            badge.pack(side='left', padx=(8, 8), pady=3)
            nm = tk.Label(rf, text=('★ ' if core else '') + name, bg=C['surface'],
                          fg=C['text'], font=FONT_S, anchor='w')
            nm.pack(side='left', fill='x', expand=True)
            t = tk.Label(rf, text='—', bg=C['surface'], fg=C['muted'],
                         font=('Segoe UI', 9), width=9, anchor='e')
            t.pack(side='right', padx=(4, 8))
            stt = tk.Label(rf, text='○', bg=C['surface'], fg=C['muted'],
                           font=FONT_B, width=3, anchor='e')
            stt.pack(side='right')
            if core:
                ToolTip(nm, '★ Bước cốt lõi — daily_sync exit 0 chỉ khi bước này OK')
            self.step_rows.append({'frame': rf, 'badge': badge, 'name': nm, 'status': stt,
                                   'time': t, 'state': 'pending', 't0': None})

        c2 = self.card(f, 'Console')
        c2.pack(fill='both', expand=True, pady=(4, 12))
        self.txt_run = scrolledtext.ScrolledText(c2._body, bg=C['console'], fg=C['console_f'],
                                                  insertbackground=C['console_f'],
                                                  font=('Consolas', 9), relief='flat',
                                                  height=12, padx=10, pady=8,
                                                  highlightthickness=0)
        self.txt_run.tag_config('step', foreground='#38bdf8')
        self.txt_run.tag_config('ok', foreground='#4ade80')
        self.txt_run.tag_config('err', foreground='#f87171')
        self.txt_run.tag_config('warn', foreground='#fbbf24')
        self.txt_run.tag_config('hl', foreground='#facc15')
        self.txt_run.pack(fill='both', expand=True, padx=1, pady=1)

    # --- step tracking ---
    @staticmethod
    def _step_colors():
        """Đọc trực tiếp C[] để tự đổi màu khi đổi theme."""
        return {
            'pending': ('○', C['muted']),
            'running': ('▶', C['accent']),
            'ok':      ('✔', C['ok']),
            'fail':    ('✘', C['err']),
            'skip':    ('–', C['muted']),
        }

    def _set_step(self, i, state, t=None):
        row = self.step_rows[i]
        prev = row['state']
        row['state'] = state
        bg = C['sel'] if state == 'running' else C['surface']
        row['frame'].config(bg=bg)
        icon, fg = self._step_colors().get(state, ('○', C['muted']))
        for w in (row['badge'], row['name'], row['status'], row['time']):
            w.config(bg=bg)
        row['status'].config(text=icon, fg=fg)
        row['badge'].config(fg=fg if state in ('running', 'ok', 'fail') else C['muted'],
                            bg=C['sel_run'] if state == 'running' else C['surface2'])
        if t is not None:
            row['time'].config(text=t, fg=fg if state in ('ok', 'fail') else C['muted'])
        if state != prev:
            done_n = sum(1 for r in self.step_rows if r['state'] in ('ok', 'fail'))
            self.progress['value'] = done_n

    def _reset_steps(self):
        for i in range(len(self.step_rows)):
            self.step_rows[i]['t0'] = None
            self._set_step(i, 'pending', '—')
        self.progress['value'] = 0
        self.lbl_step_now.config(text=f'Bước — / {len(STEPS)}', fg=C['muted'])

    def _tick_run_ui(self):
        if not self.running:
            return
        now = time.time()
        for row in self.step_rows:
            if row['state'] == 'running' and row['t0']:
                row['time'].config(text=f"⏱ {int(now - row['t0'])}s", fg=C['accent'])
        done_n = sum(1 for r in self.step_rows if r['state'] in ('ok', 'fail'))
        cur = next((i for i, r in enumerate(self.step_rows) if r['state'] == 'running'), None)
        if cur is not None:
            self.lbl_step_now.config(text=f'Bước {cur + 1}/{len(STEPS)} · {done_n} xong',
                                     fg=C['accent'])
        self.after(1000, self._tick_run_ui)

    def _step_index(self, key):
        return next((i for i, s in enumerate(STEPS) if s[0] == key), None)

    def _parse_run_line(self, line):
        m = re.match(_TS + r'=== STEP: (\S+) ===$', line)
        if m:
            idx = self._step_index(m.group(1))
            if idx is not None:
                for j in range(idx):  # các bước trước đã chạy qua (mắc lỗi parse?) → đánh dấu bỏ qua
                    if self.step_rows[j]['state'] == 'pending':
                        self._set_step(j, 'skip', '—')
                self._set_step(idx, 'running', '⏱ 0s')
                self.step_rows[idx]['t0'] = time.time()
                self.lbl_run_state.config(text=f"▶ {STEPS[idx][1]} …", fg=C['accent'])
            return
        m = re.match(_TS + r'OK (\S+) \((\d+)s\)$', line)
        if m:
            idx = self._step_index(m.group(1))
            if idx is not None:
                self._set_step(idx, 'ok', f"{m.group(2)}s")
                okn = sum(1 for r in self.step_rows if r['state'] == 'ok')
                self.lbl_run_state.config(text=f'✔ {okn}/{len(STEPS)} bước đã OK', fg=C['ok'])
            return
        m = re.match(_TS + r'FAIL (\S+) rc=(-?\d+)', line)
        if m:
            idx = self._step_index(m.group(1))
            if idx is not None:
                self._set_step(idx, 'fail', f"rc={m.group(2)}")
            return
        m = re.match(_TS + r'TIMEOUT (\S+)', line)
        if m:
            idx = self._step_index(m.group(1))
            if idx is not None:
                self._set_step(idx, 'fail', 'timeout')
            return
        if line.startswith('RESULTS '):
            try:
                self._apply_results(ast.literal_eval(line[len('RESULTS '):].strip()))
            except Exception:
                pass

    def _apply_results(self, res):
        if not isinstance(res, dict):
            return
        for i, (key, name, rk, core) in enumerate(STEPS):
            if rk not in res:
                continue
            row = self.step_rows[i]
            if row['state'] == 'running':
                row['t0'] = None
            if res[rk]:
                cur = str(row['time'].cget('text'))
                self._set_step(i, 'ok', cur if re.match(r'^\d+s$', cur) else 'OK')
            elif row['state'] != 'fail':
                self._set_step(i, 'fail', 'FAIL')

    def _log_tag(self, msg):
        if re.match(_TS + r'=== STEP:', msg):
            return ('step',)
        if re.match(_TS + r'OK ', msg):
            return ('ok',)
        if re.match(_TS + r'(FAIL|TIMEOUT|ERROR)', msg) or re.match(r'^(FAIL|TIMEOUT|ERROR)\b', msg):
            return ('err',)
        if re.match(r'^\[?\d{2}:\d{2}:\d{2}\]? (WARN|SKIP)' , msg) or msg.startswith('SKIP'):
            return ('warn',)
        if msg.startswith('$ ') or msg.startswith('RESULTS') or 'DAILY SYNC' in msg[:45]:
            return ('hl',)
        return ()

    def _log_run(self, msg):
        def ui():
            self.txt_run.insert('end', msg + '\n', self._log_tag(msg))
            self.txt_run.see('end')
        self._post(ui)

    def _set_run_buttons(self, running):
        st = 'disabled' if running else 'normal'
        self.btn_run.config(state=st)
        self.btn_home_run.config(state=st)
        self.btn_task_run.config(state=st)
        self.btn_verify.config(state=st)
        self.btn_stop.config(state='normal' if running else 'disabled')

    def _flash_window(self):
        try:
            import ctypes
            from ctypes import wintypes

            class FLASHWINFO(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.UINT), ('hwnd', wintypes.HWND),
                            ('dwFlags', wintypes.DWORD), ('uCount', wintypes.UINT),
                            ('dwTimeout', wintypes.DWORD)]
            fi = FLASHWINFO(ctypes.sizeof(FLASHWINFO), self.winfo_id(), 15, 6, 0)
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(fi))
        except Exception:
            pass

    def run_sync(self):
        if self.running or self._single_running:
            messagebox.showwarning('Đang chạy', 'Sync đang chạy — hãy Dừng trước hoặc chờ xong.')
            return
        self.nb.select(self.tab_run)
        self._reset_steps()
        self.running = True
        self._stop_requested = False
        self._set_run_buttons(True)
        self.lbl_run_state.config(text='⏳ Đang khởi động…', fg=C['accent'])
        self.lbl_status.config(text='● Sync đang chạy…', fg=C['info'])
        self.txt_run.delete('1.0', 'end')
        self._log_run(f'$ daily_sync.py — {len(STEPS)} bước · log đầy đủ trong logs/')
        self.after(1000, self._tick_run_ui)
        threading.Thread(target=self._run_sync_worker, daemon=True).start()

    def _run_sync_worker(self):
        py = os.path.join(HERE, 'daily_sync.py')
        env = dict(os.environ)
        env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        try:
            self.proc = subprocess.Popen(
                [sys.executable, '-X', 'utf8', py], cwd=HERE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                bufsize=1, env=env)
            for line in self.proc.stdout:
                line = line.rstrip('\n')
                self._log_run(line)
                self._post(self._parse_run_line, line)
            rc = self.proc.wait()
            self._post(self._finish_run, rc)
        except Exception as e:
            self._log_run(f'ERROR: {e}')
            self._post(self._finish_run, -1, str(e))

    def _finish_run(self, rc, err=None):
        for i, row in enumerate(self.step_rows):  # bước đang dở khi bị dừng/crash
            if row['state'] == 'running':
                self._set_step(i, 'fail', 'đã dừng')
                row['t0'] = None
        okn = sum(1 for r in self.step_rows if r['state'] == 'ok')
        failn = sum(1 for r in self.step_rows if r['state'] == 'fail')
        self.running = False
        self._set_run_buttons(False)
        if self._stop_requested:
            state, fg = f'⏹ Đã dừng — {okn}/{len(STEPS)} bước', C['warn']
            self.lbl_status.config(text='● Sync đã dừng', fg=C['warn'])
        elif err:
            state, fg = f'❌ {err}', C['err']
            self.lbl_status.config(text=f'● {err}', fg=C['err'])
        elif rc == 0 and failn == 0:
            state, fg = f'✅ Hoàn thành — {len(STEPS)}/{len(STEPS)} bước OK', C['ok']
            self.lbl_status.config(text=f'● Sync OK — {len(self.sheets)} sheet đã kiểm tra', fg=C['ok'])
        elif rc == 0:
            state, fg = f'⚠ Core OK nhưng {failn} bước FAIL — {okn}/{len(STEPS)}', C['warn']
            self.lbl_status.config(text=f'● Xong với {failn} bước lỗi', fg=C['warn'])
        else:
            state, fg = f'⚠ Exit {rc} — {okn}/{len(STEPS)} bước OK', C['err']
            self.lbl_status.config(text=f'● Exit {rc}', fg=C['err'])
        self.lbl_run_state.config(text=state, fg=fg)
        self.lbl_step_now.config(text=f'{okn}/{len(STEPS)} OK', fg=fg)
        self._flash_window()
        self.refresh_all()

    def stop_sync(self):
        if not (self.running or self._single_running) or not self.proc or self._stop_requested:
            return
        what = 'sync' if self.running else 'verify'
        if not messagebox.askyesno('Dừng',
                                   f'Dừng {what} đang chạy?\n'
                                   'Các bước chưa chạy sẽ bị bỏ qua.'):
            return
        self._stop_requested = True
        self.lbl_run_state.config(text='⏹ Đang dừng…', fg=C['warn'])
        try:
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(self.proc.pid)],
                           capture_output=True, timeout=10)
            self._log_run('⏹ stopped by user (taskkill /T — kill cả tree)')
        except Exception as e:
            self._log_run(f'taskkill err: {e}')

    def run_via_task(self):
        ok, msg = cfg.run_task_now(self.settings.get('task_name', 'sci99-sheets-daily'))
        messagebox.showinfo('Task Scheduler', msg or ('OK' if ok else 'FAIL'))

    # --- chạy nhanh verify_all_status.py (không đụng pipeline) ---
    def run_verify(self):
        if self.running or self._single_running:
            messagebox.showwarning('Đang chạy', 'Đang có tiến trình — chờ hoàn tất trước.')
            return
        self.nb.select(self.tab_run)
        self._single_running = True
        self._stop_requested = False
        self._set_run_buttons(True)
        self.lbl_run_state.config(text='▶ verify_all_status.py …', fg=C['accent'])
        self.lbl_status.config(text='● Đang verify…', fg=C['info'])
        self.txt_run.delete('1.0', 'end')
        self._log_run(f'$ python -X utf8 verify_all_status.py  ({len(self.sheets)} tab)')
        threading.Thread(target=self._run_verify_worker, daemon=True).start()

    def _run_verify_worker(self):
        env = dict(os.environ)
        env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        rc = -1
        try:
            self.proc = subprocess.Popen(
                [sys.executable, '-X', 'utf8', 'verify_all_status.py'], cwd=HERE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                bufsize=1, env=env)
            for line in self.proc.stdout:
                self._log_run(line.rstrip('\n'))
            rc = self.proc.wait()
        except Exception as e:
            self._log_run(f'ERROR: {e}')
        self._post(self._finish_single, rc)

    def _finish_single(self, rc):
        self._single_running = False
        self.proc = None
        self._set_run_buttons(False)
        if self._stop_requested:
            state, fg = '⏹ Đã dừng verify', C['warn']
            self.lbl_status.config(text='● Verify đã dừng', fg=C['warn'])
        elif rc == 0:
            state, fg = f'✅ Verify OK — {len(self.sheets)} tab', C['ok']
            self.lbl_status.config(text=f'● Verify OK — {len(self.sheets)} tab', fg=C['ok'])
        else:
            state, fg = f'⚠ Verify rc={rc} — xem console', C['warn']
            self.lbl_status.config(text=f'● Verify rc={rc}', fg=C['warn'])
        self.lbl_run_state.config(text=state, fg=fg)
        self._flash_window()
        self.refresh_sheet_status()
        self.refresh_history()

    # ---------------- Settings ----------------
    def _build_settings(self):
        f = self.tab_set

        # LEFT: credentials + sheet
        cL = self.card(f, '🔐  Đăng nhập & Google Sheet')
        cL.pack(side='left', fill='both', expand=True, padx=(0, 6), pady=12)
        inn = tk.Frame(cL._body, bg=C['surface'])
        inn.pack(fill='both', expand=True, padx=14, pady=(0, 14))

        def lab(r, c, text, columnspan=1, **kw):
            tk.Label(inn, text=text, bg=C['surface'], fg=C['muted'],
                     font=FONT_S, **kw).grid(row=r, column=c, columnspan=columnspan,
                                             sticky='w', pady=(6, 0))

        lab(0, 0, 'Username', columnspan=3)
        self.ent_user = self.entry(inn, width=36)
        self.ent_user.grid(row=1, column=0, columnspan=3, sticky='ew', pady=4)
        self.ent_user.insert(0, self.settings.get('sci99_username', ''))

        lab(2, 0, 'Password', columnspan=3)
        pwrow = tk.Frame(inn, bg=C['surface'])
        pwrow.grid(row=3, column=0, columnspan=3, sticky='ew', pady=4)
        self.ent_pass = self.entry(pwrow, width=30, show='•')
        self.ent_pass.pack(side='left', fill='x', expand=True)
        self.ent_pass.insert(0, self.settings.get('sci99_password', ''))
        self.btn(pwrow, '👁 Hiện', self.toggle_pass, kind='ghost').pack(side='left', padx=(6, 0))

        lab(4, 0, 'Spreadsheet ID', columnspan=3)
        self.ent_sid = self.entry(inn, width=52)
        self.ent_sid.grid(row=5, column=0, columnspan=3, sticky='ew', pady=4)
        self.ent_sid.insert(0, self.settings.get('spreadsheet_id', ''))

        lab(6, 0, 'Service account JSON', columnspan=3)
        crrow = tk.Frame(inn, bg=C['surface'])
        crrow.grid(row=7, column=0, columnspan=3, sticky='ew', pady=4)
        self.ent_creds = self.entry(crrow, width=40)
        self.ent_creds.pack(side='left', fill='x', expand=True)
        self.ent_creds.insert(0, self.settings.get('service_account_json', ''))
        self.btn(crrow, 'Chọn file…', self.pick_creds, kind='ghost').pack(side='left', padx=(6, 0))

        lab(8, 0, 'Task name (Windows)', columnspan=3)
        self.ent_task = self.entry(inn, width=36)
        self.ent_task.grid(row=9, column=0, columnspan=3, sticky='ew', pady=4)
        self.ent_task.insert(0, self.settings.get('task_name', 'sci99-sheets-daily'))

        self.btn(inn, '💾  LƯU CÀI ĐẶT', self.save_settings_ui, kind='primary'
                 ).grid(row=10, column=0, columnspan=3, sticky='w', pady=(16, 4))
        inn.columnconfigure(0, weight=1)

        self.lbl_set_status = tk.Label(inn, text='', bg=C['surface'], fg=C['muted'],
                                       font=FONT_S, justify='left', wraplength=420)
        self.lbl_set_status.grid(row=11, column=0, columnspan=3, sticky='w', pady=(8, 14))

        # RIGHT: schedule
        cR = self.card(f, '⏰  Lịch chạy tự động')
        cR.pack(side='right', fill='both', expand=True, padx=(6, 0), pady=12)
        rin = tk.Frame(cR._body, bg=C['surface'])
        rin.pack(fill='both', expand=True, padx=14, pady=(0, 14))

        tk.Label(rin, text='Bật / tắt lịch tự động', bg=C['surface'], fg=C['muted'],
                 font=FONT_S).grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 4))
        self.var_sched_on = tk.BooleanVar(value=self.settings.get('schedule', {}).get('enabled', True))
        tk.Checkbutton(rin, text='Bật lịch chạy', variable=self.var_sched_on,
                       bg=C['surface'], fg=C['text'], selectcolor=C['surface2'],
                       activebackground=C['surface'], font=FONT).grid(
            row=1, column=0, columnspan=4, sticky='w')

        sch = self.settings.get('schedule', {})
        tk.Label(rin, text='Giờ', bg=C['surface'], fg=C['muted'], font=FONT_S).grid(
            row=2, column=0, sticky='w', pady=(12, 0))
        self.spn_h = tk.Spinbox(rin, from_=0, to=23, width=4, font=FONT,
                                bg=C['surface'], fg=C['text'], buttonbackground=C['surface2'],
                                relief='solid', bd=1, highlightthickness=1,
                                highlightcolor=C['accent'], highlightbackground=C['border'])
        self.spn_h.delete(0, 'end'); self.spn_h.insert(0, str(sch.get('hour', 18)))
        self.spn_h.grid(row=2, column=1, sticky='w', padx=(8, 0), pady=(12, 0))

        tk.Label(rin, text='Phút', bg=C['surface'], fg=C['muted'], font=FONT_S).grid(
            row=2, column=2, sticky='w', padx=(16, 0), pady=(12, 0))
        self.spn_m = tk.Spinbox(rin, from_=0, to=59, width=4, font=FONT,
                                bg=C['surface'], fg=C['text'], buttonbackground=C['surface2'],
                                relief='solid', bd=1, highlightthickness=1,
                                highlightcolor=C['accent'], highlightbackground=C['border'])
        self.spn_m.delete(0, 'end'); self.spn_m.insert(0, str(sch.get('minute', 30)))
        self.spn_m.grid(row=2, column=3, sticky='w', padx=(8, 0), pady=(12, 0))

        tk.Label(rin, text='Ngày trong tuần', bg=C['surface'], fg=C['muted'],
                 font=FONT_S).grid(row=3, column=0, columnspan=4, sticky='w', pady=(16, 4))
        day_frame = tk.Frame(rin, bg=C['surface'])
        day_frame.grid(row=4, column=0, columnspan=4, sticky='w')
        self.day_vars = {}
        days  = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
        labels = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']
        active = set(sch.get('days', days))
        for i, (d, lab_) in enumerate(zip(days, labels)):
            v = tk.BooleanVar(value=d in active)
            self.day_vars[d] = v
            tk.Checkbutton(day_frame, text=lab_, variable=v, bg=C['surface'], fg=C['text'],
                           selectcolor=C['surface2'], activebackground=C['surface'],
                           font=FONT_S).pack(side='left', padx=4)

        self.btn(rin, '📅  LƯU & ÁP DỤNG LỊCH', self.save_schedule_ui, kind='ok'
                 ).grid(row=5, column=0, columnspan=4, sticky='w', pady=(18, 6))
        self.btn(rin, '▶  Chạy thử Task ngay', self.run_via_task, kind='ghost'
                 ).grid(row=6, column=0, columnspan=4, sticky='w', pady=(0, 4))

        self.lbl_sched_preview = tk.Label(rin, text='', bg=C['surface'], fg=C['muted'],
                                          font=FONT_S, justify='left', wraplength=380)
        self.lbl_sched_preview.grid(row=7, column=0, columnspan=4, sticky='w', pady=(12, 14))
        self._refresh_sched_preview()

    def toggle_pass(self):
        if self.ent_pass.cget('show') == '•':
            self.ent_pass.config(show='')
        else:
            self.ent_pass.config(show='•')

    def pick_creds(self):
        path = filedialog.askopenfilename(
            title='Chọn service_account.json',
            filetypes=[('JSON', '*.json'), ('All', '*.*')],
            initialdir=os.path.dirname(self.settings.get('service_account_json', HERE)))
        if path:
            self.ent_creds.delete(0, 'end')
            self.ent_creds.insert(0, path)

    def save_settings_ui(self):
        self.settings['sci99_username'] = self.ent_user.get().strip()
        self.settings['sci99_password'] = self.ent_pass.get()
        self.settings['spreadsheet_id'] = self.ent_sid.get().strip()
        self.settings['service_account_json'] = self.ent_creds.get().strip()
        self.settings['task_name'] = self.ent_task.get().strip() or 'sci99-sheets-daily'
        self.settings.setdefault('schedule', {})
        self.settings['schedule']['enabled'] = bool(self.var_sched_on.get())
        try:
            self.settings['schedule']['hour'] = int(self.spn_h.get())
            self.settings['schedule']['minute'] = int(self.spn_m.get())
        except ValueError:
            pass
        self.settings['schedule']['days'] = [d for d, v in self.day_vars.items() if v.get()]
        p = cfg.save_settings(self.settings)
        cfg.apply_login_to_scripts(self.settings)
        self.lbl_set_status.config(text=f'✅ Đã lưu: {p}\n✅ Đã ghi login vào script',
                                   fg=C['ok'])
        messagebox.showinfo('Lưu', 'Đã lưu cài đặt + cập nhật login scripts.')
        self.refresh_all()

    def save_schedule_ui(self):
        self.settings.setdefault('schedule', {})
        self.settings['schedule']['enabled'] = bool(self.var_sched_on.get())
        try:
            self.settings['schedule']['hour'] = int(self.spn_h.get())
            self.settings['schedule']['minute'] = int(self.spn_m.get())
        except ValueError:
            messagebox.showerror('Lỗi', 'Giờ/Phút không hợp lệ')
            return
        self.settings['schedule']['days'] = [d for d, v in self.day_vars.items() if v.get()]
        if not self.settings['schedule']['days']:
            messagebox.showerror('Lỗi', 'Chọn ít nhất 1 ngày')
            return
        self.settings['task_name'] = self.ent_task.get().strip() or 'sci99-sheets-daily'
        cfg.save_settings(self.settings)
        ok, msg = cfg.apply_schedule(self.settings)
        if ok:
            self.lbl_set_status.config(text=f'✅ Schedule OK: {msg}', fg=C['ok'])
            messagebox.showinfo('Schedule', f'Áp dụng thành công:\n{msg}')
        else:
            self.lbl_set_status.config(text=f'❌ {msg}', fg=C['err'])
            messagebox.showerror('Schedule', msg)
        self._refresh_sched_preview()
        self.refresh_schedule_status()

    def _refresh_sched_preview(self):
        st = cfg.get_schedule_status(self.settings.get('task_name', 'sci99-sheets-daily'))
        if not st.get('exists'):
            self.lbl_sched_preview.config(text='Task: chưa tồn tại', fg=C['warn'])
            return
        self.lbl_sched_preview.config(
            text=(f"Task: {self.settings.get('task_name')}\n"
                  f"State: {st.get('status','?')}  ·  Next: {st.get('next_run','?')}\n"
                  f"Time: {st.get('start_time','?')}  ·  Days: {st.get('days','?')}"),
            fg=C['muted'])

    def pause_schedule(self):
        ok, msg = cfg.enable_task(self.settings.get('task_name', 'sci99-sheets-daily'),
                                  enable=False)
        messagebox.showinfo('Tạm dừng', msg or ('OK' if ok else 'FAIL'))
        self.refresh_schedule_status()

    def resume_schedule(self):
        ok, msg = cfg.enable_task(self.settings.get('task_name', 'sci99-sheets-daily'),
                                  enable=True)
        messagebox.showinfo('Bật lại', msg or ('OK' if ok else 'FAIL'))
        self.refresh_schedule_status()

    # ---------------- Logs ----------------
    def _build_logs(self):
        f = self.tab_logs
        top = tk.Frame(f, bg=C['bg'])
        top.pack(fill='x', pady=(12, 8))
        tk.Label(top, text='Chọn log:', bg=C['bg'], fg=C['muted'], font=FONT_S).pack(side='left')
        self.cmb_log = ttk.Combobox(top, state='readonly', width=52, font=FONT)
        self.cmb_log.pack(side='left', padx=8)
        self.btn(top, 'Mở', self.open_selected_log, kind='ghost').pack(side='left', padx=4)
        self.btn(top, 'Thư mục logs', self.open_logs_dir, kind='ghost').pack(side='left', padx=4)
        self.btn(top, '⟳ Refresh', self.refresh_logs_list, kind='ghost').pack(side='left', padx=4)

        box = self.card(f, '📄  Nội dung log')
        box.pack(fill='both', expand=True, pady=(0, 12))
        self.txt_logs = scrolledtext.ScrolledText(box._body, bg=C['console'], fg=C['console_f'],
                                                    insertbackground=C['console_f'],
                                                    font=('Consolas', 9), relief='flat',
                                                    padx=10, pady=8, highlightthickness=0)
        self.txt_logs.pack(fill='both', expand=True, padx=1, pady=1)
        self.refresh_logs_list()

    def refresh_logs_list(self):
        logs = sorted(glob.glob(os.path.join(HERE, 'logs', '*.log')), reverse=True)
        names = [os.path.basename(p) for p in logs]
        self.cmb_log['values'] = names
        if names:
            self.cmb_log.set(names[0])
            self._show_log(os.path.join(HERE, 'logs', names[0]))

    def _show_log(self, path):
        self.txt_logs.delete('1.0', 'end')
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
                self.txt_logs.insert('end', ''.join(lines[-4000:]))
            self.txt_logs.see('end')
        except Exception as e:
            self.txt_logs.insert('end', f'error: {e}')

    def open_selected_log(self):
        name = self.cmb_log.get()
        if name:
            self._show_log(os.path.join(HERE, 'logs', name))

    def open_logs_dir(self):
        d = os.path.join(HERE, 'logs')
        os.makedirs(d, exist_ok=True)
        os.startfile(d)


def main():
    app = App()
    app.mainloop()

if __name__ == '__main__':
    main()
