# LiteSeal

轻量的图片 / PDF 批量加水印桌面工具(Windows)。所见即所得,拖进来、调参数、导出,三步完事。

## 功能

### 文件与导出
- 支持 **PNG / JPG / WEBP / BMP / PDF** 批量加水印,可直接拖拽导入,列表内按 `Delete` 删除
- 手机照片自动按 **EXIF 方向**摆正,预览与导出一致
- 导出在后台线程进行,界面不卡顿,带进度条;单个文件失败不影响批次,失败原因直接提示
- 导出完成后可一键**打开输出文件夹**;图片可保持原格式或统一转 PNG / JPG / WEBP;PDF 输出 `xxx_watermarked.pdf`(总页数不变)
- **自动记住**上次的水印参数、水印图片、输出目录、窗口大小和面板布局,下次启动直接就绪

### 水印能力
- **文字水印**:六种中文字体(微软雅黑 / 黑体 / 宋体 / 楷体 / 仿宋 / Arial)、内容、大小、颜色
- **图片水印**:PNG logo 盖章,支持缩放
- **通用参数**:不透明度、旋转角度;大小按画面短边百分比计算,批量处理尺寸不一的文件比例一致
- 两种布局:**九宫格单枚摆放**(位置 + 边距,也可在预览里**直接拖动**任意摆放)或**平铺整个画面**(密度可调,隔行交错)

### 预览(所见即所得)
- 始终保持宽高比:滚轮 / `Ctrl+滚轮` 缩放,拖拽平移,双击或 `Ctrl+0` 适应窗口,`Ctrl+=` / `Ctrl+-` 步进
- 非平铺水印是独立图层,鼠标变抓手,**按住直接拖到想要的位置**
- 两侧面板可一键收起,预览区占满整窗
- **PDF**:翻页按钮 + **点击页码数字原位变输入框**回车跳转(非法 / 越界 / 空输入一律不理会,保持当前页)
- **弹窗点选式选页**:点"选择页面…",单击选中 / 取消,`Shift+单击` 连选一段,全选 / 清空 / 奇数页 / 偶数页快捷;**预览实时同步**,没选中的页当场盖"未加水印"角标

## 技术栈

| 组件 | 用途 |
| --- | --- |
| Python 3.10+ | 运行环境(开发实测 3.14) |
| PySide6 (Qt for Python) | 桌面界面,Qt 官方 Python 绑定 |
| PySide6-Fluent-Widgets | Win11 Fluent 风格 UI 组件库 |
| Pillow | 图像解码 / 水印图层渲染 |
| PyMuPDF | PDF 页面渲染与水印写入 |
| PyInstaller + Inno Setup 7 | 打包免安装程序与 setup.exe 安装包 |

架构上**水印引擎(`app/core`)与界面(`app/ui`)完全分离**:引擎只依赖 Pillow / PyMuPDF,不依赖 Qt,未来加命令行模式或换 UI 框架可直接复用。

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

本项目以 **[GNU AGPL-3.0](LICENSE)** 协议开源发布。你可以自由使用、学习、修改和分发;若你修改后提供网络服务或分发软件,需按同协议开放源码。商业使用不被禁止,但须遵守 AGPL-3.0 的开源义务。

### 第三方开源组件

本项目站在以下开源项目的肩膀上,感谢这些项目的作者(详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)):

| 组件 | 许可证 | 用途 | 合规说明 |
| --- | --- | --- | --- |
| [PySide6 / Qt](https://www.qt.io/) | LGPL-3.0 | GUI 框架 | 以动态链接方式引用 |
| [PySide6-Fluent-Widgets](https://qfluentwidgets.com/) | GPL-3.0 | Fluent UI 组件 | 本项目整体 AGPL-3.0,兼容 |
| [Pillow](https://python-pillow.org/) | MIT-CMU | 图像处理 | 宽松许可 |
| [PyMuPDF](https://pymupdf.readthedocs.io/) | AGPL-3.0 | PDF 处理 | 同 AGPL,兼容 |
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0(含引导例外) | 打包工具 | 仅构建期使用,不传染产物 |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | Inno Setup License | 安装包制作 | 仅构建期使用 |

> 若你 fork 后想改用 MIT / Apache 等宽松许可证,需先替换 PyMuPDF(可换 pypdf + reportlab)与 qfluentwidgets,并重审上表。应用图标由 `app/resources/make_icon.py` 程序化生成,不含第三方素材。
