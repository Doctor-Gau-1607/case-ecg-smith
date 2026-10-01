#!/usr/bin/env python3
"""lam_case.py — mọi việc của một lượt dịch Case ECG (Dr. Smith’s ECG Blog), trừ phần dịch chữ.

  python3 tools/lam_case.py chuan-bi --so 5
      Nhận N case kế tiếp (đánh dấu "dang" + đẩy lên để lượt khác không làm trùng),
      lấy trang + ảnh gốc từ nhánh nguon, tách khối vào /home/claude/cv/<slug>/W.
      In ra danh sách lô cần dịch.
  python3 tools/lam_case.py dung --slug <slug> --title "<tiêu đề tiếng Việt, KHÔNG kèm ngày>" [--tu-khoa "..."]
      Dựng c/<slug>.html + c/<slug>_anh/, tự kiểm; đạt thì ghi "xong" vào danh sách.
  python3 tools/lam_case.py tra-lai --slug case-002 --ly-do "..."
      Trả case về "chua" (lượt sau làm lại), ghi lý do.
  python3 tools/lam_case.py day-len
      Commit + đẩy mọi thay đổi (c/, du-lieu/) lên main.
  python3 tools/lam_case.py tien-do
      In số case đã xong / đang / chưa, số case đã có nguồn.

Chạy từ gốc bản clone main (khuyên dùng: clone sparse, xem QUY-TRINH.md).
"""
import argparse, json, os, re, subprocess, sys, time, shutil

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS_P = os.path.join(GOC, 'du-lieu', 'danh-sach.json')
MG = os.path.join(GOC, 'tools', 'medguide.py')
CV = os.environ.get('CASE_VIEC', '/home/claude/cv')          # thư mục làm việc
NG = os.environ.get('CASE_NGUON', '/home/claude/cv/_nguon')  # bản clone sparse nhánh nguon
REPO = 'https://github.com/Doctor-Gau-1607/case-ecg-smith'
PHIEN = 1
GIOI_HAN_MB = 900          # GitHub Pages: trang công khai tối đa 1 GB
HET_HAN_GIU = 4 * 3600   # case "dang" quá 4 giờ coi như lượt trước bỏ dở

ap = argparse.ArgumentParser()
sp = ap.add_subparsers(dest='lenh', required=True)
p = sp.add_parser('chuan-bi'); p.add_argument('--so', type=int, default=5)
p = sp.add_parser('dung'); p.add_argument('--slug', required=True); p.add_argument('--title', required=True)
p.add_argument('--tu-khoa', default='')
p = sp.add_parser('tra-lai'); p.add_argument('--slug', required=True); p.add_argument('--ly-do', default='')
sp.add_parser('day-len'); sp.add_parser('tien-do')
A = ap.parse_args()


def sh(*a, cwd=GOC, check=True, cap=False):
    r = subprocess.run(list(a), cwd=cwd, text=True, capture_output=cap)
    if check and r.returncode != 0:
        sys.exit(f'LỖI lệnh {" ".join(a)}\n{r.stdout if cap else ""}{r.stderr if cap else ""}')
    return r


def doc_ds():
    return json.load(open(DS_P, encoding='utf-8'))


def ghi_ds(ds):
    json.dump(ds, open(DS_P, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)


def day(thong_diep, duong_dan):
    """commit + pull --rebase + push, thử lại khi có lượt khác vừa đẩy."""
    sh('git', 'add', '--sparse', *duong_dan)
    if sh('git', 'diff', '--cached', '--quiet', check=False).returncode != 0:
        sh('git', 'commit', '-q', '-m', thong_diep + '\n\nCo-Authored-By: Claude <noreply@anthropic.com>')
    else:
        # không có thay đổi mới, nhưng có thể còn commit cũ chưa đẩy (lần trước kẹt)
        sh('git', 'fetch', '-q', 'origin', 'main', check=False)
        if sh('git', 'rev-list', '--count', 'origin/main..HEAD', cap=True).stdout.strip() == '0':
            print('Không có gì mới để đẩy.'); return
    for t in range(6):
        # --autostash: tệp khác đang sửa dở (vd. thuat-ngu.md) không làm kẹt rebase
        if sh('git', 'pull', '-q', '--rebase', '--autostash', 'origin', 'main', check=False).returncode != 0:
            # xung đột chỉ có thể ở danh-sach.json: lấy bản mới rồi áp lại thay đổi của mình
            sh('git', 'rebase', '--abort', check=False)
            sys.exit('LỖI: rebase xung đột — xem lại du-lieu/danh-sach.json rồi chạy lại day-len')
        if sh('git', 'push', '-q', 'origin', 'HEAD:main', check=False).returncode == 0:
            print('Đã đẩy lên main.'); return
        time.sleep(10 * (t + 1))
    sys.exit('LỖI: không đẩy được lên main (xem quyền truy cập repo).')


def nguon_san_sang():
    """clone/cập nhật sparse nhánh nguon, trả về tập slug đã có nguồn đầy đủ."""
    if not os.path.isdir(os.path.join(NG, '.git')):
        os.makedirs(os.path.dirname(NG), exist_ok=True)
        sh('git', 'clone', '-q', '--depth', '1', '--filter=blob:none', '--no-checkout', '-b', 'nguon', REPO, NG, cwd='/')
        sh('git', 'sparse-checkout', 'set', '--no-cone', '/*/nguon.json', cwd=NG)
        sh('git', 'checkout', '-q', 'nguon', cwd=NG)
    else:
        sh('git', 'fetch', '-q', '--depth', '1', 'origin', 'nguon', cwd=NG)
        sh('git', 'reset', '-q', '--hard', 'FETCH_HEAD', cwd=NG)
    ok, mat, go = set(), {}, set()
    for s in os.listdir(NG):
        f = os.path.join(NG, s, 'nguon.json')
        if os.path.isfile(f):
            d = json.load(open(f, encoding='utf-8'))
            if d.get('phien') == PHIEN and d.get('khong_ton_tai'):
                go.add(s)
            elif d.get('phien') == PHIEN and not d.get('loi'):
                (mat.__setitem__(s, d['anh_mat']) if d.get('anh_mat') else ok.add(s))
    nguon_san_sang.mat = mat
    nguon_san_sang.go = go
    return ok


def dung_luong_mb():
    # cộng dồn kích thước từng case đã ghi lúc dựng (không cần checkout cả thư mục c/)
    return round(sum(c.get('kb', 0) for c in doc_ds()) / 1024)


def kich_thuoc_kb(slug):
    tong = os.path.getsize(os.path.join(GOC, 'c', slug + '.html'))
    for g, _, fs in os.walk(os.path.join(GOC, 'c', slug + '_anh')):
        tong += sum(os.path.getsize(os.path.join(g, f)) for f in fs)
    return round(tong / 1024)


if A.lenh == 'tien-do':
    ds = doc_ds()
    from collections import Counter
    print(Counter(c['trang_thai'] for c in ds))
    print('Dung lượng c/:', dung_luong_mb(), 'MB /', GIOI_HAN_MB, 'MB')
    try:
        print('Đã có nguồn:', len(nguon_san_sang()), '/', len(ds))
    except SystemExit as e:
        print('Chưa có nhánh nguon:', e)

elif A.lenh == 'chuan-bi':
    sh('git', 'pull', '-q', '--rebase', 'origin', 'main')
    co_nguon = nguon_san_sang()
    if dung_luong_mb() > GIOI_HAN_MB:
        print(f'DỪNG: thư mục c/ đã quá {GIOI_HAN_MB} MB — cần mở repo tiếp theo (báo người dùng).'); sys.exit(0)
    ds = doc_ds(); bay_gio = time.time(); chon = []
    for c in ds:
        if c['trang_thai'] == 'chua' and c['slug'] in nguon_san_sang.go:
            c['trang_thai'] = 'khong_ton_tai'; c['ly_do'] = 'trang gốc 404 — tác giả đã gỡ bài'
            continue
        if c['trang_thai'] == 'chua' and c['slug'] in nguon_san_sang.mat:
            c['trang_thai'] = 'cho_anh'; c['ly_do'] = 'ảnh gốc 404: ' + ', '.join(nguon_san_sang.mat[c['slug']][:3])
            continue
        if len(chon) >= A.so:
            break
        giu = c['trang_thai'] == 'dang' and bay_gio - c.get('giu_luc', 0) > HET_HAN_GIU
        if (c['trang_thai'] == 'chua' or giu) and c['slug'] in co_nguon:
            c['trang_thai'] = 'dang'; c['giu_luc'] = int(bay_gio); chon.append(c)
    if not chon:
        if json.dumps(ds) != json.dumps(doc_ds()):      # có case vừa được đánh dấu cho_anh / khong_ton_tai
            ghi_ds(ds); day('Đánh dấu case chờ ảnh / đã bị gỡ', ['du-lieu/danh-sach.json'])
        print('KHÔNG CÒN CASE NÀO SẴN SÀNG (hết case, hoặc nhánh nguon chưa tải tới).'); sys.exit(0)
    ghi_ds(ds)
    day('Nhận dịch: ' + ', '.join(c['nhan'] for c in chon), ['du-lieu/danh-sach.json'])
    sh('git', 'sparse-checkout', 'add', *[f'/{c["slug"]}/' for c in chon], cwd=NG)
    for c in chon:
        w = os.path.join(CV, c['slug'])
        shutil.rmtree(w, ignore_errors=True); os.makedirs(w)
        r = sh(sys.executable, MG, 'trich', '--src', os.path.join(NG, c['slug'], 'trang.html'),
               '--work', os.path.join(w, 'W'), '--chon', 'div.entry-content', cap=True)
        lo = sorted(f for f in os.listdir(os.path.join(w, 'W', 'lo')) if re.match(r'lo-\d+\.json$', f))
        print(f"\n=== {c['slug']}  ({c['nhan']}, đăng {c['ngay_dang']})  {len(lo)} lô dịch: {w}/W/lo/")
        print('  Tiêu đề gốc:', c['tieu_de_en'])
        print('\n'.join('  ' + x for x in r.stdout.strip().splitlines()))

elif A.lenh == 'dung':
    ds = doc_ds(); c = next(x for x in ds if x['slug'] == A.slug)
    w = os.path.join(CV, A.slug, 'W')
    y, m_, d_ = c['ngay_dang'].split('-')
    tieu_de = f'{d_}/{m_}/{y} — ' + re.sub(r'^\d{1,2}/\d{1,2}/\d{4}\s*[—–-]\s*', '', A.title.strip())
    # ảnh đại diện (featured image) chỉ đặt ở đầu bài khi nó KHÔNG trùng một ảnh trong thân bài
    meta0 = json.load(open(os.path.join(w, 'meta.json'), encoding='utf-8'))
    than = {x['name'] for k in json.load(open(os.path.join(w, 'khoi.json'), encoding='utf-8')) for x in k.get('anh', [])}
    anh_dau = ['--anh-dau'] if meta0.get('hero') and meta0['hero'] not in than else []
    r = sh(sys.executable, MG, 'dung', '--work', w, '--full', os.path.join(NG, A.slug, 'goc'),
           '--out', os.path.join(GOC, 'c'), '--slug', A.slug, '--dich', '--jpeg', *anh_dau, '--ve', '../index.html',
           '--title', tieu_de, '--nhan', f"CASE ECG {c['nhan']} · DR. SMITH’S ECG BLOG", cap=True, check=False)
    print(r.stdout[-3000:], r.stderr[-2000:])
    if 'KẾT QUẢ: ĐẠT' not in r.stdout:
        sys.exit('CHƯA ĐẠT — sửa bản dịch (lo-*.vi.json) rồi chạy lại lệnh dung.')
    # kiểm chéo: mọi ảnh/video trang gọi tới đều có tệp
    from urllib.parse import unquote
    page = open(os.path.join(GOC, 'c', A.slug + '.html'), encoding='utf-8').read()
    thieu = [f for f in set(re.findall(r'(?:src|href|poster)="(' + re.escape(A.slug) + r'_anh/[^"]+)"', page))
             if not os.path.isfile(os.path.join(GOC, 'c', unquote(f)))]
    if thieu:
        sys.exit(f'THIẾU tệp media: {thieu[:5]}')
    meta = json.load(open(os.path.join(w, 'meta.json'), encoding='utf-8'))
    c.update(tieu_de_en=meta.get('tieu_de', '') or c['tieu_de_en'], tieu_de_vi=tieu_de, tu_khoa=A.tu_khoa,
             trang_thai='xong', ngay=time.strftime('%Y-%m-%d'), kb=kich_thuoc_kb(A.slug))
    c.pop('giu_luc', None); c.pop('ly_do', None)
    ghi_ds(ds); print('ĐÃ XONG', A.slug, '·', tieu_de)
    mb = dung_luong_mb()
    if mb > GIOI_HAN_MB:
        print(f'CẢNH BÁO: c/ đã {mb} MB (> {GIOI_HAN_MB} MB) — đẩy lên rồi dừng lượt, báo người dùng cần repo tiếp theo.')

elif A.lenh == 'tra-lai':
    ds = doc_ds(); c = next(x for x in ds if x['slug'] == A.slug)
    c['trang_thai'] = 'chua'; c.pop('giu_luc', None); c['ly_do'] = A.ly_do
    ghi_ds(ds); print('Đã trả lại', A.slug)

elif A.lenh == 'day-len':
    ds = doc_ds()
    xong = [c['nhan'] for c in ds if c['trang_thai'] == 'xong']
    day(f'Case ECG: cập nhật bản dịch (đã xong {len(xong)}/{len(ds)})', ['c', 'du-lieu'])
