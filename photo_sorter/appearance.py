"""Session-local clothing support. Pose localizes clothing; it is not an identity."""
from pathlib import Path
import os
import urllib.request
import zipfile
import cv2
import numpy as np
from .policy import main_bodies, face_belongs

POSE_MODEL = 'yolo11n-pose.pt'
POSE_URL = f'https://github.com/ultralytics/assets/releases/download/v8.3.0/{POSE_MODEL}'


def download_pose(folder, progress=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / POSE_MODEL
    if target.exists() and zipfile.is_zipfile(target):
        return
    temporary = folder / (POSE_MODEL + '.part')
    try:
        with urllib.request.urlopen(POSE_URL, timeout=120) as response, temporary.open('wb') as out:
            total = int(response.headers.get('Content-Length', 0))
            received = 0
            while chunk := response.read(1024 * 256):
                out.write(chunk)
                received += len(chunk)
                if progress:
                    progress(received, total)
        if not zipfile.is_zipfile(temporary) or temporary.stat().st_size < 1000000:
            raise ValueError('Model tư thế tải chưa đầy đủ hoặc sai định dạng.')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


class AppearanceEngine:
    def __init__(self, folder):
        path = Path(folder).resolve() / POSE_MODEL
        if not path.is_file():
            raise FileNotFoundError('Chưa có model tư thế. Bấm Tải model dáng/trang phục.')
        # Set before importing Ultralytics; never auto-fetch models or packages at inference.
        os.environ['YOLO_OFFLINE'] = 'true'
        os.environ['YOLO_AUTOINSTALL'] = 'false'
        config = Path(folder).resolve().parent / 'data' / 'ultralytics'
        config.mkdir(parents=True, exist_ok=True)
        os.environ['YOLO_CONFIG_DIR'] = str(config)
        try:
            from ultralytics import YOLO, settings
        except ImportError as exc:
            raise RuntimeError('Cần cài requirements-appearance.txt trước khi bật trang phục/dáng.') from exc
        settings.update({'sync': False})
        self.model = YOLO(str(path), task='pose')

    def detect(self, image):
        result = self.model.predict(image, device='cpu', imgsz=640, conf=0.55,
                                    verbose=False, save=False)[0]
        if result.boxes is None or result.keypoints is None:
            return []
        boxes = result.boxes.xyxy.cpu().numpy()
        points = result.keypoints.data.cpu().numpy()
        return [{'box': b.tolist(), 'points': p.tolist()} for b, p in zip(boxes, points)]

    def enroll(self, image):
        bodies = self.detect(image)
        if len(bodies) != 1:
            raise ValueError(f'Mẫu trang phục cần đúng một người; tìm thấy {len(bodies)} người.')
        descriptor = clothing_descriptor(image, bodies[0])
        if descriptor is None:
            raise ValueError('Không thấy đủ vai/hông hoặc vùng áo quá nhỏ. Chọn ảnh toàn thân rõ hơn.')
        return descriptor


def region_histogram(image, points):
    polygon = np.asarray(points, dtype=np.float32)
    center = polygon.mean(axis=0)
    polygon = center + (polygon - center) * 0.8  # avoid background and garment edges
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, polygon.astype(np.int32), 255)
    if cv2.countNonZero(mask) < 500:
        return None
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    # Include brightness: black/white clothing has little useful hue.
    hist = cv2.calcHist([hsv], [0, 1, 2], mask, [12, 4, 4], [0, 180, 0, 256, 0, 256]).flatten()
    hist /= max(float(hist.sum()), 1e-9)
    return hist.tolist()


def clothing_descriptor(image, body):
    p = np.asarray(body['points'])
    if p.shape != (17, 3) or any(p[i, 2] < 0.5 for i in (5, 6, 11, 12)):
        return None
    upper = region_histogram(image, p[[5, 6, 12, 11], :2])
    if upper is None:
        return None
    lower = None
    if all(p[i, 2] >= 0.5 for i in (13, 14)):
        lower = region_histogram(image, p[[11, 12, 14, 13], :2])
    return {'version': 1, 'upper': upper, 'lower': lower}


def clothing_similarity(a, b):
    def score(x, y):
        return float(np.sqrt(np.asarray(x) * np.asarray(y)).sum())
    upper = score(a['upper'], b['upper'])
    if a.get('lower') is not None and b.get('lower') is not None:
        return min(1.0, 0.7 * upper + 0.3 * score(a['lower'], b['lower']))
    return min(1.0, upper)


def clothing_scores(descriptor, profiles):
    if descriptor is None:
        return []
    ranks = []
    for name, samples in profiles.items():
        scores = sorted((clothing_similarity(descriptor, s) for s in samples), reverse=True)
        if scores:
            # Two reference views must agree before clothing may support an auto label.
            ranks.append((sum(scores[:2]) / len(scores[:2]), name, len(scores)))
    return sorted(ranks, reverse=True)
