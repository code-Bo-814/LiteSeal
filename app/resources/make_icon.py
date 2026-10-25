"""生成应用图标:在项目根目录运行 .venv/Scripts/python -m app.resources.make_icon"""

import os

from PIL import Image, ImageDraw

from app.core.image_wm import load_font

HERE = os.path.dirname(os.path.abspath(__file__))
S = 512


def build() -> Image.Image:
    img = Image.new("RGBA", (S, S), (13, 138, 148, 255))

    # 斜向半透明白条,呼应"水印"意象
    stripe = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(stripe).polygon([(0, 400), (S, 90), (S, 190), (0, 500)],
                                   fill=(255, 255, 255, 36))
    img = Image.alpha_composite(img, stripe)

    # 圆角蒙版最后套上,斜条才不会露出圆角
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([16, 16, S - 16, S - 16], radius=100, fill=255)
    img.putalpha(mask)

    draw = ImageDraw.Draw(img)
    font = load_font(230, "黑体")
    draw.text((S / 2, S / 2), "LS", font=font, fill=(255, 255, 255, 255), anchor="mm")
    return img


def main():
    icon = build()
    png = os.path.join(HERE, "icon.png")
    ico = os.path.join(HERE, "icon.ico")
    icon.save(png)
    icon.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                          (64, 64), (128, 128), (256, 256)])
    print("written:", png, "and", ico)


if __name__ == "__main__":
    main()
