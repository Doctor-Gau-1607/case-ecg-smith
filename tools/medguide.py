#!/usr/bin/env python3
"""medguide.py — dựng một bài web thành trang đọc theo khung MEDGUIDE (có hoặc không dịch).

Hai giai đoạn:
  1) python3 medguide.py trich --src TRANG.html --work W [--chon "div.entry-content"] [--base URL]
       Tách thân bài thành các khối (W/khoi.json), liệt kê ảnh/video gốc cần có (W/media.json),
       và chia phần chữ cần dịch thành các lô W/lo/lo-NNN.json.
  2) python3 medguide.py dung --work W --full THU_MUC_MEDIA_GOC --out OUT --slug ten-bai
       [--dich] [--title "..."] [--nhan "..."] [--nguoi-dich "..."] [--anh-dau]
       Dựng OUT/<slug>.html + OUT/<slug>_anh/ (ảnh + video gốc), rồi tự kiểm.
       --dich: lấy bản dịch từ W/lo/lo-NNN.vi.json (cùng cấu trúc với lo-NNN.json).

Ảnh và video LUÔN lấy từ bản gốc trong --full (zip tải qua Chrome, đã giải nén). Không dùng ảnh
trong thư mục _files của trang lưu Ctrl+S. Thiếu tệp gốc nào là dừng, không dựng.
Tên tệp gốc = đường dẫn URL sau '/uploads/' (hoặc cả path), '/' đổi thành '_' — trùng quy tắc
với đoạn JS tải media qua Chrome.
"""
import re, os, sys, json, html, shutil, argparse, unicodedata
from urllib.parse import urlparse, unquote, urljoin
from bs4 import BeautifulSoup, NavigableString, Comment, Tag


def noi(base, u):
    """urljoin an toàn: link hỏng trong bài gốc (vd href chứa '[' bị hiểu là IPv6) → '' (bỏ link, giữ chữ)."""
    try:
        return urljoin(base, u)
    except ValueError:
        return ''

ap = argparse.ArgumentParser()
sp = ap.add_subparsers(dest='lenh', required=True)
a1 = sp.add_parser('trich')
a1.add_argument('--src', required=True)
a1.add_argument('--work', required=True)
a1.add_argument('--chon', default='')
a1.add_argument('--base', default='')
a1.add_argument('--co-lo', type=int, default=7000, help='số ký tự chữ tối đa mỗi lô dịch')
a2 = sp.add_parser('dung')
a2.add_argument('--work', required=True)
a2.add_argument('--full', required=True)
a2.add_argument('--out', default='out')
a2.add_argument('--slug', required=True)
a2.add_argument('--dich', action='store_true')
a2.add_argument('--title', default='')
a2.add_argument('--nhan', default='')
a2.add_argument('--nguoi-dich', default='')
a2.add_argument('--anh-dau', action='store_true', help='đặt ảnh đại diện (og:image) ở đầu bài, không đánh số')
a2.add_argument('--max-rong', type=int, default=1600)
a2.add_argument('--nen-video', action='store_true', help='nén video sang MP4 H.264 ≤1280×720 (CRF 26, AAC 96k) cho nhẹ repo')
a2.add_argument('--jpeg', action='store_true', help='đổi mọi ảnh tĩnh sang .jpg (q85, rộng tối đa --max-rong) cho nhẹ repo')
a2.add_argument('--khong-dong-nguon', action='store_true', help='không in dòng "Bản dịch tiếng Việt của bài…" ở đầu trang')
a2.add_argument('--ve', default='', help='link quay về mục lục (vd ../index.html)')
a2.add_argument('--ds-media', default='', help='tệp liệt kê tên media có trong zip trên máy người dùng '
                '(unzip -Z1), dùng khi zip quá lớn không kéo hết về container được')
A = ap.parse_args()

IMG_RE = re.compile(r'\.(jpe?g|png|gif|webp|bmp|svg|avif)(\?|#|$)', re.I)
YT_RE = re.compile(r'(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=|shorts/)|youtu\.be/)([\w-]{11})')
JUNK = ['script', 'style', 'noscript', 'form', 'ins', 'button', 'input', 'select', 'textarea', 'nav', 'aside']
JUNK_CLS = re.compile(r'(ftwp-in-post|social-share|sharedaddy|share-list|jp-relatedposts|'
                      r'wpdiscuz|comments|related|yarpp|addtoany|a2a_|post-navigation|'
                      r'author-box|breadcrumb|toc_container|ez-toc|lwptoc|newsletter|advert|promo|cookie)', re.I)
BO_RE = re.compile(r'(enlarg\w*\b.{0,40}\bclick|click\w*\b.{0,40}\benlarg)', re.I)
REF_RE = re.compile(r'^\s*(references?|bibliography|t[àa]i li[ệe]u tham kh[ảa]o|ngu[ồo]n tham kh[ảa]o|literature)\b', re.I)

def url_name(u):
    p = unquote(urlparse(u).path)
    p = p.split('/uploads/', 1)[1] if '/uploads/' in p else p.lstrip('/')
    n = re.sub(r'[\\/:*?"<>|]+', '_', p)
    if len(n.encode('utf-8')) > 120:          # tên quá dài (Blogger): rút gọn + băm để không trùng
        import hashlib
        goc, duoi = os.path.splitext(n)
        cuoi = re.sub(r'[^A-Za-z0-9._-]+', '-', p.rsplit('/', 1)[-1].rsplit('.', 1)[0])[:60].strip('-')
        n = f"{cuoi}-{hashlib.sha1(p.encode('utf-8')).hexdigest()[:12]}{duoi[:6]}"
    return n

def slugify(s):
    s = unicodedata.normalize('NFD', s.replace('đ', 'd').replace('Đ', 'D'))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')

def txt_norm(s):
    return re.sub(r'\s+', '', s).replace('\xa0', '')

# =====================================================================================
#  GIAI ĐOẠN 1: TÁCH KHỐI
# =====================================================================================
def trich():
    raw = open(A.src, encoding='utf-8', errors='replace').read()
    soup = BeautifulSoup(raw, 'lxml')
    m = re.search(r'saved from url=\(\d+\)(\S+?)\s*-->', raw[:5000])
    link = soup.find('link', rel='canonical')
    base = A.base or (m.group(1) if m else '') or (link.get('href') if link else '')
    if not base.startswith('http'):
        print('CẢNH BÁO: không biết URL gốc của trang; hãy thêm --base URL để đổi link tương đối thành tuyệt đối')
    def ab(u):
        # Ctrl+S đổi link ảnh thành bản sao cục bộ "./X_files/..." — không phải ảnh gốc, bỏ qua
        if not u or u.startswith(('data:', 'file:', 'blob:', './')) or '_files/' in u:
            return ''
        return noi(base, u)

    sels = [A.chon] if A.chon else ['div.entry-content', 'div.post-content', 'div.td-post-content',
                                    'div.article-content', 'article', 'main', 'body']
    body = None
    for s in sels:
        el = soup.select_one(s)
        if el and len(el.get_text(strip=True)) > 200:
            body = el; break
    if body is None:
        # bài ngắn (thông báo bài giảng, video nhúng…): chấp nhận vùng thân bài riêng nếu có chữ hoặc media
        for s in sels:
            if s in ('article', 'main', 'body'):
                continue
            el = soup.select_one(s)
            if el and (el.get_text(strip=True) or el.find(['img', 'iframe', 'video', 'audio', 'embed', 'object'])):
                body = el; break
    if body is None:
        sys.exit('Không tìm thấy phần thân bài; hãy chỉ định --chon "<css selector>"')

    for c in body.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for t in body.find_all(JUNK):
        t.decompose()
    for t in body.find_all(True):
        if getattr(t, 'decomposed', False) or t.name in ('html', 'body'):
            continue
        cl = ' '.join(t.get('class', []) or []) + ' ' + (t.get('id') or '')
        if JUNK_CLS.search(cl):
            t.decompose()
    for t in body.find_all(['video', 'audio', 'iframe', 'object']):   # chữ dự phòng trong thẻ media
        for s in t.find_all(string=True):
            s.extract()

    og_t = soup.find('meta', property='og:title')
    h1 = soup.select_one('h1.entry-title') or soup.select_one('h1.cs-entry__title') or soup.select_one('.post-title.entry-title') or soup.find('h1')
    tieu_de = (h1.get_text(' ', strip=True) if h1 else '') or \
        re.split(r'\s[|–—]\s', (og_t['content'] if og_t else '') or soup.title.get_text())[0].strip()
    for h in body.find_all('h1'):          # tiêu đề bài nằm trong vùng thân bài thì bỏ khỏi thân
        if h.get_text(' ', strip=True) == tieu_de:
            h.decompose()
    site = soup.find('meta', property='og:site_name')
    ogi = soup.find('meta', property='og:image')

    def largest_srcset(img, attr='srcset'):
        best, bw = None, -1
        for part in (img.get(attr) or '').split(','):
            bits = part.strip().split()
            if not bits:
                continue
            w = bits[1] if len(bits) > 1 else '1w'
            try:
                n = float(re.sub(r'[^\d.]', '', w) or 0) * (1 if w.endswith('w') else 1000)
            except ValueError:
                n = 0
            u = ab(bits[0])
            if n > bw and u and u.startswith('http'):
                best, bw = u, n
        return best

    def lon_blogger(u):
        if not u or not re.search(r'(blogger\.googleusercontent\.com|bp\.blogspot\.com)', u):
            return u
        u2 = re.sub(r'/(s\d+|w\d+(-h\d+)?)(-[a-z0-9-]+)?/([^/]+)$', r'/s1600/\4', u)
        u2 = re.sub(r'=(s\d+|w\d+(-h\d+)?)(-[a-z0-9-]+)?$', '=s1600', u2)
        return u2

    def lon_wp(u):
        # WordPress: 'anh-1024x451.png' -> 'anh.png' (bản gốc tải lên); URL cũ giữ làm dự phòng
        if not u or '/wp-content/uploads/' not in u:
            return u
        u2 = re.sub(r'-\d+x\d+(\.[A-Za-z0-9]+)$', r'\1', u)
        if u2 != u:
            du_phong[url_name(u2)] = u
        return u2

    def goc_anh(img):
        return lon_wp(lon_blogger(goc_anh0(img)))

    def goc_anh0(img):
        a = img.find_parent('a')
        if a and a.get('href') and IMG_RE.search(a['href']) and ab(a['href']).startswith('http'):
            return ab(a['href'])
        for k in ('data-orig-file', 'data-large-file', 'data-full-url', 'data-lazy-src', 'data-src'):
            if img.get(k) and ab(img[k]).startswith('http'):
                return ab(img[k])
        u = largest_srcset(img) or largest_srcset(img, 'data-srcset')
        if u:
            return u
        s = ab(img.get('src') or '')
        return s if s.startswith('http') else None

    media = {}          # name -> url
    du_phong = {}       # name -> URL dự phòng khi bản gốc không còn
    thieu_url = []
    def ghi_anh(img):
        u = goc_anh(img)
        if not u:
            thieu_url.append(str(img)[:120]); return None
        n = url_name(u); media[n] = u
        return {'name': n, 'alt': (img.get('alt') or '').replace('\xa0', ' ').strip()}

    ROMAN = re.compile(r'^\s*[IVXLC]+\s*[.)]', re.I)
    ARAB = re.compile(r'^\s*\d+\s*[.)]')
    HS = body.find_all(re.compile(r'^h[1-6]$'))
    tags = sorted({h.name for h in HS})
    lv = {t: min(6, i + 2) for i, t in enumerate(tags)}
    tach_so = False
    if tags:
        top = [h.get_text(' ', strip=True) for h in HS if h.name == tags[0]]
        if any(ROMAN.match(x) for x in top) and any(ARAB.match(x) for x in top):
            tach_so = True
            lv = {t: min(6, i + 3) for i, t in enumerate(tags)}
            lv[tags[0]] = 2
    def cap(h, text):
        if tach_so and h.name == tags[0] and not ROMAN.match(text):
            return 3 if ARAB.match(text) else 2
        return lv[h.name]

    GIU = {'strong', 'b', 'em', 'i', 'u', 'br', 'sup', 'sub', 's', 'del', 'code', 'mark', 'small'}
    LIST = {'ul', 'ol', 'li'}
    TABLE = {'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption', 'colgroup', 'col'}

    def lop_mau(style):
        mm = re.search(r'(?<![-\w])color:\s*(#[0-9a-fA-F]{3,6}|rgb\([^)]*\)|[a-z]+)', style or '')
        if not mm:
            return None, None
        v = mm.group(1).lower()
        named = {'blue': '#0000ff', 'red': '#ff0000', 'green': '#008000', 'black': '#000000',
                 'navy': '#000080', 'darkred': '#8b0000', 'orange': '#ffa500', 'purple': '#800080'}
        v = named.get(v, v)
        if v.startswith('rgb'):
            n = [int(x) for x in re.findall(r'\d+', v)[:3]]
        elif v.startswith('#'):
            hx = v[1:]
            if len(hx) == 3:
                hx = ''.join(c * 2 for c in hx)
            if not re.match(r'[0-9a-f]{6}', hx):
                return None, None
            n = [int(hx[i:i + 2], 16) for i in (0, 2, 4)]
        else:
            return None, None
        if len(n) < 3:      # màu viết sai (vd "#", "rgb()") → coi như không có màu
            return None, None
        r, g, b = n
        if max(n) - min(n) < 40:
            return None, None
        if b >= r and b >= g:
            return 'c-xanh', None
        if r >= g and r >= b and g < 170:
            return 'c-do', None
        if g >= r and g >= b:
            return 'c-luc', None
        return None, f'#{r:02x}{g:02x}{b:02x}'

    def clean(node, extra=()):
        keep = GIU | set(extra)
        for t in list(node.find_all(True)):
            wpc = [x for x in re.findall(r'has-([a-z0-9-]+)-color', ' '.join(t.get('class', []) or []))
                   if x not in ('inline', 'text') and 'background' not in x] if t.name in ('mark', 'span') else []
            if wpc:
                m_ = wpc[0]
                t.name = 'span'
                t.attrs = {'class': 'c-do' if re.search(r'red|orange|pink', m_) else 'c-xanh' if re.search(r'blue|cyan', m_)
                           else 'c-luc' if 'green' in m_ else 'c-nhat'}
                continue
            if t.name in keep:
                at = {}
                for k in ('colspan', 'rowspan'):
                    if t.get(k):
                        at[k] = t[k]
                if t.name in ('td', 'th'):
                    bg = re.search(r'background(?:-color)?:\s*(#[0-9a-fA-F]{3,6}|rgb\([^)]*\))', t.get('style', ''))
                    if bg:
                        at['style'] = f'background:{bg.group(1)}'
                if t.name == 'ol' and t.get('start'):
                    at['start'] = t['start']
                t.attrs = at
            elif t.name in ('span', 'font'):
                cls, keepc = lop_mau(t.get('style', '') or ('color:' + t['color'] if t.get('color') else ''))
                if cls:
                    t.name = 'span'; t.attrs = {'class': cls}
                elif keepc:
                    t.name = 'span'; t.attrs = {'style': f'color:{keepc}'}
                else:
                    t.unwrap()
            elif t.name == 'a':
                href = noi(base, t.get('href', '') or '') if (t.get('href') or '').strip() else ''
                if href.startswith('http') and not IMG_RE.search(href):
                    t.attrs = {'href': href, 'target': '_blank', 'rel': 'noopener'}
                else:
                    t.unwrap()
            else:
                t.unwrap()
        s = node.decode_contents()
        s = re.sub(r'\s*<br/?>\s*', '<br>', s)
        s = '<br>'.join(seg for seg in s.split('<br>')
                        if not (BO_RE.search(re.sub(r'<[^>]+>', '', seg)) and len(re.sub(r'<[^>]+>', '', seg)) < 160))
        s = re.sub(r'^(\s|<br>)+|(\s|<br>)+$', '', s)
        return s.replace('\xa0', ' ')

    K = []
    def them(**kw):
        kw['id'] = len(K) + 1; K.append(kw); return kw

    def la_gallery(el):
        cl = ' '.join(el.get('class', []) or [])
        return bool(re.search(r'(^|\s)(gallery|wp-block-gallery|blocks-gallery-grid|tiled-gallery|ngg-galleryoverview)(\s|$)', cl))

    def anh_rieng(el, caption=None):
        for img in el.find_all('img'):
            x = ghi_anh(img)
            if x:
                them(loai='fig', anh=[x], cap=caption)
                caption = None
            a = img.find_parent('a')
            (a if a and a in el.descendants else img).extract()

    def media_nhung(c, caption=None):
        n = c.name
        if n == 'iframe':
            src = ab(c.get('src') or c.get('data-src') or c.get('data-lazy-src') or '')
            if src.startswith('//'):
                src = 'https:' + src
            y = YT_RE.search(src)
            if y:
                them(loai='yt', vid=y.group(1), cap=caption)
            elif src.startswith('http'):
                them(loai='iframe', src=src, cap=caption)
        elif n == 'video':
            s = c.get('src') or (c.find('source') or {}).get('src') or c.get('data-src')
            s = ab(s) if s else ''
            if s.startswith('http'):
                nm = url_name(s); media[nm] = s
                po = ab(c.get('poster')) if c.get('poster') else ''
                pn = None
                if po and po.startswith('http'):
                    pn = url_name(po); media[pn] = po
                them(loai='video', name=nm, poster=pn, cap=caption)
            else:
                thieu_url.append('video không có src: ' + str(c)[:100])

    INLINE = {'b', 'strong', 'i', 'em', 'u', 'span', 'a', 'font', 'sup', 'sub', 'small', 'mark', 's', 'del', 'code'}
    BLOCKY = ['p', 'div', 'ul', 'ol', 'table', 'img', 'iframe', 'video', 'figure', 'blockquote',
              'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br']
    def la_inline(c):
        if isinstance(c, NavigableString):
            return True
        return isinstance(c, Tag) and c.name in INLINE and not c.find(BLOCKY)
    def walk(el):
        buf = []
        def xa():
            if not buf:
                return
            w = soup.new_tag('p')
            for x in buf:
                w.append(x.extract())
            buf.clear()
            t = clean(w)
            if re.sub(r'<[^>]+>|\s', '', t):
                them(loai='p', tag='p', html=t.strip())
        for c in list(el.children):
            if la_inline(c):
                buf.append(c); continue
            if isinstance(c, Tag) and c.name == 'br':
                xa(); continue
            xa()
            if not isinstance(c, Tag):
                continue
            n = c.name
            cl = ' '.join(c.get('class', []) or [])
            if n == 'table' and 'tr-caption-container' in cl:
                ct = c.find(class_='tr-caption')
                capt = clean(ct) if ct else None
                if ct:
                    ct.extract()
                anh_rieng(c, capt)
                continue
            if re.match(r'^h[1-6]$', n):
                text = re.sub(r'\s+', ' ', c.get_text().replace('\xa0', ' ')).strip()
                if not text:
                    continue
                anh_rieng(c)
                them(loai='h', cap_do=cap(c, text), html=html.escape(text))
            elif la_gallery(c):
                items = [x for x in (ghi_anh(i) for i in c.find_all('img')) if x]
                mm = re.search(r'(?:gallery-)?columns-(\d)', cl)
                caps = [t for t in (clean(fc) for fc in c.find_all('figcaption')) if t]
                them(loai='gal', cot=min(max(int(mm.group(1)) if mm else 3, 1), 6), anh=items, caps=caps)
            elif n == 'figure':
                fc = c.find('figcaption')
                capt = clean(fc) if fc else None
                if fc:
                    fc.extract()
                if c.find('table'):
                    if capt:
                        them(loai='p', tag='p', lop='chu-thich-float', html=capt)
                    walk(c)
                elif c.find(['iframe', 'video']):
                    for mtag in c.find_all(['iframe', 'video']):
                        media_nhung(mtag, capt); capt = None
                    if capt:
                        them(loai='p', tag='p', lop='chu-thich-anh', html=capt)
                else:
                    anh_rieng(c, capt)
                    rest = clean(c)
                    if re.sub(r'<br>|\s', '', rest):
                        them(loai='p', tag='p', html=rest)
            elif n in ('iframe', 'video'):
                media_nhung(c)
            elif n in ('p', 'blockquote', 'pre', 'address', 'dd', 'dt') or (n == 'div' and not c.find(
                    ['p', 'div', 'figure', 'table', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                     'iframe', 'video', 'blockquote']) and 'alert' not in cl):
                if c.find(['iframe', 'video']):
                    for mtag in c.find_all(['iframe', 'video']):
                        media_nhung(mtag); mtag.extract()
                if c.find('img'):
                    anh_rieng(c)
                t = clean(c)
                if re.sub(r'<[^>]+>|\s', '', t):
                    them(loai='p', tag='blockquote' if n == 'blockquote' else 'p', html=t)
            elif n in ('ul', 'ol'):
                if c.find(['iframe', 'video']):
                    for mtag in c.find_all(['iframe', 'video']):
                        media_nhung(mtag); mtag.extract()
                if c.find('img'):
                    anh_rieng(c)
                t = clean(c, LIST)
                if re.sub(r'<[^>]+>|\s', '', t):
                    them(loai='list', tag=n, start=c.get('start'), html=t)
            elif n == 'table':
                if c.find('img'):
                    anh_rieng(c)
                them(loai='table', html=clean(c, TABLE | LIST))
            elif n == 'img':
                x = ghi_anh(c)
                if x:
                    them(loai='fig', anh=[x], cap=None)
            elif n == 'hr':
                them(loai='hr')
            elif 'alert' in cl or 'notice' in cl:
                t = re.sub(r'\s+', ' ', c.get_text(' ', strip=True))
                if t:
                    them(loai='note', html=html.escape(t))
            else:
                walk(c)
        xa()

    goc_text = txt_norm(body.get_text(''))
    n_img = len(body.find_all('img'))
    walk(body)

    # đánh dấu khối thuộc mục Tài liệu tham khảo (giữ nguyên tiếng gốc, không đưa đi dịch)
    trong_tk, cap_tk = False, 9
    for k in K:
        if k['loai'] == 'h':
            t = html.unescape(k['html'])
            if REF_RE.match(t):
                trong_tk, cap_tk = True, k['cap_do']; continue
            if trong_tk and k['cap_do'] <= cap_tk:
                trong_tk = False
        if trong_tk:
            k['tk'] = True

    hero = None
    if ogi and ogi.get('content'):
        u = lon_wp(lon_blogger(ab(ogi['content'])))
        if u.startswith('http'):
            hero = url_name(u); media[hero] = u

    os.makedirs(os.path.join(A.work, 'lo'), exist_ok=True)
    json.dump(K, open(os.path.join(A.work, 'khoi.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump([dict({'name': k, 'url': v}, **({'du_phong': du_phong[k]} if k in du_phong else {})) for k, v in media.items()],
              open(os.path.join(A.work, 'media.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    meta = {'url': base, 'tieu_de': tieu_de, 'site': site['content'] if site else urlparse(base).netloc,
            'goc_text': goc_text, 'n_img': n_img, 'hero': hero}
    json.dump(meta, open(os.path.join(A.work, 'meta.json'), 'w', encoding='utf-8'), ensure_ascii=False)

    # các lô dịch: chỉ phần chữ; khối Tài liệu tham khảo không đưa vào
    for f in os.listdir(os.path.join(A.work, 'lo')):
        if re.match(r'lo-\d+\.json$', f):
            os.remove(os.path.join(A.work, 'lo', f))
    lo, cur, dem, so = [], [], 0, 0
    def dong_lo():
        nonlocal cur, dem, so
        if cur:
            so += 1
            json.dump(cur, open(os.path.join(A.work, 'lo', f'lo-{so:03d}.json'), 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)
        cur, dem = [], 0
    for k in K:
        if k.get('tk'):
            continue
        e = {'id': k['id']}
        if k.get('html') and k['loai'] != 'hr':
            e['html'] = k['html']
        if k.get('cap'):
            e['cap'] = k['cap']
        if k.get('caps'):
            e['caps'] = k['caps']
        alts = [x['alt'] for x in k.get('anh', [])]
        if any(alts):
            e['alts'] = alts
        if len(e) == 1:
            continue
        n = len(json.dumps(e, ensure_ascii=False))
        if dem + n > A.co_lo and cur:
            dong_lo()
        cur.append(e); dem += n
    dong_lo()

    from collections import Counter
    c = Counter(k['loai'] for k in K)
    print(f'Tiêu đề: {tieu_de}\nURL gốc: {base}')
    print(f'Khối: {len(K)}  ' + ', '.join(f'{a}={b}' for a, b in c.most_common()))
    print(f'Media gốc cần có: {len(media)} tệp khác nhau (ảnh {sum(1 for k in K for _ in k.get("anh", []))} vị trí'
          f' / {n_img} <img> trong bản gốc; video tệp {c["video"]}; YouTube {c["yt"]}; iframe khác {c["iframe"]})')
    print(f'Lô dịch: {so} tệp trong {A.work}/lo/  (khối Tài liệu tham khảo giữ nguyên: {sum(1 for k in K if k.get("tk"))})')
    if thieu_url:
        print(f'CẢNH BÁO: {len(thieu_url)} ảnh/video không xác định được URL gốc:')
        for x in thieu_url[:10]:
            print('  ', x)

# =====================================================================================
#  GIAI ĐOẠN 2: DỰNG TRANG
# =====================================================================================
CSS = r''':root{
 --nen:#f2f4f6; --giay:#ffffff; --chu:#172033; --nhat:#5b6675; --vien:#e3e7ec;
 --do:#b30000; --xanh:#004b87; --diu:#f6f8fa; --danh:#fff3cd;
}
:root[data-nen="toi"]{
 --nen:#12151b; --giay:#1b2029; --chu:#e6eaf0; --nhat:#9aa5b4; --vien:#2c333f;
 --do:#ff8a8a; --xanh:#7fb6e6; --diu:#232a35; --danh:#5a4a12;
}
*{box-sizing:border-box}
html{font-size:var(--co,16px)}
body{margin:0;background:var(--nen);color:var(--chu);
 font-family:"Noto Sans","Segoe UI",Roboto,Arial,sans-serif;
 font-size:1rem;line-height:1.7;-webkit-text-size-adjust:100%}
a{color:var(--xanh)}
.bo-cuc{display:grid;grid-template-columns:320px minmax(0,1fr);gap:22px;
 max-width:1500px;margin:0 auto;padding:22px}
/* ---- cột mục lục ---- */
.muc-luc{position:sticky;top:22px;align-self:start;height:calc(100vh - 44px);
 background:var(--giay);border-radius:16px;padding:16px 10px;display:flex;
 flex-direction:column;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.ml-dau{display:flex;justify-content:space-between;align-items:center;
 padding:2px 10px 10px;font-size:.78rem;font-weight:800;letter-spacing:.09em;
 color:var(--do);border-bottom:1px solid var(--vien)}
#phanTram{color:var(--nhat)}
/* Thu gọn / mở lại cột mục lục. Trang nhớ lựa chọn, vì người đọc guideline
   mở lại nhiều lần và không muốn mỗi lần lại phải thu tay. */
.ml-dau .nut-thu{margin-left:8px;border:1px solid var(--vien);background:var(--giay);
 color:var(--chu);border-radius:7px;padding:1px 8px;cursor:pointer;font:inherit;
 font-size:.9rem;line-height:1.4}
@media(min-width:981px){
 :root[data-ml="thu"] .bo-cuc{grid-template-columns:minmax(0,1fr)}
 :root[data-ml="thu"] .muc-luc{display:none}
 :root[data-ml="thu"] .hien-ml{display:block}
}
.o-tim{padding:10px 8px 6px}
.o-tim input{width:100%;padding:8px 10px;border:1px solid var(--vien);
 border-radius:9px;background:var(--diu);color:var(--chu);font:inherit;font-size:.85rem}
.tim-dieu-khien{display:flex;gap:6px;align-items:center;margin-top:6px;
 font-size:.76rem;color:var(--nhat)}
.tim-dieu-khien button{border:1px solid var(--vien);background:var(--giay);
 color:var(--chu);border-radius:7px;padding:2px 9px;cursor:pointer;font:inherit}
.ml-cuon{overflow-y:auto;flex:1;margin-top:4px}
#dsMuc{list-style:none;margin:0;padding:0}
#dsMuc a{display:block;padding:7px 12px;border-radius:9px;text-decoration:none;
 color:var(--chu);font-size:.87rem;line-height:1.4}
#dsMuc a:hover{background:var(--diu)}
#dsMuc a.dang-doc{background:var(--diu);color:var(--do);font-weight:700;
 box-shadow:inset 3px 0 0 var(--do)}
#dsMuc .cap-1>a{font-weight:700}
#dsMuc .cap-2>a{padding-left:26px;font-size:.85rem}
#dsMuc .cap-3>a{padding-left:40px;font-size:.82rem;color:var(--nhat)}
#dsMuc .cap-4>a,#dsMuc .cap-5>a{padding-left:54px;font-size:.8rem;color:var(--nhat)}
/* ---- thân bài ---- */
.dau-bai,.to-giay{background:var(--giay);border-radius:16px;
 box-shadow:0 1px 3px rgba(0,0,0,.06)}
.dau-bai{padding:28px 34px;margin-bottom:22px}
.nhan{font-size:.76rem;font-weight:800;letter-spacing:.16em;color:var(--nhat)}
.dau-bai h1{margin:.25em 0 .35em;font-size:2rem;line-height:1.25;color:var(--do)}
.dich-gia{color:var(--nhat);font-size:.92rem;margin:0}
.dich-gia b{color:var(--xanh)}
.to-giay{padding:34px 40px 60px}
.to-giay h2{color:var(--do);font-size:1.65rem;margin:1.7em 0 .5em;
 padding-bottom:4px;border-bottom:2px solid var(--vien)}
.to-giay h2:first-child{margin-top:0}
.to-giay h3{color:var(--xanh);font-size:1.3rem;margin:1.5em 0 .4em}
.to-giay h4{font-size:1.08rem;margin:1.3em 0 .3em}
.to-giay h5,.to-giay h6{font-size:1rem;margin:1.2em 0 .3em;color:var(--nhat)}
.to-giay p{margin:0 0 .85em;text-align:justify}
.to-giay p.cham{padding-left:1.35em;text-indent:-1.1em;text-align:left}
figure{margin:1.4em 0;text-align:center}
figure img{max-width:100%;height:auto;border:1px solid var(--vien);border-radius:10px}
/* ---- bảng ---- */
.tham-chieu{color:var(--xanh);font-weight:600;text-decoration:none;
 border-bottom:1px dotted currentColor}
.tham-chieu:hover{border-bottom-style:solid}
.chu-thich-float{font-weight:600;margin:0 0 .4em}
.khung-bang{overflow-x:auto;margin:1.4em 0;border-radius:10px;
 border:1px solid var(--vien)}
.khung-bang table{border-collapse:collapse;width:100%;font-size:.88rem;
 table-layout:fixed}
.to-giay p,.to-giay li,.to-giay dd{overflow-wrap:break-word}
.to-giay sup{overflow-wrap:anywhere}
.khung-bang td{border:1px solid var(--vien);padding:9px 11px;vertical-align:top;
 line-height:1.5;word-wrap:break-word}
.khung-bang td.sat{padding-left:0;padding-right:0}
.khung-bang td.giua{text-align:center;vertical-align:middle}
.khung-bang td.ky-hieu{font-weight:800;white-space:nowrap}
.khung-bang td.nen-toi,.khung-bang td.nen-toi *{color:#fff}
.khung-bang td.nen-sang,.khung-bang td.nen-sang *{color:#12151b}
.khung-bang td span{display:block}
.khung-bang td span.cham{padding-left:1.1em;text-indent:-1em}
mark.danh{background:var(--danh);color:inherit;border-radius:3px}
/* Ô có màu ép màu chữ cho cả con cháu, kể cả <mark> của phần tìm trong bài — chữ
   trắng trên nền vàng nhạt là tìm thấy mà không nhìn thấy. Trả chữ về màu trang. */
.khung-bang td.nen-toi mark.danh,.khung-bang td.nen-sang mark.danh,
.khung-bang td.nen-toi mark.danh *,.khung-bang td.nen-sang mark.danh *{color:var(--chu)}
mark.danh.dang{outline:2px solid var(--do)}
/* ---- nút nổi ---- */
.thanh-nut{position:fixed;right:18px;bottom:18px;display:flex;gap:8px;z-index:9}
.thanh-nut button{width:42px;height:42px;border-radius:50%;cursor:pointer;
 border:1px solid var(--vien);background:var(--giay);color:var(--chu);
 font-size:1rem;font-weight:700;box-shadow:0 2px 8px rgba(0,0,0,.14)}
.hien-ml{display:none}
/* ---- màn hình hẹp ---- */
@media(max-width:980px){
 .bo-cuc{grid-template-columns:minmax(0,1fr);padding:12px}
 .muc-luc{position:fixed;inset:0 auto 0 0;width:88%;max-width:340px;z-index:20;
  border-radius:0;height:100vh;transform:translateX(-102%);transition:transform .2s}
 .muc-luc.mo{transform:none}
 .hien-ml{display:block}
 .to-giay{padding:22px 18px 44px}
 /* Màn hình điện thoại: giữ bề rộng tối thiểu cho bảng rồi cho cuộn ngang,
    thay vì bóp cột hẹp tới mức "Trung bình" xuống dòng thành "Tr un g bì nh". */
 .khung-bang table{min-width:620px}
 .dau-bai{padding:20px}
 .dau-bai h1{font-size:1.5rem}
}
/* ---- in ra giấy ---- */
@media print{
 /* Nền tối được nhớ trong localStorage: bật một lần là mọi lần in sau đều dính.
    Giấy luôn trắng, nên trả bảng màu về bản sáng trước khi in — nếu không, chữ
    #e6eaf0 in lên giấy trắng là mất hẳn. */
 :root,:root[data-nen="toi"]{--nen:#fff;--giay:#fff;--chu:#172033;--nhat:#4a5462;
  --vien:#c9ced5;--do:#b30000;--xanh:#004b87;--diu:#f6f8fa;--danh:#fff3cd}
 body{background:#fff;font-size:11.5pt}
 .muc-luc,.thanh-nut{display:none!important}
 .bo-cuc{display:block;max-width:none;padding:0}
 .dau-bai,.to-giay{box-shadow:none;border-radius:0;padding:0}
 .to-giay h2,.to-giay h3{break-after:avoid}
 .khung-bang,figure{break-inside:avoid}
 .khung-bang td{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}'''
EXTRA_CSS = r'''
.c-xanh{color:var(--xanh)} .c-do{color:var(--do)} .c-luc{color:var(--luc)} .c-nhat{color:var(--nhat)}
:root{--luc:#1d7a3a} :root[data-nen="toi"]{--luc:#7fd49a}
.ban-quyen{display:inline-block;margin:.4em 0 1.2em!important;padding:6px 14px;border-radius:9px;
 background:var(--diu);border:1px solid var(--vien);color:var(--nhat);font-size:.88rem}
.note{background:var(--diu);border-left:4px solid var(--xanh);border-radius:0 10px 10px 0;padding:10px 16px;margin:1.1em 0}
.note p:last-child{margin-bottom:0}
.canh-bao{background:#fff4d6;border:1px solid #e8c97a;color:#4a3a10;border-radius:10px;padding:12px 16px;margin:0 0 18px;font-size:.93em}
:root[data-nen="toi"] .canh-bao{background:#3a2f12;border-color:#6b5a1a;color:#f0e2bd}
.to-giay blockquote{margin:1em 0;padding:.6em 1em;border-left:4px solid var(--vien);background:var(--diu);border-radius:0 10px 10px 0}
.to-giay ul,.to-giay ol{padding-left:1.5em;margin:0 0 .9em}
.to-giay li{margin:.2em 0}
.to-giay hr{border:0;border-top:1px solid var(--vien);margin:1.6em 0}
.khung-bang th{border:1px solid var(--vien);padding:9px 11px;vertical-align:top;background:var(--diu);text-align:left;line-height:1.5}
.khung-bang td[style*="background"],.khung-bang th[style*="background"]{color:#12151b}
.tk p,.tk li{font-size:.9em;color:var(--nhat);text-align:left}
figcaption,.chu-thich-anh{font-size:.88rem;color:var(--nhat);margin-top:.45em;text-align:center;line-height:1.55}
figcaption b{color:var(--chu)}
figure.anh-dau img{width:100%;max-height:420px;object-fit:cover}
figure video{width:100%;max-height:78vh;background:#000;border-radius:10px;display:block}
.khung-video{position:relative;padding-top:56.25%;margin:0;border-radius:10px;overflow:hidden;background:#000}
.khung-video iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
.yt{position:relative;width:100%;aspect-ratio:16/9;background:#000;cursor:pointer;display:block;border-radius:10px;overflow:hidden}
.yt img{width:100%;height:100%;object-fit:cover;display:block;opacity:.86;border:0!important;border-radius:0!important;transition:opacity .2s}
.yt:hover img{opacity:1}
.yt .play{position:absolute;inset:0;display:grid;place-items:center;pointer-events:none}
.yt .play svg{width:58px;height:58px;filter:drop-shadow(0 2px 8px rgba(0,0,0,.5))}
.yt iframe{width:100%;height:100%;border:0;display:block}
.badge{position:absolute;left:8px;top:8px;background:rgba(0,0,0,.72);color:#fff;font-size:11.5px;padding:2px 8px;border-radius:20px;pointer-events:none}
.ytlink{display:inline-block;margin-left:8px;font-size:.92em;color:var(--xanh);text-decoration:none;border:1px solid var(--vien);border-radius:20px;padding:1px 10px;white-space:nowrap}
.bo-anh{display:grid;gap:8px;margin:1em 0 1.4em;align-items:start}
.bo-anh.cot-1{grid-template-columns:repeat(1,minmax(0,1fr))}
.bo-anh.cot-2{grid-template-columns:repeat(2,minmax(0,1fr))}
.bo-anh.cot-3{grid-template-columns:repeat(3,minmax(0,1fr))}
.bo-anh.cot-4{grid-template-columns:repeat(4,minmax(0,1fr))}
.bo-anh.cot-5{grid-template-columns:repeat(5,minmax(0,1fr))}
.bo-anh.cot-6{grid-template-columns:repeat(6,minmax(0,1fr))}
.o-anh{display:block;border-radius:8px;overflow:hidden;background:#000;
 border:1px solid var(--vien);cursor:zoom-in;line-height:0}
.o-anh img{display:block;width:100%;height:auto}
figure .o-anh{display:inline-block;background:none;border:0}
figure .o-anh img{border:1px solid var(--vien);border-radius:10px}
@media(max-width:980px){
 .bo-anh.cot-3,.bo-anh.cot-4,.bo-anh.cot-5,.bo-anh.cot-6{grid-template-columns:repeat(3,minmax(0,1fr))}
}
@media(max-width:560px){
 .bo-anh.cot-3,.bo-anh.cot-4,.bo-anh.cot-5,.bo-anh.cot-6{grid-template-columns:repeat(2,minmax(0,1fr))}
}
.xem-anh{position:fixed;inset:0;z-index:50;background:rgba(8,10,14,.94);display:none;
 flex-direction:column;align-items:center;justify-content:center;padding:14px}
.xem-anh.mo{display:flex}
.xem-anh img{max-width:100%;max-height:calc(100vh - 110px);object-fit:contain;border-radius:6px;background:#000}
.xem-anh .xa-chu{color:#dfe5ec;font-size:.85rem;max-width:1100px;margin-top:10px;text-align:center;
 line-height:1.5;max-height:5.2em;overflow:auto}
.xem-anh .xa-dem{position:absolute;top:14px;left:18px;color:#c4ccd6;font-size:.85rem}
.xem-anh button{position:absolute;border:0;background:rgba(255,255,255,.12);color:#fff;
 width:46px;height:46px;border-radius:50%;font-size:1.3rem;cursor:pointer}
.xem-anh button:hover{background:rgba(255,255,255,.25)}
.xem-anh .xa-dong{top:12px;right:14px}
.xem-anh .xa-truoc{left:14px;top:50%;transform:translateY(-50%)}
.xem-anh .xa-sau{right:14px;top:50%;transform:translateY(-50%)}
@media print{
 .xem-anh,.canh-bao,.ytlink{display:none!important}
 .bo-anh{break-inside:avoid}
 .o-anh{background:none}
}
'''
JS = r'''(function(){
 var goc=document.documentElement, ds=document.getElementById('dsMuc'),
     giay=document.getElementById('toGiay'), pt=document.getElementById('phanTram'),
     ml=document.getElementById('mucLuc');
 var dau=[].slice.call(giay.querySelectorAll('h2,h3,h4,h5,h6'));

 // mục lục
 dau.forEach(function(h){
  var li=document.createElement('li');
  li.className='cap-'+(+h.tagName[1]-1);
  var a=document.createElement('a');
  a.href='#'+h.id; a.textContent=h.textContent;
  a.addEventListener('click',function(){ ml.classList.remove('mo'); });
  li.appendChild(a); ds.appendChild(li);
 });
 var neo=[].slice.call(ds.querySelectorAll('a'));

 function capNhat(){
  var i=0;
  for(var k=0;k<dau.length;k++){ if(dau[k].getBoundingClientRect().top<140) i=k; }
  neo.forEach(function(a,k){ a.classList.toggle('dang-doc',k===i); });
  var a=neo[i];
  if(a){ var cuon=a.closest('.ml-cuon');
   if(cuon){ var h=a.getBoundingClientRect(), c=cuon.getBoundingClientRect();
    if(h.top<c.top||h.bottom>c.bottom) cuon.scrollTop+=h.top-c.top-c.height/3; } }
  var het=document.documentElement.scrollHeight-innerHeight;
  pt.textContent=(het>0?Math.min(100,Math.round(scrollY/het*100)):100)+'%';
 }
 addEventListener('scroll',capNhat,{passive:true});
 addEventListener('resize',capNhat); capNhat();

 // cỡ chữ + nền tối, nhớ lựa chọn
 function docNho(k,md){ try{ return localStorage.getItem(k)||md; }catch(e){ return md; } }
 function ghiNho(k,v){ try{ localStorage.setItem(k,v); }catch(e){} }
 var co=parseInt(docNho('gl-co','16'),10);
 function apCo(){ goc.style.setProperty('--co',co+'px'); ghiNho('gl-co',co); capNhat(); }
 apCo();
 goc.setAttribute('data-nen',docNho('gl-nen','sang'));
 document.getElementById('nutTang').onclick=function(){ co=Math.min(24,co+1); apCo(); };
 document.getElementById('nutGiam').onclick=function(){ co=Math.max(12,co-1); apCo(); };
 document.getElementById('nutNen').onclick=function(){
  var v=goc.getAttribute('data-nen')==='toi'?'sang':'toi';
  goc.setAttribute('data-nen',v); ghiNho('gl-nen',v);
 };
 // thu gọn / mở lại cột mục lục (nhớ lựa chọn)
 goc.setAttribute('data-ml',docNho('gl-ml',''));
 function datMl(v){ goc.setAttribute('data-ml',v); ghiNho('gl-ml',v); capNhat(); }
 document.getElementById('nutThu').onclick=function(){ datMl('thu'); };
 document.getElementById('nutMl').onclick=function(){
  // màn hình rộng: nút ≡ mở lại cột đã thu; màn hình hẹp: kéo cột ra/vào
  if(innerWidth>980 && goc.getAttribute('data-ml')==='thu'){ datMl(''); return; }
  ml.classList.toggle('mo');
 };

 // tìm trong bài
 var o=document.getElementById('oTim'), dem=document.getElementById('demTim'), hit=[], vt=-1;
 function xoaDanh(){
  hit=[]; vt=-1;
  var m=giay.querySelectorAll('mark.danh');
  for(var i=0;i<m.length;i++){ var p=m[i].parentNode;
   p.replaceChild(document.createTextNode(m[i].textContent),m[i]); p.normalize(); }
 }
 function danhDau(q){
  xoaDanh();
  if(q.length<2){ dem.textContent=''; return; }
  var tw=document.createTreeWalker(giay,NodeFilter.SHOW_TEXT,null), nut=[], n;
  while((n=tw.nextNode())) if(n.nodeValue.trim()) nut.push(n);
  var kq=q.toLowerCase();
  nut.forEach(function(n){
   var s=n.nodeValue, l=s.toLowerCase(), i=l.indexOf(kq);
   if(i<0) return;
   var cha=n.parentNode, sau=n, dich=0;
   while(i>=0){
    var giua=sau.splitText(i-dich); dich=i+q.length;
    sau=giua.splitText(q.length);
    var mk=document.createElement('mark'); mk.className='danh';
    cha.replaceChild(mk,giua); mk.appendChild(giua); hit.push(mk);
    i=l.indexOf(kq,dich);
   }
  });
  dem.textContent=hit.length?('1/'+hit.length):'0';
  if(hit.length){ vt=0; toi(0); }
 }
 function toi(i){
  if(!hit.length) return;
  hit.forEach(function(m){ m.classList.remove('dang'); });
  vt=(i+hit.length)%hit.length;
  hit[vt].classList.add('dang');
  hit[vt].scrollIntoView({block:'center',behavior:'smooth'});
  dem.textContent=(vt+1)+'/'+hit.length;
 }
 var cho;
 o.addEventListener('input',function(){ clearTimeout(cho);
  cho=setTimeout(function(){ danhDau(o.value.trim()); },250); });
 o.addEventListener('keydown',function(e){ if(e.key==='Enter'){ e.preventDefault();
  toi(vt+(e.shiftKey?-1:1)); } });
 document.getElementById('timTruoc').onclick=function(){ toi(vt-1); };
 document.getElementById('timSau').onclick=function(){ toi(vt+1); };
 addEventListener('beforeprint',xoaDanh);
})();'''
JS_THEM = r'''
// xem ảnh phóng to: bấm ảnh để mở, ←/→ chuyển ảnh trong cùng bộ, Esc để đóng
(function(){
 var hop=document.getElementById('xemAnh'), anh=hop.querySelector('img'),
     chu=hop.querySelector('.xa-chu'), dem=hop.querySelector('.xa-dem'), bo=[], vt=0;
 function hien(i){
  vt=(i+bo.length)%bo.length; var a=bo[vt], im=a.querySelector('img');
  anh.src=a.getAttribute('href'); anh.alt=im.alt; chu.textContent=im.alt;
  chu.style.display=im.alt?'':'none';
  dem.textContent=bo.length>1?(vt+1)+' / '+bo.length:'';
  hop.querySelector('.xa-truoc').style.display=hop.querySelector('.xa-sau').style.display=bo.length>1?'':'none';
 }
 function dong(){ hop.classList.remove('mo'); anh.removeAttribute('src'); document.body.style.overflow=''; }
 document.getElementById('toGiay').addEventListener('click',function(e){
  var a=e.target.closest('a.o-anh'); if(!a) return;
  e.preventDefault();
  var cha=a.closest('.bo-anh');
  bo=cha?[].slice.call(cha.querySelectorAll('a.o-anh')):[a];
  hien(bo.indexOf(a)); hop.classList.add('mo'); document.body.style.overflow='hidden';
 });
 hop.querySelector('.xa-dong').onclick=dong;
 hop.querySelector('.xa-truoc').onclick=function(e){ e.stopPropagation(); hien(vt-1); };
 hop.querySelector('.xa-sau').onclick=function(e){ e.stopPropagation(); hien(vt+1); };
 hop.addEventListener('click',function(e){ if(e.target===hop) dong(); });
 addEventListener('keydown',function(e){
  if(!hop.classList.contains('mo')) return;
  if(e.key==='Escape') dong();
  else if(e.key==='ArrowLeft') hien(vt-1);
  else if(e.key==='ArrowRight') hien(vt+1);
 });
 var x0=null;
 hop.addEventListener('touchstart',function(e){ x0=e.touches[0].clientX; },{passive:true});
 hop.addEventListener('touchend',function(e){ if(x0===null) return;
  var dx=e.changedTouches[0].clientX-x0; x0=null;
  if(Math.abs(dx)>50) hien(vt+(dx<0?1:-1)); });
})();
// video YouTube: chỉ tải khi bấm. YouTube trả "Lỗi 153" khi trang không gửi được referrer
// (mở từ ổ đĩa file:// hoặc khung sandbox) — khi đó mở thẳng tab YouTube.
(function(){
 var giay=document.getElementById('toGiay'), ds=giay.querySelectorAll('.yt');
 if(!ds.length) return;
 var canEmbed=/^https?:$/.test(location.protocol) &&
   (typeof window.origin==='undefined' || (window.origin && window.origin!=='null'));
 var PLAY='<span class="play"><svg viewBox="0 0 68 48"><path fill="#f00" d="M66.5 7.7a8.6 8.6 0 0 0-6-6C55.2 0 34 0 34 0S12.8 0 7.5 1.7a8.6 8.6 0 0 0-6 6A90 90 0 0 0 0 24a90 90 0 0 0 1.5 16.3 8.6 8.6 0 0 0 6 6C12.8 48 34 48 34 48s21.2 0 26.5-1.7a8.6 8.6 0 0 0 6-6A90 90 0 0 0 68 24a90 90 0 0 0-1.5-16.3z"/><path fill="#fff" d="M27 34l18-10-18-10z"/></svg></span>';
 [].forEach.call(ds,function(b){
  var id=b.getAttribute('data-id'), n=b.getAttribute('data-n')||'Video', watch='https://www.youtube.com/watch?v='+id;
  b.innerHTML='<img loading="lazy" src="https://i.ytimg.com/vi/'+id+'/hqdefault.jpg" alt="'+n+'">'+PLAY+'<span class="badge">▶ '+n+'</span>';
  b.setAttribute('role','button'); b.setAttribute('tabindex','0');
  var fig=b.closest('figure'), cap=fig&&fig.querySelector('figcaption');
  if(!cap&&fig){ cap=document.createElement('figcaption'); fig.appendChild(cap); }
  if(cap){ var a=document.createElement('a'); a.className='ytlink'; a.href=watch; a.target='_blank';
   a.rel='noopener'; a.textContent='Mở trên YouTube ↗'; cap.appendChild(a); }
  function load(){
   if(!canEmbed){ window.open(watch,'_blank','noopener'); return; }
   b.innerHTML='<iframe src="https://www.youtube-nocookie.com/embed/'+id+'?rel=0&autoplay=1" '+
    'referrerpolicy="strict-origin-when-cross-origin" allow="accelerometer;autoplay;clipboard-write;'+
    'encrypted-media;gyroscope;picture-in-picture" allowfullscreen title="'+n+'"></iframe>';
   b.style.cursor='default';
  }
  b.addEventListener('click',load);
  b.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); load(); } });
 });
 if(!canEmbed){
  var w=document.createElement('div'); w.className='canh-bao';
  w.innerHTML='<b>Lưu ý:</b> trang đang mở trực tiếp từ ổ đĩa (hoặc trong khung xem trước) nên YouTube chặn phát nhúng '+
   '(<i>Lỗi 153</i>). Bấm vào video sẽ mở tab YouTube. Đăng trang lên web (https) thì video phát ngay trong trang.';
  giay.insertBefore(w, giay.firstChild);
 }
})();
'''

def dung():
    W = A.work
    K = json.load(open(os.path.join(W, 'khoi.json'), encoding='utf-8'))
    meta = json.load(open(os.path.join(W, 'meta.json'), encoding='utf-8'))
    ANH = A.slug + '_anh'
    OUT_ANH = os.path.join(A.out, ANH)
    if os.path.isdir(OUT_ANH):
        shutil.rmtree(OUT_ANH)
    os.makedirs(OUT_ANH, exist_ok=True)
    loi, canh = [], []

    # ---- bản dịch ----
    VI = {}
    if A.dich:
        import glob
        goc_lo = {}
        for f in sorted(glob.glob(os.path.join(W, 'lo', 'lo-*.json'))):
            if f.endswith('.vi.json'):
                continue
            for e in json.load(open(f, encoding='utf-8')):
                goc_lo[e['id']] = e
            fv = f[:-5] + '.vi.json'
            if not os.path.exists(fv):
                loi.append(f'thiếu bản dịch {os.path.basename(fv)}'); continue
            for e in json.load(open(fv, encoding='utf-8')):
                VI[e['id']] = e
        for i in goc_lo:
            if i not in VI:
                loi.append(f'khối {i}: chưa có bản dịch')
        for i in VI:
            if i not in goc_lo:
                loi.append(f'khối {i}: có trong bản dịch nhưng không có trong bản gốc')
        if not A.title:
            loi.append('--dich cần --title "<tên bài đã dịch>"')

    # ---- media gốc: bắt buộc có đủ ----
    try:
        from PIL import Image
    except ImportError:
        Image = None
    sizes = {}
    can = set()
    for k in K:
        for x in k.get('anh', []):
            can.add(x['name'])
        if k['loai'] == 'video':
            can.add(k['name'])
            if k.get('poster'):
                can.add(k['poster'])
    if A.anh_dau and meta.get('hero'):
        can.add(meta['hero'])
    co_san = set()
    if A.ds_media:
        co_san = {x.strip() for x in open(A.ds_media, encoding='utf-8') if x.strip()}
    chi_tren_may = {n for n in can if not os.path.isfile(os.path.join(A.full, n)) and n in co_san}
    thieu = sorted(n for n in can if not os.path.isfile(os.path.join(A.full, n)) and n not in co_san)
    if thieu:
        print(f'DỪNG: thiếu {len(thieu)} tệp ảnh/video gốc trong {A.full}:')
        for n in thieu[:30]:
            print('  THIẾU', n)
        print('→ Tải lại bằng đoạn JS qua Chrome; không dùng ảnh trong thư mục _files.')
        sys.exit(2)
    nho = []
    doi = {}            # tên gốc -> tên tệp trong <slug>_anh (khi --jpeg / --nen-video đổi đuôi)

    def ffmpeg_exe():
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return shutil.which('ffmpeg')

    for n in sorted(can - chi_tren_may):
        src, dst = os.path.join(A.full, n), os.path.join(OUT_ANH, n)
        if A.nen_video and re.search(r'\.(mp4|mov|m4v|webm|avi|mkv)$', n, re.I) and ffmpeg_exe():
            import subprocess
            moi = re.sub(r'\.[A-Za-z0-9]+$', '', n) + '.mp4'
            if moi != n and (moi in can or moi in doi.values()):
                moi = n + '.mp4'
            ra = os.path.join(OUT_ANH, moi)
            r = subprocess.run([ffmpeg_exe(), '-v', 'error', '-y', '-i', src, '-vf',
                                "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease,"
                                "scale=trunc(iw/2)*2:trunc(ih/2)*2", '-c:v', 'libx264', '-preset', 'veryfast',
                                '-crf', '26', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k',
                                '-movflags', '+faststart', ra], capture_output=True, text=True, timeout=1800)
            if r.returncode == 0 and os.path.getsize(ra) > 0:
                if os.path.getsize(ra) < os.path.getsize(src) or not n.lower().endswith('.mp4'):
                    doi[n] = moi
                    if moi != n and os.path.exists(dst) and dst != ra:
                        os.remove(dst)
                    continue
                os.remove(ra)          # bản nén không nhỏ hơn: giữ bản gốc
            else:
                canh.append(f'không nén được video {n}: {r.stderr[-200:]}')
                if os.path.exists(ra):
                    os.remove(ra)
        if A.jpeg and Image and re.search(r'\.(jpe?g|png|webp|bmp)$', n, re.I):
            try:
                im = Image.open(src); w, h = im.size
                if im.mode in ('RGBA', 'LA', 'P', 'PA'):
                    im = im.convert('RGBA'); nen = Image.new('RGB', im.size, (255, 255, 255))
                    nen.paste(im, mask=im.split()[-1]); im = nen
                else:
                    im = im.convert('RGB')
                if w > A.max_rong:
                    im = im.resize((A.max_rong, round(h * A.max_rong / w)), Image.LANCZOS)
                moi = re.sub(r'\.[A-Za-z0-9]+$', '', n) + '.jpg'
                if moi != n and (moi in can or moi in doi.values()):
                    moi = n + '.jpg'
                im.save(os.path.join(OUT_ANH, moi), 'JPEG', quality=85, optimize=True, progressive=True)
                doi[n] = moi; sizes[n] = im.size
                if max(im.size) <= 150:
                    nho.append(n)
                continue
            except Exception:
                pass
        if Image and IMG_RE.search(n):
            try:
                im = Image.open(src); fmt = im.format; w, h = im.size
                if fmt in ('JPEG', 'PNG') and (w > A.max_rong or (fmt == 'JPEG' and os.path.getsize(src) > 300_000)):
                    if w > A.max_rong:
                        im = im.resize((A.max_rong, round(h * A.max_rong / w)), Image.LANCZOS)
                    if fmt == 'JPEG':
                        im.convert('RGB').save(dst, 'JPEG', quality=85, optimize=True, progressive=True)
                    else:
                        im.save(dst, 'PNG', optimize=True)
                    if w <= A.max_rong and os.path.getsize(dst) >= os.path.getsize(src):
                        shutil.copy(src, dst)
                else:
                    shutil.copy(src, dst)
                sizes[n] = Image.open(dst).size
                if max(sizes[n]) <= 150:
                    nho.append(n)
                continue
            except Exception:
                pass
        shutil.copy(src, dst)

    def img_html(x, alt):
        wh = sizes.get(x)
        x = doi.get(x, x)
        a = f' width="{wh[0]}" height="{wh[1]}"' if wh else ''
        alt = html.escape(html.unescape(re.sub(r'<[^>]+>', '', alt or '')), quote=True)
        from urllib.parse import quote
        q = quote(x)
        return (f'<a class="o-anh" href="{ANH}/{q}"><img src="{ANH}/{q}" alt="{alt}"{a} '
                f'loading="lazy" decoding="async"></a>')

    def lay(k, f):
        """Trường f của khối k: bản dịch nếu có, không thì bản gốc."""
        v = VI.get(k['id'], {})
        if f in v and v[f] not in (None, ''):
            return v[f]
        return k.get(f)

    out, n_vi_tri_anh, n_video = [], 0, 0
    trong_tk = False
    for k in K:
        L = k['loai']
        if k.get('tk') and not trong_tk:
            out.append('<div class="tk">'); trong_tk = True
        if not k.get('tk') and trong_tk:
            out.append('</div>'); trong_tk = False
        v = VI.get(k['id'], {})
        if L == 'h':
            t = lay(k, 'html')
            out.append(f'<h{k["cap_do"]} id="@@ID@@">{t}</h{k["cap_do"]}>')
        elif L == 'p':
            t = lay(k, 'html')
            if v.get('nang'):             # người dịch nâng đoạn in đậm thành tiêu đề mục con
                c = int(v['nang'])
                out.append(f'<h{c} id="@@ID@@">{re.sub(r"<[^>]+>", "", t).strip()}</h{c}>')
                continue
            lop = f' class="{k["lop"]}"' if k.get('lop') else ''
            tag = k.get('tag', 'p')
            s = f'<{tag}{lop}>{t}</{tag}>'
            out.append(f'<div class="note">{s}</div>' if v.get('note') else s)
        elif L == 'list':
            st = f' start="{k["start"]}"' if k.get('start') else ''
            out.append(f'<{k["tag"]}{st}>{lay(k, "html")}</{k["tag"]}>')
        elif L == 'table':
            out.append(f'<div class="khung-bang"><table>{lay(k, "html")}</table></div>')
        elif L == 'fig':
            alts = v.get('alts') or [x['alt'] for x in k['anh']]
            cap = lay(k, 'cap')
            for j, x in enumerate(k['anh']):
                n_vi_tri_anh += 1
                out.append(f'<figure>{img_html(x["name"], alts[j] if j < len(alts) else x["alt"])}'
                           + (f'<figcaption>{cap}</figcaption>' if cap and j == 0 else '') + '</figure>')
        elif L == 'gal':
            alts = v.get('alts') or [x['alt'] for x in k['anh']]
            n_vi_tri_anh += len(k['anh'])
            out.append(f'<div class="bo-anh cot-{k["cot"]}">' + ''.join(
                img_html(x['name'], alts[j] if j < len(alts) else x['alt']) for j, x in enumerate(k['anh'])) + '</div>')
            for c in (v.get('caps') or k.get('caps') or []):
                out.append(f'<p class="chu-thich-anh">{c}</p>')
        elif L == 'yt':
            n_video += 1
            cap = lay(k, 'cap') or ''
            m = re.search(r'(Video|Clip)\s*\d+', re.sub(r'<[^>]+>', '', cap), re.I)
            nhan = m.group(0) if m else 'Video'
            out.append(f'<figure><div class="yt" data-id="{k["vid"]}" data-n="{html.escape(nhan)}"></div>'
                       + (f'<figcaption>{cap}</figcaption>' if cap else '') + '</figure>')
        elif L == 'iframe':
            n_video += 1
            cap = lay(k, 'cap')
            out.append(f'<figure><div class="khung-video"><iframe src="{html.escape(k["src"], quote=True)}" loading="lazy" '
                       f'allowfullscreen allow="fullscreen; encrypted-media; picture-in-picture"></iframe></div>'
                       + (f'<figcaption>{cap}</figcaption>' if cap else '') + '</figure>')
        elif L == 'video':
            n_video += 1
            cap = lay(k, 'cap')
            po = f' poster="{ANH}/{doi.get(k["poster"], k["poster"])}"' if k.get('poster') else ''
            out.append(f'<figure><video controls preload="metadata" playsinline src="{ANH}/{doi.get(k["name"], k["name"])}"{po}></video>'
                       + (f'<figcaption>{cap}</figcaption>' if cap else '') + '</figure>')
        elif L == 'hr':
            out.append('<hr>')
        elif L == 'note':
            out.append(f'<p class="ban-quyen">{lay(k, "html")}</p>')
    if trong_tk:
        out.append('</div>')

    # id tiêu đề
    used = set()
    def hid(m):
        t = html.unescape(re.sub(r'<[^>]+>', '', m.group(2)))
        s = slugify(t) or 'muc'; b, i = s, 2
        while s in used:
            s = f'{b}-{i}'; i += 1
        used.add(s)
        return f'<h{m.group(1)} id="{s}">{m.group(2)}</h{m.group(1)}>'
    body_html = re.sub(r'<h(\d) id="@@ID@@">(.*?)</h\1>', hid, '\n'.join(out), flags=re.S)

    if A.anh_dau and meta.get('hero'):
        body_html = f'<figure class="anh-dau">{img_html(meta["hero"], "")}</figure>\n' + body_html

    # ---- đầu trang ----
    so_anh = len({x['name'] for k in K for x in k.get('anh', [])})
    goc_link = html.escape(meta.get('url') or '', quote=True)
    site = html.escape(meta.get('site') or '')
    if A.dich:
        title = A.title
        nhan = A.nhan or f'BẢN DỊCH · {(meta.get("site") or "").upper()}'
        vid_txt = f' và {n_video} video' if n_video else ''
        nguon = (f'<p class="dich-gia">Bản dịch tiếng Việt của bài <a href="{goc_link}" target="_blank" rel="noopener">'
                 f'"{html.escape(meta["tieu_de"])}"</a> – {site}. Giữ nguyên toàn bộ {n_vi_tri_anh} hình ảnh{vid_txt} của bản gốc.'
                 + (f' Người dịch: <b>{html.escape(A.nguoi_dich)}</b>.' if A.nguoi_dich else '') + '</p>')
    else:
        title = A.title or meta['tieu_de']
        nhan = A.nhan or (f'BÀI GIẢNG · {(meta.get("site") or "").upper()}' if meta.get('site') else 'TÀI LIỆU')
        hien = re.sub(r'^https?://(www\.)?', '', meta.get('url') or '').rstrip('/')
        nguon = (f'<p class="dich-gia">Nguồn: <a href="{goc_link}" target="_blank" rel="noopener">{site}'
                 + (f' — {html.escape(hien)}' if hien else '') + '</a></p>')

    if A.khong_dong_nguon:
        nguon = ''
    if A.ve:
        nguon = (f'<p class="dich-gia"><a href="{html.escape(A.ve, quote=True)}">← Mục lục Case ECG</a></p>' + nguon)
    page = f"""<!doctype html>
<html lang="vi" data-nen="sang">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
{CSS.strip()}
{EXTRA_CSS.strip()}
</style>
</head>
<body>
<div class="bo-cuc">
 <aside class="muc-luc" id="mucLuc">
  <div class="ml-dau"><span>NỘI DUNG</span><span id="phanTram">0%</span><button
    id="nutThu" class="nut-thu" type="button" title="Thu gọn mục lục">«</button></div>
  <div class="o-tim">
   <input id="oTim" type="search" placeholder="Tìm trong tài liệu…" autocomplete="off">
   <div class="tim-dieu-khien">
    <button id="timTruoc" type="button">↑</button>
    <button id="timSau" type="button">↓</button>
    <span id="demTim"></span>
   </div>
  </div>
  <div class="ml-cuon"><ul id="dsMuc"></ul></div>
 </aside>
 <main>
  <section class="dau-bai">
   <div class="nhan">{html.escape(nhan)}</div>
   <h1>{html.escape(title)}</h1>
   {nguon}
  </section>
  <section class="to-giay" id="toGiay">
{body_html}
  </section>
 </main>
</div>
<div class="thanh-nut">
 <button id="nutMl" class="hien-ml" type="button" title="Mục lục">≡</button>
 <button id="nutGiam" type="button" title="Chữ nhỏ hơn">A-</button>
 <button id="nutTang" type="button" title="Chữ lớn hơn">A+</button>
 <button id="nutNen" type="button" title="Nền sáng/tối">◐</button>
</div>
<div class="xem-anh" id="xemAnh" role="dialog" aria-label="Xem ảnh">
 <span class="xa-dem"></span>
 <button class="xa-dong" type="button" title="Đóng (Esc)">✕</button>
 <button class="xa-truoc" type="button" title="Ảnh trước (←)">‹</button>
 <img alt="">
 <button class="xa-sau" type="button" title="Ảnh sau (→)">›</button>
 <div class="xa-chu"></div>
</div>
<script>
{JS.strip()}
{JS_THEM.strip()}
</script>
</body>
</html>
"""
    os.makedirs(A.out, exist_ok=True)
    dich = os.path.join(A.out, A.slug + '.html')
    open(dich, 'w', encoding='utf-8').write(page)

    # ================= tự kiểm =================
    ra = BeautifulSoup(page, 'lxml').select_one('#toGiay')
    print(f'Trang: {dich}  ({len(page.encode()) // 1024} KB)')
    n_img_goc = sum(len(k.get('anh', [])) for k in K)
    print(f'Ảnh: {n_vi_tri_anh} vị trí / {n_img_goc} trong bản gốc; {len(can)} tệp media gốc; '
          f'video/iframe: {n_video}')
    if n_vi_tri_anh != n_img_goc:
        loi.append('số vị trí ảnh lệch bản gốc')
    if nho:
        canh.append(f'{len(nho)} ảnh gốc ≤150 px (có thể là biểu tượng thật, hoặc tải nhầm ảnh thu nhỏ): {nho[:5]}')

    if not A.dich:
        ra_text = txt_norm(ra.get_text(''))
        ok = ra_text == meta['goc_text']
        print(f'Chữ khớp bản gốc: {"ĐÚNG" if ok else "LỆCH"}  ({len(meta["goc_text"])} / {len(ra_text)} ký tự)')
        if not ok:
            g = meta['goc_text']
            for i, (x, y) in enumerate(zip(g, ra_text)):
                if x != y:
                    print('  gốc:', g[max(0, i - 50):i + 50]); print('  ra :', ra_text[max(0, i - 50):i + 50]); break
            loi.append('chữ lệch bản gốc')
    else:
        from collections import Counter
        def the(s):
            return Counter(re.findall(r'<([a-z0-9]+)(?:\s[^>]*)?>', s or ''))
        def so(s):
            t = re.sub(r'<[^>]+>', ' ', s or '')
            return Counter(re.findall(r'\d+', t))
        def tieng_anh(s):
            t = re.sub(r'<sup>.*?</sup>|<a [^>]*>.*?</a>', ' ', s or '', flags=re.S)
            t = re.sub(r'<[^>]+>', ' ', html.unescape(t))
            t = re.sub(r'\([^()]*\)', ' ', t)          # thuật ngữ gốc trong ngoặc là đúng quy ước
            return re.findall(r"(?:\b[A-Za-z][A-Za-z'’-]*\b[ ,;:]+){4,}\b[A-Za-z][A-Za-z'’-]*\b", t)
        goc = {k['id']: k for k in K}
        for i, v in VI.items():
            k = goc.get(i)
            if not k:
                continue
            cap_goc = k.get('cap')
            cap_ = [('html', k.get('html'), v.get('html')), ('cap', cap_goc, v.get('cap'))]
            cap_ += [(f'caps[{j}]', a, b) for j, (a, b) in enumerate(zip(k.get('caps') or [], v.get('caps') or []))]
            for ten, a, b in cap_:
                if not a:
                    continue
                if not b:
                    loi.append(f'khối {i}.{ten}: trống bản dịch'); continue
                if the(a) != the(b):
                    loi.append(f'khối {i}.{ten}: thẻ HTML khác bản gốc {dict(the(a) - the(b))} / {dict(the(b) - the(a))}')
                if so(a) != so(b):
                    canh.append(f'khối {i}.{ten}: số khác bản gốc — thiếu {dict(so(a) - so(b))}, thừa {dict(so(b) - so(a))}')
                ta = tieng_anh(b)
                if ta:
                    canh.append(f'khối {i}.{ten}: còn câu tiếng nước ngoài: {ta[0][:90]!r}')
                if a == b and len(re.findall(r'[A-Za-z]{3,}', re.sub(r'<[^>]+>', '', a))) >= 3:
                    loi.append(f'khối {i}.{ten}: y hệt bản gốc (chưa dịch?)')
            if k.get('anh') and 'alts' in v and len(v['alts']) != len(k['anh']):
                loi.append(f'khối {i}: số chú thích ảnh (alts) khác số ảnh')
        print(f'Khối đã dịch: {len(VI)}; khối Tài liệu tham khảo giữ nguyên: {sum(1 for k in K if k.get("tk"))}')
    heads = ra.find_all(re.compile(r'^h[2-6]$'))
    print('Mục lục (' + str(len(heads)) + '):', ' | '.join(h.get_text() for h in heads if h.name in ('h2', 'h3'))[:700])
    for c in canh[:40]:
        print('CẢNH BÁO', c)
    for l in loi[:60]:
        print('LỖI', l)
    print('KẾT QUẢ:', 'ĐẠT' if not loi else f'CHƯA ĐẠT ({len(loi)} lỗi)')
    if loi:
        sys.exit(1)

if A.lenh == 'trich':
    trich()
else:
    dung()
