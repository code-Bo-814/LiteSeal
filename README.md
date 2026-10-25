# LiteSeal

轻量的图片 / PDF 批量加水印桌面工具(Windows)。

![技术栈](https://img.shields.io/badge/Python-PySide6-blue)

## 功能

- 支持 **PNG / JPG / WEBP / BMP / PDF** 批量加水印,可直接拖拽导入
- **文字水印**:自定义内容、大小、颜色、透明度、旋转角度
- **图片水印**:用 PNG logo 盖章,支持缩放
- 两种布局:**九宫格单枚摆放**(位置 + 边距)或 **平铺整个画面**(密度可调)
- 所见即所得的实时预览(图片与 PDF 效果一致,PDF 预览首页)
- 图片可保持原格式或统一输出为 PNG / JPG / WEBP;PDF 输出 `xxx_watermarked.pdf`
- 导出在后台线程进行,界面不卡顿

## 开发运行

要求 Python 3.10+(Windows)。

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 运行
python main.py

# 核心引擎冒烟测试(生成 tests/output 查看效果)
python tests/test_core.py

# GUI 启动测试(窗口弹出 2.5 秒后自动关闭)
python tests/smoke_gui.py
```

## 打包安装程序

两步:PyInstaller 打出免安装程序 → Inno Setup 包成 setup.exe。

1. 安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)(带中文语言包),确保 `iscc` 在 PATH 里
2. 双击或命令行运行:

```bat
packaging\build_windows.bat
```

产物:

- `dist\LiteSeal\` —— 免安装版程序目录
- `packaging\dist\LiteSeal-Setup-0.1.0.exe` —— 标准安装包(带向导、开始菜单/桌面快捷方式、卸载器)

## 目录结构

```
LiteSeal/
├── main.py                 # 入口
├── app/
│   ├── core/               # 水印引擎(与界面无关,可复用/写 CLI)
│   │   ├── models.py       # WatermarkConfig 参数模型
│   │   ├── image_wm.py     # Pillow 图层引擎(图片与 PDF 共用)
│   │   ├── pdf_wm.py       # PyMuPDF PDF 水印
│   │   └── exporter.py     # 批量导出分发
│   └── ui/
│       ├── main_window.py  # 主窗口
│       └── workers.py      # 导出线程
├── packaging/              # PyInstaller spec / Inno Setup 脚本 / 构建脚本
└── tests/                  # 冒烟测试
```

## 许可证

本项目以 **AGPL-3.0** 开源发布(完整文本见 `LICENSE`)。

依赖许可一览:

| 依赖 | 许可证 | 说明 |
| --- | --- | --- |
| PyMuPDF | AGPL-3.0 | 要求整个项目以 AGPL 兼容许可开源——本项目正是如此 |
| PySide6-Fluent-Widgets | GPL-3.0 | 开源版本;界面组件 |
| PySide6 (Qt) | LGPL-3.0 | 正常引用即可 |
| Pillow | MIT-CMU | 宽松 |
| PyInstaller | GPL-2.0 | 仅构建工具,打包产物不受传染 |

> 注意:若将来想改用 MIT/Apache 等宽松许可证,需先替换掉 PyMuPDF
> (可换 pypdf + reportlab)与 qfluentwidgets,并重审上表。
