import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from photo_sorter.storage import Store, sha256, validate_roots, valid_name


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.base / 'source'
        self.output = self.base / 'output'
        self.source.mkdir()
        self.output.mkdir()
        self.store = Store(self.base / 'data')

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def save(self, path, label='Huyền'):
        digest = sha256(path)
        key = self.store.identity(path, self.source, self.output, digest)
        self.store.save(key, path, self.source, self.output, digest, label, 'test', {})
        return key

    def test_collision_and_manual_reassignment(self):
        path = self.source / 'a.jpg'
        path.write_bytes(b'original')
        target = self.output / 'Huyền' / 'a.jpg'
        target.parent.mkdir()
        target.write_bytes(b'existing')
        key = self.save(path)
        self.assertEqual(target.read_bytes(), b'existing')
        self.assertTrue(self.store.done(key))
        previous = Path(self.store.records(self.source, self.output)[0]['destination'])
        self.save(path, 'Nhóm')
        self.assertFalse(previous.exists())
        self.assertEqual(path.read_bytes(), b'original')
        self.assertEqual(target.read_bytes(), b'existing')
        self.assertTrue(self.store.done(key))

    def test_resume_pending_copy(self):
        path = self.source / 'a.png'
        path.write_bytes(b'image')
        with patch.object(self.store, 'finish', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                self.save(path)
        self.store.recover(self.source, self.output)
        rows = self.store.records(self.source, self.output)
        self.assertEqual(len(rows), 1)
        self.assertTrue(self.store.done(rows[0]['id']))
        self.store.recover(self.source, self.output)
        self.assertEqual(len(list(self.output.rglob('*.png'))), 1)

    def test_changed_copy_not_deleted(self):
        path = self.source / 'a.jpg'
        path.write_bytes(b'original')
        self.save(path)
        dest = Path(self.store.records(self.source, self.output)[0]['destination'])
        dest.write_bytes(b'edited by user')
        self.save(path, 'Nhóm')
        self.assertEqual(dest.read_bytes(), b'edited by user')

    def test_changed_source_new_identity(self):
        path = self.source / 'a.jpg'
        path.write_bytes(b'one')
        key = self.save(path)
        path.write_bytes(b'two')
        self.assertNotEqual(key, self.save(path))

    def test_validation(self):
        for name in ['../x', 'CON', 'a:b', 'x.', 'NUL.txt', '']:
            with self.assertRaises(ValueError):
                valid_name(name)
        self.assertEqual(valid_name('Huyền'), 'Huyền')
        with self.assertRaises(ValueError):
            validate_roots(self.source, self.source / 'output')

    def test_outfits_isolated_by_session_and_persist(self):
        self.store.add_person('Huyền')
        descriptor = {'version': 1, 'upper': [1, 0], 'lower': None}
        self.assertTrue(self.store.add_outfit('Buổi 1', 'Huyền', b'outfit', '.jpg', descriptor))
        self.assertFalse(self.store.add_outfit('Buổi 1', 'Huyền', b'outfit', '.jpg', descriptor))
        self.assertEqual(self.store.outfit_profiles('Buổi 2')['Huyền'], [])
        self.store.db.close()
        self.store = Store(self.base / 'data')
        self.assertEqual(self.store.outfit_profiles('Buổi 1')['Huyền'], [descriptor])
        row = self.store.outfit_samples('Buổi 1', 'Huyền')[0]
        self.store.remove_outfit(row['id'])
        self.assertFalse(Path(row['path']).exists())
        self.assertEqual(self.store.outfit_profiles('Buổi 1')['Huyền'], [])

    def test_retry_unknown_respects_manual_and_signature(self):
        path = self.source / 'a.jpg'
        path.write_bytes(b'photo')
        key = self.save(path, 'Chưa phân loại')
        self.assertTrue(self.store.retry_unknown(key, 'new'))
        self.store.save(key, path, self.source, self.output, sha256(path), 'Chưa phân loại', '',
                        {'processing_signature': 'new'})
        self.assertFalse(self.store.retry_unknown(key, 'new'))
        self.assertTrue(self.store.retry_unknown(key, 'changed'))
        self.store.save(key, path, self.source, self.output, sha256(path), 'Chưa phân loại', '', {}, manual=True)
        self.assertFalse(self.store.retry_unknown(key, 'changed'))


    def test_remove_person_preserves_photos_and_other_people(self):
        self.store.add_person('Huyền')
        self.store.add_person('Thanh')
        self.store.add_sample('Huyền', b'face', '.jpg', [1, 0])
        self.store.add_sample('Thanh', b'other face', '.jpg', [0, 1])
        for session in ['day1', 'day2']:
            self.store.add_outfit(session, 'Huyền', b'clothes', '.jpg', {'upper': [1]})
        owned = [Path(r['path']) for r in self.store.samples('Huyền')]
        owned += [Path(r['path']) for r in self.store.db.execute('SELECT path FROM outfits')]
        other = Path(self.store.samples('Thanh')[0]['path'])
        source = self.source / 'original.jpg'
        source.write_bytes(b'original')
        key = self.save(source)
        self.assertEqual(self.store.remove_person('Huyền'), [])
        self.assertEqual(self.store.people(), ['Thanh'])
        self.assertEqual(self.store.samples('Huyền'), [])
        self.assertEqual(self.store.outfit_samples('day2', 'Huyền'), [])
        self.assertTrue(all(not p.exists() for p in owned))
        self.assertTrue(other.exists())
        self.assertTrue(self.store.done(key))
        self.assertEqual(source.read_bytes(), b'original')
        self.store.db.close()
        self.store = Store(self.base / 'data')
        self.assertNotIn('Huyền', self.store.embeddings())
        self.store.add_person('Huyền')
        self.assertEqual(self.store.samples('Huyền'), [])

    def test_remove_person_cleanup_failure_still_removes_identity(self):
        self.store.add_person('Huyền')
        self.store.add_sample('Huyền', b'face', '.jpg', [1])
        with patch.object(Path, 'unlink', side_effect=PermissionError('busy')):
            self.assertEqual(len(self.store.remove_person('Huyền')), 1)
        self.assertEqual(self.store.people(), [])
        self.assertEqual(self.store.embeddings(), {})
        self.assertEqual(self.store.remove_person('Huyền'), [])



if __name__ == '__main__':
    unittest.main()
