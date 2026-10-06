# SCI99 → Google Sheets Autosync (2 spreadsheet: 33 tab + 50 tab)

Tự động lấy giá sci99.com / 100ppi / echemi / mysteel / chinabgao và ghi vào **2 spreadsheet**:

- **sheet cũ** `1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU` — 33 tab dữ liệu (4 tab index chỉ là link), script legacy per-product
- **sheet mới** `1pnDkBjLjfXgNE-Qv7rU7risEfcM3y4f4nd-OTN9XEu0` — 50 tab dữ liệu + 3 tab index (`SCI99`/`ECHEMI`/`100PPI`), ghi bởi `scripts/update_raw_*.py`

Sort ngày giảm dần, anti-dup theo ngày. Cả 2 sheet đều được `daily_sync.py` cập nhật trong 1 lần chạy (18 bước).

## Cấu trúc thư mục

```
D:\Desktop\sci99\
├── SKILL.md
├── INSTALL.md
├── README.md
├── Mo app SCI99.bat              # Mở GUI từ root
├── scripts\
│   ├── daily_sync.py             # Orchestrator 18 bước (Task Scheduler)
│   ├── daily_sync.bat
│   ├── login_sci99_daily.py      # Headless login → cookies
│   ├── login_sci99.py
│   ├── fetch_daily_sources.py    # ARTICLES + cjj + SW table
│   ├── update_from_detail_pages.py   # Chi tiết trang (赖/苏/色/CaHPO4/蛋/vit/palm)
│   ├── update_amino_from_articles.py # 缬氨酸 / 精氨酸 / 异亮氨酸
│   ├── update_mcp_two_blocks.py      # 磷酸二氢钙 B1 + B2
│   ├── update_choline_echemi.py      # 氯化胆碱 (echemi, Chrome sạch + CDP)
│   ├── update_mdcph_weekly.py        # 磷酸一二钙-每周 (vip.sci99 API → PDF)
│   ├── update_whey_sci99.py          # 乳清粉 (sci99 search, tuần 1 lần)
│   ├── update_inositol_100ppi.py     # 肌醇 (100ppi, playwright)
│   ├── update_fsb_mysteel.py         # 发酵豆粕 (mysteel chart API)
│   ├── update_fx_sheet.py        # 汇率 sheet 25 cặp từ shibor 历史数据
│   ├── update_fx_rate.py         # cột 汇率/USD của CẢ 2 sheet (batch read)
│   ├── raw_lib.py                # lib chung cho sheet mới (write_all/read_grid/analyze)
│   ├── update_raw_100ppi.py      # 26 tab 100ppi (strict trader filter)
│   ├── update_raw_echemi.py      # 15 tab echemi (CDP 9335 + chart score)
│   ├── update_raw_sci99.py       # 6 tab prices.sci99 detail
│   ├── update_raw_sci99_pdf.py   # 2 tab vip.sci99 weekly PDF
│   ├── update_raw_cnbg.py        # 1 tab chinabgao 三甲胺
│   ├── verify_all_status.py      # batched status 33 + 50 tab (GUI import collect_all)
│   ├── sci99_gui.py               # GUI 6 tab (Dashboard / Sức khỏe / Dữ liệu / Chạy sync / Cài đặt / Logs), theme ttkbootstrap
│   ├── app_config.py
│   ├── app_settings.json
│   ├── Mo app.bat
│   ├── diid_mapping.json
│   ├── sci99_cookies.json
│   ├── echemi_cookies.json        # cookie echemi (tự refresh khi bước 6 pass)
│   ├── mcp_cjj_articles.json
│   ├── mcp_sw_price_history.json
│   ├── tools\                     # Maintenance one-off (không chạy daily)
│   │   ├── repair_100ppi_leaks.py   # one-off: dọn row leak/trader sai (không daily)
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
2. Spreadsheet IDs:
   - sheet cũ `1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU` (33 tab)
   - sheet mới `1pnDkBjLjfXgNE-Qv7rU7risEfcM3y4f4nd-OTN9XEu0` (50 tab + 3 index)
   - (sheet very-old `1hmDLpYOALH8-Fu4pxG-VJZURDtz3Z2UzWwTPAOs230I` — archive, không ghi nữa)
3. sci99 login: xem `scripts/app_settings.json` (file gitignored — tự ghi vào `login_sci99*.py` qua GUI tab ⚙ Cài đặt)
4. Python: playwright, gspread, google-auth, requests, pandas, openpyxl, pymupdf, **ttkbootstrap** (GUI theme)

## Các tab

### Sheet cũ (33 tab dữ liệu + 4 tab index)

汇率, 赖氨酸70_河北_sci99, 赖氨酸70_山东_sci99, 赖氨酸98_河北_sci99, 赖氨酸98_山东_sci99, 苏氨酸_河北_sci99, 苏氨酸_山东_sci99, 缬氨酸_sci99_search, 精氨酸, 异亮氨酸, 色氨酸_sci99, 氯化胆碱_echemi, 磷酸氢钙_sci99, 磷酸一二钙_pdf_sci99, 磷酸二氢钙_云南_sci99_search, 磷酸二氢钙_西南_sci99, 蛋氨酸_山东_sci99, 蛋氨酸_河南_sci99, 维生素A_sci99, 维生素B1_sci99, 维生素B2_sci99, 维生素C_sci99, 维生素D3_sci99, 维生素E_sci99, 玉米蛋白粉_sci99, DDGS_sci, 鱼粉_sci99, 乳清粉_sci99, 肌醇_国产_100ppi, 发酵豆粕_mysteel, 棕榈油_天津24_sci99, 棕榈油_张家港52_sci99, 棕榈油_张家港24_sci99

> Lưu ý: riêng sheet **汇率** dùng EU comma-decimal 4dp (`6,7489`), dates start row 2, footer 2 dòng cuối.

### Sheet mới (50 tab dữ liệu + 3 tab index)

Danh sách tab lấy động từ worksheet (mọi tab trừ `SCI99`/`ECHEMI`/`100PPI` — 3 tab index chỉ chứa link), xem `scripts/verify_all_status.py` khi cần. Nhóm nguồn:

| Nguồn | Số tab | Script |
|--------|--------|--------|
| 100ppi (备注 trader) | 26 | `update_raw_100ppi.py` |
| echemi (chart score, CDP 9335) | 15 | `update_raw_echemi.py` |
| prices.sci99 detail | 6 | `update_raw_sci99.py` |
| vip.sci99 weekly PDF (磷酸一铵/二铵) | 2 | `update_raw_sci99_pdf.py` |
| chinabgao 三甲胺 | 1 | `update_raw_cnbg.py` |

Quy ước riêng của sheet mới:

| Quy chuẩn | Mô tả |
|-----------|--------|
| A1 | URL nguồn (mọi tab) |
| Ngày | serial số (`2026-10-06` → `462xx`), cột header chứa `日期` |
| FX | cột `汇率/USD` do `update_fx_rate.py` **chỉ fill ô trống** (chạy sau cùng) |
| Trader | tab có 备注 trader mà trang không trả row trader đó → **skip**, không trộn trader khác |
| Dedupe | `raw_lib.write_all` tự xóa đuôi block cũ khi block ngắn lại (`old_end`) |

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

:: Full daily (cũng là Task Scheduler sci99-sheets-daily — giờ xem tab ⚙ Cài đặt)
python -X utf8 scripts\daily_sync.py
:: hoặc scripts\daily_sync.bat
```

### Các bước daily_sync (18 bước)

**Sheet cũ (legacy):**

1. `login_sci99_daily.py` — cookies
2. `fetch_daily_sources.py` — ARTICLES + mcp_cjj + mcp_sw
3. `update_from_detail_pages.py` — detail-page products — **core**
4. `update_amino_from_articles.py` — 3 amino từ article
5. `update_mcp_two_blocks.py` — 磷酸二氢钙 — **core**
6. `update_choline_echemi.py` — 氯化胆碱 60% (echemi): tự launch Chrome sạch (`--remote-debugging-port`) + CDP, auto-kéo Aliyun slider khi cookie cũ, **tự export cookie mới** vào `echemi_cookies.json` khi qua; non-core, SKIP nếu vẫn kẹt (chạy manual thì kéo tay trong 75s chờ sẵn)
7. `update_mdcph_weekly.py` — 磷酸一二钙-每周 (vip.sci99 API → PDF周报 → pymupdf; non-core, SKIP khi chưa có report mới — báo ra thứ 5)
8. `update_whey_sci99.py` — 乳清粉低蛋白 天津 (sci99 search 4 trang, JS pager `li.link-btn[data-current]`, early-stop khi gặp ngày đã có; bài tuần — chỉ có bài mới vào thứ 2)
9. `update_inositol_100ppi.py` — 肌醇 99% 湖北 (100ppi `plist-1-7598-N`, playwright vì site chặn requests; early-stop khi trang cũ hơn sheet; ~3 trang lịch sử là tối đa)
10. `update_fsb_mysteel.py` — 发酵豆粕 50% 营口 (mysteel chart API `getTrendValueByCodeAndTime indexCode=ID01213983 type=103`, JSONP, 1 năm daily)

**Sheet mới (5 updater, mỗi nguồn 1 lần ghi batch):**

11. `update_raw_100ppi.py` — 26 tab (playwright; strict trader filter: tab thiếu row trader → skip)
12. `update_raw_echemi.py` — 15 tab (headless Chrome CDP 9335 + chart score)
13. `update_raw_sci99.py` — 6 tab prices.sci99 detail (header-driven, spec/market filter)
14. `update_raw_sci99_pdf.py` — 2 tab vip.sci99 PDF (SKIP khi chưa có report mới)
15. `update_raw_cnbg.py` — 1 tab chinabgao 三甲胺 (chọn row gần giá hiện tại nhất)

**FX + verify (chạy sau cùng):**

16. `update_fx_sheet.py` — 汇率 25 cặp (shibor 历史数据)
17. `update_fx_rate.py` — cột 汇率/USD của **cả 2 sheet** (batch read, chỉ fill ô trống → heal row mới; PHẢI chạy sau 11–15)
18. `verify_all_status.py` — status 33 + 50 tab (batched `values_batch_get`, best-effort, có thể 429)

Exit code: 0 khi 2 bước core (`detail_pages` + `mcp`) OK — các bước còn lại best-effort.

### Maintenance

```bat
python -X utf8 scripts\tools\scan_duplicate_dates.py --fix
python -X utf8 scripts\tools\format_vit_palm_sheet.py
python -X utf8 scripts\tools\format_mdcph_weekly_sheet.py
python -X utf8 scripts\verify_all_status.py
```

## GUI (`Mo app SCI99.bat`)

6 tab — theme `ttkbootstrap` (`bootstrap-light` / `bootstrap-dark`, nút ☀/🌙 lưu vào cài đặt):

| Tab | Nội dung |
|-----|----------|
| 🏠 Dashboard | Lịch chạy (Task Scheduler), KPI, trạng thái 33 tab (batched ~5s), lịch sử chạy gần đây |
| 🩺 Sức khỏe | **Quản lý cả 2 sheet**: card `33/33` + `50/50`, bảng 83 tab (mới nhất / dòng / URL A1 / trạng thái), lọc + "chỉ hiện lỗi", double-click mở sheet, **tự đọc batch mỗi 5 phút** |
| 📁 Dữ liệu | Xem/Export CSV 1 tab bất kỳ |
| ▶ Chạy sync | Tiến trình 18 bước realtime + console (F6 chạy, Esc dừng) |
| ⚙ Cài đặt | Login sci99, spreadsheet id, Task Scheduler ON/OFF + giờ |
| 📜 Logs | Đọc `logs/daily_*.log` |

- Phím tắt: `F5` làm mới · `F6` chạy sync · `Esc` dừng
- Nút ▶ trong GUI = `daily_sync.py` → cập nhật cả 2 sheet
- Không có `ttkbootstrap` app vẫn chạy (fallback theme `clam`): `pip install ttkbootstrap`

## Task Scheduler

- Name: `sci99-sheets-daily`
- Daily, target: `scripts\daily_sync.bat` (mặc định 18:30 — giờ hiện hành xem tab ⚙ Cài đặt)
- GUI tab Cài đặt: ON/OFF, chỉnh giờ, chạy ngay (`app_config.apply_schedule`)

## Troubleshooting

| Lỗi | Giải pháp |
|-----|-----------|
| Google API 429 Quota | Verify/raw/fx đều đã batch (`values_batch_get`) + retry 25–60s; vẫn 429 → đợi 1–2 phút chạy lại. GIẢM read: đừng mở lại tab 🩺 liên tục (mỗi lần ~6 call) |
| Verify báo `NO DATES` / `MISSING` | Tab thiếu header `日期` hoặc bị đổi tên — mở sheet kiểm tra; sheet mới còn thiếu cột ngày nếu updater chưa từng chạy |
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
