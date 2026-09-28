# SCI99 → Google Sheets Autosync (33 tab, sheet "2026.09.25")

Tự động lấy giá sci99.com và ghi vào 33 tab Google Sheets: sort ngày `M/D/YYYY` giảm dần, anti-dup theo ngày.

## Cấu trúc thư mục

```
D:\Desktop\14-sci99-sheets-autosync\
├── SKILL.md
├── INSTALL.md
├── Mo app SCI99.bat              # Mở GUI từ root
├── scripts\
│   ├── daily_sync.py             # Orchestrator 13 bước (Task Scheduler)
│   ├── daily_sync.bat
│   ├── login_sci99_daily.py      # Headless login → cookies
│   ├── login_sci99.py
│   ├── fetch_daily_sources.py    # ARTICLES + cjj + SW table
│   ├── update_from_detail_pages.py   # Chi tiết trang (赖/苏/色/CaHPO4/蛋/vit/palm)
│   ├── update_amino_from_articles.py # 缬氨酸 / 精氨酸 / 异亮氨酸
│   ├── update_mcp_two_blocks.py      # 磷酸二氢钙 B1 + B2
│   ├── update_choline_echemi.py      # 氯化胆碱 (echemi, Chrome sạch + CDP)
│   ├── update_mdcph_weekly.py        # 磷酸一二钙-每周 (vip.sci99 API → PDF)
│   ├── update_fx_sheet.py        # 汇率 sheet 25 cặp từ shibor 历史数据
│   ├── update_fx_rate.py         # 汇率/USD col of ALL sheets (USD/CNY中间价)
│   ├── verify_all_status.py
│   ├── sci99_gui.py               # GUI 5 tab (tiến trình 13 bước realtime, F5/F6/Esc)
│   ├── app_config.py
│   ├── app_settings.json
│   ├── Mo app.bat
│   ├── diid_mapping.json
│   ├── sci99_cookies.json
│   ├── echemi_cookies.json        # cookie echemi (tự refresh khi bước 6 pass)
│   ├── mcp_cjj_articles.json
│   ├── mcp_sw_price_history.json
│   ├── tools\                     # Maintenance one-off (không chạy daily)
│   │   ├── scan_duplicate_dates.py    # --fix: xóa ngày trùng per block
│   │   ├── format_vit_palm_sheet.py   # EU→plain, drop future, sort, dedupe 维生素/棕榈油
│   │   ├── format_mdcph_weekly_sheet.py
│   │   └── open_cjj_articles.py       # Legacy helper (daily dùng fetch_daily_sources)
│   ├── logs\                      # daily_YYYYMMDD_HHMMSS.log
│   ├── .echemi_profile\           # Chrome profile riêng của bước 6 (runtime)
│   └── _archive\                  # One-off scripts cũ (không dùng daily)
└── assets\
```

## Đầu vào

1. Service Account: `C:\Users\DELL\.openclaw\workspace\secrets\service_account.json`
2. Spreadsheet ID (sheet "2026.09.25", 33 tab): `1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU`
   (sheet cũ `1hmDLpYOALH8-Fu4pxG-VJZURDtz3Z2UzWwTPAOs230I` — archive, không ghi nữa)
3. sci99 login: xem `scripts/app_settings.json` (file gitignored — tự ghi vào `login_sci99*.py` qua GUI tab ⚙ Cài đặt)
4. Python: playwright, gspread, google-auth

## 33 tab

汇率, 赖氨酸70_河北_sci99, 赖氨酸70_山东_sci99, 赖氨酸98_河北_sci99, 赖氨酸98_山东_sci99, 苏氨酸_河北_sci99, 苏氨酸_山东_sci99, 缬氨酸_sci99_search, 精氨酸, 异亮氨酸, 色氨酸_sci99, 氯化胆碱_echemi, 磷酸氢钙_sci99, 磷酸一二钙_pdf_sci99, 磷酸二氢钙_云南_sci99_search, 磷酸二氢钙_西南_sci99, 蛋氨酸_山东_sci99, 蛋氨酸_河南_sci99, 维生素A_sci99, 维生素B1_sci99, 维生素B2_sci99, 维生素C_sci99, 维生素D3_sci99, 维生素E_sci99, 玉米蛋白粉_sci99, DDGS_sci, 鱼粉_sci99, 乳清粉_sci99, 肌醇_国产_100ppi, 发酵豆粕_mysteel, 棕榈油_天津24_sci99, 棕榈油_张家港52_sci99, 棕榈油_张家港24_sci99

> Lưu ý: riêng sheet **汇率** dùng EU comma-decimal 4dp (`6,7489`), dates start row 2, footer 2 dòng cuối.

## Format quy tắc

| Quy chuẩn | Mô tả |
|-----------|--------|
| Ngày | `M/D/YYYY` |
| Giá | **Số trần** (không dùng EU format) |
| Sort | Giảm dần theo ngày từng block |
| Anti-dup | Chỉ giữ 1 row / ngày / block |
| 涨跌 | Âm: `(25)` |
| 比例 | `-0,50%` (comma thập phân) |
| Future | Drop ngày > hôm nay |

## Chạy

```bat
:: GUI
Mo app SCI99.bat
:: hoặc scripts\Mo app.bat

:: Full daily (cũng là Task Scheduler sci99-sheets-daily, 18:30)
python -X utf8 scripts\daily_sync.py
:: hoặc scripts\daily_sync.bat
```

### Các bước daily_sync

1. `login_sci99_daily.py` — cookies
2. `fetch_daily_sources.py` — ARTICLES + mcp_cjj + mcp_sw
3. `update_from_detail_pages.py` — detail-page products
4. `update_amino_from_articles.py` — 3 amino từ article
5. `update_mcp_two_blocks.py` — 磷酸二氢钙
6. `update_choline_echemi.py` — 氯化胆碱 60% (echemi): tự launch Chrome sạch (`--remote-debugging-port`) + CDP, auto-kéo Aliyun slider khi cookie cũ, **tự export cookie mới** vào `echemi_cookies.json` khi qua; non-core, SKIP nếu vẫn kẹt (chạy manual thì kéo tay trong 75s chờ sẵn)
7. `update_mdcph_weekly.py` — 磷酸一二钙-每周 (vip.sci99 API → PDF周报 → pymupdf; non-core, SKIP khi chưa có report mới — báo ra thứ 5)
8. `update_whey_sci99.py` — 乳清粉低蛋白 天津 (sci99 search 4 trang, JS pager `li.link-btn[data-current]`, early-stop khi gặp ngày đã có; bài tuần — chỉ có bài mới vào thứ 2)
9. `update_inositol_100ppi.py` — 肌醇 99% 湖北 (100ppi `plist-1-7598-N`, playwright vì site chặn requests; early-stop khi trang cũ hơn sheet; ~3 trang lịch sử là tối đa)
10. `update_fsb_mysteel.py` — 发酵豆粕 50% 营口 (mysteel chart API `getTrendValueByCodeAndTime indexCode=ID01213983 type=103`, JSONP, 1 năm daily)
11. `update_fx_sheet.py` — 汇率 25 cặp (shibor 历史数据)
12. `update_fx_rate.py` — cột 汇率/USD của tất cả sheet (USD/CNY中间价, tự dò FX col từ header; chạy SAU 8-10 để heal ô K mới)
13. `verify_all_status.py` — status 33 tab (best-effort, có thể 429)

### Maintenance

```bat
python -X utf8 scripts\tools\scan_duplicate_dates.py --fix
python -X utf8 scripts\tools\format_vit_palm_sheet.py
python -X utf8 scripts\tools\format_mdcph_weekly_sheet.py
python -X utf8 scripts\verify_all_status.py
```

## Task Scheduler

- Name: `sci99-sheets-daily`
- Daily 18:30, target: `scripts\daily_sync.bat`
- GUI tab Cài đặt: ON/OFF, chỉnh giờ, chạy ngay (`app_config.apply_schedule`)

## Troubleshooting

| Lỗi | Giải pháp |
|-----|-----------|
| Google API 429 Quota | Chờ 60–150s rồi chạy lại verify |
| Login sci99 fail | Chạy GUI → Cài đặt → Save (ghi lại user/pass) rồi retry |
| sci99 trả 403 Forbidden (WAF rate-limit transient) | Chờ 10–30p rồi chạy lại; detail + amino đã tự retry 2 lần / abort sau 4 liên tiếp. KHÔNG append `?keyword=` vào URL article (gây 403) |
| Article "no date" | Xem có phải body trả về "403 Forbidden" không — fetch lại; URL phải sạch (không `?keyword=`) |
| I/O closed file | Dùng `python -X utf8`; không wrap stdout bằng TextIOWrapper ở module level nếu spawn subprocess |
| Tkinter crash từ thread | Không `self.after()` từ worker — dùng `queue.Queue` + poll |
| Ngày trùng | `scripts\tools\scan_duplicate_dates.py --fix` |
| EU format / future date | `scripts\tools\format_vit_palm_sheet.py` |
| echemi hiện "滑动验证页面" (choline SKIP) | Bước 6 tự auto-kéo slider + tự refresh cookie nếu qua được. Vẫn SKIP → chạy tay `python -X utf8 scripts\update_choline_echemi.py`, window mở ra kéo slider trong 75s; script sẽ tự lưu cookie mới. Profile Chrome step này: `scripts\.echemi_profile` (riêng, không đụng Chrome của user) |

## Lưu ý

- `_archive/`: script one-off, KHÔNG dùng daily.
- prices.sci99.com API POST chưa bắt được; parse HTML table đủ dùng.
- 磷酸一二钙-每周: lấy từ PDF report (không có diid/ppid sci99).
