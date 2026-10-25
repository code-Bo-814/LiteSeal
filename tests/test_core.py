"""核心引擎冒烟测试:python tests/test_core.py

生成测试图片和 PDF,分别打上文字/图片水印、单枚/平铺,验证输出文件有效。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf as fitz
from PIL import Image

from app.core.exporter import export_file
from app.core.image_wm import apply_image_watermark
from app.core.models import WatermarkConfig

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)


def make_test_image(path: str, size=(1200, 800)):
    img = Image.new("RGB", size)
    for x in range(size[0]):
        for_y = x * 255 // size[0]
        img.paste((for_y, 100, 255 - for_y), (x, 0, x + 1, size[1]))
    img.save(path)
    return path


def make_test_pdf(path: str, pages=3):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"LiteSeal test page {i + 1}", fontsize=24)
    doc.save(path)
    doc.close()
    return path


def make_logo(path: str):
    Image.new("RGBA", (200, 200), (255, 80, 80, 180)).save(path)
    return path


def main():
    image = make_test_image(os.path.join(OUT, "sample.png"))
    pdf = make_test_pdf(os.path.join(OUT, "sample.pdf"))
    logo = make_logo(os.path.join(OUT, "logo.png"))

    cases = [
        ("text-single", WatermarkConfig()),
        ("text-tiled", WatermarkConfig(tiled=True, tile_spacing=180, rotation=-45)),
        ("logo-single", WatermarkConfig(mode="image", image_path=logo, position="bottom-right", rotation=0)),
        ("logo-tiled", WatermarkConfig(mode="image", image_path=logo, tiled=True, rotation=-30, opacity=30)),
    ]

    for name, cfg in cases:
        src_img = Image.open(image)
        out_img = os.path.join(OUT, f"wm_{name}.png")
        apply_image_watermark(src_img, cfg).convert("RGB").save(out_img)
        assert os.path.getsize(out_img) > 0, f"图片输出为空: {name}"

        out_pdf = export_file(pdf, cfg, OUT)
        assert os.path.exists(out_pdf), f"PDF 未生成: {name}"
        with fitz.open(out_pdf) as doc:
            assert len(doc) == 3, f"PDF 页数不对: {name}"

    # JPEG 输出(需要丢 alpha)
    out_jpg = export_file(image, WatermarkConfig(), OUT, img_format="jpg")
    assert out_jpg.endswith(".jpg") and os.path.getsize(out_jpg) > 0

    print("ALL CORE TESTS PASSED")
    print("输出目录:", OUT)


if __name__ == "__main__":
    main()
