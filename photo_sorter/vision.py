from pathlib import Path
import hashlib
import urllib.request
import os
import numpy as np
import cv2
from PIL import Image, ImageOps
from .policy import principal_faces, choose_identity, supported_identity

MODELS = {
    'face_detection_yunet_2023mar.onnx': 'face_detection_yunet',
    'face_recognition_sface_2021dec.onnx': 'face_recognition_sface',
}


def download_models(folder):
    """Verify downloads against the upstream Git LFS SHA-256 pointer."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, directory in MODELS.items():
        path = folder / name
        pointer_url = f'https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/{directory}/{name}'
        with urllib.request.urlopen(pointer_url, timeout=60) as response:
            pointer = response.read().decode('ascii')
        digest = next(line.split('sha256:')[1] for line in pointer.splitlines() if line.startswith('oid sha256:'))
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            continue
        url = f'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{directory}/{name}'
        tmp = path.with_suffix('.part')
        try:
            with urllib.request.urlopen(url, timeout=120) as response, tmp.open('wb') as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
            if hashlib.sha256(tmp.read_bytes()).hexdigest() != digest:
                raise ValueError(f'Sai checksum: {name}')
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)


def read_image(path, max_side=1800):
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((max_side, max_side))
        return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


class FaceEngine:
    def __init__(self, folder):
        folder = Path(folder)
        for name in MODELS:
            if not (folder / name).exists():
                raise FileNotFoundError('Chưa có model. Bấm tải model trong thanh bên.')
        self.detector = cv2.FaceDetectorYN.create(str(folder / next(iter(MODELS))), '', (320, 320), 0.9)
        self.recognizer = cv2.FaceRecognizerSF.create(str(folder / 'face_recognition_sface_2021dec.onnx'), '')

    def detect(self, image):
        self.detector.setInputSize((image.shape[1], image.shape[0]))
        faces = self.detector.detect(image)[1]
        return [] if faces is None else list(faces)

    def feature(self, image, face):
        crop = self.recognizer.alignCrop(image, face)
        vector = self.recognizer.feature(crop).flatten()
        return vector / max(float(np.linalg.norm(vector)), 1e-9)

    def enroll(self, path):
        image = read_image(path)
        faces = self.detect(image)
        if len(faces) != 1:
            raise ValueError(f'Ảnh mẫu phải có đúng một mặt rõ; tìm thấy {len(faces)} mặt.')
        if min(faces[0][2:4]) < 60:
            raise ValueError('Mặt mẫu quá nhỏ (cần ít nhất 60 px sau thu nhỏ).')
        return self.feature(image, faces[0]).tolist()

    def classify(self, path, people, threshold=0.50, margin=0.10, relative_area=0.20,
                 min_fraction=0.001, appearance=None, outfits=None):
        image = read_image(path)
        faces = self.detect(image)
        main = principal_faces(faces, image.shape[0] * image.shape[1], relative_area, min_fraction)
        details = {'detected': len(faces), 'main': len(main), 'matches': [],
                   'method': 'face', 'outfit_matches': []}
        bodies = []
        if appearance is not None:
            from .appearance import main_bodies, face_belongs, clothing_descriptor, clothing_scores
            bodies = main_bodies(appearance.detect(image), image.shape[0] * image.shape[1])
            details['main_bodies'] = len(bodies)
            details['body_boxes'] = [b['box'] for b in bodies]
        if len(main) >= 2 or len(bodies) >= 2:
            details['method'] = 'group'
            return 'Nhóm', 'Có từ hai khuôn mặt hoặc toàn thân chính', details
        scores = []
        if main and min(main[0][2:4]) >= 40:
            vector = self.feature(image, main[0])
            scores = sorted(((max(float(np.dot(vector, sample)) for sample in samples), name)
                             for name, samples in people.items() if samples), reverse=True)
            details['matches'] = [{'person': n, 'cosine': round(s, 4)} for s, n in scores[:3]]
        outfit_ranks = []
        if len(bodies) == 1:
            if main and not face_belongs(main[0], bodies[0]):
                details['method'] = 'uncertain'
                return 'Chưa phân loại', 'Mặt và toàn thân không thuộc cùng chủ thể rõ ràng', details
            descriptor = clothing_descriptor(image, bodies[0])
            outfit_ranks = clothing_scores(descriptor, outfits or {})
            details['outfit_matches'] = [{'person': n, 'similarity': round(s, 4), 'samples': c}
                                         for s, n, c in outfit_ranks[:3]]
            if outfit_ranks and outfit_ranks[0][0] >= 0.75:
                # Suggestion only; absence of a reliable face never auto-identifies.
                details['suggestion'] = outfit_ranks[0][1]
        label = supported_identity(scores, outfit_ranks, threshold, margin)
        if label != 'Chưa phân loại':
            if choose_identity(scores, threshold, margin) == label:
                return label, 'Khớp mặt vượt ngưỡng và độ cách biệt', details
            details['method'] = 'face+clothing'
            return label, 'Mặt và ít nhất hai mẫu trang phục cùng hỗ trợ', details
        details['method'] = 'uncertain'
        return label, ('Chỉ có gợi ý trang phục; cần bạn xác nhận' if details.get('suggestion')
                       else 'Không đủ bằng chứng nhận diện hoặc có nhiều người dễ nhầm'), details
