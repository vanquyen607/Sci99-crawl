# Hướng dẫn cài đặt và khởi động hệ thống

## 1. Cài đặt Python Dependencies

```bash
pip3 install playwright gspread google-auth-oauthlib pandas openpyxl
playwright install
```

Giải thích các gói:
- `playwright`: Điều khiển trình duyệt Chrome/Edge (download Excel).
- `gspread`: Tự động hóa Google Sheets.
- `google-auth-oauthlib`: Xác thực cho Google API.
- `pandas`: Xử lý Excel, dữ liệu & format.
- `openpyxl`: Đọc/ghi file Excel.

## 2. Thiết lập Secret Service Account cho Google Sheets

Mặc định trong `scripts/...py` đang đọc từ:

```
C:\Users\DELL\.openclaw\workspace\secrets\service_account.json
```

Nếu bạn cần copy sang thư mục skill:

```bash
mkdir -p "C:\Users\DELL\.openclaw\skills\14-sci99-sheets-autosync\secrets"
copy "C:\Users\DELL\.openclaw\workspace\secrets\service_account.json" "C:\Users\DELL\.openclaw\skills\14-sci99-sheets-autosync\secrets\service_account.json"
```

Sau khi copy, chỉnh lại đường dẫn trong tất cả script (đã sẵn trong workspace).

## 3. Khởi động Chrome/CDP browser ngay trong Workspace

### Cách 1: Dùng terminal Workspace

```bash
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
"
```

### Cách 2: Dùng UI Workspace (nếu có)

Chạy lệnh trong terminal Workspace:

```bash
screen(browser_show)
```

Sau đó mở địa chỉ: `http://127.0.0.1:18800` (đã tự động bật bởi Playwright).

## 4. Cấu trúc thư mục

```
D:\Desktop\14-sci99-sheets-autosync\
├── SKILL.md
├── INSTALL.md                         # Hướng dẫn cài đặt (file này)
├── Mo app SCI99.bat                   # Mở GUI
└── scripts\
    ├── daily_sync.py / daily_sync.bat # Orchestrator 10 bước
    ├── login_sci99_daily.py           # Headless login → cookies
    ├── login_sci99.py
    ├── fetch_daily_sources.py
    ├── update_from_detail_pages.py
    ├── update_amino_from_articles.py
    ├── update_mcp_two_blocks.py
    ├── update_choline_echemi.py       # 氯化胆碱 (echemi, Chrome sạch + CDP)
    ├── update_mdcph_weekly.py         # 磷酸一二钙-每周 (vip.sci99 API → PDF)
    ├── update_fx_sheet.py             # 汇率 25 cặp (shibor)
    ├── update_fx_rate.py              # 汇率/USD cols (all sheets)
    ├── verify_all_status.py
    ├── sci99_gui.py / app_config.py / app_settings.json / Mo app.bat
    ├── diid_mapping.json, sci99_cookies.json, echemi_cookies.json, mcp_*.json
    ├── tools\                         # Maintenance one-off (không daily)
    │   ├── scan_duplicate_dates.py    # --fix: ngày trùng
    │   ├── format_vit_palm_sheet.py
    │   ├── format_mdcph_weekly_sheet.py
    │   └── open_cjj_articles.py       # Legacy helper
    ├── logs\                          # daily_YYYYMMDD_HHMMSS.log
    ├── .echemi_profile\               # Chrome profile riêng của bước choline
    └── _archive\                      # One-off scripts cũ (không daily)
```

Task Scheduler: `sci99-sheets-daily` → `scripts\daily_sync.bat`, 18:30 hàng ngày.

## 5. Kiểm tra trình duyệt đã bật CDP

Sau khi chạy lệnh khởi động browser, mở trình duyệt và kiểm tra:

```bash
curl http://127.0.0.1:18800/json  # để check CDP Websocket URL
```

Nếu nhận được JSON error (ví dụ `{"error": "Page not found"}`) nghĩa là Chrome đang chạy CDP và sẵn sàng để script kết nối.

## 6. Công cụ hữu ích khi debug

- **Tạo log chi tiết**: Mỗi script dump tất cả output ra terminal stdout/stderr + file log vào thư mục `logs/` (nếu code đã thêm ghi log).
- **Áp dụng encoding UTF-8**: Mở terminal (PowerShell/Command Prompt) và set môi trường:

```powershell
$env:PYTHONUTF8=1
```

Hoặc chỉnh `sys.stdout.reconfigure(encoding='utf-8')` trong từng script (đã sẵn).

- **Check tháng ngày**: Sau khi chạy import, đọc log để chắc chắn chưa duplicate ngày và đã sort giảm dần.

Nếu bạn muốn, tôi có thể tạo file `logs/` cấu trúc và các helper logging thì private message me.

## 7. Lưu ý daily workflow

- `scripts\daily_sync.py` chạy tuần tự 10 bước; log trong `scripts\logs\daily_*.log`.
- Core steps bắt buộc: `update_from_detail_pages.py` + `update_mcp_two_blocks.py` (exit 0 nếu 2 bước này OK).
- FX steps (best-effort): `update_fx_sheet.py` (汇率 sheet) + `update_fx_rate.py` (汇率/USD col of all sheets).
- One-off/repair scripts nằm trong `scripts\_archive\` — không đưa vào daily.