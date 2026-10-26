"""基于 PyMuPDF 的 PDF 水印。

每页按 2x 页面尺寸渲染水印图层后整页叠加,文字锐度和预览一致。
"""

from __future__ import annotations

import io
import os
import tempfile

import pymupdf as fitz
from PIL import Image

from .image_wm import build_layer
from .models import WatermarkConfig

_ZOOM = 2.0  # 图层渲染倍率,保证叠加进 PDF 后文字清晰


import re

_PAGE_TABLE = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "，": ",", "、": ",", "；": ";", "：": ",",
    "（": ",", "）": ",",
    "～": "-", "〜": "-", "－": "-", "–": "-", "—": "-",
    "　": " ",
})


def _normalize_spec(spec: str) -> str:
    """把各种人手写法归一成 "1,3,5-8" 的形状,标点长得不一样也能认。"""
    s = spec.translate(_PAGE_TABLE)
    s = s.replace("到", "-").replace("至", "-")
    s = re.sub(r"[;:|/\s]+", ",", s)   # 其余分隔符与空白一律当逗号
    s = s.replace("第", "").replace("页", "")
    s = re.sub(r"-{2,}", "-", s)
    s = re.sub(r",{2,}", ",", s)
    return s.strip(",")


def parse_page_spec(spec: str, total: int) -> list[int]:
    """把 "1,3,5-8" 这类页码描述解析成 0 起始页索引列表。

    空 / "全部" / "全选" = 所有页;"奇数页" / "偶数页" 取相应页;
    兼容全角数字与标点、"第1、3页"、"1~3"、"3到5" 等写法;
    超出 total 的页码裁掉;完全无法理解时抛 ValueError。
    """
    if spec is None:
        return list(range(total))
    s = _normalize_spec(str(spec))
    if not s or s.lower() in ("all", "全部", "全选"):
        return list(range(total))
    if s.lower() in ("odd", "奇数"):
        return list(range(0, total, 2))
    if s.lower() in ("even", "偶数"):
        return list(range(1, total, 2))
    indices: set[int] = set()
    for token in s.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_s, _, end_s = token.partition("-")
            try:
                start = int(start_s) if start_s.strip() else 1
                end = int(end_s) if end_s.strip() else total  # "3-" = 3 到最后一页
            except ValueError:
                raise ValueError(f"页码写法不对: {token}")
            if start < 1 or end < start:
                raise ValueError(f"页码写法不对: {token}")
            indices.update(range(start - 1, min(end, total)))
        else:
            try:
                page = int(token)
            except ValueError:
                raise ValueError(f"页码写法不对: {token}")
            if page < 1:
                raise ValueError(f"页码写法不对: {token}")
            if page <= total:
                indices.add(page - 1)
    if not indices:
        raise ValueError("页码范围不在文档页数内")
    return sorted(indices)


def pages_to_spec(indices: list[int], total: int) -> str:
    """把 0 起始页索引列表压成紧凑页码串(如 "1,3,5-8");全选返回 ""(=全部)。"""
    idx = sorted({i for i in indices if 0 <= i < total})
    if not idx or len(idx) == total:
        return ""
    parts = []
    start = prev = idx[0]
    for i in idx[1:]:
        if i == prev + 1:
            prev = i
            continue
        parts.append(str(start + 1) if start == prev else f"{start + 1}-{prev + 1}")
        start = prev = i
    parts.append(str(start + 1) if start == prev else f"{start + 1}-{prev + 1}")
    return ",".join(parts)


def pdf_page_count(path: str) -> int:
    with fitz.open(path) as doc:
        return len(doc)


def pdf_page_image(path: str, page_no: int = 0, max_px: int = 1400) -> Image.Image:
    """渲染 PDF 某一页为 PIL 图片,用于预览。"""
    with fitz.open(path) as doc:
        page = doc[page_no]
        zoom = min(max_px / max(page.rect.width, 1), max_px / max(page.rect.height, 1), 3.0)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def apply_pdf_watermark(src_path: str, out_path: str, cfg: WatermarkConfig,
                        progress=None) -> str:
    """给 PDF 叠加水印并另存;cfg.pdf_pages 指定页码(空=全部)。

    src == out 时通过临时文件覆盖。
    """
    doc = fitz.open(src_path)
    try:
        pages = parse_page_spec(cfg.pdf_pages, len(doc))
        total = len(pages)
        for i, index in enumerate(pages):
            page = doc[index]
            rect = page.rect
            size = (max(1, round(rect.width * _ZOOM)), max(1, round(rect.height * _ZOOM)))
            layer = build_layer(size, cfg)
            buf = io.BytesIO()
            layer.save(buf, "PNG")
            page.insert_image(rect, stream=buf.getvalue(), overlay=True)
            if progress:
                progress(i + 1, total)
        if os.path.abspath(src_path) == os.path.abspath(out_path):
            fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=os.path.dirname(out_path) or None)
            os.close(fd)
            doc.save(tmp, garbage=3, deflate=True)
            doc.close()
            os.replace(tmp, out_path)
        else:
            doc.save(out_path, garbage=3, deflate=True)
    finally:
        if not doc.is_closed:
            doc.close()
    return out_path
