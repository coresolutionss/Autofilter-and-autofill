"""Local card boundary detection and perspective correction for camera photos."""
import cv2
import numpy as np
from PIL import Image


def crop_photo(image, crop=None):
    crop = crop or {"horizontal": [0, 100], "vertical": [0, 100]}
    left, right = crop["horizontal"]
    top, bottom = crop["vertical"]
    if not (0 <= left < right <= 100 and 0 <= top < bottom <= 100):
        raise ValueError("Crop must include a nonempty area inside the photo.")
    width, height = image.size
    box = (int(width * left / 100), int(height * top / 100),
           int(width * right / 100), int(height * bottom / 100))
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError("Crop is too small.")
    return image.crop(box)


def straighten_card(image, return_original_crop=False):
    """Return (image, corrected). Leave uncertain boundaries untouched."""
    original = np.asarray(image.convert("RGB"))
    height, width = original.shape[:2]
    scale = min(1.0, 1400 / max(width, height))
    small = cv2.resize(original, (round(width * scale), round(height * scale)))
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 35, 110)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = small.shape[0] * small.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:25]:
        area = cv2.contourArea(contour)
        if not .12 * frame_area <= area <= .98 * frame_area:
            continue
        polygon = cv2.approxPolyDP(contour, .025 * cv2.arcLength(contour, True), True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        points = polygon.reshape(4, 2).astype(np.float32) / scale
        sums, differences = points.sum(axis=1), np.diff(points, axis=1).ravel()
        ordered = np.array([points[sums.argmin()], points[differences.argmin()],
                            points[sums.argmax()], points[differences.argmax()]], dtype=np.float32)
        if len(np.unique(ordered, axis=0)) != 4:
            continue
        tl, tr, br, bl = ordered
        out_width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
        out_height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
        ratio = max(out_width, out_height) / max(1, min(out_width, out_height))
        if not 1.25 <= ratio <= 2.2 or min(out_width, out_height) < 100:
            continue
        out_width, out_height = int(out_width), int(out_height)
        target = np.array([[0, 0], [out_width - 1, 0], [out_width - 1, out_height - 1], [0, out_height - 1]], dtype=np.float32)
        transform = cv2.getPerspectiveTransform(ordered, target)
        corrected = cv2.warpPerspective(original, transform, (out_width, out_height), flags=cv2.INTER_CUBIC)
        result = (Image.fromarray(corrected), True)
        if return_original_crop:
            bounds = (max(0, int(points[:, 0].min())), max(0, int(points[:, 1].min())),
                      min(width, int(np.ceil(points[:, 0].max()))), min(height, int(np.ceil(points[:, 1].max()))))
            return (*result, image.crop(bounds))
        return result
    result = (image.copy(), False)
    return (*result, image.copy()) if return_original_crop else result


def enlarge_for_ocr(image):
    """Bound OCR memory while enlarging the small lettering in card photos."""
    target = min(2200, max(1600, max(image.size)))
    scale = target / max(image.size)
    return image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.BICUBIC)
