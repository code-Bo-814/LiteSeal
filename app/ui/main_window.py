"""LiteSeal 主窗口。

布局:左侧文件列表 | 中间预览 | 右侧水印参数面板。
所有参数变动经 150ms 防抖后刷新预览;导出走 ExportWorker 后台线程。
"""

from __future__ import annotations

import os

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (QColorDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMainWindow, QStackedWidget, QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CardWidget, ComboBox, FluentIcon as FIF,
                            InfoBar, InfoBarPosition, LineEdit, ListWidget,
                            PrimaryPushButton, ProgressBar, PushButton, ScrollArea,
                            SegmentedWidget, Slider, StrongBodyLabel, SubtitleLabel,
                            SwitchButton, ToolButton)

from app import APP_NAME, __version__
from app.core.image_wm import apply_image_watermark
from app.core.models import IMAGE_EXTS, PDF_EXTS, POSITION_LABELS, POSITIONS, SUPPORTED_EXTS, WatermarkConfig
from app.core.pdf_wm import pdf_page_image
from app.ui.workers import ExportWorker

PREVIEW_MAX_PX = 1400
IMAGE_FORMAT_ITEMS = ["保持原格式", "PNG", "JPG", "WEBP"]


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class FileList(ListWidget):
    """支持拖拽导入的文件列表。"""

    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            files = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            self.files_dropped.emit(files)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)

        self._files: list[str] = []
        self._watermark_image_path = ""
        self._worker: ExportWorker | None = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._render_preview)

        self._build_ui()
        self._collect_config()  # 初始化一次内部状态
        self._render_preview()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = SubtitleLabel(APP_NAME)
        version = BodyLabel(f"v{__version__} · 给图片和 PDF 批量加水印")
        version.setTextColor(QColor(128, 128, 128), QColor(160, 160, 160))
        header.addWidget(title)
        header.addWidget(version)
        header.addStretch(1)
        root.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(10)
        content.addWidget(self._build_file_panel(), stretch=0)
        content.addWidget(self._build_preview_panel(), stretch=1)
        content.addWidget(self._build_settings_panel(), stretch=0)
        root.addLayout(content, stretch=1)

        root.addWidget(self._build_status_bar())

    def _build_file_panel(self) -> QWidget:
        panel = CardWidget()
        panel.setFixedWidth(260)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(StrongBodyLabel("文件"))

        self.file_list = FileList()
        self.file_list.currentRowChanged.connect(self._on_file_selected)
        self.file_list.files_dropped.connect(self.add_files)
        layout.addWidget(self.file_list, stretch=1)

        btn_row1 = QHBoxLayout()
        btn_add = PushButton(FIF.ADD, "添加")
        btn_add.clicked.connect(self._pick_files)
        btn_remove = ToolButton(FIF.DELETE)
        btn_remove.setToolTip("移除选中")
        btn_remove.clicked.connect(self._remove_selected)
        btn_row1.addWidget(btn_add, stretch=1)
        btn_row1.addWidget(btn_remove)
        layout.addLayout(btn_row1)

        btn_clear = PushButton(FIF.CLOSE, "清空列表")
        btn_clear.clicked.connect(self._clear_files)
        layout.addWidget(btn_clear)
        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = CardWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(StrongBodyLabel("预览"))

        self.preview_area = ScrollArea()
        self.preview_area.setWidgetResizable(True)
        self.preview_area.setFrameShape(ScrollArea.Shape.NoFrame)
        self.preview_label = QLabel("把文件拖进左侧列表开始使用")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(200, 200)
        self.preview_area.setWidget(self.preview_label)
        layout.addWidget(self.preview_area, stretch=1)
        return panel

    def _build_settings_panel(self) -> QWidget:
        outer = CardWidget()
        outer.setFixedWidth(330)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(ScrollArea.Shape.NoFrame)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        scroll.setWidget(panel)
        outer_layout.addWidget(scroll)

        # 水印类型切换
        self.mode_segment = SegmentedWidget(panel)
        self.mode_segment.addItem(routeKey="text", text="文字水印", onClick=lambda: self._on_mode_changed("text"))
        self.mode_segment.addItem(routeKey="image", text="图片水印", onClick=lambda: self._on_mode_changed("image"))
        self.mode_segment.setCurrentItem("text")
        layout.addWidget(self.mode_segment)

        # 文字 / 图片两种参数页
        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._build_text_settings())
        self.mode_stack.addWidget(self._build_image_settings())
        layout.addWidget(self.mode_stack)

        layout.addWidget(self._separator())

        # 公共参数
        layout.addWidget(self._slider_row("不透明度", 5, 100, 40, "%", lambda v: setattr(self, "_opacity", v)))
        layout.addWidget(self._slider_row("旋转角度", -90, 90, -30, "°", lambda v: setattr(self, "_rotation", v)))

        self.tiled_switch = SwitchButton("平铺整个画面", panel)
        self.tiled_switch.checkedChanged.connect(self._on_tiled_changed)
        layout.addWidget(self.tiled_switch)

        self.tile_row = self._slider_row("平铺疏密", 120, 400, 200, "%", lambda v: setattr(self, "_tile_spacing", v))
        layout.addWidget(self.tile_row)

        pos_row = QHBoxLayout()
        pos_row.addWidget(BodyLabel("位置"))
        self.position_combo = ComboBox()
        for key in POSITIONS:
            self.position_combo.addItem(POSITION_LABELS[key], userData=key)
        self.position_combo.setCurrentIndex(4)  # 居中
        self.position_combo.currentIndexChanged.connect(self._schedule_preview)
        pos_row.addWidget(self.position_combo, stretch=1)
        pos_widget = QWidget()
        pos_widget.setLayout(pos_row)
        self.pos_widget = pos_widget
        layout.addWidget(pos_widget)

        layout.addWidget(self._slider_row("边距", 0, 20, 4, "%", lambda v: setattr(self, "_margin", v)))
        self.margin_row = layout.itemAt(layout.count() - 1).widget()

        layout.addWidget(self._separator())

        # 输出设置
        out_row = QHBoxLayout()
        out_row.addWidget(BodyLabel("图片输出格式"))
        self.format_combo = ComboBox()
        self.format_combo.addItems(IMAGE_FORMAT_ITEMS)
        out_row.addWidget(self.format_combo, stretch=1)
        out_widget = QWidget()
        out_widget.setLayout(out_row)
        layout.addWidget(out_widget)

        self.export_btn = PrimaryPushButton(FIF.SAVE, "选择文件夹并导出")
        self.export_btn.clicked.connect(self._export)
        layout.addWidget(self.export_btn)
        layout.addStretch(1)

        self._on_tiled_changed(False)
        return outer

    def _build_text_settings(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        self.text_edit = LineEdit()
        self.text_edit.setPlaceholderText("输入水印文字")
        self.text_edit.setText("LiteSeal")
        self.text_edit.textChanged.connect(self._schedule_preview)
        layout.addWidget(self.text_edit)

        layout.addWidget(self._slider_row("文字大小", 3, 30, 6, "%", lambda v: setattr(self, "_font_size", v)))

        color_row = QHBoxLayout()
        color_row.addWidget(BodyLabel("文字颜色"))
        self._color = "#FFFFFF"
        self.color_btn = ToolButton(FIF.BRUSH)
        self.color_btn.clicked.connect(self._pick_color)
        self._update_color_btn()
        color_row.addWidget(self.color_btn)
        color_row.addStretch(1)
        color_widget = QWidget()
        color_widget.setLayout(color_row)
        layout.addWidget(color_widget)
        return w

    def _build_image_settings(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        pick_btn = PushButton(FIF.PHOTO, "选择水印图片")
        pick_btn.clicked.connect(self._pick_watermark_image)
        layout.addWidget(pick_btn)
        self.image_path_label = BodyLabel("未选择(建议用带透明通道的 PNG)")
        self.image_path_label.setTextColor(QColor(128, 128, 128), QColor(160, 160, 160))
        self.image_path_label.setWordWrap(True)
        layout.addWidget(self.image_path_label)

        layout.addWidget(self._slider_row("图片大小", 3, 60, 14, "%", lambda v: setattr(self, "_image_size", v)))
        return w

    def _slider_row(self, label: str, min_v: int, max_v: int, value: int,
                    suffix: str, on_change) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        top = QHBoxLayout()
        name = BodyLabel(label)
        value_label = BodyLabel(f"{value}{suffix}")
        top.addWidget(name)
        top.addStretch(1)
        top.addWidget(value_label)
        slider = Slider(Qt.Horizontal)
        slider.setRange(min_v, max_v)
        slider.setValue(value)

        def changed(v):
            value_label.setText(f"{v}{suffix}")
            on_change(v)
            self._schedule_preview()

        slider.valueChanged.connect(changed)
        layout.addLayout(top)
        layout.addWidget(slider)
        w.slider = slider  # 保留引用
        return w

    def _separator(self) -> QWidget:
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(128,128,128,60);")
        return line

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 0, 4, 0)
        self.progress = ProgressBar()
        self.progress.setFixedWidth(260)
        self.progress.hide()
        self.status_label = BodyLabel("就绪")
        self.status_label.setTextColor(QColor(128, 128, 128), QColor(160, 160, 160))
        layout.addWidget(self.status_label, stretch=1)
        layout.addWidget(self.progress)
        return bar

    # ------------------------------------------------------- 配置收集与预览

    def _collect_config(self) -> WatermarkConfig:
        return WatermarkConfig(
            mode=self.mode_segment.currentItem() if hasattr(self, "mode_segment") else "text",
            text=self.text_edit.text() if hasattr(self, "text_edit") else "LiteSeal",
            font_size_pct=getattr(self, "_font_size", 6),
            color=getattr(self, "_color", "#FFFFFF"),
            image_path=self._watermark_image_path,
            image_size_pct=getattr(self, "_image_size", 14),
            opacity=getattr(self, "_opacity", 40),
            rotation=getattr(self, "_rotation", -30),
            tiled=self.tiled_switch.isChecked() if hasattr(self, "tiled_switch") else False,
            tile_spacing=getattr(self, "_tile_spacing", 200),
            position=self.position_combo.currentData() if hasattr(self, "position_combo") else "center",
            margin_pct=getattr(self, "_margin", 4),
        )

    def _schedule_preview(self):
        self._preview_timer.start()

    def _on_file_selected(self, row):
        self._render_preview()

    def _current_file(self) -> str | None:
        if not self._files:
            return None
        row = self.file_list.currentRow()
        if 0 <= row < len(self._files):
            return self._files[row]
        return self._files[0]

    def _load_preview_base(self, path: str) -> Image.Image | None:
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in PDF_EXTS:
                return pdf_page_image(path, 0, PREVIEW_MAX_PX)
            if ext in IMAGE_EXTS:
                with Image.open(path) as img:
                    img = img.convert("RGBA")
                    img.thumbnail((PREVIEW_MAX_PX, PREVIEW_MAX_PX), Image.Resampling.LANCZOS)
                    return img.copy()
        except Exception as e:
            self.preview_label.setText(f"无法打开文件:\n{e}")
        return None

    def _render_preview(self):
        path = self._current_file()
        if not path:
            self.preview_label.clear()
            self.preview_label.setText("把文件拖进左侧列表开始使用")
            return
        base = self._load_preview_base(path)
        if base is None:
            return
        result = apply_image_watermark(base, self._collect_config())
        pixmap = _pil_to_pixmap(result)
        self.preview_label.setText("")
        self.preview_label.setPixmap(pixmap)

    # ---------------------------------------------------------- 文件列表操作

    def add_files(self, paths: list[str]):
        added = 0
        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if ext in SUPPORTED_EXTS and p not in self._files:
                self._files.append(p)
                self.file_list.addItem(os.path.basename(p))
                added += 1
        if added:
            if self.file_list.currentRow() < 0:
                self.file_list.setCurrentRow(0)
            self._render_preview()
            self.status_label.setText(f"共 {len(self._files)} 个文件(新增 {added} 个)")
        else:
            self._toast("warning", "没有可添加的文件",
                        "支持的格式:PNG / JPG / WEBP / BMP / PDF")

    def _pick_files(self):
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", f"支持的文件 ({exts})")
        if files:
            self.add_files(files)

    def _remove_selected(self):
        row = self.file_list.currentRow()
        if row < 0:
            return
        self.file_list.takeItem(row)
        del self._files[row]
        self._render_preview()

    def _clear_files(self):
        self.file_list.clear()
        self._files.clear()
        self._render_preview()

    # ------------------------------------------------------------- 参数交互

    def _on_mode_changed(self, mode: str):
        self.mode_stack.setCurrentIndex(0 if mode == "text" else 1)
        self._schedule_preview()

    def _on_tiled_changed(self, checked: bool):
        self.tile_row.setVisible(checked)
        self.pos_widget.setVisible(not checked)
        self.margin_row.setVisible(not checked)
        self._schedule_preview()

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._color), self, "选择文字颜色")
        if color.isValid():
            self._color = color.name()
            self._update_color_btn()
            self._schedule_preview()

    def _update_color_btn(self):
        self.color_btn.setStyleSheet(
            f"ToolButton {{ background: {self._color}; border: 1px solid rgba(0,0,0,40); border-radius: 4px; }}")

    def _pick_watermark_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择水印图片", "",
                                              "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self._watermark_image_path = path
            self.image_path_label.setText(os.path.basename(path))
            self.mode_segment.setCurrentItem("image")
            self._on_mode_changed("image")

    # ---------------------------------------------------------------- 导出

    def _export(self):
        if not self._files:
            self._toast("warning", "列表是空的", "先添加要加水印的文件")
            return
        if self._worker is not None:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if not out_dir:
            return
        img_format = ["keep", "png", "jpg", "webp"][self.format_combo.currentIndex()]
        cfg = self._collect_config()

        self._worker = ExportWorker(list(self._files), cfg, out_dir, img_format, self)
        self._worker.progress.connect(self._on_export_progress)
        self._worker.file_failed.connect(lambda p, err: print(f"[失败] {p}: {err}"))
        self._worker.finished_all.connect(self._on_export_finished)
        self.export_btn.setEnabled(False)
        self.progress.show()
        self.progress.setValue(0)
        self._worker.start()

    def _on_export_progress(self, current: int, total: int, name: str):
        self.progress.setMaximum(total)
        self.progress.setValue(current - 1)
        self.status_label.setText(f"正在处理 {current}/{total}:{name}")

    def _on_export_finished(self, ok: int, fail: int):
        self.progress.hide()
        self.export_btn.setEnabled(True)
        self._worker = None
        self.status_label.setText(f"导出完成:成功 {ok} 个,失败 {fail} 个")
        if fail:
            self._toast("warning", "部分文件导出失败", f"成功 {ok} 个,失败 {fail} 个,详情见控制台")
        else:
            self._toast("success", "导出完成", f"成功导出 {ok} 个文件")

    def _toast(self, kind: str, title: str, content: str):
        show = getattr(InfoBar, kind)
        show(title=title, content=content, orient=Qt.Horizontal, isClosable=True,
             position=InfoBarPosition.TOP, duration=3000, parent=self)

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        super().closeEvent(event)
