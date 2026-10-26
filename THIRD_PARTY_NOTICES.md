# 第三方开源组件声明(THIRD PARTY NOTICES)

LiteSeal 使用了以下优秀的开源组件。各组件归其原作者所有,本文件按其许可证要求作出声明与致谢。

本项目以 **GNU AGPL-3.0** 发布,与下表各组件的许可证均兼容。

| # | 组件 | 版本 | 许可证 | 用途 | 主页 |
| --- | --- | --- | --- | --- | --- |
| 1 | PySide6 (Qt for Python) | 6.12 | LGPL-3.0 | 桌面 GUI 框架(动态链接引用) | https://www.qt.io/ |
| 2 | PySide6-Fluent-Widgets | 1.11 | GPL-3.0 | Fluent Design 风格 UI 组件库 | https://qfluentwidgets.com/ |
| 3 | Pillow | 13.0 | MIT-CMU | 图像解码、水印图层渲染与格式转换 | https://python-pillow.org/ |
| 4 | PyMuPDF | 2.0 | AGPL-3.0 | PDF 页面渲染与水印写入 | https://pymupdf.readthedocs.io/ |
| 5 | PyInstaller | 6.22 | GPL-2.0(含 bootloader 例外) | 构建独立可执行程序(仅构建期使用) | https://pyinstaller.org/ |
| 6 | Inno Setup | 7.x | Inno Setup License | 制作 Windows 安装包(仅构建期使用) | https://jrsoftware.org/isinfo.php |

## 许可证合规说明

1. **PySide6(LGPL-3.0)**:本应用以常规导入方式(相当于动态链接)使用 PySide6,用户可自行替换其副本,符合 LGPL-3.0 要求。
2. **PySide6-Fluent-Widgets(GPL-3.0)**:其免费版按 GPL-3.0 授权;本项目随之以 AGPL-3.0(与 GPL-3.0 单向兼容)发布,合规。
3. **PyMuPDF(AGPL-3.0)**:本项目整体以 AGPL-3.0 发布并随分发提供完整源码,满足其要求。
4. **PyInstaller / Inno Setup**:属于构建工具链,仅在本项目开发期使用,其许可证不要求以之打包的产物遵守同许可证(且本项目本身即开源)。
5. 应用图标由 `app/resources/make_icon.py` 程序化生成,不包含任何第三方素材;文档中的 Shields.io 徽章为外部服务,不随仓库分发。

## 各许可证全文

- AGPL-3.0:见本仓库 `LICENSE`,或 https://www.gnu.org/licenses/agpl-3.0.txt
- LGPL-3.0:https://www.gnu.org/licenses/lgpl-3.0.html
- GPL-3.0:https://www.gnu.org/licenses/gpl-3.0.html
- MIT-CMU(Pillow):https://github.com/python-pillow/Pillow/blob/main/LICENSE
- Inno Setup License:https://jrsoftware.org/files/license.txt

如有任何许可证方面的问题或发现声明疏漏,请提 Issue 联系我们,我们会及时补正。
