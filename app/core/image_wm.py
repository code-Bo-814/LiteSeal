"""基于 Pillow 的水印图层引擎。

图片水印和 PDF 水印共用这套图层逻辑:
按目标尺寸生成一张 RGBA 水印图层,再叠加到底图上,
保证 GUI 预览、图片输出、PDF 输出三处效果完全一致。
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from .models import WatermarkConfig

# Windows 常见中文字体,按优先级尝试
_FONT_CANDIDATES = [
    "msyh.ttc",      # 微软雅黑
    "simhei.ttf",    # 黑体
    "simsun.ttc",    # 宋体
    "arial.ttf",
]


def load_font(px: int) -> ImageFont.FreeTypeFont:
    for name in _FONT_CANDIDATES:
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        try:
            return ImageFont.truetype(path, max(8, px))
        except OSError:
            continue
    return ImageFont.load_default()


def _apply_opacity(img: Image.Image, opacity: int) -> Image.Image:
    if opacity >= 100 or img.mode != "RGBA":
        return img
    alpha = img.getchannel("A").point(lambda v: v * opacity // 100)
    img.putalpha(alpha)
    return img


def _text_element(cfg: WatermarkConfig, base_px: int) -> Image.Image:
    px = max(8, round(base_px * cfg.font_size_pct / 100))
    font = load_font(px)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), cfg.text or " ", font=font)
    pad = max(2, px // 8)
    w, h = right - left, bottom - top
    img = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((pad - left, pad - top), cfg.text or " ", font=font, fill=cfg.color)
    return img


def _image_element(cfg: WatermarkConfig, base_px: int) -> Image.Image:
    logo = Image.open(cfg.image_path).convert("RGBA")
    target_h = max(8, round(base_px * cfg.image_size_pct / 100))
    target_w = max(8, round(logo.width * target_h / logo.height))
    return logo.resize((target_w, target_h), Image.Resampling.LANCZOS)


def build_layer(size: tuple[int, int], cfg: WatermarkConfig) -> Image.Image:
    """生成与 size 同尺寸的 RGBA 水印图层。"""
    width, height = size
    base_px = min(width, height)
    element = _image_element(cfg, base_px) if cfg.mode == "image" else _text_element(cfg, base_px)
    ew, eh = element.size

    if cfg.rotation % 360 != 0:
        element = element.rotate(cfg.rotation, resample=Image.Resampling.BICUBIC, expand=True)
        element = _apply_opacity(element, cfg.opacity)
    else:
        element = _apply_opacity(element, cfg.opacity)

    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    if cfg.tiled:
        # 平铺:在超出一圈的画布上铺格子,再裁回原尺寸,旋转后四角才不会露白
        step_x = max(8, round(ew * cfg.tile_spacing / 100))
        step_y = max(8, round(eh * cfg.tile_spacing / 100))
        pad_x, pad_y = ew * 2, eh * 2
        canvas = Image.new("RGBA", (width + pad_x * 2, height + pad_y * 2), (0, 0, 0, 0))
        y = 0
        row = 0
        while y < canvas.height:
            offset = (step_x // 2) if row % 2 else 0  # 隔行错开半个间距
            x = -offset
            while x < canvas.width:
                canvas.alpha_composite(element, (x, y))
                x += step_x
            y += step_y
            row += 1
        layer.alpha_composite(canvas.crop((pad_x, pad_y, pad_x + width, pad_y + height)))
    else:
        margin = round(base_px * cfg.margin_pct / 100)
        y_opts = {"top": margin, "middle": (height - eh) // 2, "bottom": height - eh - margin}
        x_opts = {"left": margin, "center": (width - ew) // 2, "right": width - ew - margin}
        if "-" in cfg.position:
            v, h = cfg.position.split("-", 1)
        else:  # "center"
            v, h = "middle", "center"
        layer.alpha_composite(element, (x_opts[h], y_opts[v]))

    return layer


def apply_image_watermark(img: Image.Image, cfg: WatermarkConfig) -> Image.Image:
    """给 PIL 图片叠加水印,返回 RGBA 结果。"""
    img = img.convert("RGBA")
    return Image.alpha_composite(img, build_layer(img.size, cfg))


def save_image(img: Image.Image, path: str, fmt: str) -> None:
    """按目标格式保存,JPEG 自动丢 alpha。"""
    if fmt in ("jpg", "jpeg"):
        img.convert("RGB").save(path, "JPEG", quality=92)
    elif fmt == "png":
        img.save(path, "PNG")
    elif fmt == "webp":
        img.save(path, "WEBP", quality=92)
    elif fmt == "bmp":
        img.convert("RGB").save(path, "BMP")
    else:
        raise ValueError(f"不支持的图片格式: {fmt}")
