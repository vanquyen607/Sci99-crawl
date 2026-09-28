# -*- coding: utf-8 -*-
"""Fetch daily sources:
- Search sci99 for latest 河南郑州和谐通氨基酸报价动态 → update ARTICLES list in update_amino_from_articles.py
- Fetch 川金诺 articles → mcp_cjj_articles.json
- Fetch prices.sci99 SW table → mcp_sw_price_history.json
"""
import sys, io, re, json, os, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
from urllib.parse import quote
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
COOKIES = os.path.join(HERE, 'sci99_cookies.json')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

def load_cookies(ctx):
    if not os.path.exists(COOKIES):
        print('no cookies file')
        return
    with open(COOKIES, encoding='utf-8') as f:
        cks = json.load(f)
    ctx.add_cookies([{'name': c['name'], 'value': c['value'],
                      'domain': c.get('domain', '.sci99.com'),
                      'path': c.get('path', '/')} for c in cks])
    print(f'loaded {len(cks)} cookies')

def onclick_paths(page, kw, pages=2):
    paths = []
    for pn in range(1, pages + 1):
        url = f'https://www.sci99.com/search.html?keyword={quote(kw)}' + (f'&page={pn}' if pn > 1 else '')
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=35000)
            page.wait_for_timeout(3000)
            found = page.evaluate('''() => {
                const out = [];
                document.querySelectorAll('a[onclick]').forEach(a => {
                    const t = (a.innerText||'').replace(/\\s+/g,' ').trim();
                    const oc = a.getAttribute('onclick')||'';
                    const m = oc.match(/jumpToPath\\(encodeURI\\('([^']+)'\\)\\)/);
                    if (m && t) out.push({t, path: m[1]});
                });
                return out;
            }''')
            for f_ in found:
                if f_['path'] not in [x['path'] for x in paths]:
                    paths.append(f_)
            print(f'  search p{pn}: +{len(found)} total={len(paths)}')
        except Exception as e:
            print(f'  search p{pn} err: {e}')
    return paths

def extract_article(page, url):
    page.goto(url, wait_until='domcontentloaded', timeout=35000)
    page.wait_for_timeout(2500)
    text = page.evaluate('() => document.body.innerText')
    title = page.title()
    return title, text

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, viewport={'width': 1440, 'height': 1000})
        load_cookies(ctx)
        page = ctx.new_page()

        # ---- 1) Amino articles (和谐通) ----
        print('=== fetch amino articles ===')
        amino_paths = onclick_paths(page, '河南郑州和谐通氨基酸报价动态', pages=2)
        amino_paths = [x for x in amino_paths if '和谐通' in x['t']][:12]
        print(f'amino paths: {len(amino_paths)}')
        articles = []
        for item in amino_paths:
            path = item['path'].split('?')[0]
            url = 'https://www.sci99.com' + path
            try:
                title, text = extract_article(page, url)
                m = re.search(r'(20\d{2}-\d{2}-\d{2})', text[:2000])
                date_s = m.group(1) if m else ''
                articles.append({'url': url, 'title': title, 'date': date_s})
                print(f'  {date_s} {url}')
            except Exception as e:
                print(f'  err {url}: {e}')
        # rewrite ARTICLES in update_amino_from_articles.py
        ami_py = os.path.join(HERE, 'update_amino_from_articles.py')
        with open(ami_py, encoding='utf-8') as f:
            src = f.read()
        # build new ARTICLES block (clean URLs — ?keyword= suffix gets 403 from WAF)
        lines = []
        for a in articles:
            lines.append(f"    '{a['url']}',  # {a['date']}")
        new_block = 'ARTICLES = [\n' + '\n'.join(lines) + '\n]'
        src2, n = re.subn(r'ARTICLES = \[.*?\]', new_block, src, count=1, flags=re.S)
        if n:
            with open(ami_py, 'w', encoding='utf-8') as f:
                f.write(src2)
            print(f'updated ARTICLES in update_amino_from_articles.py ({len(articles)} urls)')
        else:
            print('WARN: could not rewrite ARTICLES block')

        # ---- 2) MCP 川金诺 articles ----
        print('=== fetch MCP 川金诺 articles ===')
        cjj_paths = []
        for kw in ['磷酸二氢钙 昆明川金诺', '磷酸二氢钙 川金诺']:
            for x in onclick_paths(page, kw, pages=2):
                if '川金诺' in x['t'] and '磷酸二氢钙' in x['t'] and x['path'] not in [y['path'] for y in cjj_paths]:
                    cjj_paths.append(x)
        cjj_paths = cjj_paths[:20]
        print(f'cjj paths: {len(cjj_paths)}')
        arts = []
        for item in cjj_paths:
            path = item['path'].split('?')[0]
            url = 'https://www.sci99.com' + path
            try:
                title, text = extract_article(page, url)
                m = re.search(r'(20\d{2}-\d{2}-\d{2})', text[:2500])
                date_s = m.group(1) if m else ''
                price_lines = [ln.strip() for ln in text.splitlines()
                               if re.search(r'磷酸二氢钙|川金诺|元/吨|报价|暂不报价', ln)]
                sentences = []
                for m2 in re.finditer(r'磷酸二氢钙', text):
                    i = m2.start()
                    para = text[max(0, i-80): i+400]
                    if re.search(r'\d{3,4}', para):
                        sentences.append(para.replace('\n', ' | ')[:500])
                arts.append({
                    'title': title, 'url': url, 'search_date': item['t'],
                    'date_hint': date_s, 'text': text[:100000],
                    'price_lines': price_lines[:50], 'sentences': sentences[:20],
                    'nums_near': [],
                })
                print(f'  {date_s} {url}')
            except Exception as e:
                print(f'  err {url}: {e}')
        out = os.path.join(HERE, 'mcp_cjj_articles.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({'paths': cjj_paths, 'articles': arts}, f, ensure_ascii=False, indent=2)
        print(f'saved {out} articles={len(arts)}')

        # ---- 3) MCP SW price table ----
        print('=== fetch MCP SW prices table ===')
        sw_url = 'https://prices.sci99.com/cn/product_price.aspx?diid=14507&ppid=12309&cycletype=day'
        try:
            last_err = None
            for att in range(2):
                try:
                    page.goto(sw_url, wait_until='domcontentloaded', timeout=40000)
                    last_err = None
                    break
                except Exception as ge:
                    last_err = ge
                    print(f'SW goto fail #{att + 1}: {ge}')
                    if att == 0:
                        time.sleep(20)
            if last_err:
                raise last_err
            page.wait_for_timeout(5000)
            # wait for price list table
            data = page.evaluate('''() => {
                const tables = [];
                document.querySelectorAll('table').forEach(tb => {
                    const rows = [];
                    tb.querySelectorAll('tr').forEach(tr => {
                        const cells = [];
                        tr.querySelectorAll('th,td').forEach(td => cells.push((td.innerText||'').trim()));
                        if (cells.length) rows.push(cells);
                    });
                    if (rows.length > 3) tables.push(rows);
                });
                const body = document.body.innerText;
                return {tables, body: body.slice(0, 200000)};
            }''')
            # find table with 日期 header
            best = None
            for rows in data['tables']:
                header = ' '.join(rows[0]) if rows else ''
                if '日期' in header and ('最低' in header or '平均' in header or '价格' in header or len(rows[0]) >= 8):
                    best = rows
                    break
            if not best and data['tables']:
                # pick largest
                best = max(data['tables'], key=len)
            print(f'tables found={len(data["tables"])} best_rows={len(best) if best else 0}')
            # parse into same shape as mcp_sw_price_history.json tables[0]
            parsed = []
            if best:
                # normalize header
                header = best[0]
                # try map columns
                def col(*names):
                    for i, h in enumerate(header):
                        for n in names:
                            if n in h:
                                return i
                    return None
                i_date = col('日期') or 1
                i_prod = col('商品名称', '产品') or 2
                i_mkt = col('市场') or 3
                i_spec = col('规格') or 5
                i_dtype = col('数据类型') or 7
                i_min = col('最低') or 8
                i_max = col('最高') or 9
                i_avg = col('平均') or 10
                i_chg = col('涨跌值', '涨跌') or 11
                i_pct = col('涨跌幅', '涨幅') or 12
                i_unit = col('单位') or 13
                i_cond = col('价格条件') or 14
                i_rem = col('备注') or 15
                id_ = col('ID') or 0
                out_rows = [header]
                for r in best[1:]:
                    rr = r + [''] * 20
                    d = rr[i_date] if i_date < len(rr) else ''
                    if not re.search(r'20\d{2}', d or ''):
                        continue
                    def g(i):
                        return rr[i] if i is not None and i < len(rr) else ''
                    out_rows.append([
                        g(id_), g(i_date), g(i_prod), g(i_mkt), '',
                        g(i_spec), '市场价格', g(i_dtype),
                        g(i_min), g(i_max), g(i_avg),
                        g(i_chg), g(i_pct), g(i_unit), g(i_cond), g(i_rem),
                    ])
                parsed = out_rows
                print(f'parsed data rows={len(parsed)-1}')
                if len(parsed) > 1:
                    print(' sample', parsed[1][:13])
            sw_out = {
                'url': sw_url,
                'title': '单曲线',
                'body': data['body'],
                'tables': [{'i': 0, 'rows': parsed or []}],
            }
            outp = os.path.join(HERE, 'mcp_sw_price_history.json')
            with open(outp, 'w', encoding='utf-8') as f:
                json.dump(sw_out, f, ensure_ascii=False, indent=2)
            print(f'saved {outp}')
        except Exception as e:
            print('SW fetch err:', e)
            import traceback; traceback.print_exc()

        browser.close()
    print('FETCH SOURCES DONE')

if __name__ == '__main__':
    main()
