from pathlib import Path
from collections import Counter
import json
import hashlib
import tempfile
import streamlit as st
from PIL import Image, ImageOps
from filelock import FileLock, Timeout
from photo_sorter.storage import Store, SPECIAL, validate_roots, scan, sha256
from photo_sorter.vision import FaceEngine, download_models, MODELS, read_image
from photo_sorter.appearance import AppearanceEngine, download_pose

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'
MODEL_DIR = BASE / 'models'
DATA.mkdir(exist_ok=True)
st.set_page_config(page_title='Phân loại ảnh local', layout='wide')
st.title('Phân loại ảnh sau buổi chụp')
st.caption('JPG · JPEG · PNG | Xử lý trên máy | Copy nguyên bản | Nhận diện mặt + hỗ trợ trang phục/dáng')
store = Store(DATA)
lock = FileLock(str(DATA / 'processing.lock'), timeout=0)


def thumbnail(path):
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert('RGB')
            im.thumbnail((420, 280))
            st.image(im)
    except Exception as exc:
        st.caption(f'Không xem được ảnh: {exc}')


def engine():
    return FaceEngine(MODEL_DIR)


# Paths are shared by processing and review and survive app restarts.
settings_path = DATA / 'settings.json'
try:
    saved = json.loads(settings_path.read_text('utf-8')) if settings_path.exists() else {}
except (ValueError, OSError):
    saved = {}

with st.sidebar:
    st.header('Model local')
    ready = all((MODEL_DIR / n).is_file() for n in MODELS)
    st.write('✅ Đã có model' if ready else 'Cần tải model lần đầu (~39 MB)')
    if st.button('Tải / kiểm tra model'):
        try:
            with lock, st.spinner('Tải YuNet và SFace từ OpenCV Zoo…'):
                download_models(MODEL_DIR)
            st.success('Model sẵn sàng. Có thể ngắt Internet.')
        except Exception as exc:
            st.error(str(exc))
    st.caption('Chỉ tải model dùng Internet. Ảnh và đặc trưng mặt không gửi ra ngoài.')
    st.header('Trang phục & dáng')
    use_appearance = st.checkbox('Bật hỗ trợ trang phục/dáng', value=saved.get('appearance', False))
    session = st.text_input('Tên buổi chụp', value=saved.get('session', ''), placeholder='DaLat-2026-10-26')
    known_sessions = [r[0] for r in store.db.execute('SELECT DISTINCT session FROM outfits ORDER BY session')]
    if known_sessions:
        st.caption('Buổi đã lưu: ' + ' · '.join(known_sessions))
    st.caption('Dùng tên buổi riêng để không trộn trang phục khác ngày. Dáng dùng tìm người/vùng quần áo, không xác định danh tính.')
    if st.button('Tải model dáng/trang phục'):
        try:
            with lock, st.spinner('Tải YOLO11n-pose…'):
                progress_bar = st.progress(0.0)
                def update_download(done, total):
                    progress_bar.progress(min(done / total, 1.0) if total else 0.0,
                                          text=f'Đã tải {done / 1048576:.1f} MB')
                download_pose(MODEL_DIR, update_download)
            st.success('Đã tải model tư thế.')
        except Exception as exc:
            st.error(str(exc))
    st.caption('Cần cài requirements-appearance.txt. Mất thêm thời gian chạy CPU. Không thấy mặt: chỉ gợi ý để duyệt.')
    st.header('Ngưỡng phân loại')
    threshold = st.slider('Cosine tối thiểu', 0.30, 0.90, 0.50, 0.01)
    margin = st.slider('Cách biệt với người đứng thứ hai', 0.01, 0.30, 0.10, 0.01)
    relative = st.slider('Diện tích mặt / mặt lớn nhất', 0.05, 0.60, 0.20, 0.05)
    fraction = st.number_input('Diện tích mặt / ảnh tối thiểu', 0.0001, 0.05, 0.001, 0.0005, format='%.4f')
    st.caption('Cosine không phải xác suất. Tăng ngưỡng để giảm gán nhầm. Lọc hậu cảnh dựa vào kích thước mặt, có thể bỏ sót người đứng xa.')

    st.header('Ngưỡng dáng & trang phục')
    previous_appearance = saved.get('appearance_settings', {})
    body_confidence = st.slider('Độ tin cậy phát hiện toàn thân', 0.20, 0.95,
                                previous_appearance.get('body_confidence', 0.55), 0.01)
    body_relative = st.slider('Diện tích người / người lớn nhất', 0.05, 0.80,
                              previous_appearance.get('body_relative', 0.25), 0.05)
    body_minimum = st.number_input('Diện tích người / ảnh tối thiểu', 0.001, 0.25,
                                   previous_appearance.get('body_minimum', 0.025), 0.005, format='%.3f')
    st.caption('Giảm các ngưỡng trên để bắt người nhỏ/xa hơn; có thể tính cả người đi đường vào Nhóm.')
    outfit_threshold = st.slider('Tương đồng trang phục để hỗ trợ gán người', 0.50, 0.99,
                                 previous_appearance.get('outfit_threshold', 0.88), 0.01)
    outfit_margin = st.slider('Cách biệt trang phục với người thứ hai', 0.01, 0.40,
                              previous_appearance.get('outfit_margin', 0.12), 0.01)
    suggestion_threshold = st.slider('Tương đồng trang phục để hiện gợi ý', 0.30, 0.99,
                                     previous_appearance.get('suggestion_threshold', 0.75), 0.01)
    st.caption('Không thấy mặt vẫn chỉ gợi ý. Hạ ngưỡng trang phục dễ nhầm người mặc giống nhau. Các ngưỡng này chỉ dùng khi bật hỗ trợ dáng/trang phục.')
    appearance_settings = dict(body_confidence=body_confidence, body_relative=body_relative,
                               body_minimum=body_minimum, outfit_threshold=outfit_threshold,
                               outfit_margin=outfit_margin, suggestion_threshold=suggestion_threshold)
    if st.button('Lưu ngưỡng dáng/trang phục'):
        try:
            with lock:
                current_settings = json.loads(settings_path.read_text('utf-8')) if settings_path.exists() else {}
                current_settings['appearance_settings'] = appearance_settings
                settings_path.write_text(json.dumps(current_settings, ensure_ascii=False), 'utf-8')
            st.success('Đã lưu ngưỡng cho lần mở sau.')
        except Exception as exc:
            st.error(str(exc))

people_tab, run_tab, review_tab = st.tabs(['1. Người & ảnh mẫu', '2. Phân loại', '3. Xem & sửa'])
with people_tab:
    if 'person_deleted' in st.session_state:
        st.success(st.session_state.pop('person_deleted'))
    if 'cleanup_warning' in st.session_state:
        st.warning('Đã bỏ dữ liệu nhận diện, nhưng chưa xóa được một số file mẫu: ' + ', '.join(st.session_state.pop('cleanup_warning')))
    with st.form('person', clear_on_submit=True):
        name = st.text_input('Tên người', placeholder='Nhập tên người cần phân loại')
        if st.form_submit_button('Thêm người'):
            try:
                with lock:
                    store.add_person(name)
                st.success('Đã lưu người.')
            except Exception as exc:
                st.error(str(exc))
    people = store.people()
    if people:
        person = st.selectbox('Người cần thêm ảnh mẫu', people)
        with st.expander('Xóa người khỏi danh sách nhận diện'):
            st.caption('Xóa người đang chọn cùng toàn bộ mẫu mặt và trang phục ở mọi buổi chụp. Ảnh gốc và kết quả đã phân loại được giữ nguyên.')
            if st.button(f'Xóa {person} khỏi nhận diện', key='delete_person_' + person):
                try:
                    with lock:
                        remaining = store.remove_person(person)
                    if remaining:
                        st.session_state['cleanup_warning'] = remaining
                    st.session_state['person_deleted'] = f'Đã xóa {person} khỏi danh sách nhận diện.'
                    st.rerun()
                except Timeout:
                    st.error('Đang có phiên xử lý. Hãy đợi phiên đó xong rồi xóa người.')
                except Exception as exc:
                    st.error(str(exc))
        st.caption('Chọn 3–10 ảnh rõ, chỉ có một khuôn mặt mỗi ảnh; nên có nhiều góc và ánh sáng khác nhau.')
        uploads = st.file_uploader('Chọn nhiều ảnh mẫu', type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
        if st.button('Kiểm tra và lưu ảnh mẫu', disabled=not uploads):
            try:
                with lock:
                    recognizer = engine()
                    for upload in uploads:
                        try:
                            payload = upload.getvalue()
                            with tempfile.TemporaryDirectory() as tmp:
                                path = Path(tmp) / ('sample' + Path(upload.name).suffix.lower())
                                path.write_bytes(payload)
                                feature = recognizer.enroll(path)
                            added = store.add_sample(person, payload, Path(upload.name).suffix, feature)
                            st.success(f'{upload.name}: ' + ('đã lưu' if added else 'đã có, bỏ qua'))
                        except Exception as exc:
                            st.warning(f'{upload.name}: {exc}')
            except Exception as exc:
                st.error(str(exc))
        samples = store.samples(person)
        st.write(f'{person}: {len(samples)} ảnh mẫu hợp lệ')
        for i, sample in enumerate(samples):
            with st.expander(f'Ảnh mẫu {i + 1}'):
                thumbnail(sample['path'])
                if st.button('Xóa ảnh mẫu', key=sample['id']):
                    try:
                        with lock:
                            store.remove_sample(sample['id'])
                        st.rerun()
                    except Timeout:
                        st.error('Đang có phiên khác xử lý.')
        st.subheader('Ảnh mẫu trang phục của buổi chụp')
        st.caption('Chọn ít nhất 2 ảnh khác nhau của đúng người đang chọn, thấy rõ vai/hông. Có thể dùng ảnh quay lưng; bạn chịu trách nhiệm chọn đúng người.')
        if session.strip():
            st.write(f'Buổi: {session.strip()} · Người: {person}')
            outfit_uploads = st.file_uploader('Chọn ảnh mẫu trang phục', type=['jpg', 'jpeg', 'png'],
                                            accept_multiple_files=True, key='outfit_uploads')
            if st.button('Lưu mẫu trang phục', disabled=not outfit_uploads):
                try:
                    with lock:
                        body_engine = AppearanceEngine(MODEL_DIR)
                        for upload in outfit_uploads:
                            try:
                                payload = upload.getvalue()
                                with tempfile.TemporaryDirectory() as tmp:
                                    path = Path(tmp) / ('outfit' + Path(upload.name).suffix.lower())
                                    path.write_bytes(payload)
                                    descriptor = body_engine.enroll(read_image(path))
                                added = store.add_outfit(session.strip(), person, payload,
                                                         Path(upload.name).suffix, descriptor)
                                st.success(f'{upload.name}: ' + ('đã lưu' if added else 'đã có, bỏ qua'))
                            except Exception as exc:
                                st.warning(f'{upload.name}: {exc}')
                except Exception as exc:
                    st.error(str(exc))
            for outfit in store.outfit_samples(session.strip(), person):
                with st.expander('Mẫu trang phục ' + outfit['id'][:8]):
                    thumbnail(outfit['path'])
                    if st.button('Xóa mẫu trang phục', key='delete_outfit_' + outfit['id']):
                        try:
                            with lock:
                                store.remove_outfit(outfit['id'])
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
        else:
            st.info('Nhập tên buổi chụp trong thanh bên để lưu mẫu trang phục.')
    else:
        st.info('Thêm ít nhất một người rồi chọn ảnh mẫu.')

with run_tab:
    source_text = st.text_input('Thư mục ảnh nguồn (quét cả thư mục con)', value=saved.get('source', ''), placeholder=r'D:\BuoiChup\AnhGoc')
    output_text = st.text_input('Thư mục kết quả', value=saved.get('output', ''), placeholder=r'D:\BuoiChup\KetQua')
    batch = st.number_input('Số ảnh tối đa mỗi lượt (chạy tiếp để xử lý phần còn lại)', 1, 10000, 100)
    st.caption('Mỗi ảnh hoàn thành được lưu ngay. Chạy tiếp bỏ qua ảnh đã xong, kể cả kết quả sửa tay. Đổi mẫu/ngưỡng không tự phân loại lại ảnh cũ.')
    retry_unknown = st.checkbox('Thử lại ảnh Chưa phân loại với mẫu/cấu hình mới (giữ ảnh gán tay)')
    if st.button('Bắt đầu / chạy tiếp', type='primary'):
        try:
            if not source_text.strip() or not output_text.strip():
                raise ValueError('Nhập đủ hai thư mục.')
            with lock:
                source, output = validate_roots(source_text, output_text, DATA)
                if use_appearance and not session.strip():
                    raise ValueError('Nhập tên buổi chụp khi bật hỗ trợ trang phục/dáng.')
                settings_path.write_text(json.dumps({'source': str(source), 'output': str(output),
                                                    'session': session.strip(), 'appearance': use_appearance,
                                                    'appearance_settings': appearance_settings}, ensure_ascii=False), 'utf-8')
                for pending in store.records(source, output):
                    if pending['status'] == 'pending':
                        try:
                            store.finish(pending['id'])
                        except Exception as exc:
                            st.warning(f"Chưa phục hồi được {pending['source']}: {exc}")
                recognizer = engine()
                body_engine = AppearanceEngine(MODEL_DIR) if use_appearance else None
                outfits = store.outfit_profiles(session.strip()) if use_appearance else {}
                if use_appearance and not any(outfits.values()):
                    st.warning('Buổi này chưa có mẫu trang phục; chỉ bổ sung phát hiện toàn thân/nhóm.')
                embeddings = store.embeddings()
                if not any(embeddings.values()):
                    raise ValueError('Cần ít nhất một ảnh mẫu hợp lệ trước khi chạy.')
                signature = hashlib.sha256(json.dumps({
                    'version': 'appearance-v1', 'people': embeddings, 'outfits': outfits,
                    'threshold': threshold, 'margin': margin, 'relative': relative,
                    'fraction': fraction, 'appearance': use_appearance, 'session': session.strip(),
                    'appearance_settings': appearance_settings,
                }, sort_keys=True).encode()).hexdigest()
                paths = scan(source)
                bar = st.progress(0.0)
                status = st.empty()
                preview = st.empty()
                counts = Counter()
                for i, path in enumerate(paths):
                    status.write(f'{i + 1}/{len(paths)} — {path.name}')
                    try:
                        digest = sha256(path)
                        key = store.identity(path, source, output, digest)
                        if store.done(key) and not (retry_unknown and store.retry_unknown(key, signature)):
                            counts['Bỏ qua'] += 1
                        else:
                            label, reason, details = recognizer.classify(path, embeddings, threshold, margin, relative, fraction,
                                                                        appearance=body_engine, outfits=outfits,
                                                                        appearance_settings=appearance_settings)
                            details['processing_signature'] = signature
                            details['settings'] = {'threshold': threshold, 'margin': margin, 'relative_area': relative, 'min_fraction': fraction,
                                                   'appearance': use_appearance, 'session': session.strip(),
                                                   'appearance_settings': appearance_settings}
                            store.save(key, path, source, output, digest, label, reason, details)
                            counts['Đã xử lý'] += 1
                            with preview.container():
                                thumbnail(path)
                                st.write(f'{path.name} → {label}')
                    except Exception as exc:
                        counts['Lỗi'] += 1
                        st.warning(f'{path.name}: {exc} (sẽ thử lại ở lượt sau)')
                    bar.progress((i + 1) / max(len(paths), 1))
                    if counts['Đã xử lý'] + counts['Lỗi'] >= batch:
                        break
                st.success('Lượt xử lý kết thúc. ' + ' · '.join(f'{k}: {v}' for k, v in counts.items()))
                if not paths:
                    st.info('Không tìm thấy JPG/JPEG/PNG.')
        except Timeout:
            st.error('Một phiên khác đang xử lý. Hãy chờ phiên đó hoàn thành.')
        except Exception as exc:
            st.error(str(exc))

with review_tab:
    if source_text.strip() and output_text.strip():
        source, output = Path(source_text).resolve(), Path(output_text).resolve()
        rows = store.records(source, output)
        done = [r for r in rows if r['status'] == 'done']
        stats = Counter(r['label'] for r in done)
        st.write(f'Tổng đã xong: {len(done)} · Chờ phục hồi copy: {len(rows) - len(done)}')
        if stats:
            st.dataframe([{'Phân loại': k, 'Số ảnh': v} for k, v in stats.items()], hide_index=True)
        selected = st.selectbox('Lọc kết quả', ['Tất cả'] + sorted(stats))
        filtered = [r for r in done if selected == 'Tất cả' or r['label'] == selected]
        page = st.number_input('Trang (12 ảnh/trang)', 1, max(1, (len(filtered) + 11) // 12), 1)
        for row in filtered[(page - 1) * 12:page * 12]:
            with st.container(border=True):
                left, right = st.columns([1, 2])
                with left:
                    thumbnail(row['destination'])
                with right:
                    st.write(Path(row['source']).name)
                    st.caption(row['source'])
                    st.write(f"{row['label']} · {'Sửa tay' if row['manual'] else row['reason']}")
                    detail = json.loads(row['details'])
                    if detail.get('suggestion') and row['label'] == 'Chưa phân loại':
                        st.info(f"Gợi ý theo trang phục: {detail['suggestion']} — cần bạn xác nhận bên dưới.")
                    with st.expander('Chi tiết nhận diện'):
                        st.json(json.loads(row['details']))
                    options = list(dict.fromkeys(SPECIAL + store.people() + [row['label']]))
                    target = st.selectbox('Gán lại', options, index=options.index(row['label']), key='label_' + row['id'])
                    if st.button('Lưu phân loại', key='save_' + row['id']):
                        try:
                            with lock:
                                if sha256(row['source']) != row['digest']:
                                    raise ValueError('Ảnh nguồn đã thay đổi; cần xử lý lại.')
                                store.save(row['id'], row['source'], source, output, row['digest'], target, 'Người dùng gán lại', json.loads(row['details']), manual=True)
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
    else:
        st.info('Nhập thư mục nguồn và kết quả ở tab Phân loại.')
store.db.close()
