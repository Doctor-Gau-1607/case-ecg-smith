#!/usr/bin/env python3
"""can_tai.py — bước kiểm nhanh trong workflow: còn đủ nguồn sẵn sàng thì KHÔNG cần tải.

  python3 can_tai.py --main main --nguon ng_json --nguong 60
ng_json: bản clone sparse nhánh nguon chỉ chứa */nguon.json (vài trăm KB).
Ghi `can=1` (cần tải) hoặc `can=0` vào $GITHUB_OUTPUT. "Sẵn sàng" = case còn "chua" có nguồn tải đủ,
không lỗi, không mất ảnh.
"""
import argparse, glob, json, os, time

ap = argparse.ArgumentParser()
ap.add_argument('--main', required=True)
ap.add_argument('--nguon', required=True)
ap.add_argument('--nguong', type=int, default=60)
A = ap.parse_args()
ds = {c['slug']: c for c in json.load(open(os.path.join(A.main, 'du-lieu', 'danh-sach.json'), encoding='utf-8'))}
san = 0; co = set(); loi_cu = 0
for f in glob.glob(os.path.join(A.nguon, '*', 'nguon.json')):
    s = os.path.basename(os.path.dirname(f))
    d = json.load(open(f, encoding='utf-8'))
    co.add(s)
    if ds.get(s, {}).get('trang_thai') != 'chua':
        continue
    if not d.get('loi') and not d.get('anh_mat') and not d.get('khong_ton_tai'):
        san += 1
    elif d.get('loi'):
        # case lỗi tải: thử lại tối đa mỗi ngày một lần (không tải lại mỗi giờ)
        try:
            if time.time() - time.mktime(time.strptime(d.get('luc', ''), '%Y-%m-%d %H:%M:%S')) > 86400:
                loi_cu += 1
        except ValueError:
            loi_cu += 1
# case "chua" chưa từng có nguồn (vd. bài mới vừa được bai_moi.py thêm vào)
chua_co_nguon = sum(1 for s, c in ds.items() if c['trang_thai'] == 'chua' and s not in co)
can = san < A.nguong and (chua_co_nguon > 0 or loi_cu > 0)
print(f'Nguồn sẵn sàng cho case "chua": {san} (ngưỡng {A.nguong}); chưa có nguồn: {chua_co_nguon}; '
      f'lỗi cần thử lại: {loi_cu} → {"TẢI THÊM" if can else "bỏ qua lượt này"}')
with open(os.environ.get('GITHUB_OUTPUT', '/dev/null'), 'a') as o:
    o.write(f'can={int(can)}\n')
