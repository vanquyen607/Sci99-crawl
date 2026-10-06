# Sci99-crawl

Crawler sci99.com + echemi/mysteel/100ppi → Google Sheets (2 spreadsheet: 33 tab cũ + 51 tab mới), tự đồng bộ hằng ngày qua Windows Task Scheduler, kèm app GUI điều khiển (theme ttkbootstrap, tab 🩺 Sức khỏe theo dõi cả 2 sheet).

## Chạy

| Việc | Cách |
| --- | --- |
| Mở app GUI | double-click `Mo app SCI99.bat` |
| Chạy pipeline 18 bước | `python -X utf8 scripts/daily_sync.py` (hoặc nút ▶ trong GUI) |
| Lịch tự động | Task Scheduler `sci99-sheets-daily` — sửa trong tab ⚙ Cài đặt của GUI |

- GUI phím tắt: `F5` làm mới · `F6` chạy sync · `Esc` dừng
- Tab 🩺 Sức khỏe: 33 + 51 tab, tự đọc batch mỗi 5 phút (cần `pip install ttkbootstrap`)
- Log: `scripts/logs/daily_*.log`

## Cấu trúc

```
Mo app SCI99.bat        launcher GUI
scripts/
  sci99_gui.py          app GUI (Dashboard / Sức khỏe / Dữ liệu / Chạy sync / Cài đặt / Logs)
  daily_sync.py         orchestrator 18 bước
  app_config.py         đọc/ghi app_settings.json + Task Scheduler
  newsheet_lib.py       shared write/read sheet cũ (format 17 cột)
  raw_lib.py            shared write/read sheet mới (write_all + dọn đuôi block)
  update_raw_*.py       5 updater sheet mới (100ppi / echemi / sci99 / PDF / chinabgao)
  update_*.py           các updater sheet cũ theo nguồn
  verify_all_status.py  đối chiếu 33 + 51 tab (batch, GUI import collect_all)
```

Phụ thuộc: `pip install playwright gspread google-auth pandas openpyxl requests pymupdf ttkbootstrap`
(xem `INSTALL.md`, chi tiết kỹ thuật xem `SKILL.md`)

## Cấu hình (KHÔNG commit)

Các file sau nằm trong `.gitignore` vì chứa credentials — máy mới phải khai lại
qua GUI tab ⚙ Cài đặt (lưu lại sẽ ghi thẳng vào `login_sci99*.py`):

- `scripts/app_settings.json` — user/pass sci99, spreadsheet_id, lịch chạy
- `scripts/login_sci99.py`, `scripts/login_sci99_daily.py`
- `scripts/sci99_cookies.json`, `scripts/echemi_cookies.json`
- Google Service Account JSON (đường dẫn đặt ngoài repo)

Sheet đang ghi (cả 2 do `daily_sync.py` cập nhật trong 1 lần chạy):

| | Spreadsheet ID | Nội dung |
| --- | --- | --- |
| Sheet cũ | `1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU` | 33 tab dữ liệu (script legacy) |
| Sheet mới | `1pnDkBjLjfXgNE-Qv7rU7risEfcM3y4f4nd-OTN9XEu0` | 51 tab dữ liệu + 3 tab index (A1 = URL nguồn) |
