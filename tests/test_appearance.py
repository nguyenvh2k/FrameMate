"""Image descriptors and pipeline tests; no downloaded model required."""
import unittest
from unittest.mock import Mock, patch

try:
    import numpy as np
    from photo_sorter.appearance import clothing_descriptor, clothing_similarity, clothing_scores
    from photo_sorter.vision import FaceEngine
    IMAGE_LIBS = True
except ImportError:
    IMAGE_LIBS = False


@unittest.skipUnless(IMAGE_LIBS, 'Cần numpy, OpenCV, Pillow từ requirements.txt')
class AppearanceImageTests(unittest.TestCase):
    def setUp(self):
        self.image = np.full((400, 300, 3), (0, 0, 255), dtype=np.uint8)
        points = np.zeros((17, 3))
        for i, xy in {5: (60, 60), 6: (180, 60), 11: (60, 220), 12: (180, 220),
                      13: (60, 350), 14: (180, 350)}.items():
            points[i] = [*xy, .99]
        self.body = {'box': [40, 0, 200, 390], 'points': points.tolist()}

    def test_color_descriptor_and_two_view_ranking(self):
        red = clothing_descriptor(self.image, self.body)
        blue = clothing_descriptor(np.full_like(self.image, (255, 0, 0)), self.body)
        self.assertAlmostEqual(clothing_similarity(red, red), 1.0, places=5)
        self.assertLess(clothing_similarity(red, blue), .1)
        ranks = clothing_scores(red, {'A': [red, red], 'B': [blue, blue]})
        self.assertEqual(ranks[0][1:], ('A', 2))

    def test_missing_shoulders_rejects_descriptor(self):
        self.body['points'][5][2] = 0
        self.assertIsNone(clothing_descriptor(self.image, self.body))

    def classify(self, faces, bodies, outfits=None, people=None):
        engine = FaceEngine.__new__(FaceEngine)
        engine.detect = Mock(return_value=faces)
        engine.feature = Mock(return_value=np.array([1.0, 0.0]))
        appearance = Mock()
        appearance.detect.return_value = bodies
        with patch('photo_sorter.vision.read_image', return_value=self.image):
            return engine.classify('unused.jpg', people or {}, appearance=appearance, outfits=outfits or {})

    def test_two_bodies_without_faces_are_group(self):
        second = {'box': [200, 0, 300, 390], 'points': self.body['points']}
        label, _, _ = self.classify([], [self.body, second])
        self.assertEqual(label, 'Nhóm')

    def test_no_face_only_suggests(self):
        red = clothing_descriptor(self.image, self.body)
        label, _, details = self.classify([], [self.body], {'A': [red, red]})
        self.assertEqual(label, 'Chưa phân loại')
        self.assertEqual(details['suggestion'], 'A')

    def test_borderline_face_combines_with_clothing(self):
        red = clothing_descriptor(self.image, self.body)
        label, _, details = self.classify([[70, 5, 50, 50]], [self.body],
                                         {'A': [red, red]}, {'A': [[.46, .8879189]]})
        self.assertEqual(label, 'A')
        self.assertEqual(details['method'], 'face+clothing')

    def test_face_on_other_person_rejected(self):
        label, _, _ = self.classify([[240, 5, 50, 50]], [self.body], people={'A': [[1, 0]]})
        self.assertEqual(label, 'Chưa phân loại')
