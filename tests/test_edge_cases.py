"""核心引擎边界测试:python tests/test_edge_cases.py

覆盖:损坏/空文件、特殊色彩模式、极端比例、大图、中文与空格文件名、
格式转换、EXIF 方向、加密 PDF、页码范围解析。
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf as fitz
from PIL import Image

from app.core.exporter import export_file
from app.core.image_wm import apply_image_watermark
from app.core.models import WatermarkConfig
from app.core.pdf_wm import parse_page_spec

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output", "edge")
os.makedirs(OUT, exist_ok=True)
CFG = WatermarkConfig()


def expect_error(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except Exception as e:
        assert str(e), "异常信息不应为空"
        return
    raise AssertionError(f"应当报错但没有: {fn.__name__}")


def make(name, img):
    path = os.path.join(OUT, name)
    img.save(path)
    return path


def main():
    # 1) 损坏 / 空文件:报干净错误,不能把进程带崩
    broken = os.path.join(OUT, "broken.png")
    with open(broken, "wb") as f:
        f.write(b"this is not an image at all")
    expect_error(export_file, broken, CFG, OUT)
    empty = os.path.join(OUT, "empty.png")
    open(empty, "wb").close()
    expect_error(export_file, empty, CFG, OUT)

    # 2) 特殊色彩模式
    p_img = Image.new("P", (60, 40))
    p_img.putpalette([i // 3 for i in range(768)])
    for src in (
        make("palette.png", p_img),
        make("gray.png", Image.new("L", (60, 40), 120)),
        make("cmyk.jpg", Image.new("CMYK", (60, 40), (50, 50, 50, 0))),
        make("rgba.png", Image.new("RGBA", (60, 40), (200, 30, 30, 128))),
    ):
        out = export_file(src, CFG, OUT)  # keep = 各自转 png/jpg
        assert os.path.getsize(out) > 0, src

    # 3) 极端宽高比:单枚与平铺都不越界
    stick = make("stick.png", Image.new("RGB", (3000, 100), (10, 120, 160)))
    for cfg in (CFG, WatermarkConfig(tiled=True, tile_spacing=150)):
        out = apply_image_watermark(Image.open(stick), cfg)
        assert out.size == (3000, 100), out.size

    # 4) 大图性能:4000x3000 单次处理应有明确上限
    big = make("big.png", Image.new("RGB", (4000, 3000), (90, 90, 200)))
    t0 = time.time()
    export_file(big, CFG, OUT)
    cost = time.time() - t0
    assert cost < 15, f"大图处理过慢: {cost:.1f}s"

    # 5) 中文 + 空格文件名
    cn = make("测试 图 片.png", Image.new("RGB", (300, 200), (20, 150, 90)))
    out = export_file(cn, CFG, OUT)
    assert os.path.isfile(out) and "测试 图 片_watermarked" in out

    # 6) 格式转换矩阵
    webp_src = make("conv.webp", Image.new("RGB", (80, 60), (150, 60, 60)))
    bmp_src = make("conv.bmp", Image.new("RGB", (80, 60), (60, 150, 60)))
    assert export_file(webp_src, CFG, OUT, img_format="png").endswith(".png")
    assert export_file(bmp_src, CFG, OUT, img_format="webp").endswith(".webp")
    assert export_file(bmp_src, CFG, OUT, img_format="jpg").endswith(".jpg")

    # 7) EXIF 方向:竖拍照片导出后应按摆正后的尺寸
    exif_src = os.path.join(OUT, "exif.jpg")
    ex = Image.Exif()
    ex[274] = 6  # Orientation: 旋转 90°CW 显示
    Image.new("RGB", (200, 100), (170, 60, 60)).save(exif_src, exif=ex.tobytes())
    out = export_file(exif_src, CFG, OUT, img_format="png")
    assert Image.open(out).size == (100, 200), Image.open(out).size

    # 8) 加密 PDF:报干净错误
    enc = os.path.join(OUT, "encrypted.pdf")
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "secret")
    doc.save(enc, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()
    expect_error(export_file, enc, CFG, OUT)

    # 9) 页码范围:开放区间与越界
    assert parse_page_spec("3-", 5) == [2, 3, 4]
    assert parse_page_spec("-2", 5) == [0, 1]
    assert parse_page_spec("2-", 3) == [1, 2]
    expect_error(parse_page_spec, "9-10", 3)  # 全越界 => "不在页数内"
    expect_error(parse_page_spec, "5-2", 3)

    print("ALL EDGE CASE TESTS PASSED")


if __name__ == "__main__":
    main()
