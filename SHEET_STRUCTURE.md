# Cấu trúc 2 spreadsheet (spec để dựng lại)

Cập nhật 2026-11-19, đọc trực tiếp từ 2 sheet đang chạy + code trong `scripts/`.
Dùng file này khi mất sheet / tạo sheet mới / đổi tài khoản: dựng lại đúng tên tab,
đúng header và đúng công thức mẫu là các updater tự tải lại toàn bộ lịch sử.

## 1. Tổng quan

| | Sheet cũ | Sheet mới (原料) |
| --- | --- | --- |
| Spreadsheet ID hiện tại | `1kuN8rT9shOellupamis9iyb6CpZFaWpao4VLdzZnQQU` | `1pnDkBjLjfXgNE-Qv7rU7risEfcM3y4f4nd-OTN9XEu0` |
| Config key (`app_settings.json`) | `spreadsheet_id` | `raw_spreadsheet_id` |
| Tab dữ liệu | 33 | 51 |
| Tab index | 4: `SCI99`, `ECHEMI`, `100PPI`, `MYSTEEL` | 3: `SCI99`, `ECHEMI`, `100PPI` |
| Script ghi | `update_from_detail_pages`, `update_amino_from_articles`, `update_choline_echemi`, `update_mcp_two_blocks`, `update_mdcph_weekly`, `update_whey_sci99`, `update_inositol_100ppi`, `update_fsb_mysteel`, `update_fx_sheet` | `update_raw_100ppi`, `update_raw_echemi`, `update_raw_sci99`, `update_raw_sci99_pdf`, `update_raw_cnbg` |
| Ngày | serial (epoch 1899-12-30), trừ tab `汇率` | serial |

Nguyên tắc:

- **Mỗi tab = 1 chuỗi giá** (1 sản phẩm × 1 thị trường × 1 nguồn).
- Script **không tạo tab** — thiếu tab là `WorksheetNotFound`, thiếu A1 URL là tab bị bỏ qua.
- Tên tab phải khớp **tuyệt đối**, kể cả khoảng trắng/ký tự: `棕榈油_张家港 24°_sci99`,
  `DDGS_sci`, `氯化胆碱_echemi`.
- Dữ liệu mới nhất ở trên cùng. Không merge ô trong vùng dữ liệu.
- Script tự nhận width = cột cuối có nội dung (đọc tối đa 26 cột), nên dư cột trống không sao.

## 2. Quy ước chung của 1 tab dữ liệu

### 2.1. Bố cục dòng

| Dòng | Nội dung |
| --- | --- |
| 1, cột A | URL nguồn. **Bắt buộc với sheet mới** (raw_lib nhóm tab theo URL để fetch); sheet cũ chỉ để tham khảo, có tab trống ô này vẫn chạy |
| 2 | Header (trừ 2 tab `三甲胺_*_cnbg`: header dòng 3) |
| 3 | Dòng dữ liệu đầu tiên (cnbg: dòng 4) — **nên có 1 dòng mẫu đủ công thức** |

Riêng `三甲胺_鲁西化工_cnbg`: dòng 1 = URL + nhãn `鲁西化工 99,9%` ở I1,
dòng 2 = rác `TÁCH RA 2 CÁI` / `国产99.99%` — giữ nguyên, script bỏ qua.

### 2.2. Layout chuẩn 17 cột (sheet cũ, phần lớn tab sheet mới)

| Cột | Header | Ghi chú |
| --- | --- | --- |
| A | 日期 | serial, format date |
| B | 产品名称 |  |
| C | 规格型号 |  |
| D | 市场 |  |
| E | 数据类型 | 市场价 / 出厂价 / 市场均价 |
| F | 最低价 | có thể trống |
| G | 最高价 | có thể trống |
| H | 平均价 … | **cột giá** — raw_lib nhận theo header chứa `平均价` |
| I | 涨跌 | công thức |
| J | 比例 | công thức, format % |
| K | 汇率 USD | text số thập phân dấu chấm (vd `6.7128`), do `update_fx_rate` điền |
| L | 折成美金 | công thức |
| M | 退税后（-13%） | công thức |
| N | 拉柜+报关费 | hằng số 10 |
| O | 海运费 | hằng số 30 |
| P | CIF 估算 | công thức |
| Q | 备注 | text (có thể trống) |

Công thức mẫu cho dòng `n` (n = 3, 4, 5…):

```
I: =Hn-H(n+1)
J: =(Hn-H(n+1))/H(n+1)
L: =Hn/Kn          (một số tab ghi =+Hn/Kn — tương đương)
M: =Ln*87%         (biến thể: 91% ở 玉米蛋白粉/DDGS, 100% ở 苏氨酸_河北)
N: 10              (tab đơn giá/kg dùng =10/1000)
O: 30              (tab đơn giá/kg dùng =30/1000)
P: =Mn+Nn+On
```

`update_raw_*` sẽ lấy công thức mẫu từ dòng dữ liệu đầu tiên rồi tự sinh lại
`I/J` và điền `L/M/P` cho mọi dòng (chỉ nhận công thức tham chiếu cùng dòng).

### 2.3. Các biến thể phải giữ đúng

| Tab | Khác chuẩn |
| --- | --- |
| `三甲胺_鲁西化工_cnbg`, `三甲胺_国产_cnbg` | 9 cột: 日期/产品名称/规格型号/市场/数据类型/**平均价(F)**/涨跌/比例/备注. Giá ở F, công thức `=Fn-F(n+1)`, `=(Fn-F(n+1))/F(n+1)` |
| `玉米淀粉_100ppi` | đảo thứ tự: … H 平均价, I 涨跌, J 比例, **K 备注, L 汇率, M 折成美金, N 退税后, O 拉柜, P 海运费, Q CIF** (`=Nn+On+Pn`, `=Hn/Ln`) |
| `棕榈油_天津_sci99`, `棕榈油_52度棕榈油_sci99`, `棕榈油_张家港 24°_sci99` | 10 cột, **không có block FX**: … H 平均价, I 涨跌, J 备注 |
| `鱼粉_sci99` | header chỉ tới 备注 (không 比例/FX): 日期…平均价, 涨跌, 备注 |
| `色氨酸_sci99` | D = 数据类型, E = 市场 (đảo so với chuẩn) |
| `磷酸*` | header 退税后 có suffix ngày (vd `退税后（-13%）（1.2.2026）`) — không cần giống hệt, miễn giữ `退税后` |
| Tab echemi / 100ppi sheet mới | 11 cột, dừng ở 备注 (không FX) |
| Tab sci99 sheet mới | 11 cột, dừng ở 备注 (trừ `维生素E_sci99` 17 cột như sheet cũ) |

### 2.4. Cách raw_lib nhận dạng tab (để header không bị lệch)

- Header row = dòng đầu tiên (trong 6 dòng đầu) có **ô đúng chữ `日期`**.
- Cột giá = cột đầu tiên chứa `平均价`; `涨跌` = bắt đầu bằng `涨跌`; `比例` = bắt đầu bằng `比例`;
  cột FX = chứa `汇率`.
- Dòng dữ liệu đầu = dòng đầu sau header mà cột A parse được thành ngày.
- Vì vậy tên cột có thể khác unit (元/吨 vs 元/千克, có/không khoảng trắng) nhưng
  **không được đổi các từ khoá trên**.

## 3. Sheet cũ — 33 tab

### 3.1. Tab index (chỉ để tra cứu, script không đọc)

`A1 = SHEET`, từ A2 là tên tab. Danh sách hiện tại **không đầy đủ** (SCI99 chỉ 20 dòng):

| Tab index | Nội dung |
| --- | --- |
| `SCI99` | 维生素A/B1/B2/C/D3, 赖氨酸70/98 ×(河北/山东), 苏氨酸 ×2, 色氨酸, 蛋氨酸 ×2, 磷酸氢钙, 磷酸二氢钙_西南, 玉米蛋白粉, 鱼粉, DDGS |
| `ECHEMI` | 氯化胆碱_echemi |
| `100PPI` | 肌醇_国产_100ppi |
| `MYSTEEL` | 发酵豆粕_mysteel |

### 3.2. 22 tab từ `update_from_detail_pages.py`

URL dạng: `https://prices.sci99.com/cn/product_price.aspx?diid=<diid>&ppid=<ppid>&ppname=<tên>&cycletype=day`

| Tab | ppid | diid | Ghi chú |
| --- | --- | --- | --- |
| 赖氨酸70_河北_sci99 | 12418 | 29728 | |
| 赖氨酸70_山东_sci99 | 12418 | 29738 | A1 hiện trống |
| 赖氨酸98_河北_sci99 | 12418 | 29729 | |
| 赖氨酸98_山东_sci99 | 12418 | 29739 | |
| 苏氨酸_河北_sci99 | 12425 | 36690 | 退税 100% |
| 苏氨酸_山东_sci99 | 12425 | 29724 | |
| 色氨酸_sci99 | 12424 | 119847 | D/E đảo |
| 磷酸氢钙_sci99 | 12311 | 113439 | |
| 蛋氨酸_山东_sci99 | 12416 | 29716 | |
| 蛋氨酸_河南_sci99 | 12416 | 29713 | |
| 维生素A_sci99 | 13393 | 68520 | |
| 维生素B1_sci99 | 12426 | 36931 | |
| 维生素B2_sci99 | 31385 | 79215 | |
| 维生素C_sci99 | 12427 | 68504 | |
| 维生素D3_sci99 | 12428 | 36929 | |
| 维生素E_sci99 | 13394 | 68516 | **trùng** tab `维生素E_sci99` sheet mới |
| 玉米蛋白粉_sci99 | 12430 | 21076 | 退税 91% |
| DDGS_sci | 12414 | 76220 | 退税 91% |
| 鱼粉_sci99 | 12429 | 14401 | không FX |
| 棕榈油_天津24_sci99 | 12670 | 15089 | |
| 棕榈油_张家港52_sci99 | 12670 | 70832 | |
| 棕榈油_张家港24_sci99 | 12670 | 15086 | |

### 3.3. 11 tab còn lại

| Tab | Nguồn / A1 | Script | Ghi chú |
| --- | --- | --- | --- |
| 精氨酸 | `https://www.sci99.com/search.html?keyword=河南郑州和谐通氨基酸报价动态` | `update_amino_from_articles` | từ bài viết, 17 cột |
| 异亮氨酸 | (cùng URL trên) | `update_amino_from_articles` | 17 cột |
| 缬氨酸_sci99_search | (cùng URL trên) | `update_amino_from_articles` | 17 cột |
| 氯化胆碱_echemi | `https://www.echemi.com/productsInformation/pid_Rock3892-cholinechloride.html` | `update_choline_echemi` | 1 block A..Q; **cần ≥1 dòng mẫu**; trùng tab sheet mới |
| 磷酸二氢钙_云南_sci99_search | `https://www.sci99.com/search.html?keyword=磷酸二氢钙` | `update_mcp_two_blocks` | block B1, 17 cột |
| 磷酸二氢钙_西南_sci99 | `https://prices.sci99.com/cn/product_price.aspx?diid=14507&ppid=12309&...` | `update_mcp_two_blocks` | block B2, 17 cột |
| 磷酸一二钙_pdf_sci99 | `https://vip.sci99.com/` | `update_mdcph_weekly` | PDF weekly |
| 乳清粉_sci99 | `https://www.sci99.com/search.html?keyword=乳清粉` | `update_whey_sci99` | 17 cột |
| 肌醇_国产_100ppi | `https://www.100ppi.com/mprice/plist-1-7598-3.html` | `update_inositol_100ppi` | 17 cột |
| 发酵豆粕_mysteel | `https://m.mysteel.com/hot/1559042.html` | `update_fsb_mysteel` | 17 cột |
| 汇率 | — | `update_fx_sheet` | xem 3.4 |

### 3.4. Tab `汇率`

- 26 cột: `日期` + 25 cặp, đúng thứ tự:
  `USD/CNY, EUR/CNY, 100JPY/CNY, HKD/CNY, GBP/CNY, AUD/CNY, NZD/CNY, SGD/CNY, CHF/CNY, CAD/CNY,
  CNY/MOP, CNY/MYR, CNY/RUB, CNY/ZAR, CNY/KRW, CNY/AED, CNY/SAR, CNY/HUF, CNY/PLN, CNY/DKK,
  CNY/SEK, CNY/NOK, CNY/TRY, CNY/MXN, CNY/THB`
- Ngày = **text** `M/D/YYYY` (không phải serial).
- Giá trị = text thập phân kiểu EU: dấu phẩy (`6,7128`). `update_fx_sheet` so khớp header với API shibor;
  sai thứ tự/tên cặp là nó bỏ qua cả tab.

## 4. Sheet mới — 51 tab + 3 index

### 4.1. Tab index (danh sách đầy đủ — dùng để rebuild)

`A1 = SHEET`, A2.. = tên tab.

| Index | Các tab |
| --- | --- |
| `SCI99` (6) | 维生素E_sci99, 棕榈油_天津_sci99, 棕榈油_52度棕榈油_sci99, 棕榈油_张家港 24°_sci99, 豆粕_sci99, 玉米_sci99 |
| `ECHEMI` (15) | 尿素, 硫酸亚铁, 碳酸氢铵, 棕榈油, 环氧乙烷, 氢氧化钠, 丙酸, 苯甲酸, 丁酸, 甲酸, 乙酸, 磷酸, 硫酸, 盐酸 (đều `_echemi`), 氯化胆碱_echemi |
| `100PPI` (26) | 抗氧化剂_国产, 抗氧剂BHT_国产, 纽甜, 葡萄糖, 糖精钠, 丙酸钙, 甜菜碱, 环氧乙烷, 三甲胺_鲁西化工, 三甲胺_国产, 氧化锌, 丙酸_国产, 丁酸, 富马酸_山西, 富马酸_淄博, 甲酸_南京巴斯夫, 甲酸_鲁西, 甲酸_鲁西化工, 柠檬酸, 乳酸, 乙酸, 磷酸, 硫酸, 铜, 锌, 玉米淀粉 (đều `_100ppi`) |

### 4.2. 15 tab `_echemi` (11 cột, không FX)

URL: `https://www.echemi.com/productsInformation/<path>`

| Tab | path |
| --- | --- |
| 尿素_echemi | `pd20150901160-urea.html` |
| 氯化胆碱_echemi | `pid_Rock3892-cholinechloride.html` |
| 硫酸亚铁_echemi | `pd20160420102823025-ferrous-sulfate.html` |
| 碳酸氢铵_echemi | `pd20150901032-ammonium-bicarbonate.html` |
| 棕榈油_echemi | `pid_Rock26783-palmoil.html` |
| 环氧乙烷_echemi | `pid_Rock13784-ethylene-oxide-eo.html` |
| 氢氧化钠_echemi | `pd20150901041-caustic-soda-pearls.html` |
| 苯甲酸_echemi | `pd20150901103-benzoic-acid.html` |
| 丙酸_echemi | `pd20150901068-propionic-acid.html` |
| 丁酸_echemi | `pid_Rock15098-isobutyricacid.html` |
| 甲酸_echemi | `pd20150901218-formic-acid.html` |
| 乙酸_echemi | `temppid160628000977-acetic-acid.html` |
| 磷酸_echemi | `pd20150901061-phosphoric-acid.html` |
| 硫酸_echemi | `pid_Rock19440-sulfuric-acid.html` |
| 盐酸_echemi | `pid_Rock19088-hydrochloric-acid.html` |

### 4.3. 26 tab `_100ppi` (11 cột, không FX)

URL: `https://www.100ppi.com/mprice/plist-1-<id>-1.html`
(`肌醇` bên sheet cũ dùng `plist-1-7598-3.html`)

| Tab | plist id |
| --- | --- |
| 抗氧化剂_国产_100ppi | 11804 |
| 抗氧剂BHT_国产_100ppi | 17560 |
| 纽甜_100ppi | 9374 |
| 葡萄糖_100ppi | 866 |
| 糖精钠_100ppi | 9483 |
| 丙酸钙_100ppi | 11298 |
| 甜菜碱_100ppi | 5961 |
| 环氧乙烷_100ppi | 359 |
| 三甲胺_鲁西化工_100ppi | 1285 |
| 三甲胺_国产_100ppi | 1285 |
| 氧化锌_100ppi | 848 |
| 丙酸_国产_100ppi | 1516 |
| 丁酸_100ppi | 1615 |
| 富马酸_山西_100ppi | 3279 |
| 富马酸_淄博_100ppi | 3279 |
| 甲酸_南京巴斯夫_100ppi | 1726 |
| 甲酸_鲁西_100ppi | 1726 |
| 甲酸_鲁西化工_100ppi | 1726 |
| 柠檬酸_100ppi | 1409 |
| 乳酸_100ppi | 2023 |
| 乙酸_100ppi | 4476 |
| 磷酸_100ppi | 558 |
| 硫酸_100ppi | 515 |
| 铜_100ppi | 61 |
| 锌_100ppi | 64 |
| 玉米淀粉_100ppi | 3107 |

### 4.4. 6 tab `_sci99` + 2 PDF + 2 cnbg

| Tab | Nguồn | Ghi chú |
| --- | --- | --- |
| 维生素E_sci99 | `prices.sci99.com` diid=68516 ppid=13394 | 17 cột (có FX) |
| 棕榈油_天津_sci99 | diid=15089 ppid=12534 | 10 cột, không FX |
| 棕榈油_52度棕榈油_sci99 | diid=70832 ppid=12534 | 10 cột, không FX |
| 棕榈油_张家港 24°_sci99 | diid=15086 ppid=12534 | 10 cột, không FX (chú ý khoảng trắng trong tên) |
| 豆粕_sci99 | diid=15029 ppid=12417 | 11 cột, không FX |
| 玉米_sci99 | diid=68326 ppid=12540 | 11 cột, không FX |
| 磷酸一铵_pdf_sci99 | `https://vip.sci99.com/` | 17 cột, PDF weekly |
| 磷酸二铵_pdf_sci99 | `https://vip.sci99.com/` | 17 cột, PDF weekly |
| 三甲胺_鲁西化工_cnbg | `https://www.chinabgao.com/jiage/sanjiaan/` | 9 cột, header dòng 3 |
| 三甲胺_国产_cnbg | `https://www.chinabgao.com/jiage/sanjiaan/` | 9 cột, header dòng 3 |

## 5. Dựng lại — 2 cách

### Cách A (khuyến nghị): nhân bản sheet hiện có

1. Mở sheet hiện tại → **File → Make a copy** (làm cho cả 2 sheet).
2. Share bản copy cho `client_email` của service account, quyền **Editor**.
3. Nếu muốn sạch dữ liệu: xoá từ dòng data đầu tiên trở xuống, **giữ dòng 1 (URL), header và 1 dòng mẫu công thức**.
4. Nhập 2 ID mới vào GUI ⚙ Cài đặt (hoặc `scripts/app_settings.json`).
5. `python -X utf8 scripts\verify_all_status.py` → 33/33 + 51/51, rồi chạy `daily_sync`.

Lưu ý: service account không tự copy được (không có dung lượng Drive) — phải copy bằng tài khoản Google của bạn.

### Cách B: dựng tay từ file này

1. Tạo spreadsheet mới, share cho service account (Editor).
2. Tạo tab index trước, `A1 = SHEET`, dán danh sách ở mục 4.1 (sheet mới) và 3.1 (sheet cũ).
3. Với từng tab: tạo tab đúng tên → A1 = URL (bắt buộc với sheet mới) → dán header đúng
   mục 2.2/2.3 → tạo **1 dòng mẫu** ở dòng 3 (cnbg dòng 4) với đủ công thức I/J/L/M/P.
4. Thêm dòng vào `scripts/app_settings.json` (`sheets` chỉ là danh sách hiển thị trong GUI, không bắt buộc).
5. Chạy updater — chúng tự tải lại lịch sử:
   - `update_from_detail_pages.py` — full history từ sci99 detail page.
   - `update_raw_100ppi/echemi/sci99/cnbg.py` — fetch lại cả chuỗi (100ppi phân trang, echemi chart, cnbg).
   - `update_choline_echemi.py` — **bắt buộc có ≥1 dòng mẫu**, nếu block trống nó SKIP.
6. `update_fx_sheet.py` (điền 汇率) → `update_fx_rate.py` (điền cột K toàn bộ) → `verify_all_status.py`.

## 6. Script ↔ tab (tóm tắt)

| Script | Tab |
| --- | --- |
| `update_from_detail_pages.py` | 22 tab sci99 detail (mục 3.2) |
| `update_amino_from_articles.py` | 精氨酸, 异亮氨酸, 缬氨酸_sci99_search |
| `update_choline_echemi.py` | 氯化胆碱_echemi (sheet cũ) |
| `update_mcp_two_blocks.py` | 磷酸二氢钙_云南_sci99_search, 磷酸二氢钙_西南_sci99 |
| `update_mdcph_weekly.py` | 磷酸一二钙_pdf_sci99 |
| `update_whey_sci99.py` | 乳清粉_sci99 |
| `update_inositol_100ppi.py` | 肌醇_国产_100ppi |
| `update_fsb_mysteel.py` | 发酵豆粕_mysteel |
| `update_fx_sheet.py` | 汇率 |
| `update_fx_rate.py` | cột 汇率 của **cả 2 sheet** |
| `update_raw_echemi.py` | 15 tab `_echemi` |
| `update_raw_100ppi.py` | 26 tab `_100ppi` |
| `update_raw_sci99.py` | 6 tab `_sci99` |
| `update_raw_sci99_pdf.py` | 2 tab `_pdf_sci99` |
| `update_raw_cnbg.py` | 2 tab `_cnbg` |
| `verify_all_status.py` | đọc toàn bộ (không ghi) |

## 7. Ghi chú / dị biệt đã biết

- **Trùng giữa 2 sheet** (cố ý giữ cả hai, chưa quyết bỏ): `氯化胆碱_echemi`, `维生素E_sci99`,
  và 3 cặp 棕榈油 (天津 24°, 张家港 24°, 张家港 52°) — cùng diid/pid nhưng khác ppid.
- `甜菜碱_100ppi`: nguồn đổi tên series `甜菜碱BS-0` → `BS-12`, script dùng `NAME_ALIAS`.
- 3 tab 棕榈油 sheet mới đang kẹt 10/22 do hết hạn subscription sci99 (không phải lỗi cấu trúc).
- Nguồn 100ppi đã ngừng đăng: `乙酸` (11/16), `抗氧剂BHT` (11/12), `纽甜` (11/12), `丁酸` (10/29)
  — tab vẫn tồn tại, script chỉ thêm khi nguồn có dòng mới.
- `三甲胺_*_cnbg` script chủ động bỏ qua khi trang nguồn không đổi (stale 10/29 là bình thường).
- Cột K (汇率 USD) là **text** dấu chấm; tab `汇率` là text dấu phẩy. Đừng format thành số/ngày.
