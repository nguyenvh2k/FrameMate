"""Pure decision rules, independent from model inference."""
def principal_faces(faces, image_area, relative_area, min_fraction):
    if len(faces) == 0:
        return []
    biggest = max(float(f[2] * f[3]) for f in faces)
    return [f for f in faces if f[2] * f[3] >= biggest * relative_area
            and f[2] * f[3] >= image_area * min_fraction]


def choose_identity(scores, threshold, margin):
    if not scores or scores[0][0] < threshold:
        return 'Chưa phân loại'
    if len(scores) > 1 and scores[0][0] - scores[1][0] < margin:
        return 'Chưa phân loại'
    return scores[0][1]


def supported_identity(face_scores, clothing_scores, face_threshold=0.50, face_margin=0.10):
    """Clothing must agree with a plausible face; never identify by clothes alone."""
    strong = choose_identity(face_scores, face_threshold, face_margin)
    if strong != 'Chưa phân loại':
        return strong
    if not face_scores or not clothing_scores:
        return 'Chưa phân loại'
    face_score, person = face_scores[0]
    outfit_score, outfit_person, count = clothing_scores[0]
    if person != outfit_person or count < 2 or face_score < max(0.40, face_threshold - 0.08):
        return 'Chưa phân loại'
    if len(face_scores) > 1 and face_score - face_scores[1][0] < max(0.04, face_margin / 2):
        return 'Chưa phân loại'
    if outfit_score < 0.88:
        return 'Chưa phân loại'
    if len(clothing_scores) > 1 and outfit_score - clothing_scores[1][0] < 0.12:
        return 'Chưa phân loại'
    return person

def main_bodies(bodies, image_area, relative=0.25, minimum=0.025):
    if not bodies:
        return []
    def area(body):
        x1, y1, x2, y2 = body['box']
        return max(0, x2 - x1) * max(0, y2 - y1)
    largest = max(map(area, bodies))
    return [b for b in bodies if area(b) >= max(largest * relative, image_area * minimum)]


def face_belongs(face, body):
    x, y, w, h = face[:4]
    x1, y1, x2, y2 = body['box']
    return x1 <= x + w / 2 <= x2 and y1 <= y + h / 2 <= y1 + (y2 - y1) * 0.45

