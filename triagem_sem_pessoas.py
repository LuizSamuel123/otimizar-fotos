import argparse
import csv
import math
import os
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def iter_images(folder: Path):
    for item in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
        if item.is_file() and item.suffix.casefold() in EXTS:
            yield item


def safe_rel_name(path: Path) -> str:
    return path.name.replace("\n", " ").replace("\r", " ")


def fit_text(draw: ImageDraw.ImageDraw, text: str, width: int, font):
    if draw.textlength(text, font=font) <= width:
        return [text]
    words = text.split()
    lines = []
    current = ""
    for word in words or [text]:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    clipped = []
    for original in lines[:2]:
        line = original
        while draw.textlength(line + "...", font=font) > width and len(line) > 4:
            line = line[:-1]
        clipped.append(line + "..." if line != original else line)
    return clipped[:2]


def create_sheets(src: Path, out: Path, per_sheet: int, cols: int, thumb: int, start_at: int = 1, limit: int = 0):
    out.mkdir(parents=True, exist_ok=True)
    files = list(iter_images(src))
    files = files[start_at - 1 :]
    if limit:
        files = files[:limit]
    font = ImageFont.load_default()
    rows = math.ceil(per_sheet / cols)
    label_h = 42
    margin = 14
    gap = 10
    cell_w = thumb
    cell_h = thumb + label_h
    sheet_w = margin * 2 + cols * cell_w + (cols - 1) * gap
    sheet_h = margin * 2 + rows * cell_h + (rows - 1) * gap

    index_rows = []
    for sheet_no, start in enumerate(range(0, len(files), per_sheet), start=1):
        page_files = files[start : start + per_sheet]
        sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
        draw = ImageDraw.Draw(sheet)
        for pos, path in enumerate(page_files):
            row, col = divmod(pos, cols)
            x = margin + col * (cell_w + gap)
            y = margin + row * (cell_h + gap)
            try:
                with Image.open(path) as img:
                    img = ImageOps.exif_transpose(img).convert("RGB")
                    img.thumbnail((thumb, thumb), Image.Resampling.LANCZOS)
                    bg = Image.new("RGB", (thumb, thumb), (235, 235, 235))
                    bg.paste(img, ((thumb - img.width) // 2, (thumb - img.height) // 2))
                    sheet.paste(bg, (x, y))
            except Exception as exc:
                draw.rectangle([x, y, x + thumb, y + thumb], fill=(250, 230, 230), outline=(180, 40, 40))
                draw.text((x + 5, y + 5), f"ERRO: {exc}", fill=(120, 0, 0), font=font)

            label = f"{start_at + start + pos:04d} {safe_rel_name(path)}"
            draw.rectangle([x, y + thumb, x + thumb, y + cell_h], fill="white")
            for line_no, line in enumerate(fit_text(draw, label, thumb - 6, font)):
                draw.text((x + 3, y + thumb + 3 + line_no * 13), line, fill="black", font=font)
            index_rows.append({"idx": start_at + start + pos, "sheet": sheet_no, "file": path.name})

        sheet_path = out / f"prancha_{sheet_no:03d}.jpg"
        sheet.save(sheet_path, quality=90)

    with (out / "indice_pranchas.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["idx", "sheet", "file"])
        writer.writeheader()
        writer.writerows(index_rows)
    print(f"Pranchas: {math.ceil(len(files) / per_sheet)}")
    print(f"Imagens indexadas: {len(files)}")
    print(out)


def move_from_list(src: Path, dest: Path, list_file: Path):
    dest.mkdir(parents=True, exist_ok=True)
    names = []
    for raw in list_file.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        names.append(raw)

    moved = 0
    skipped = []
    for name in names:
        origin = src / name
        if not origin.exists():
            skipped.append(name)
            continue
        target = dest / origin.name
        if target.exists():
            stem, suffix = origin.stem, origin.suffix
            counter = 2
            while target.exists():
                target = dest / f"{stem} ({counter}){suffix}"
                counter += 1
        shutil.move(str(origin), str(target))
        moved += 1
    print(f"Movidas: {moved}")
    if skipped:
        print("Ignoradas por nao encontrar:")
        for name in skipped:
            print(name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--per-sheet", type=int, default=80)
    parser.add_argument("--cols", type=int, default=8)
    parser.add_argument("--thumb", type=int, default=210)
    parser.add_argument("--start-at", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--move-list", type=Path)
    parser.add_argument("--dest", type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    if args.move_list:
        if not args.dest:
            raise SystemExit("--dest e obrigatorio com --move-list")
        move_from_list(source, args.dest.resolve(), args.move_list.resolve())
    else:
        if not args.out:
            raise SystemExit("--out e obrigatorio para criar pranchas")
        create_sheets(source, args.out.resolve(), args.per_sheet, args.cols, args.thumb, args.start_at, args.limit)


if __name__ == "__main__":
    main()
