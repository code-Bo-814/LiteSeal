"""生成应用图标:在项目根目录运行 .venv/Scripts/python -m app.resources.make_icon"""

import os
from PIL import Image, ImageDraw
from app.core.image_wm import load_font

HERE = os.path.dirname(os.path.abspath(__file__))
S = 512

def build() -> Image.Image:
    # 1. 创建纯透明画布
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    
    # 定义青色主题色和黑色
    theme_color = (13, 138, 148, 255) 
    black_color = (0, 0, 0, 255)
    
    # 2. 画阴影（向右下偏移 6 像素的黑框）
    shadow_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw_shadow = ImageDraw.Draw(shadow_layer)
    offset = 6
    draw_shadow.rounded_rectangle(
        [32 + offset, 32 + offset, S - 32 + offset, S - 32 + offset], 
        radius=100, outline=black_color, width=8
    )
    img = Image.alpha_composite(img, shadow_layer)
    
    # 3. 画正面的黑色实线边框
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [32, 32, S - 32, S - 32], 
        radius=100, outline=black_color, width=8
    )

    # 4. 画反光条
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([32, 32, S - 32, S - 32], radius=100, fill=255)
    
    stripe_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw_stripe = ImageDraw.Draw(stripe_layer)
    
    # 反光条1：主斜条（大面积的青绿半透明）
    draw_stripe.polygon([(0, 400), (S, 100), (S, 200), (0, 500)],
                        fill=(theme_color[0], theme_color[1], theme_color[2], 90))
    
    # 反光条2：左上角中号条（偏白的青绿高光，冲出云霄）
    # 坐标：[(0, 200), (400, -34), (400, 6), (0, 240)]
    draw_stripe.polygon([(0, 200), (400, -34), (400, 6), (0, 240)],
                        fill=(150, 230, 240, 100)) 
    
    # 反光条3：极细高光（0.8 半透明版）
    draw_stripe.polygon([(0, 170), (400, -64), (400, -60), (0, 174)],
                        fill=(140, 240, 250, 130)) 
    
    # 裁剪并叠加反光条
    stripe_cropped = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    stripe_cropped.paste(stripe_layer, (0, 0), mask)
    img = Image.alpha_composite(img, stripe_cropped)

    # 5. 写字 "LS"
    draw = ImageDraw.Draw(img)
    font = load_font(230, "黑体")
    
    draw.text((S / 2 + 4, S / 2 + 4), "LS", font=font, fill=black_color, anchor="mm")
    draw.text(
        (S / 2, S / 2), "LS", font=font, 
        fill=theme_color, 
        anchor="mm",
        stroke_width=4, 
        stroke_fill=black_color
    )
    
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