# Phân loại ảnh local bằng Streamlit

Bản hiện tại xử lý JPG/JPEG/PNG bằng **khuôn mặt**, có tùy chọn **hỗ trợ trang phục và phát hiện dáng/toàn thân**, chạy CPU trên máy. Nhập thư mục nguồn và kết quả, tạo người và chọn nhiều ảnh mẫu, chạy phân loại rồi xem thumbnail để gán sửa. Không cần tài khoản/API key/GPU. Không có dịch vụ cloud nhận ảnh.

## Chạy trên Windows

Cài Python **3.11, 3.12 hoặc 3.13 64-bit** (chọn Add Python to PATH). Mở PowerShell tại thư mục dự án:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe download_models.py
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Nếu dùng Python 3.11 hoặc 3.13, đổi lệnh đầu thành `py -3.11` hoặc `py -3.13`. Không cần activate môi trường hay đổi ExecutionPolicy. Sau khi cài, có thể nhấp đúp **run_windows.bat**. Mở **http://127.0.0.1:8501** nếu trình duyệt chưa tự mở. Dừng server bằng Ctrl+C ở cửa sổ terminal.

Chỉ quá trình cài thư viện và tải model cần Internet. Có thể bỏ lệnh `download_models.py` rồi bấm **Tải / kiểm tra model** trong UI. Sau đó ứng dụng hoạt động offline. Cấu hình tắt telemetry Streamlit và chỉ bind loopback nằm trong `.streamlit/config.toml`.

## Cách dùng

1. Tab **Người & ảnh mẫu**: nhập tên, ví dụ `Huyền`; chọn người rồi upload nhiều JPG/JPEG/PNG. Nhấn **Kiểm tra và lưu ảnh mẫu**. Dùng 3–10 mẫu rõ, nhiều góc mặt, chỉ một mặt mỗi mẫu. Ảnh có nhiều mặt hoặc mặt quá nhỏ bị từ chối để không chọn nhầm người. Xóa mẫu sai bằng nút cạnh thumbnail.
2. Tab **Phân loại**: nhập đường dẫn đầy đủ nguồn và kết quả, ví dụ `D:\BuoiChup\AnhGoc` và `D:\BuoiChup\KetQua`. Đây là đường dẫn trên máy đang chạy Python. Không để hai thư mục nằm trong nhau. Công cụ quét đệ quy thư mục con.
3. Bấm **Bắt đầu / chạy tiếp**. Mặc định xử lý tối đa 100 ảnh mới/lượt. Theo dõi tiến độ, thumbnail và số ảnh bỏ qua/đã xử lý/lỗi. Chạy tiếp cho phần còn lại. Để dừng có thể dùng nút Stop của Streamlit; kết quả đã hoàn thành được giữ lại.
4. Tab **Xem & sửa**: xem thống kê, lọc theo tên/Nhóm/Chưa phân loại, xem mỗi trang 12 ảnh, chọn **Gán lại → Lưu phân loại**. Thay đổi được áp dụng vào thư mục kết quả ngay. Có thể thêm người mới rồi gán tay.

Kết quả:

```text
KetQua/
  Huyền/
  Người khác/
  Nhóm/
  Chưa phân loại/
```

## Quy tắc khi chỉ dùng mặt

- YuNet phát hiện mặt, SFace tạo vector đặc trưng; cosine lớn nhất giữa mặt và các ảnh mẫu của mỗi người được dùng để xếp hạng.
- Một mặt chính chỉ được gán người khi cosine ≥ **0.50** và cách người đứng thứ hai ≥ **0.10**. Nếu chỉ có một người đăng ký, vẫn phải vượt ngưỡng cosine. Không đủ điều kiện thì **Chưa phân loại**. Điểm cosine không phải phần trăm chắc chắn.
- Từ hai **mặt chính** trở lên vào **Nhóm**, kể cả người chưa đăng ký; không cần xác định danh tính tất cả thành viên.
- Mặt chính có diện tích ít nhất **20% mặt lớn nhất** và **0.1% diện tích ảnh**. Các mặt nhỏ hơn được coi là hậu cảnh. Có thể đổi trong thanh bên.
- Không có mặt, quay lưng, bị che, mặt quá nhỏ hoặc kết quả dễ nhầm → **Chưa phân loại**. Mặt đơn cần chiều nhỏ nhất ≥ 40 px sau thu nhỏ để được nhận diện; mẫu cần ≥ 60 px.
- Ảnh được xoay đúng EXIF và thu nhỏ cạnh dài tối đa 1800 px để suy luận. File xuất là bản copy byte-for-byte của ảnh gốc, không phải ảnh thu nhỏ.

**Giới hạn:** Kích thước mặt chỉ là cách ước lượng chủ thể. Người đi đường đứng gần có thể khiến ảnh vào Nhóm; người chính đứng xa hoặc quay lưng có thể bị bỏ sót. Khi tắt hỗ trợ dáng, tool không phát hiện toàn thân nên có thể bỏ sót người không thấy mặt. Khi bật, model tư thế cũng có thể bỏ sót hoặc phát hiện nhầm. Cần duyệt lại ảnh quan trọng. Ngưỡng mặc định thận trọng nhưng vẫn cần hiệu chỉnh trên buổi chụp thực tế.

## Lưu cấu hình và chạy tiếp

- `data/catalog.sqlite`: danh sách người, vector mặt, nhật ký phân loại và các chỉnh sửa tay.
- `data/outfits/`: ảnh mẫu trang phục; vector và tên buổi chụp nằm trong bảng `outfits` của SQLite. Tạo bảng bổ sung tự động, giữ nguyên dữ liệu cũ.
- `data/samples/`: bản sao ảnh mẫu. Không phụ thuộc file mẫu ở vị trí cũ.
- `data/settings.json`: hai thư mục, tên buổi chụp và trạng thái bật trang phục được sử dụng ở lượt chạy gần nhất. Ngưỡng được ghi trong chi tiết từng kết quả; khi khởi động lại UI dùng ngưỡng mặc định.
- `models/`: hai model ONNX. Sao lưu cả `data/` và `models/` để giữ cấu hình; bản hiện tại lưu đường dẫn tuyệt đối, nên giữ nguyên vị trí thư mục dự án khi khôi phục.
- Định danh xử lý gồm thư mục nguồn, kết quả, đường dẫn ảnh và SHA-256 nội dung. Lượt sau vẫn đọc để kiểm tra hash nhưng không chạy nhận diện/copy lại ảnh đã xong có bản copy hợp lệ. Ảnh có nội dung mới tại cùng đường dẫn được xem là phiên bản mới; bản kết quả cũ vẫn được giữ.
- Kết quả được lưu sau từng ảnh. Ý định copy được ghi trước thao tác file để phục hồi nếu ứng dụng bị dừng. Khóa liên tiến trình ngăn hai phiên đồng thời thay đổi dữ liệu.
- Đổi ảnh mẫu/ngưỡng không tự thay đổi kết quả đã xong hoặc sửa tay. Có thể bật **Thử lại ảnh Chưa phân loại với mẫu/cấu hình mới**: chỉ xét lại ảnh tự động chưa phân loại khi dấu vân tay cấu hình thay đổi; không lặp mãi cùng ảnh qua các lượt 100 ảnh. Mọi ảnh đã gán tay đều được bỏ qua khi bản copy còn hợp lệ. Muốn nhận diện lại toàn bộ theo cấu hình mới, chọn **thư mục kết quả mới**; hoặc gán lại thủ công từng ảnh.
- File ảnh hỏng/không đọc được báo lỗi và được thử lại lượt sau, không đánh dấu đã phân loại.

## Bảo toàn file

Nguồn chỉ được đọc. File đích được tạo độc quyền, không ghi đè; trùng tên được thêm hậu tố UUID. Gán lại sẽ copy vào thư mục mới rồi chỉ xóa bản kết quả cũ do ứng dụng quản lý nếu hash vẫn khớp. Bản kết quả đã được người dùng chỉnh sửa bên ngoài được giữ nguyên.

Nếu hệ điều hành dừng giữa lúc ghi file, có thể còn bản copy thiếu trong kết quả. Chạy tiếp tạo bản đầy đủ dưới tên khác nếu file đó không khớp hash; bản không khớp được giữ để tránh xóa file người dùng đã thay đổi. Dữ liệu sinh trắc học và ảnh mẫu nằm local trong `data/`; không chia sẻ thư mục này nếu không có chủ ý.

## Model và nguồn tải

- **YuNet**: `face_detection_yunet_2023mar.onnx` (~0.23 MB), phát hiện mặt và 5 landmark. [Model và giấy phép MIT tại OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet).
- **SFace**: `face_recognition_sface_2021dec.onnx` (~37 MB), vector nhận diện mặt. [Model và giấy phép Apache 2.0 tại OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface).
- Model tải từ `media.githubusercontent.com/media/opencv/opencv_zoo/main/models/...`; kiểm tra SHA-256 theo Git LFS pointer chính thức trước khi thay file. Nếu mạng bị chặn, tải hai file ONNX chính thức trên máy khác, chép đúng tên vào `models/`. Không dùng file pointer Git LFS vài trăm byte thay cho model thật.
- [Tài liệu OpenCV về YuNet/SFace](https://docs.opencv.org/4.10.0/d0/dd4/tutorial_dnn_face.html) dùng cosine 0.363 làm ví dụ; ứng dụng chọn 0.50 và thêm điều kiện cách biệt để ưu tiên không đoán ép. Đây không phải mức đảm bảo độ chính xác cho mọi bộ ảnh.

## Bật trang phục/dáng (bản cập nhật)

Dừng ứng dụng bằng Ctrl+C trước khi cập nhật thư viện. Với máy đã cài bản cũ, chạy trong PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y opencv-python-headless
.\.venv\Scripts\python.exe -m pip install -r requirements-appearance.txt
.\.venv\Scripts\python.exe download_appearance.py
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Bản mới dùng `opencv-python` để tương thích với dependency của Ultralytics; không cài đồng thời bản headless và bản thường vì cả hai cùng cung cấp `cv2`. Lần cài thêm có **PyTorch**, dung lượng lớn hơn nhiều so với model mặt và có thể mất vài phút. Không cần CUDA/GPU. Chế độ chỉ dùng mặt vẫn hoạt động khi chưa cài bộ dependency tùy chọn.

1. Bật **Hỗ trợ trang phục/dáng** trong thanh bên, nhập **tên buổi chụp riêng** (ví dụ `DaLat-2026-10-26`). Tên buổi đã có mẫu được hiển thị bên dưới để dùng lại. Nếu đổi trang phục giữa buổi, có thể thêm nhiều mẫu cho mỗi bộ đồ hoặc dùng tên buổi/đợt riêng.
2. Ở tab Người, chọn người rồi thêm **ít nhất 2 ảnh mẫu trang phục khác nhau** trong đúng buổi đó. Ảnh cần chỉ có một người, thấy rõ vai và hông; có thể quay lưng. Tool không tự lấy trang phục từ ảnh mặt cũ vì chúng có thể thuộc buổi khác.
3. Chạy phân loại như trước. Muốn cập nhật ảnh cũ còn chưa phân loại, đánh dấu **Thử lại ảnh Chưa phân loại với mẫu/cấu hình mới**.
4. Tab xem/sửa sẽ hiện **Gợi ý theo trang phục** nếu có. Chọn người rồi bấm Lưu phân loại để xác nhận. Gợi ý chưa được coi là kết quả chắc chắn.

### Cơ chế mới

- **YOLO11n-pose**, file `yolo11n-pose.pt`, tìm hộp toàn thân và 17 điểm khớp. Chạy CPU local. [Tài liệu model chính thức](https://docs.ultralytics.com/models/yolo11/) và [định dạng keypoint](https://docs.ultralytics.com/tasks/pose/).
- Hai toàn thân chính trở lên → Nhóm, kể cả không thấy mặt. Toàn thân chính cần diện tích ít nhất 25% người lớn nhất và 2.5% ảnh. Đây vẫn là heuristic lọc hậu cảnh, không hiểu ý đồ buổi chụp.
- Dùng vai/hông xác định vùng áo, hông/gối xác định vùng quần nếu có. Thu vùng lấy màu vào trong để giảm nền. So sánh histogram màu HSV của từng vùng (áo 70%, quần 30% khi có cả hai); không có phần quần thì so áo. Chưa có mô hình re-identification hay nhận dạng dáng đi.
- Mặt đủ chắc vẫn là tín hiệu quyết định. Nếu mặt thiếu một chút độ chắc: phải cùng ứng viên với trang phục, có ít nhất 2 mẫu, điểm màu trung bình hai mẫu gần nhất ≥ 0.88, cách người tiếp theo ≥ 0.12. Mặt vẫn cần cosine ≥ max(0.40, ngưỡng người dùng − 0.08) và cách biệt ≥ max(0.04, một nửa cách biệt người dùng).
- **Không thấy mặt hoặc mặt quá yếu: không tự gán người chỉ nhờ quần áo.** Có thể hiển thị gợi ý từ điểm màu ≥ 0.75 để duyệt. Người mặc giống nhau, ánh sáng khác nhau, áo bị che hoặc vùng người chồng nhau đều có thể gây nhầm.
- Dáng được dùng định vị cơ thể và vùng trang phục, **không phải nhận diện danh tính từ hình thể**. Mẫu không thấy vai/hông rõ bị từ chối.
- Mẫu được tách theo tên buổi; dữ liệu không tự học từ các ảnh tool vừa đoán, tránh lan truyền gán nhầm.

Model tải bằng nút trong UI hoặc `download_appearance.py`, từ [release chính thức v8.3.0](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-pose.pt). Script hiển thị số MB đã tải, kiểm tra định dạng archive trước khi lưu. Model tư thế không có kiểm tra SHA-256 upstream như model mặt. Chỉ dùng file model từ nguồn chính thức. Có thể tải ở máy khác rồi chép vào `models/`.

Ultralytics/model thuộc điều khoản [AGPL-3.0 hoặc giấy phép Enterprise](https://www.ultralytics.com/license); đây là dependency tùy chọn, cần xem điều khoản nếu phân phối sản phẩm. Suy luận không tự tải model/gói; cấu hình offline và tắt đồng bộ được áp dụng trước khi tạo model.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Các kiểm thử gồm: không nhận diện chỉ bằng áo, mặt/trang phục mâu thuẫn, trang phục giống nhau, hỗ trợ mặt gần ngưỡng, giữ ưu tiên mặt rõ, tách buổi, lưu mẫu qua khởi động lại, bảo toàn sửa tay và không lặp ảnh chưa phân loại với cùng cấu hình. Các kiểm thử ảnh tổng hợp/pipeline không cần tải model nhưng cần numpy/OpenCV/Pillow.

Môi trường phát triển đã chạy 16 kiểm thử logic/lưu trữ và kiểm tra cú pháp thành công. Sáu kiểm thử xử lý ảnh/pipeline bị bỏ qua do thiếu thư viện. Chưa chạy giao diện hoặc suy luận YOLO thực tế: mạng tải gói bị chặn, Python Windows trong `.venv` không chạy được từ môi trường WSL này. Chưa có số đo độ chính xác trên ảnh chụp của bạn.

Trước khi chạy cả buổi, thử bộ nhỏ có ảnh đơn, nhóm, quay lưng, người mặc giống nhau và người nhỏ hậu cảnh; duyệt gợi ý và kiểm tra gán lại. Ngưỡng mặc định là quy tắc thận trọng, không phải xác suất hay cam kết độ chính xác.

## Xóa người khỏi nhận diện

Trong tab **Người & ảnh mẫu**, chọn người → mở **Xóa người khỏi danh sách nhận diện** → bấm **Xóa [tên] khỏi nhận diện**. Tool xóa người, vector và ảnh mẫu mặt/trang phục ở tất cả buổi chụp. Ảnh nguồn, bản copy kết quả và lịch sử phân loại giữ nguyên; nhãn tên cũ vẫn có thể xuất hiện trong lịch sử. Các lượt nhận diện sau không xét người đã xóa. Có thể thêm lại cùng tên và đăng ký mẫu mới. Nếu file mẫu đang bị chương trình khác giữ, tool báo file chưa dọn được nhưng dữ liệu nhận diện vẫn đã bị loại bỏ.

## Tùy chỉnh ngưỡng dáng/trang phục

Thanh bên có nhóm **Ngưỡng dáng & trang phục**:

- **Độ tin cậy phát hiện toàn thân**: mặc định 0.55. Giảm để phát hiện người khó thấy hơn, nhưng tăng nguy cơ phát hiện nhầm.
- **Diện tích người / người lớn nhất**: mặc định 0.25; **Diện tích người / ảnh tối thiểu**: 0.025. Giảm để tính người nhỏ/xa là người chính; có thể đưa người hậu cảnh vào Nhóm.
- **Tương đồng trang phục để hỗ trợ gán người**: mặc định 0.88; **Cách biệt trang phục với người thứ hai**: 0.12. Điều chỉnh hai ngưỡng này không bỏ yêu cầu có mặt đủ bằng chứng và ít nhất hai mẫu trang phục.
- **Tương đồng trang phục để hiện gợi ý**: mặc định 0.75. Ví dụ điểm 0.6122 sẽ hiện gợi ý nếu đặt 0.60. Không thấy mặt vẫn không tự gán người.

Bấm **Lưu ngưỡng dáng/trang phục** để lưu ngay; bắt đầu phân loại cũng tự lưu. Ngưỡng được ghi trong chi tiết từng kết quả và tính vào dấu vân tay cấu hình. Sau khi đổi, bật **Thử lại ảnh Chưa phân loại với mẫu/cấu hình mới** để áp dụng cho ảnh cũ chưa phân loại; ảnh sửa tay giữ nguyên. Các ngưỡng mới không thay đổi bước kiểm tra chất lượng ảnh mẫu.
