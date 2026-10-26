import unittest
from photo_sorter.policy import principal_faces, choose_identity


class PolicyTests(unittest.TestCase):
    def test_unknown_and_ambiguous_rejected(self):
        self.assertEqual(choose_identity([], .5, .1), 'Chưa phân loại')
        self.assertEqual(choose_identity([(.49, 'A')], .5, .1), 'Chưa phân loại')
        self.assertEqual(choose_identity([(.7, 'A'), (.65, 'B')], .5, .1), 'Chưa phân loại')
        self.assertEqual(choose_identity([(.7, 'A'), (.4, 'B')], .5, .1), 'A')

    def test_small_background_ignored(self):
        main = [0, 0, 100, 100]
        background = [0, 0, 15, 15]
        self.assertEqual(principal_faces([main, background], 1000000, .2, .001), [main])

    def test_group_and_no_faces(self):
        faces = [[0, 0, 100, 100], [100, 0, 80, 80]]
        self.assertEqual(len(principal_faces(faces, 1000000, .2, .001)), 2)
        self.assertEqual(principal_faces([], 1000000, .2, .001), [])
        self.assertEqual(principal_faces([[0, 0, 10, 10]], 1000000, .2, .001), [])


class AppearancePolicyTests(unittest.TestCase):
    def test_clothes_never_identify_without_face(self):
        from photo_sorter.policy import supported_identity
        self.assertEqual(supported_identity([], [(1.0, 'A', 10)]), 'Chưa phân loại')
        self.assertEqual(supported_identity([(.20, 'A')], [(1.0, 'A', 10)]), 'Chưa phân loại')

    def test_clothes_support_borderline_face(self):
        from photo_sorter.policy import supported_identity
        self.assertEqual(supported_identity([(.46, 'A'), (.30, 'B')], [(.95, 'A', 2), (.70, 'B', 3)]), 'A')

    def test_ambiguous_outfit_or_face_stays_unknown(self):
        from photo_sorter.policy import supported_identity
        for faces, outfits in [
            ([(.46, 'A')], [(.95, 'A', 2), (.94, 'B', 2)]),
            ([(.46, 'A')], [(.95, 'A', 1)]),
            ([(.46, 'A')], [(.99, 'B', 2)]),
            ([(.46, 'A'), (.45, 'B')], [(.99, 'A', 2)]),
        ]:
            with self.subTest(faces=faces, outfits=outfits):
                self.assertEqual(supported_identity(faces, outfits), 'Chưa phân loại')

    def test_strong_face_wins_over_clothing(self):
        from photo_sorter.policy import supported_identity
        self.assertEqual(supported_identity([(.75, 'A')], [(.99, 'B', 2)]), 'A')

    def test_stricter_user_threshold_applies_to_support(self):
        from photo_sorter.policy import supported_identity
        self.assertEqual(supported_identity([(.46, 'A')], [(.99, 'A', 2)], .7), 'Chưa phân loại')

    def test_body_filter_and_face_association(self):
        from photo_sorter.policy import main_bodies, face_belongs
        a = {'box': [0, 0, 200, 600]}
        b = {'box': [300, 0, 480, 580]}
        small = {'box': [800, 0, 820, 60]}
        self.assertEqual(main_bodies([a, b, small], 1000000), [a, b])
        self.assertTrue(face_belongs([20, 10, 50, 50], a))
        self.assertFalse(face_belongs([320, 10, 50, 50], a))
        self.assertFalse(face_belongs([20, 500, 50, 50], a))
