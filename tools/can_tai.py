#!/usr/bin/env python3
"""can_tai.py — bước kiểm nhanh trong workflow: còn đủ nguồn sẵn sàng thì KHÔNG cần tải.

  python3 can_tai.py --main main --nguon ng_json --nguong 60
ng_json: bản clone sparse nhánh nguon chỉ chứa */nguon.json (vài trăm KB).
Ghi `can=1` (cần tải) hoặc `can=0` vào $GITHUB_OUTPUT. "Sẵn sàng" = case còn "chua" có nguồn tải đủ,
không lỗi, không mất ảnh.
"""
import argparse, glob, json, os

ap = argparse.ArgumentParser()
ap.add_argument('--main', required=True)
ap.add_argument('--nguon', required=True)
ap.add_argument('--nguong', type=int, default=60)
A = ap.parse_args()
ds = {c['slug']: c for c in json.load(open(os.path.join(A.main, 'du-lieu', 'danh-sach.json'), encoding='utf-8'))}
san = 0
for f in glob.glob(os.path.join(A.nguon, '*', 'nguon.json')):
    s = os.path.basename(os.path.dirname(f))
    d = json.load(open(f, encoding='utf-8'))
    if ds.get(s, {}).get('trang_thai') == 'chua' and not d.get('loi') and not d.get('anh_mat') and not d.get('khong_ton_tai'):
        san += 1
can = san < A.nguong
print(f'Nguồn sẵn sàng cho case "chua": {san} (ngưỡng {A.nguong}) → {"TẢI THÊM" if can else "đủ, bỏ qua lượt này"}')
with open(os.environ.get('GITHUB_OUTPUT', '/dev/null'), 'a') as o:
    o.write(f'can={int(can)}\n')
