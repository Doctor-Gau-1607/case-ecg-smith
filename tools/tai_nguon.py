#!/usr/bin/env python3
"""tai_nguon.py — chạy trong GitHub Actions: chuẩn bị "cửa sổ" nguồn cho các case sắp dịch.

Nhánh `nguon` chỉ giữ nguồn của các case CHƯA xong (đang dịch + N case kế tiếp), và được dựng lại
thành MỘT commit mồ côi mỗi lần chạy (force-push). Nhờ vậy repo không phình mãi theo ảnh gốc:
case dịch xong thì nguồn của nó rơi khỏi nhánh ở lượt tải sau.

  python3 tai_nguon.py --main main --cu ng_cu --out ng_moi --cua-so 80

  ng_cu/<slug>/...       nhánh nguon hiện có (để dùng lại, không tải lại)
  ng_moi/<slug>/trang.html   trang gốc (có dòng "saved from url")
  ng_moi/<slug>/goc/<tên>    ảnh/video gốc. Ảnh tĩnh rộng > 1600 px hoặc nặng > 400 KB được lưu lại
                             dưới dạng JPEG q92 rộng 1600 px (giữ NGUYÊN TÊN tệp để medguide.py tìm thấy;
                             medguide --jpeg sẽ xuất ra .jpg)
  ng_moi/<slug>/nguon.json   url, số media, lỗi, thời điểm tải

Lịch sự với máy chủ blog: một luồng, nghỉ giữa các yêu cầu, User-Agent định danh rõ.
"""
import argparse, io, json, os, re, shutil, subprocess, sys, tempfile, time
import urllib.request, urllib.error, urllib.parse

ap = argparse.ArgumentParser()
ap.add_argument('--main', required=True)
ap.add_argument('--cu', default='')
ap.add_argument('--out', required=True)
ap.add_argument('--cua-so', type=int, default=80, help='số case CHƯA dịch được chuẩn bị sẵn nguồn')
ap.add_argument('--han-phut', type=int, default=300, help='dừng tải mới sau chừng này phút')
A = ap.parse_args()

UA = 'Mozilla/5.0 (compatible; MEDGUIDE-CaseECG-Smith/1.0; +https://github.com/Doctor-Gau-1607/case-ecg-smith)'
MG = os.path.join(A.main, 'tools', 'medguide.py')
DS = json.load(open(os.path.join(A.main, 'du-lieu', 'danh-sach.json'), encoding='utf-8'))
PHIEN = 1
BAT_DAU = time.time()
os.makedirs(A.out, exist_ok=True)


def tai(url, lan=5):
    loi = None
    # link ảnh cũ của Blogger có dấu cách / ký tự lạ ("Screen Shot 2022-02-08 at 8.32.20 AM.png") → mã hoá %
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    for t in range(lan):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read(), r.geturl()
        except urllib.error.HTTPError as e:
            loi = e
            if e.code in (404, 410):
                break
            time.sleep((90 if e.code in (429, 503) else 5) * (t + 1))
        except Exception as e:  # noqa
            loi = e
            time.sleep(5 * (t + 1))
    raise loi


def gon_anh(data, ten):
    """Ảnh tĩnh lớn -> JPEG q92 rộng tối đa 1600 px (giữ tên). GIF/SVG/video giữ nguyên."""
    if not re.search(r'\.(jpe?g|png|webp|bmp)$', ten, re.I) or len(data) < 400_000:
        return data
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)); w, h = im.size
        if im.mode in ('RGBA', 'LA', 'P', 'PA'):
            im = im.convert('RGBA'); nen = Image.new('RGB', im.size, (255, 255, 255))
            nen.paste(im, mask=im.split()[-1]); im = nen
        else:
            im = im.convert('RGB')
        if w > 1600:
            im = im.resize((1600, round(h * 1600 / w)), Image.LANCZOS)
        b = io.BytesIO(); im.save(b, 'JPEG', quality=92, optimize=True)
        return b.getvalue() if len(b.getvalue()) < len(data) else data
    except Exception:  # noqa
        return data


def gon_video(data, ten):
    """Video nặng (> 8 MB) -> MP4 H.264 ≤1280×720 CRF 23 (giữ NGUYÊN TÊN tệp; medguide --nen-video xuất .mp4).
    Máy chủ GitHub Actions có sẵn ffmpeg. Lỗi thì giữ nguyên dữ liệu gốc."""
    if not re.search(r'\.(mp4|mov|m4v|webm|avi|mkv)$', ten, re.I) or len(data) < 8_000_000 or not shutil.which('ffmpeg'):
        return data
    with tempfile.TemporaryDirectory() as t:
        vao, ra = os.path.join(t, 'vao' + os.path.splitext(ten)[1]), os.path.join(t, 'ra.mp4')
        open(vao, 'wb').write(data)
        r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', vao, '-vf',
                            "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease,"
                            "scale=trunc(iw/2)*2:trunc(ih/2)*2", '-c:v', 'libx264', '-preset', 'veryfast',
                            '-crf', '23', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                            '-movflags', '+faststart', ra], capture_output=True)
        if r.returncode == 0 and os.path.isfile(ra) and 0 < os.path.getsize(ra) < len(data):
            if os.path.getsize(ra) <= 90_000_000:
                return open(ra, 'rb').read()
            data = open(ra, 'rb').read()
        # vẫn quá lớn cho GitHub (giới hạn 100 MB/tệp) → nén mạnh hơn nhưng GIỮ 720p (người dùng yêu cầu
        # không hạ độ phân giải dưới 720p): preset chậm hơn, tăng dần CRF, AAC 96k
        for crf in ('27', '30', '33'):
            ra2 = os.path.join(t, f'ra{crf}.mp4')
            r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', vao, '-vf',
                                "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease,"
                                "scale=trunc(iw/2)*2:trunc(ih/2)*2", '-c:v', 'libx264', '-preset', 'slow',
                                '-crf', crf, '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k',
                                '-movflags', '+faststart', ra2], capture_output=True)
            if r.returncode == 0 and os.path.isfile(ra2) and 0 < os.path.getsize(ra2) < len(data):
                data = open(ra2, 'rb').read()
                if len(data) <= 90_000_000:
                    break
    return data


# cửa sổ: mọi case "dang" + các case "chua" kế tiếp theo thứ tự danh sách (mới nhất trước)
can = [c for c in DS if c['trang_thai'] == 'dang']
can += [c for c in DS if c['trang_thai'] in ('chua', 'cho_anh')][:A.cua_so]
print('Cửa sổ:', len(can), 'case', flush=True)

moi = giu = 0
for c in can:
    s = c['slug']; d = os.path.join(A.out, s)
    cu = os.path.join(A.cu, s) if A.cu else ''
    if cu and os.path.isfile(os.path.join(cu, 'nguon.json')):
        info = json.load(open(os.path.join(cu, 'nguon.json'), encoding='utf-8'))
        if info.get('phien') == PHIEN and not info.get('loi'):
            shutil.copytree(cu, d); giu += 1
            continue
    if (time.time() - BAT_DAU) / 60 > A.han_phut:
        print('Hết giờ, để phần còn lại cho lượt sau.'); break
    os.makedirs(os.path.join(d, 'goc'), exist_ok=True)
    info = {'url': c['url'], 'loi': [], 'phien': PHIEN}
    try:
        body, cuoi = tai(c['url'])
        html = body.decode('utf-8', 'replace')
        open(os.path.join(d, 'trang.html'), 'w', encoding='utf-8').write(
            f'<!-- saved from url=({len(cuoi)}){cuoi} -->\n' + html)
        with tempfile.TemporaryDirectory() as w:
            r = subprocess.run([sys.executable, MG, 'trich', '--src', os.path.join(d, 'trang.html'),
                                '--work', w, '--chon', 'div.entry-content'], capture_output=True, text=True)
            info['trich'] = r.stdout.strip().splitlines()[-4:] + r.stderr.strip().splitlines()[-3:]
            media = json.load(open(os.path.join(w, 'media.json'))) if r.returncode == 0 else []
            if r.returncode != 0 and 'Không tìm thấy phần thân bài' in (r.stdout + r.stderr):
                # trang có thật nhưng thân bài rỗng (bản trùng/nháp của bài khác) → không có gì để dịch
                info['khong_ton_tai'] = True
                info['ly_do'] = 'trang gốc không có nội dung (thân bài rỗng — thường là bản trùng của bài khác)'
            elif r.returncode != 0:
                info['loi'].append('trich lỗi')
        for m in media:
            f = os.path.join(d, 'goc', m['name'])
            ok = False
            for u in [m['url']] + ([m['du_phong']] if m.get('du_phong') else []):
                try:
                    data, _ = tai(u)
                    data = gon_video(data, m['name'])
                    if len(data) > 95_000_000:
                        info['loi'].append(f'{u} quá 95 MB (kể cả sau khi nén), không lưu được trên GitHub'); ok = True; break
                    open(f, 'wb').write(gon_anh(data, m['name'])); ok = True
                    if u != m['url']:
                        info.setdefault('dung_du_phong', []).append(u)
                    break
                except urllib.error.HTTPError as e:
                    if e.code not in (404, 410):
                        info['loi'].append(f'{u} {e}'); ok = True; break
                except Exception as e:  # noqa
                    info['loi'].append(f'{u} {e}'); ok = True; break
                time.sleep(0.5)
            if not ok:
                info.setdefault('anh_mat', []).append(m['url'])
            time.sleep(0.5)
        info['so_media'] = len(media)
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            info['khong_ton_tai'] = True        # tác giả đã gỡ bài: không tải lại, lam_case đánh dấu
        else:
            info['loi'].append(f'trang: {e}')
    except Exception as e:  # noqa
        info['loi'].append(f'trang: {e}')
    info['luc'] = time.strftime('%Y-%m-%d %H:%M:%S')
    json.dump(info, open(os.path.join(d, 'nguon.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(s, 'media', info.get('so_media'), 'lỗi', len(info['loi']), 'mất', len(info.get('anh_mat', [])), flush=True)
    moi += 1
    time.sleep(4)
print(f'Xong: giữ lại {giu}, tải mới {moi}')
