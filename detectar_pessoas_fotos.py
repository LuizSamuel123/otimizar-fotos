import argparse
import csv
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2


EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
WORKER_CASCADES = None
WORKER_HOG = None


def iter_images(folder: Path):
    for item in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
        if item.is_file() and item.suffix.casefold() in EXTS:
            yield item


def load_cascade(name: str):
    path = Path(cv2.data.haarcascades) / name
    cascade = cv2.CascadeClassifier(str(path))
    if cascade.empty():
        raise RuntimeError(f"Nao consegui carregar {path}")
    return cascade


def resize_for_detection(img, max_side=700):
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return img
    scale = max_side / longest
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def detect(path: Path, cascades, hog=None):
    img = cv2.imread(str(path))
    if img is None:
        return {"error": "cv2.imread falhou"}
    img = resize_for_detection(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    counts = {}
    for name, cascade, scale_factor, min_neighbors, min_size in cascades:
        hits = cascade.detectMultiScale(
            gray,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors,
            minSize=min_size,
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        counts[name] = len(hits)

    if hog is None:
        counts["hog_people"] = 0
    else:
        bodies, _weights = hog.detectMultiScale(
            img,
            winStride=(8, 8),
            padding=(16, 16),
            scale=1.05,
        )
        counts["hog_people"] = len(bodies)
    counts["total"] = sum(counts.values())
    return counts


def init_worker(use_hog=False):
    global WORKER_CASCADES, WORKER_HOG
    WORKER_CASCADES = [
        ("face", load_cascade("haarcascade_frontalface_default.xml"), 1.08, 4, (24, 24)),
        ("face_alt", load_cascade("haarcascade_frontalface_alt2.xml"), 1.08, 4, (24, 24)),
        ("profile", load_cascade("haarcascade_profileface.xml"), 1.08, 4, (24, 24)),
    ]
    WORKER_HOG = None
    if use_hog:
        WORKER_HOG = cv2.HOGDescriptor()
        WORKER_HOG.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())


def worker_detect(item):
    idx, path_text = item
    path = Path(path_text)
    result = detect(path, WORKER_CASCADES, WORKER_HOG)
    row = {"idx": idx, "file": path.name}
    row.update(result)
    row["has_detection"] = int(row.get("total", 0) > 0)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--hog", action="store_true")
    parser.add_argument("--workers", type=int, default=max(1, min(6, (os.cpu_count() or 2) - 1)))
    args = parser.parse_args()

    rows = []
    files = list(iter_images(args.source.resolve()))
    total = len(files)
    work = [(idx, str(path)) for idx, path in enumerate(files, start=1)]
    if args.workers <= 1:
        init_worker(args.hog)
        for item in work:
            rows.append(worker_detect(item))
            idx = item[0]
            if idx == 1 or idx % 100 == 0 or idx == total:
                print(f"{idx}/{total}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker, initargs=(args.hog,)) as executor:
            for done, row in enumerate(executor.map(worker_detect, work, chunksize=8), start=1):
                rows.append(row)
                if done == 1 or done % 100 == 0 or done == total:
                    print(f"{done}/{total}", flush=True)

    fields = ["idx", "file", "face", "face_alt", "profile", "upper_body", "full_body", "hog_people", "total", "has_detection", "error"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    no_detection = sum(1 for row in rows if not row.get("has_detection"))
    print(f"Sem deteccao: {no_detection}")
    print(args.out)


if __name__ == "__main__":
    main()
