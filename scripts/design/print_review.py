"""将 Figma 的逐页 PNG 导出整理成 A3 横向审阅稿；长界面自动续页。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, default=None)
    parser.add_argument("--theme", choices=["vallum", "abyssus"], default="vallum")
    parser.add_argument("--manifest", type=Path, default=Path("docs/figma-work-v2.json"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--font", default="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    args = parser.parse_args()
    args.images = args.images or Path("outputs/figma-theme-organization") / args.theme
    manifest = json.loads(args.manifest.read_text())
    version = manifest["version"]
    theme_label = "白垣 · VALLUM" if args.theme == "vallum" else "苍渊 · ABYSSUS"
    tokens = json.loads(
        Path(manifest.get("tokenSource", "src/web/src/tokens.dtcg.json")).read_text()
    )
    colors = tokens["semantic"][args.theme]
    ink = colors["textPrimary"]["$value"]
    muted = colors["textSecondary"]["$value"]
    canvas = colors["bgPrimary"]["$value"]
    # 页面采用当前主题，打印边注统一使用白垣文字以便阅读。
    paper_ink = tokens["semantic"]["vallum"]["textPrimary"]["$value"]
    paper_muted = tokens["semantic"]["vallum"]["textSecondary"]["$value"]
    args.output = args.output or Path(f"docs/design/{version}-{args.theme}-review.pdf")
    width, height, margin = 3307, 2339, 100  # A3 landscape, 200 dpi.
    normal = ImageFont.truetype(args.font, 34)
    small = ImageFont.truetype(args.font, 26)
    title_font = ImageFont.truetype(args.font, 62)
    pages: list[Image.Image] = []
    index: list[tuple[str, int, int]] = []
    for i, screen in enumerate(manifest["screens"], 1):
        source = Image.open(args.images / f"{i:02d}.png").convert("RGB")
        target_width = width - 2 * margin if screen["width"] > 640 else 1120
        scale = target_width / source.width
        capacity = math.floor((height - 260) / scale)
        start, part = 0, 1
        first_page = len(pages) + 2
        while start < source.height:
            end = min(start + capacity, source.height)
            if end < source.height:
                # Prefer whitespace between rows over cutting through labels.
                band_start = max(start + 1, end - round(120 / scale))
                band = source.crop((0, band_start, source.width, end))
                band = band.convert("L").resize((400, band.height))
                scores = [
                    sum(
                        (v > 55 if args.theme == "abyssus" else v < 225)
                        for v in band.crop((0, y, 400, y + 1)).tobytes()
                    )
                    for y in range(band.height)
                ]
                # A single pale scanline can be inside a glyph. Require a blank band.
                blank_start = None
                cuts = []
                for y, score in enumerate(scores + [400]):
                    if score <= 2:
                        if blank_start is None:
                            blank_start = y
                    elif blank_start is not None:
                        if y - blank_start >= max(8, round(8 / scale)):
                            cuts.append((blank_start + y) // 2)
                        blank_start = None
                if cuts:
                    end = band_start + cuts[-1]
            crop = source.crop((0, start, source.width, end))
            crop = crop.resize((target_width, round(crop.height * scale)), Image.Resampling.LANCZOS)
            sheet = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(sheet)
            suffix = f" · 续页 {part}" if part > 1 else ""
            draw.text((margin, 45), screen["name"] + suffix, font=normal, fill=paper_ink)
            sheet.paste(crop, ((width - target_width) // 2, 130))
            draw.text(
                (margin, height - 65),
                f"Ninna · {version} · {theme_label} · Figma 可编辑源稿 · {i:02d} / {len(manifest['screens'])}",
                font=small,
                fill=paper_muted,
            )
            draw.text((width - 240, height - 65), str(len(pages) + 2), font=small, fill=paper_muted)
            pages.append(sheet)
            start, part = end, part + 1
        index.append((screen["name"], first_page, len(pages) + 1))
    cover = Image.new("RGB", (width, height), canvas)
    draw = ImageDraw.Draw(cover)
    draw.text((margin, 100), f"Ninna / {theme_label} / 界面审阅稿", font=title_font, fill=ink)
    draw.text(
        (margin, 215),
        f"{version} · A3 横向 · "
        + manifest.get("figmaLayoutDescription", "两主题独立，按业务合并 Page"),
        font=normal,
        fill=muted,
    )
    draw.text(
        (margin, 280),
        "保留采集视口内容；长画板以续页排版。数据为真实平台快照。",
        font=normal,
        fill=muted,
    )
    rows = math.ceil(len(index) / 2)
    row_height = min(118, (height - 720) // rows)
    for i, (name, first, last) in enumerate(index):
        x, y = margin + (i // rows) * 1570, 470 + (i % rows) * row_height
        draw.text((x, y), name, font=normal, fill=ink)
        draw.text(
            (x + 1120, y),
            str(first) if first == last else f"{first}–{last}",
            font=normal,
            fill=muted,
        )
    draw.text(
        (margin, height - 180),
        "设计文件：figma.com/design/ab3EG1a9aEHNyNZRJCzmD4",
        font=normal,
        fill=muted,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cover.save(args.output, "PDF", save_all=True, append_images=pages, resolution=200, quality=95)
    print(f"{args.output}: {len(pages) + 1} pages, {len(index)} interfaces")


if __name__ == "__main__":
    main()
