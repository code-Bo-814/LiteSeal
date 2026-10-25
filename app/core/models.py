"""水印配置数据模型。"""

from dataclasses import dataclass

# 九宫格位置
POSITIONS = [
    "top-left", "top-center", "top-right",
    "middle-left", "center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
]

POSITION_LABELS = {
    "top-left": "左上", "top-center": "上中", "top-right": "右上",
    "middle-left": "左中", "center": "居中", "middle-right": "右中",
    "bottom-left": "左下", "bottom-center": "下中", "bottom-right": "右下",
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PDF_EXTS = {".pdf"}
SUPPORTED_EXTS = IMAGE_EXTS | PDF_EXTS


@dataclass
class WatermarkConfig:
    """一次水印任务的全部参数。size_pct 表示水印高度占画面短边的百分比。"""

    mode: str = "text"          # "text" | "image"

    # 文字水印
    text: str = "LiteSeal"
    font_size_pct: int = 6      # 文字高度 ≈ 短边 * pct / 100
    color: str = "#FFFFFF"

    # 图片水印
    image_path: str = ""
    image_size_pct: int = 14    # logo 高度 ≈ 短边 * pct / 100

    # 公共参数
    opacity: int = 40           # 0-100
    rotation: int = -30         # 角度,-90 ~ 90
    tiled: bool = False
    tile_spacing: int = 200     # 平铺间距,相邻水印中心距 = 水印尺寸 * spacing / 100
    position: str = "center"    # tiled=False 时生效
    margin_pct: int = 4         # 单个水印距边距,短边的百分比
