# -*- coding: utf-8 -*-
"""Open 川金诺 article URLs directly and extract prices (legacy helper;
daily path is fetch_daily_sources.py)."""
import sys, io, re, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
from urllib.parse import quote
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIES = os.path.join(ROOT, 'sci99_cookies.json')
OUT = os.path.join(ROOT, 'mcp_cjj_articles.json')

# From search onclick jumpToPath
PATHS = [
    '/info/3_1000008_45653428.html',
    '/info/3_1000008_45643686.html',
    '/info/3_1000008_45632935.html',
    '/info/3_1000008_45622553.html',
    '/info/3_1000008_45610186.html',
]

with open(COOKIES, encoding='utf-8') as f:
    cookies = json.load(f)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA, viewport={'width': 1440, 'height': 1000})
    try:
        ctx.add_cookies([{'name': c['name'], 'value': c['value'],
                          'domain': c.get('domain', '.sci99.com'),
                          'path': c.get('path', '/')} for c in cookies])
    except Exception as e:
        print('ck', e, flush=True)
    page = ctx.new_page()

    # First get ALL onclick paths from search (multiple pages)
    from urllib.parse import quote
    all_paths = []
    for kw in ['磷酸二氢钙 昆明川金诺', '磷酸二氢钙 川金诺', '磷酸二氢钙 报价 云南']:
        for page_n in [1, 2, 3]:
            url = f'https://www.sci99.com/search.html?keyword={quote(kw)}&page={page_n}' if page_n > 1 else f'https://www.sci99.com/search.html?keyword={quote(kw)}'
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=35000)
                page.wait_for_timeout(3500)
                found = page.evaluate('''() => {
                    const out = [];
                    document.querySelectorAll('a[onclick]').forEach(a => {
                        const t = (a.innerText||'').replace(/\\s+/g,' ').trim();
                        const oc = a.getAttribute('onclick')||'';
                        const m = oc.match(/jumpToPath\\(encodeURI\\('([^']+)'\\)\\)/);
                        if (m && t) out.push({t: t.slice(0,120), path: m[1]});
                    });
                    return out;
                }''')
                for f_ in found:
                    if '川金诺' in f_['t'] and '磷酸二氢钙' in f_['t']:
                        if f_['path'] not in [x['path'] for x in all_paths]:
                            all_paths.append(f_)
                print(f'search {kw[:20]} p{page_n}: +{len([f for f in found if "川金诺" in f["t"]])} total_paths={len(all_paths)}', flush=True)
            except Exception as e:
                print(f'search err p{page_n}: {e}', flush=True)

    print(f'\nall 川金诺 paths: {len(all_paths)}', flush=True)
    for x in all_paths:
        print(' ', x['path'], x['t'][:80], flush=True)

    # Open each article
    articles = []
    for item in all_paths[:15]:
        path = item['path'].split('?')[0]
        url = 'https://www.sci99.com' + path
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=35000)
            page.wait_for_timeout(3000)
            title = page.title()
            text = page.evaluate('() => document.body.innerText')
            # extract date from page
            mdate = re.search(r'(20\d{2}-\d{2}-\d{2}|\d{2}/\d{2}/20\d{2})', text[:2000])
            date_s = mdate.group(1) if mdate else ''
            # price-focused extraction
            price_lines = [ln.strip() for ln in text.splitlines()
                           if re.search(r'磷酸二氢钙|川金诺|元/吨|报价|出厂|参考|稳定|暂稳|上调|下调|5300|5400|5[0-9]{3}', ln)]
            focuses = re.findall(r'.{0,150}磷酸二氢钙.{0,400}', text)
            # tighter: sentence containing 磷酸二氢钙 and digits
            sentences = []
            for m in re.finditer(r'磷酸二氢钙', text):
                i = m.start()
                # expand to nearby punctuation
                start = max(0, text.rfind('。', 0, i) + 1, text.rfind('\n', 0, i) + 1)
                end = min(len(text), text.find('。', i) + 1, text.find('\n', i + 1) if text.find('\n', i + 1) > 0 else len(text))
                # also check paragraph
                para = text[max(0, i-100): i+400]
                if re.search(r'\d{3,4}', para):
                    sentences.append(para.replace('\n', ' | ')[:500])

            nums_near = []
            for m in re.finditer(r'(?:磷酸二氢钙|元/吨|报价)', text):
                i = m.start()
                ctxw = text[max(0,i-80): i+300]
                nums = re.findall(r'\d[\d,]{3,}(?:\.\d+)?', ctxw)
                if nums:
                    nums_near.append({'ctx': ctxw.replace('\n',' | ')[:400], 'nums': nums})

            print(f'\n=== {title[:80]} ===', flush=True)
            print(f'url={url} date~{date_s} len={len(text)}', flush=True)
            for s in sentences[:8]:
                print('  SENT', s[:450], flush=True)
            for ln in price_lines[:15]:
                print('  PL', ln[:300], flush=True)

            articles.append({
                'title': title, 'url': url, 'search_date': item['t'],
                'date_hint': date_s, 'text': text[:100000],
                'price_lines': price_lines[:50],
                'sentences': sentences[:20],
                'nums_near': nums_near[:20],
            })
        except Exception as e:
            print(f'err {url}: {e}', flush=True)

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'paths': all_paths, 'articles': articles}, f, ensure_ascii=False, indent=2)
    print(f'\nsaved {OUT} articles={len(articles)}', flush=True)
    browser.close()

# Print compact price summary
print('\n===== PRICE SUMMARY =====', flush=True)
for a in articles:
    print(f"\n* {a['search_date']} | {a['url']}", flush=True)
    # best price sentence
    for s in a['sentences'][:3]:
        if re.search(r'\d{4}', s):
            print('  ', s[:400], flush=True)
