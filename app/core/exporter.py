"""批量导出入口:按扩展名分发到图片 / PDF 引擎。"""

from __future__ import annotations

import os

from PIL import Image

from .image_wm import apply_image_watermark, save_image
from .models import IMAGE_EXTS, PDF_EXTS, SUPPORTED_EXTS, WatermarkConfig
from .pdf_wm import apply_pdf_watermark

_KEEP_EXT_TO_FMT = {"png": "png", "jpg": "jpg", "jpeg": "jpg", "webp": "webp", "bmp": "bmp"}


def export_file(path: str, cfg: WatermarkConfig, out_dir: str,
                img_format: str = "keep") -> str:
    """处理单个文件,输出到 out_dir,返回输出路径。img_format: keep/png/jpg/webp。"""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"不支持的文件类型: {ext}")
    stem = os.path.splitext(os.path.basename(path))[0]

    if ext in PDF_EXTS:
        out_path = os.path.join(out_dir, stem + "_watermarked.pdf")
        return apply_pdf_watermark(path, out_path, cfg)

    fmt = _KEEP_EXT_TO_FMT.get(ext.lstrip("."), "png") if img_format == "keep" else img_format
    out_ext = "jpg" if fmt == "jpg" else fmt
    out_path = os.path.join(out_dir, stem + "_watermarked." + out_ext)
    with Image.open(path) as img:
        save_image(apply_image_watermark(img, cfg), out_path, fmt)
    return out_path
