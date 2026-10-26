from pathlib import Path
from filelock import FileLock
from photo_sorter.appearance import download_pose

if __name__ == '__main__':
    base = Path(__file__).resolve().parent
    (base / 'data').mkdir(exist_ok=True)
    def progress(done, total):
        print(f'\rĐã tải {done / 1048576:.1f} / {total / 1048576:.1f} MB', end='', flush=True)
    with FileLock(str(base / 'data' / 'processing.lock'), timeout=0):
        download_pose(base / 'models', progress)
    print('\nModel dáng/trang phục đã sẵn sàng.')
