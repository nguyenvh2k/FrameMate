"""Download and validate the two official OpenCV ONNX models."""
from pathlib import Path
from filelock import FileLock
from photo_sorter.vision import download_models

if __name__ == '__main__':
    base = Path(__file__).resolve().parent
    (base / 'data').mkdir(exist_ok=True)
    with FileLock(str(base / 'data' / 'processing.lock'), timeout=0):
        download_models(base / 'models')
    print('YuNet và SFace đã sẵn sàng trong models/.')
