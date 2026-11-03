# LiteSeal

LiteSeal 是一款适用于 Windows 系统的轻量级图片与 PDF 批量加水印桌面工具。软件支持拖拽导入、实时预览与批量导出，旨在提供高效、稳定、无负担的本地水印处理体验。

## 功能特性

### 文件处理与导出
- **格式支持**：支持 PNG、JPG、WEBP、BMP、PDF 格式文件的批量加水印处理。支持拖拽导入，并可在列表中按 `Delete` 键移除文件。
- **图像方向校正**：自动根据 EXIF 信息校正手机照片方向，确保预览与导出效果一致。
- **异步导出**：导出任务在后台线程运行，提供进度条显示，避免界面卡顿。单个文件处理失败不影响整体批次，并会明确提示失败原因。
- **输出管理**：导出完成后可快速打开输出目录。图片支持保持原格式，或统一转换为 PNG/JPG/WEBP；PDF 默认输出文件名为 `xxx_watermarked.pdf`（页数与原文件一致）。
- **配置记忆**：自动保存并恢复上次使用的水印参数、水印图片、输出目录、窗口大小及面板布局配置。

### 水印能力
- **文字水印**：提供微软雅黑、黑体、宋体、楷体、仿宋、Arial 六种字体。支持自定义内容、字号大小及颜色。
- **图片水印**：支持添加 PNG 格式的 Logo 图片，并支持缩放调节。
- **通用参数**：可调节水印不透明度及旋转角度。水印尺寸基于画面短边的百分比计算，确保在处理不同尺寸文件时保持比例一致。
- **布局模式**：
  - **九宫格单枚摆放**：支持设置位置与边距，或在预览区直接拖拽水印调整位置。
  - **平铺模式**：水印覆盖整个画面，支持调节密度及隔行交错效果。

### 预览与交互
- **视图控制**：预览区始终锁定图像宽高比。支持滚轮或 `Ctrl+滚轮` 缩放、鼠标拖拽平移；双击或 `Ctrl+0` 适应窗口，`Ctrl+=` / `Ctrl+-` 步进缩放。
- **拖拽定位**：在非平铺模式下，水印作为独立图层，鼠标指针变为抓手样式，支持直接拖拽移动至目标位置。
- **界面布局**：两侧面板支持折叠，折叠后预览区将占满整个窗口。
- **PDF 页面跳转**：支持翻页按钮。点击页码数字可切换为输入框，输入页码后按回车跳转（遇到非法、越界或空输入时，将保持当前页）。
- **页面选择器**：点击“选择页面...”可打开弹窗。
  - 支持单击选中/取消选中，`Shift+单击` 连选。
  - 提供全选、清空、选择奇数页、选择偶数页快捷操作。
  - 预览区实时同步选择结果，未选中的页面会显示“未加水印”角标。

## 技术栈

| 组件 | 用途 |
| --- | --- |
| Python 3.10+ | 运行环境(开发实测 3.14) |
| PySide6 (Qt for Python) | 桌面界面,Qt 官方 Python 绑定 |
| PySide6-Fluent-Widgets | Win11 Fluent 风格 UI 组件库 |
| Pillow | 图像解码 / 水印图层渲染 |
| PyMuPDF | PDF 页面渲染与水印写入 |
| PyInstaller + Inno Setup 7 | 打包免安装程序与 setup.exe 安装包 |

架构上，水印引擎（`app/core`）与界面（`app/ui`）采用完全解耦的设计。核心引擎仅依赖 Pillow 与 PyMuPDF，不耦合任何 Qt 组件。该架构保证了核心逻辑的独立性，具备良好的扩展性，便于后续扩展 CLI（命令行）接口或适配其他 UI 框架。

## 项目结构

```
LiteSeal/
├── main.py                  # 入口
├── app/
│   ├── core/                # 水印引擎(与界面无关,可复用)
│   │   ├── models.py        # WatermarkConfig 参数模型(含默认值)
│   │   ├── image_wm.py      # Pillow 图层引擎:元素渲染 / 定位 / 平铺(图片与 PDF 共用)
│   │   ├── pdf_wm.py        # PyMuPDF:页面渲染、选页解析与写入
│   │   └── exporter.py      # 批量导出分发(格式转换 / EXIF 摆正)
│   ├── ui/
│   │   ├── main_window.py   # 主窗口、可缩放预览、参数面板、持久化
│   │   ├── page_picker.py   # PDF 选页弹窗(点选 / Shift 连选)
│   │   └── workers.py       # 后台导出线程
│   └── resources/           # 应用图标(make_icon.py 可重新生成)
├── packaging/               # PyInstaller spec / Inno Setup 脚本 / 构建脚本
├── tests/                   # 四套自动化测试(见下)
├── LICENSE                  # AGPL-3.0
└── THIRD_PARTY_NOTICES.md   # 第三方开源组件声明
```

## 开发与测试

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python main.py                    # 运行
python tests/test_core.py         # 水印引擎测试(输出样例在 tests/output)
python tests/test_edge_cases.py   # 边界测试(损坏文件 / 特殊色彩模式 / 加密 PDF / EXIF 等)
python tests/test_ui_logic.py     # UI 逻辑回归(离屏运行,不弹窗)
python tests/smoke_gui.py         # GUI 启动冒烟(弹窗 2.5 秒自动关)
```

## 打包

1. 安装 [Inno Setup 7](https://jrsoftware.org/isinfo.php)
2. 运行 `packaging\build_windows.bat`

产物:`dist\LiteSeal\`(免安装版)与 `packaging\dist\LiteSeal-Setup-<版本>.exe`(安装向导 + 快捷方式 + 卸载器)。

## 开源许可声明

本项目基于 **[GNU AGPL-3.0](LICENSE)** 协议开源发布。允许自由使用、学习、修改及分发；但若修改后的软件通过网络提供服务或对外分发，必须依据同协议开放源代码。本项目不限制商业使用，但使用者须严格履行 AGPL-3.0 规定的开源义务。

### 第三方开源组件

本项目站在以下开源项目的肩膀上，感谢这些项目的作者（详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)）：

| 组件 | 许可证 | 用途 | 合规说明 |
| --- | --- | --- | --- |
| [PySide6 / Qt](https://www.qt.io/) | LGPL-3.0 | GUI 框架 | 以动态链接方式引用 |
| [PySide6-Fluent-Widgets](https://qfluentwidgets.com/) | GPL-3.0 | Fluent UI 组件 | 本项目整体 AGPL-3.0，兼容 |
| [Pillow](https://python-pillow.org/) | MIT-CMU | 图像处理 | 宽松许可 |
| [PyMuPDF](https://pymupdf.readthedocs.io/) | AGPL-3.0 | PDF 处理 | 同 AGPL，兼容 |
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0（含引导例外） | 打包工具 | 仅构建期使用，不传染产物 |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | Inno Setup License | 安装包制作 | 仅构建期使用 |

> **开发者提示**：若你 Fork 后想改用 MIT / Apache 等宽松许可证，需先替换 PyMuPDF（可换 `pypdf` + `reportlab`）与 `qfluentwidgets`，并重新审查上表。此外，应用图标由 `app/resources/make_icon.py` 程序化生成，不含第三方素材。
