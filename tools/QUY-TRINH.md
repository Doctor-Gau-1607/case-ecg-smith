# Quy trình một lượt dịch Case ECG — Dr. Smith’s ECG Blog

Mỗi lượt (tác vụ hẹn giờ) dịch các bài kế tiếp của **Dr. Smith’s ECG Blog** (drsmithsecgblog.com — người dùng đã gọi điện xin phép) sang tiếng Việt, dựng trang theo khung MEDGUIDE và đẩy lên `main` của repo `Doctor-Gau-1607/case-ecg-smith`. Trang công khai: `https://doctor-gau-1607.github.io/case-ecg-smith/` (nhúng trong MEDGUIDE: Cận lâm sàng → ECG → Case ECG).

- **Thứ tự:** từ bài **mới nhất lùi về cũ nhất** (`du-lieu/danh-sach.json` đã xếp sẵn theo thứ tự này). Nhãn `#N` đánh theo thứ tự thời gian (#1 = bài cũ nhất 2008).
- **Làm liên tục khoảng 45–50 phút mỗi lượt**, nhận theo đợt `chuan-bi --so 5`; case đã nhận mà chưa kịp làm thì `tra-lai` cuối lượt.
- **Kho trang (từ 01/10/2026):** repo này đã gần 900 MB nên trang + ảnh của case MỚI được dựng vào repo **`Doctor-Gau-1607/case-ecg-smith-2`** (GitHub Pages riêng). `lam_case.py` tự clone sparse kho này vào `/home/claude/kho/case-ecg-smith-2` và ghi `"kho": "case-ecg-smith-2"` vào case; `day-len` đẩy kho trang trước rồi đẩy danh sách. Repo chính vẫn giữ `index.html`, `du-lieu/`, `tools/`, nhánh `nguon` và trang các case cũ. Bị từ chối quyền với kho này thì gọi `add_repo` (owner `Doctor-Gau-1607`, repo `case-ecg-smith-2`, access `push`). Kho này đầy 900 MB thì báo người dùng tạo `case-ecg-smith-3` rồi đổi `KHO_MOI` trong `lam_case.py`.
- Nguồn (trang + ảnh gốc) do GitHub Actions tải sẵn vào nhánh `nguon` (chỉ giữ các case sắp dịch). **Không tự tải từ drsmithsecgblog.com** (container không truy cập được).

## 0. Chuẩn bị (mỗi lượt là một phiên mới)

```bash
cd /home/claude
git clone -q --depth 1 --filter=blob:none --sparse https://github.com/Doctor-Gau-1607/case-ecg-smith case-ecg-smith
cd case-ecg-smith && git sparse-checkout set tools du-lieu
git config user.name "Doctor-Gau-1607"; git config user.email "doctor.gau96@gmail.com"
pip list 2>/dev/null | grep -qi beautifulsoup4 || pip install -q --break-system-packages beautifulsoup4 lxml pillow
python3 tools/lam_case.py tien-do
```
Clone hoặc push bị từ chối vì quyền: gọi tool `add_repo` (owner `Doctor-Gau-1607`, repo `case-ecg-smith`, access `push`) rồi làm lại. Không tìm cách khác.

## 1. Nhận case
```bash
python3 tools/lam_case.py chuan-bi --so 5
```
- "KHÔNG CÒN CASE NÀO SẴN SÀNG" → dừng lượt, báo lại (hết việc hoặc nhánh nguon chưa tải tới).
- "DỪNG: kho … đã quá 900 MB" → dừng lượt, báo người dùng cần mở repo tiếp theo (giới hạn 1 GB của GitHub Pages).
- Case có ảnh gốc 404 được đánh `cho_anh` tự động, không dịch; trang gốc 404 (tác giả đã gỡ bài) được đánh `khong_ton_tai`. Ghi số lượng vào báo cáo.
- **Thông báo:** KHÔNG gửi thông báo về các case `cho_anh` ở từng lượt (chỉ ghi trong báo cáo). Chỉ khi `chuan-bi` báo "KHÔNG CÒN CASE NÀO SẴN SÀNG" (đã dịch hết mọi case có thể) mới gửi MỘT thông báo gom danh sách các case còn sót (`cho_anh`, `khong_ton_tai`, lỗi tải, `tra-lai`) để người dùng xử lý.

## 1b. Case `cho_anh` (ảnh gốc 404 từ máy chủ GitHub) — chỉ xử lý khi CÓ Claude in Chrome
Lượt hẹn giờ trên đám mây thường KHÔNG có Chrome: bỏ qua, chỉ ghi số lượng vào báo cáo. Không đăng case với ảnh báo/ảnh thiếu.
Phiên có công cụ `mcp__claude-in-chrome__*` (máy người dùng đang bật): mở trang gốc trong Chrome, lấy từng ảnh trong `anh_mat` (tên tệp đích: `/home/claude/cv/<slug>/W/media.json`, khoá `url`/`du_phong` → `name`; chạy `medguide.py trich` nếu chưa có), đặt vào `/home/claude/cv/_nguon/<slug>/goc/<name>`, kiểm mở được, sửa `nguon.json` (`anh_mat` → `anh_chrome`), rồi đặt case về `chua` và dịch/dựng như thường (lệnh `dung` đọc ảnh từ thư mục đó). Không đẩy lên nhánh `nguon` (workflow tự dựng lại nhánh này).

## 2. Dịch từng case
Với mỗi case: đọc `/home/claude/cv/<slug>/W/lo/lo-NNN.json`, dịch thành `lo-NNN.vi.json` **cùng id, cùng các trường**, chỉ thay chữ. Đọc `tools/thuat-ngu.md` trước khi dịch, dùng thống nhất; gặp thuật ngữ mới hay gặp thì **thêm vào** tệp này (một dòng).

Quy ước (người đọc là bác sĩ):
- Dịch **trọn vẹn**: không tóm tắt, không bỏ câu, không gộp/cắt khối, không thêm "Kết luận".
- Thuật ngữ tiếng Việt chuẩn, lần đầu trong bài kèm tiếng Anh trong ngoặc khi hay gặp trong y văn: "blốc phân nhánh trái sau (left posterior fascicular block)". Viết tắt quốc tế giữ nguyên: ECG, STEMI, OMI, NOMI, LBBB, RBBB, LAFB, LPFB, AV, PR, QRS, QTc, LVH, LAD, LCx, RCA, PCI, CABG, AFib, VT, SVT…
- Tên chuyển đạo giữ nguyên: I, II, III, aVR, aVL, aVF, V1–V6. "Queen of Hearts", "PMcardio" giữ nguyên.
- **Giữ nguyên mọi thẻ HTML và thuộc tính** (`<strong>`, `<em>`, `<span class="c-do">`, `<a href>`, `<li>`, `<tr><td style=…>`). Chỉ dịch chữ bên trong; được đổi vị trí thẻ theo trật tự câu tiếng Việt. **Số thẻ mỗi loại phải bằng bản gốc.**
- **Giữ mọi con số** (tần số, mm, ms, ngày, số hình, "#73"…).
- Nhãn hình: `Figure N`/`Figure-N` → "Hình N", `Table N` → "Bảng N", `Video N` → "Video N"; giữ nguyên số. `alts`/`caps` dịch đủ số phần tử.
- Tên người, tên blog, tiêu đề link tới bài khác giữ nguyên. Các dòng phân cách "= = =" giữ nguyên.
- Bình luận của Ken Grauer ("MY Comment, by KEN GRAUER, MD") → "<em>BÌNH LUẬN CỦA TÔI</em>, bởi KEN GRAUER, MD" (giữ thẻ).
- Hai trường tùy chọn, chỉ khi thật cần: `"nang": 2|3` (đoạn chỉ gồm một ý in đậm làm đầu mục → tiêu đề, để mục lục không trống; ví dụ phần "MY Comment" → 2, các đầu mục in đậm trong bình luận → 3); `"note": true` (câu chốt tác giả nhấn mạnh → hộp nổi).
- Bài dài: có thể giao từng lô cho agent con, kèm nguyên tệp này và `thuat-ngu.md`; tự đọc lại chỗ nối.

Tiêu đề (`--title`): dịch tiêu đề tiếng Anh (dòng "Tiêu đề gốc" ở bước 1). **Không tự thêm ngày** — công cụ tự ghép "dd/mm/yyyy — " theo ngày đăng.
Từ khoá (`--tu-khoa`): 8–20 từ tiếng Việt + Anh về chẩn đoán/dấu hiệu chính.

## 3. Dựng + kiểm
```bash
python3 tools/lam_case.py dung --slug <slug> --title "<tiêu đề tiếng Việt>" --tu-khoa "<từ khoá>"
```
- Ảnh tự đổi sang JPEG (rộng tối đa 1600 px) cho nhẹ repo — người dùng đã đồng ý.
- `CHƯA ĐẠT` (LỖI số thẻ lệch, khối chưa dịch, y hệt bản gốc…): sửa `lo-*.vi.json`, chạy lại.
- Đọc từng dòng `CẢNH BÁO` (số thiếu/thừa, còn câu tiếng Anh dài): sửa nếu đúng là sót.
- Không sửa được sau 3 lần: `python3 tools/lam_case.py tra-lai --slug <slug> --ly-do "<vì sao>"` và làm case khác.

## 4. Đẩy lên
```bash
python3 tools/lam_case.py day-len
python3 tools/lam_case.py tien-do
```
Đẩy **sau mỗi case xong** (an toàn hơn nếu lượt bị ngắt giữa chừng).

## 5. Báo cáo cuối lượt
Một đoạn ngắn: case nào xong (nhãn + tiêu đề tiếng Việt), case nào trả lại / chờ ảnh và lý do, tiến độ tổng (xong/tổng), dung lượng c/, có lỗi gì cần người xem.

## Không được làm
- Không sửa giao diện `index.html`, không động tới repo MEDGUIDE (`Dr.Gau`) hay `case-ecg`, không xoá case đã xong.
- Không đổi `tools/medguide.py`, `tools/tai_nguon.py`, workflow — thấy lỗi công cụ thì ghi vào báo cáo.
