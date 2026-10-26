from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import sqlite3
import unicodedata
import uuid

SPECIAL = ['Nhóm', 'Chưa phân loại']
EXTENSIONS = {'.jpg', '.jpeg', '.png'}


def valid_name(name):
    name = unicodedata.normalize('NFC', name.strip())
    if not name or len(name) > 80 or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith(('.', ' ')):
        raise ValueError('Tên không hợp lệ làm tên thư mục Windows.')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))} or name in {'.', '..'}:
        raise ValueError('Tên dành riêng của Windows.')
    return name


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def validate_roots(source, output, private=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_dir():
        raise ValueError('Thư mục nguồn không tồn tại.')
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('Nguồn và kết quả phải tách biệt, không nằm trong nhau.')
    if private:
        private = Path(private).resolve()
        if any(p == private or p in private.parents or private in p.parents for p in (source, output)):
            raise ValueError('Không dùng thư mục dữ liệu cấu hình làm nguồn/kết quả.')
    output.mkdir(parents=True, exist_ok=True)
    return source, output


def scan(source):
    return sorted(p for p in source.rglob('*') if p.is_file() and not p.is_symlink() and p.suffix.lower() in EXTENSIONS)


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.folder / 'catalog.sqlite', timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS people(name TEXT PRIMARY KEY COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS samples(id TEXT PRIMARY KEY, person TEXT, path TEXT, feature TEXT, digest TEXT, UNIQUE(person,digest));
        CREATE TABLE IF NOT EXISTS outfits(id TEXT PRIMARY KEY, session TEXT, person TEXT,
          path TEXT, descriptor TEXT, digest TEXT, UNIQUE(session,person,digest));
        CREATE TABLE IF NOT EXISTS photos(id TEXT PRIMARY KEY, source TEXT, root TEXT, output TEXT, digest TEXT,
          label TEXT, reason TEXT, details TEXT, destination TEXT, status TEXT, manual INTEGER DEFAULT 0, old_destination TEXT);
        ''')

    def people(self):
        return [r[0] for r in self.db.execute('SELECT name FROM people ORDER BY name')]

    def remove_person(self, name):
        """Remove enrollment, preserving sources and historical classifications.

        Caller holds the processing lock. Return files that could not be cleaned up;
        their descriptors are already removed and cannot participate in recognition.
        """
        with self.db:
            row = self.db.execute('SELECT name FROM people WHERE name=?', (name,)).fetchone()
            if row is None:
                return []
            name = row['name']
            files = [(r['path'], 'samples') for r in self.samples(name)]
            files += [(r['path'], 'outfits') for r in self.db.execute(
                'SELECT path FROM outfits WHERE person=?', (name,))]
            self.db.execute('DELETE FROM samples WHERE person=?', (name,))
            self.db.execute('DELETE FROM outfits WHERE person=?', (name,))
            self.db.execute('DELETE FROM people WHERE name=?', (name,))
        remaining = []
        for filename, subdir in files:
            path = Path(filename)
            try:
                # Never follow stored paths outside the application's sample folders.
                if path.resolve().parent != (self.folder / subdir).resolve() or path.is_symlink():
                    remaining.append(str(path))
                    continue
                path.unlink(missing_ok=True)
            except OSError:
                remaining.append(str(path))
        return remaining

    def add_person(self, name):
        name = valid_name(name)
        if name.casefold() in {n.casefold() for n in SPECIAL + self.people()}:
            raise ValueError('Tên đã có hoặc trùng thư mục phân loại.')
        with self.db:
            self.db.execute('INSERT INTO people VALUES (?)', (name,))
        return name

    def add_sample(self, person, data, suffix, feature):
        digest = hashlib.sha256(data).hexdigest()
        if self.db.execute('SELECT 1 FROM samples WHERE person=? AND digest=?', (person, digest)).fetchone():
            return False
        sample_id = uuid.uuid4().hex
        path = self.folder / 'samples' / (sample_id + suffix.lower())
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        with self.db:
            self.db.execute('INSERT INTO samples VALUES (?,?,?,?,?)', (sample_id, person, str(path), json.dumps(feature), digest))
        return True

    def samples(self, person):
        return list(self.db.execute('SELECT * FROM samples WHERE person=?', (person,)))

    def remove_sample(self, sample_id):
        row = self.db.execute('SELECT path FROM samples WHERE id=?', (sample_id,)).fetchone()
        with self.db:
            self.db.execute('DELETE FROM samples WHERE id=?', (sample_id,))
        if row:
            Path(row[0]).unlink(missing_ok=True)

    def embeddings(self):
        return {name: [json.loads(r['feature']) for r in self.samples(name)] for name in self.people()}

    def add_outfit(self, session, person, data, suffix, descriptor):
        session = session.strip()
        if not session:
            raise ValueError('Cần tên buổi chụp riêng cho mẫu trang phục.')
        if person not in self.people():
            raise ValueError('Người chưa được đăng ký.')
        digest = hashlib.sha256(data).hexdigest()
        if self.db.execute('SELECT 1 FROM outfits WHERE session=? AND person=? AND digest=?',
                           (session, person, digest)).fetchone():
            return False
        sample_id = uuid.uuid4().hex
        path = self.folder / 'outfits' / (sample_id + suffix.lower())
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        with self.db:
            self.db.execute('INSERT INTO outfits VALUES (?,?,?,?,?,?)',
                            (sample_id, session, person, str(path), json.dumps(descriptor), digest))
        return True

    def outfit_samples(self, session, person):
        return list(self.db.execute('SELECT * FROM outfits WHERE session=? AND person=?', (session, person)))

    def outfit_profiles(self, session):
        return {name: [json.loads(r['descriptor']) for r in self.outfit_samples(session, name)]
                for name in self.people()}

    def remove_outfit(self, sample_id):
        row = self.db.execute('SELECT path FROM outfits WHERE id=?', (sample_id,)).fetchone()
        with self.db:
            self.db.execute('DELETE FROM outfits WHERE id=?', (sample_id,))
        if row:
            Path(row[0]).unlink(missing_ok=True)

    def retry_unknown(self, key, signature=None):
        row = self.db.execute('SELECT label,manual,status,details FROM photos WHERE id=?', (key,)).fetchone()
        return bool(row and row['label'] == 'Chưa phân loại' and not row['manual'] and row['status'] == 'done'
                    and (signature is None or json.loads(row['details']).get('processing_signature') != signature))

    def records(self, source, output):
        return [dict(r) for r in self.db.execute('SELECT * FROM photos WHERE root=? AND output=? ORDER BY source', (str(source), str(output)))]

    def identity(self, path, source, output, digest):
        return hashlib.sha256(json.dumps([str(source), str(output), str(path), digest]).encode()).hexdigest()

    def done(self, key):
        row = self.db.execute('SELECT * FROM photos WHERE id=?', (key,)).fetchone()
        return row and row['status'] == 'done' and Path(row['destination']).is_file() and sha256(row['destination']) == row['digest']

    def save(self, key, path, source, output, digest, label, reason, details, manual=False):
        label = valid_name(label)
        old = self.db.execute('SELECT * FROM photos WHERE id=?', (key,)).fetchone()
        old_dest = old['destination'] if old and old['status'] == 'done' else (old['old_destination'] if old else None)
        # Persist intent before copying. Recover pending copies without rerunning inference.
        destination = Path(output) / label / Path(path).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if Path(output).resolve() not in destination.resolve().parents or destination.is_symlink():
            raise ValueError('Thư mục đích chứa liên kết ra ngoài; hãy chọn thư mục khác.')
        if destination.exists():
            destination = destination.with_name(f'{destination.stem}__{uuid.uuid4().hex}{destination.suffix}')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO photos VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                            (key, str(path), str(source), str(output), digest, label, reason, json.dumps(details, ensure_ascii=False), str(destination), 'pending', int(manual), old_dest))
        self.finish(key)

    def finish(self, key):
        row = self.db.execute('SELECT * FROM photos WHERE id=?', (key,)).fetchone()
        destination = Path(row['destination'])
        if Path(row['output']).resolve() not in destination.resolve().parents or destination.is_symlink():
            raise ValueError('Đường dẫn đích không an toàn.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or sha256(destination) != row['digest']:
            if sha256(row['source']) != row['digest']:
                raise ValueError('Ảnh nguồn đã thay đổi trong lúc xử lý; hãy chạy lại.')
            # Exclusive creation prevents overwriting even when another file appears.
            while True:
                try:
                    out = destination.open('xb')
                    break
                except FileExistsError:
                    destination = destination.with_name(f'{destination.stem[:80]}__{uuid.uuid4().hex}{destination.suffix}')
                    with self.db:
                        self.db.execute('UPDATE photos SET destination=? WHERE id=?', (str(destination), key))
            try:
                with out, open(row['source'], 'rb') as src:
                    shutil.copyfileobj(src, out)
                    out.flush()
                    os.fsync(out.fileno())
                if sha256(destination) != row['digest']:
                    raise ValueError('Bản copy không khớp ảnh nguồn.')
                shutil.copystat(row['source'], destination)
            except Exception:
                destination.unlink(missing_ok=True)
                raise
        old = row['old_destination']
        if old and Path(old) != destination:
            old_path = Path(old).resolve()
            root = Path(row['output']).resolve()
            if root in old_path.parents and old_path.is_file() and sha256(old_path) == row['digest']:
                old_path.unlink()
        with self.db:
            self.db.execute("UPDATE photos SET status='done', old_destination=NULL WHERE id=?", (key,))

    def recover(self, source, output):
        for row in self.records(source, output):
            if row['status'] == 'pending':
                self.finish(row['id'])
