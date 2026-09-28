# Sci99-crawl

Crawler sci99.com + echemi/mysteel/100ppi → Google Sheets (33 tab), tự đồng bộ hằng ngày qua Windows Task Scheduler, kèm app GUI điều khiển.

## Chạy

| Việc | Cách |
| --- | --- |
| Mở app GUI | double-click `Mo app SCI99.bat` |
| Chạy pipeline 13 bước | `python -X utf8 scripts/daily_sync.py` (hoặc nút ▶ trong GUI) |
| Lịch tự động | Task Scheduler `sci99-sheets-daily` — sửa trong tab ⚙ Cài đặt của GUI |

- GUI phím tắt: `F5` làm mới · `F6` chạy sync · `Esc` dừng
- Log: `scripts/logs/daily_*.log`

## Cấu trúc

```
Mo app SCI99.bat        launcher GUI
scripts/
  sci99_gui.py          app GUI (Dashboard / Dữ liệu / Chạy sync / Cài đặt / Logs)
  daily_sync.py         orchestrator 13 bước
  app_config.py         đọc/ghi app_settings.json + Task Scheduler
  newsheet_lib.py       shared write/read sheet format 17 cột
  update_*.py           các updater theo nguồn
  verify_all_status.py  đối chiếu 33 tab
```

## Cấu hình (KHÔNG commit)

Các file sau nằm trong `.gitignore` vì chứa credentials — máy mới phải khai lại
qua GUI tab ⚙ Cài đặt (lưu lại sẽ ghi thẳng vào `login_sci99*.py`):

- `scripts/app_settings.json` — user/pass sci99, spreadsheet_id, lịch chạy
- `scripts/login_sci99.py`, `scripts/login_sci99_daily.py`
- `scripts/sci99_cookies.json`, `scripts/echemi_cookies.json`
- Google Service Account JSON (đường dẫn đặt ngoài repo)

Sheet chính: `1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU` (tab "2026.09.25", 33 tab).
