#!/usr/bin/env python3
"""bai_moi.py — chạy trong GitHub Actions (container của Claude không vào được drsmithsecgblog.com):
tìm bài MỚI trên Dr. Smith's ECG Blog qua WordPress REST API và thêm vào đầu du-lieu/danh-sach.json
với trạng thái "chua" (lượt dịch hằng tuần sẽ dịch). Bài đã có trong danh sách thì bỏ qua.

  python3 bai_moi.py --main main          # in số bài mới; ghi danh-sach.json nếu có
"""
import argparse, html, json, os, re, sys, time, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument('--main', required=True)
ap.add_argument('--so-trang', type=int, default=2, help='số trang API (mỗi trang 50 bài mới nhất) để dò')
A = ap.parse_args()

API = 'https://drsmithsecgblog.com/wp-json/wp/v2/posts?per_page=50&page={}&orderby=date&order=desc&_fields=id,date,link,slug,title'
UA = 'Mozilla/5.0 (compatible; MEDGUIDE-CaseECG-Smith/1.0; +https://github.com/Doctor-Gau-1607/case-ecg-smith)'
DS_P = os.path.join(A.main, 'du-lieu', 'danh-sach.json')
DS = json.load(open(DS_P, encoding='utf-8'))


def chuan(u):
    return u.split('#')[0].rstrip('/').lower()


da_co = {chuan(c['url']) for c in DS}
slug_co = {c['slug'] for c in DS}
moi = []
for trang in range(1, A.so_trang + 1):
    for t in range(4):
        try:
            req = urllib.request.Request(API.format(trang), headers={'User-Agent': UA})
            bai = json.load(urllib.request.urlopen(req, timeout=60))
            break
        except Exception as e:  # noqa
            loi = e; time.sleep(10 * (t + 1))
    else:
        sys.exit(f'Không đọc được API trang {trang}: {loi}')
    if not bai:
        break
    for b in bai:
        if chuan(b['link']) in da_co:
            continue
        ngay = b['date'][:10]
        slug = f"{ngay}-{b['slug'][:60].rstrip('-')}"
        while slug in slug_co:
            slug += '-2'
        slug_co.add(slug); da_co.add(chuan(b['link']))
        moi.append({'url': b['link'], 'ngay_dang': ngay, 'slug': slug,
                    'tieu_de_en': html.unescape(re.sub(r'<[^>]+>', '', b['title']['rendered'])).strip(),
                    'trang_thai': 'chua'})

if not moi:
    print('Không có bài mới.'); sys.exit(0)
so = max(c['stt'] for c in DS)
for c in sorted(moi, key=lambda x: x['ngay_dang']):          # đánh số theo thời gian (#1 = bài cũ nhất 2008)
    so += 1
    c.update(stt=so, nhan=f'#{so}')
moi.sort(key=lambda x: (x['ngay_dang'], x['stt']), reverse=True)
DS = moi + DS                                                 # danh sách xếp mới nhất trước
json.dump(DS, open(DS_P, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print(f'Bài mới: {len(moi)}')
for c in moi:
    print(' ', c['nhan'], c['ngay_dang'], c['tieu_de_en'][:90])
