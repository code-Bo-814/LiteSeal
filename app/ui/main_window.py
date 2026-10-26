"""LiteSeal 主窗口。

布局:左侧文件列表 | 中间可缩放预览(图片 / PDF 翻页) | 右侧水印参数面板。
所有参数变动经 150ms 防抖后刷新预览;导出走 ExportWorker 后台线程。
"""

from __future__ import annotations

import os
from collections import OrderedDict

from PIL import Image, ImageDraw, ImageOps
from PySide6.QtCore import QPointF, QSettings, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QColorDialog, QDialog, QFileDialog, QGraphicsPixmapItem,
                               QGraphicsScene, QGraphicsTextItem, QGraphicsView,
                               QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (BodyLabel, CardWidget, ComboBox, FluentIcon as FIF,
                            InfoBar, InfoBarPosition, LineEdit, ListWidget,
                            PrimaryPushButton, ProgressBar, PushButton, ScrollArea,
                            SegmentedWidget, Slider, StrongBodyLabel, SubtitleLabel,
                            SwitchButton, ToolButton)

from app import APP_NAME, __version__
from app.core.image_wm import (FONT_FILES, apply_image_watermark, build_element,
                               element_position, load_font)
from app.core.models import (DEFAULTS, IMAGE_EXTS, PDF_EXTS, POSITION_LABELS,
                             POSITIONS, SUPPORTED_EXTS, WatermarkConfig)
from app.core.pdf_wm import parse_page_spec, pdf_page_count, pdf_page_image, pages_to_spec
from app.ui.page_picker import PageSelectDialog
from app.ui.workers import ExportWorker

PREVIEW_MAX_PX = 1400
IMAGE_FORMAT_ITEMS = ["保持原格式", "PNG", "JPG", "WEBP"]


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class PreviewView(QGraphicsView):
    """可滚轮缩放、拖拽平移、双击复位的预览区,始终保持宽高比。"""

    zoom_changed = Signal(float)  # 当前缩放百分比
    wm_moved = Signal(float, float)  # 水印中心在画面里的比例位置

    MIN_SCALE = 0.05
    MAX_SCALE = 12.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pix_item = QGraphicsPixmapItem()
        self._pix_item.setVisible(False)
        self._scene.addItem(self._pix_item)
        self._wm_item = QGraphicsPixmapItem()  # 非平铺时的独立水印层,可拖动
        self._wm_item.setVisible(False)
        self._scene.addItem(self._wm_item)
        self._dragging_wm = False
        self._drag_grab = QPointF()
        self._hint_item = QGraphicsTextItem()
        font = self._hint_item.font()
        font.setPointSize(13)
        self._hint_item.setFont(font)
        self._hint_item.setDefaultTextColor(QColor(130, 130, 130))
        self._scene.addItem(self._hint_item)

        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._auto_fit = True

    def current_zoom(self) -> float:
        return self.transform().m11() * 100

    def set_pixmap(self, pixmap: QPixmap | None, hint: str = ""):
        self._auto_fit = True
        self._wm_item.setVisible(False)
        self._dragging_wm = False
        if pixmap is None or pixmap.isNull():
            self._pix_item.setVisible(False)
            self._hint_item.setPlainText(hint or "")
            self._hint_item.setVisible(True)
            self._scene.setSceneRect(self._hint_item.boundingRect())
            self.resetTransform()
        else:
            self._hint_item.setVisible(False)
            self._pix_item.setPixmap(pixmap)
            self._pix_item.setVisible(True)
            self._scene.setSceneRect(QRectF(pixmap.rect()))
            QTimer.singleShot(0, self.fit_view)
        self.zoom_changed.emit(self.current_zoom())

    def set_content(self, base: QPixmap, watermark: QPixmap, pos: tuple[int, int]):
        """分层显示:底图 + 独立水印元素(左上角在 pos,可拖动)。"""
        self._auto_fit = True
        self._hint_item.setVisible(False)
        self._pix_item.setPixmap(base)
        self._pix_item.setVisible(True)
        self._wm_item.setPixmap(watermark)
        self._wm_item.setPos(QPointF(pos[0], pos[1]))
        self._wm_item.setVisible(True)
        self._scene.setSceneRect(QRectF(base.rect()))
        QTimer.singleShot(0, self.fit_view)
        self.zoom_changed.emit(self.current_zoom())

    def fit_view(self):
        self._auto_fit = True
        if self._pix_item.isVisible():
            self.resetTransform()
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_changed.emit(self.current_zoom())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_fit and self._pix_item.isVisible():
            QTimer.singleShot(0, self.fit_view)

    def _apply_zoom(self, factor: float):
        current = self.transform().m11()
        target = current * factor
        if target < self.MIN_SCALE:
            factor = self.MIN_SCALE / current
        elif target > self.MAX_SCALE:
            factor = self.MAX_SCALE / current
        if abs(factor - 1.0) < 1e-9:
            return
        self._auto_fit = False
        self.scale(factor, factor)
        self.zoom_changed.emit(self.current_zoom())

    def zoom_in(self):
        self._apply_zoom(1.25)

    def zoom_out(self):
        self._apply_zoom(0.8)

    def wheelEvent(self, event):
        if not self._pix_item.isVisible():
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.08 if delta > 0 else 1 / 1.08  # Ctrl 精调
        else:
            factor = 1.25 if delta > 0 else 0.8
        self._apply_zoom(factor)
        event.accept()

    # ---- 水印拖动:按在水印上拖元素,按在空白处平移画面 ----

    def _over_watermark(self, scene_pos: QPointF) -> bool:
        return (self._wm_item.isVisible()
                and self._wm_item.contains(self._wm_item.mapFromScene(scene_pos)))

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        if (event.button() == Qt.MouseButton.LeftButton
                and self._over_watermark(scene_pos)):
            self._dragging_wm = True
            self._drag_grab = scene_pos - self._wm_item.pos()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        if self._dragging_wm:
            rect = self._scene.sceneRect()
            pm = self._wm_item.pixmap()
            new_pos = scene_pos - self._drag_grab
            x = min(max(new_pos.x(), 0), max(0, rect.width() - pm.width()))
            y = min(max(new_pos.y(), 0), max(0, rect.height() - pm.height()))
            self._wm_item.setPos(x, y)
            fx = (x + pm.width() / 2) / rect.width() if rect.width() else 0.5
            fy = (y + pm.height() / 2) / rect.height() if rect.height() else 0.5
            self.wm_moved.emit(min(max(fx, 0.0), 1.0), min(max(fy, 0.0), 1.0))
            event.accept()
            return
        if self._pix_item.isVisible():
            self.viewport().setCursor(
                Qt.CursorShape.OpenHandCursor if self._over_watermark(scene_pos)
                else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging_wm:
            self._dragging_wm = False
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.fit_view()
        super().mouseDoubleClickEvent(event)


class FileList(ListWidget):
    """支持拖拽导入的文件列表。"""

    files_dropped = Signal(list)
    delete_requested = Signal()

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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and self.currentRow() >= 0:
            self.delete_requested.emit()
        else:
            super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)

        self._files: list[str] = []
        self._wm_mode = "text"          # 自己维护,不依赖 qfluentwidgets 内部状态
        self._watermark_image_path = ""
        self._worker: ExportWorker | None = None
        self._page_index = 0
        self._pdf_pages = 1
        self._sliders: dict[str, Slider] = {}
        self._last_out_dir = ""
        self._base_cache: OrderedDict[tuple, Image.Image] = OrderedDict()
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._render_preview)

        self._build_ui()
        self._install_zoom_shortcuts()
        self._restore_settings()
        self._render_preview()

    def _install_zoom_shortcuts(self):
        """标准看图器快捷键:Ctrl+= 放大 / Ctrl+- 缩小 / Ctrl+0 适应窗口。"""
        for seq, fn in (
            (QKeySequence(QKeySequence.StandardKey.ZoomIn), self.preview_view.zoom_in),
            (QKeySequence(QKeySequence.StandardKey.ZoomOut), self.preview_view.zoom_out),
            (QKeySequence("Ctrl+0"), self.preview_view.fit_view),
        ):
            shortcut = QShortcut(seq, self)
            shortcut.activated.connect(fn)

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
        self.file_panel = self._build_file_panel()
        self.settings_panel = self._build_settings_panel()
        content.addWidget(self.file_panel, stretch=0)
        content.addWidget(self._build_preview_panel(), stretch=1)
        content.addWidget(self.settings_panel, stretch=0)
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
        self.file_list.delete_requested.connect(self._remove_selected)
        layout.addWidget(self.file_list, stretch=1)

        btn_row = QHBoxLayout()
        btn_add = PushButton(FIF.ADD, "添加")
        btn_add.clicked.connect(self._pick_files)
        btn_remove = ToolButton(FIF.DELETE)
        btn_remove.setToolTip("移除选中")
        btn_remove.clicked.connect(self._remove_selected)
        btn_row.addWidget(btn_add, stretch=1)
        btn_row.addWidget(btn_remove)
        layout.addLayout(btn_row)

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

        self.preview_view = PreviewView()
        self.preview_view.zoom_changed.connect(
            lambda pct: self.zoom_label.setText(f"{round(pct)}%"))
        self.preview_view.wm_moved.connect(self._on_wm_moved)
        layout.addWidget(self.preview_view, stretch=1)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.left_toggle = ToolButton(FIF.CARE_LEFT_SOLID)
        self.left_toggle.setToolTip("收起文件面板")
        self.left_toggle.clicked.connect(lambda: self._toggle_panel("left"))
        bar.addWidget(self.left_toggle)
        btn_zoom_out = ToolButton(FIF.ZOOM_OUT)
        btn_zoom_out.setToolTip("缩小 (Ctrl+-,也可用滚轮)")
        btn_zoom_out.clicked.connect(self.preview_view.zoom_out)
        btn_zoom_in = ToolButton(FIF.ZOOM_IN)
        btn_zoom_in.setToolTip("放大 (Ctrl++,也可用滚轮)")
        btn_zoom_in.clicked.connect(self.preview_view.zoom_in)
        btn_fit = PushButton("适应窗口")
        btn_fit.setToolTip("适应窗口 (Ctrl+0,双击预览同样生效)")
        btn_fit.clicked.connect(self.preview_view.fit_view)
        self.zoom_label = BodyLabel("100%")
        self.zoom_label.setFixedWidth(46)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        bar.addWidget(btn_zoom_out)
        bar.addWidget(btn_zoom_in)
        bar.addWidget(btn_fit)
        bar.addWidget(self.zoom_label)
        bar.addStretch(1)

        self.page_bar = QWidget()
        page_layout = QHBoxLayout(self.page_bar)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(6)
        page_prev = ToolButton(FIF.CARE_LEFT_SOLID)
        page_prev.setToolTip("上一页")
        page_prev.clicked.connect(lambda: self._on_page_change(-1))
        page_next = ToolButton(FIF.CARE_RIGHT_SOLID)
        page_next.setToolTip("下一页")
        page_next.clicked.connect(lambda: self._on_page_change(1))
        self.page_label = BodyLabel("1 / 1")
        self.page_label.setFixedWidth(60)
        self.page_label.setAlignment(Qt.AlignCenter)
        page_layout.addWidget(page_prev)
        page_layout.addWidget(self.page_label)
        page_layout.addWidget(page_next)
        bar.addWidget(self.page_bar)
        self.right_toggle = ToolButton(FIF.CARE_RIGHT_SOLID)
        self.right_toggle.setToolTip("收起参数面板")
        self.right_toggle.clicked.connect(lambda: self._toggle_panel("right"))
        bar.addWidget(self.right_toggle)
        layout.addLayout(bar)
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
        self.mode_segment.addItem(routeKey="text", text="文字水印",
                                  onClick=lambda: self._on_mode_changed("text"))
        self.mode_segment.addItem(routeKey="image", text="图片水印",
                                  onClick=lambda: self._on_mode_changed("image"))
        self.mode_segment.setCurrentItem("text")
        layout.addWidget(self.mode_segment)

        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._build_text_settings())
        self.mode_stack.addWidget(self._build_image_settings())
        layout.addWidget(self.mode_stack)

        layout.addWidget(self._separator())

        # 公共参数
        layout.addWidget(self._slider_row("opacity", "不透明度", 5, 100, 40, "%", "_opacity"))
        layout.addWidget(self._slider_row("rotation", "旋转角度", -90, 90, -30, "°", "_rotation"))

        self.tiled_switch = SwitchButton("平铺整个画面", panel)
        self.tiled_switch.checkedChanged.connect(self._on_tiled_changed)
        layout.addWidget(self.tiled_switch)

        self.tile_row = self._slider_row("tile_spacing", "平铺疏密", 120, 400, 200, "%", "_tile_spacing")
        layout.addWidget(self.tile_row)

        pos_widget = QWidget()
        pos_layout = QHBoxLayout(pos_widget)
        pos_layout.setContentsMargins(0, 0, 0, 0)
        pos_layout.addWidget(BodyLabel("位置"))
        self.position_combo = ComboBox()
        for key in POSITIONS:
            self.position_combo.addItem(POSITION_LABELS[key], userData=key)
        self.position_combo.addItem("自定义", userData="custom")
        self.position_combo.setCurrentIndex(POSITIONS.index(DEFAULTS.position))
        self.position_combo.currentIndexChanged.connect(self._on_position_changed)
        pos_layout.addWidget(self.position_combo, stretch=1)
        self.pos_widget = pos_widget
        layout.addWidget(pos_widget)

        self.margin_row = self._slider_row("margin", "边距", 0, 20, 4, "%", "_margin")
        layout.addWidget(self.margin_row)

        layout.addWidget(self._separator())

        # 输出设置
        out_widget = QWidget()
        out_layout = QHBoxLayout(out_widget)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.addWidget(BodyLabel("图片输出格式"))
        self.format_combo = ComboBox()
        self.format_combo.addItems(IMAGE_FORMAT_ITEMS)
        out_layout.addWidget(self.format_combo, stretch=1)
        layout.addWidget(out_widget)

        pages_widget = QWidget()
        pages_layout = QHBoxLayout(pages_widget)
        pages_layout.setContentsMargins(0, 0, 0, 0)
        pages_layout.addWidget(BodyLabel("水印页面"))
        self.pages_edit = LineEdit()
        self.pages_edit.setPlaceholderText("全部页面")
        self.pages_edit.setReadOnly(True)  # 选页走弹窗点选,杜绝手打歧义
        self.pages_edit.textChanged.connect(self._on_pages_edited)
        pages_layout.addWidget(self.pages_edit, stretch=1)
        pick_btn = PushButton(FIF.FILTER, "选择页面…")
        pick_btn.setToolTip("弹窗点选:单击选中,Shift+单击 连选")
        pick_btn.clicked.connect(self._open_page_picker)
        pages_layout.addWidget(pick_btn)
        self.pages_row = pages_widget
        layout.addWidget(pages_widget)
        self.pages_row.hide()  # 只在选中 PDF 时显示

        self.reset_btn = PushButton(FIF.SYNC, "恢复默认设置")
        self.reset_btn.clicked.connect(self._reset_defaults)
        layout.addWidget(self.reset_btn)

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
        self.text_edit.setText(DEFAULTS.text)
        self.text_edit.textChanged.connect(self._schedule_preview)
        layout.addWidget(self.text_edit)

        font_widget = QWidget()
        font_layout = QHBoxLayout(font_widget)
        font_layout.setContentsMargins(0, 0, 0, 0)
        font_layout.addWidget(BodyLabel("字体"))
        self.font_combo = ComboBox()
        self.font_combo.addItems(list(FONT_FILES))
        self.font_combo.currentIndexChanged.connect(self._on_font_changed)
        font_layout.addWidget(self.font_combo, stretch=1)
        layout.addWidget(font_widget)

        layout.addWidget(self._slider_row("font_size", "文字大小", 3, 30, 6, "%", "_font_size"))

        color_widget = QWidget()
        color_layout = QHBoxLayout(color_widget)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.addWidget(BodyLabel("文字颜色"))
        self._color = DEFAULTS.color
        self.color_btn = ToolButton(FIF.BRUSH)
        self.color_btn.clicked.connect(self._pick_color)
        self._update_color_btn()
        color_layout.addWidget(self.color_btn)
        color_layout.addStretch(1)
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

        layout.addWidget(self._slider_row("image_size", "图片大小", 3, 60, 14, "%", "_image_size"))
        return w

    def _slider_row(self, key: str, label: str, min_v: int, max_v: int, value: int,
                    suffix: str, attr: str) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        top = QHBoxLayout()
        top.addWidget(BodyLabel(label))
        top.addStretch(1)
        value_label = BodyLabel(f"{value}{suffix}")
        top.addWidget(value_label)
        slider = Slider(Qt.Horizontal)
        slider.setRange(min_v, max_v)
        slider.setValue(value)

        def changed(v):
            value_label.setText(f"{v}{suffix}")
            setattr(self, attr, v)
            self._schedule_preview()

        slider.valueChanged.connect(changed)
        layout.addLayout(top)
        layout.addWidget(slider)
        self._sliders[key] = slider
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
        self.open_dir_btn = PushButton(FIF.FOLDER, "打开输出文件夹")
        self.open_dir_btn.hide()
        self.open_dir_btn.clicked.connect(self._open_last_dir)
        layout.addWidget(self.open_dir_btn)
        layout.addWidget(self.progress)
        return bar

    # ------------------------------------------------------- 配置收集与预览

    def _collect_config(self) -> WatermarkConfig:
        return WatermarkConfig(
            mode=self._wm_mode,
            text=self.text_edit.text(),
            font_name=getattr(self, "_font_name", DEFAULTS.font_name),
            font_size_pct=getattr(self, "_font_size", DEFAULTS.font_size_pct),
            color=getattr(self, "_color", DEFAULTS.color),
            image_path=self._watermark_image_path,
            image_size_pct=getattr(self, "_image_size", DEFAULTS.image_size_pct),
            opacity=getattr(self, "_opacity", DEFAULTS.opacity),
            rotation=getattr(self, "_rotation", DEFAULTS.rotation),
            tiled=self.tiled_switch.isChecked(),
            tile_spacing=getattr(self, "_tile_spacing", DEFAULTS.tile_spacing),
            position=self.position_combo.currentData() or DEFAULTS.position,
            margin_pct=getattr(self, "_margin", DEFAULTS.margin_pct),
            pdf_pages=self.pages_edit.text().strip(),
            custom_pos=getattr(self, "_custom_pos", None),
        )

    def _schedule_preview(self):
        self._preview_timer.start()

    def _on_mode_changed(self, mode: str):
        self._wm_mode = mode
        self.mode_stack.setCurrentIndex(0 if mode == "text" else 1)
        self.mode_segment.setCurrentItem(mode)
        self._schedule_preview()

    def _on_font_changed(self, index: int):
        names = list(FONT_FILES)
        if 0 <= index < len(names):
            self._font_name = names[index]
            self._schedule_preview()

    def _on_position_changed(self, index: int):
        if self.position_combo.currentData() != "custom":
            self._custom_pos = None  # 选回九宫格即清除拖动位置
        self._schedule_preview()

    def _on_wm_moved(self, fx: float, fy: float):
        self._custom_pos = (fx, fy)
        idx = self.position_combo.findData("custom")
        if idx >= 0 and self.position_combo.currentIndex() != idx:
            self.position_combo.blockSignals(True)  # 只同步显示,避免触发渲染循环
            self.position_combo.setCurrentIndex(idx)
            self.position_combo.blockSignals(False)

    def _on_tiled_changed(self, checked: bool):
        self.tile_row.setVisible(checked)
        self.pos_widget.setVisible(not checked)
        self.margin_row.setVisible(not checked)
        self._schedule_preview()

    def _on_file_selected(self, row):
        self._page_index = 0
        self._render_preview()

    def _current_file(self) -> str | None:
        if not self._files:
            return None
        row = self.file_list.currentRow()
        if 0 <= row < len(self._files):
            return self._files[row]
        return self._files[0]

    MAX_BASE_CACHE = 6

    def _get_base(self, path: str, ext: str) -> Image.Image:
        """底图缓存:调滑块时免掉反复解码大图 / PDF 页面的开销。"""
        page = self._page_index if ext in PDF_EXTS else 0
        key = (path, page)
        if key in self._base_cache:
            self._base_cache.move_to_end(key)
            return self._base_cache[key]
        if ext in PDF_EXTS:
            img = pdf_page_image(path, page, PREVIEW_MAX_PX).convert("RGBA")
        else:
            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGBA")
                img.thumbnail((PREVIEW_MAX_PX, PREVIEW_MAX_PX), Image.Resampling.LANCZOS)
                img = img.copy()
        self._base_cache[key] = img
        if len(self._base_cache) > self.MAX_BASE_CACHE:
            self._base_cache.popitem(last=False)
        return img

    def _render_preview(self):
        path = self._current_file()
        if not path:
            self.page_bar.hide()
            self.pages_row.hide()
            self.preview_view.set_pixmap(None, "把文件拖进左侧列表开始使用\n\n"
                                           "预览:滚轮缩放 · 拖动水印调位置 · 双击适应窗口")
            return

        ext = os.path.splitext(path)[1].lower()
        selected = None  # 图片文件不涉及选页;PDF 解析出选中的 0 起始页列表
        try:
            if ext in PDF_EXTS:
                self._pdf_pages = pdf_page_count(path)
                self._page_index = min(max(self._page_index, 0), self._pdf_pages - 1)
                self.page_label.setText(f"{self._page_index + 1} / {self._pdf_pages}")
                self.page_bar.show()
                self.pages_row.show()
                try:
                    selected = parse_page_spec(self.pages_edit.text().strip(), self._pdf_pages)
                except ValueError as e:
                    self.preview_view.set_pixmap(
                        None, f"页码范围看不懂:{e}\n\n示例:1,3 · 2-5 · 3- · 奇数页 · 全部")
                    return
                self._update_pages_hint()
            else:
                self.page_bar.hide()
                self.pages_row.hide()
            base = self._get_base(path, ext)
        except Exception as e:
            self.page_bar.hide()
            self.pages_row.hide()
            self.preview_view.set_pixmap(None, f"无法打开文件:\n{e}")
            return

        cfg = self._collect_config()
        if cfg.mode == "image" and not cfg.image_path:
            self.preview_view.set_pixmap(None, "图片水印:请先在右侧选择水印图片")
            return
        page_selected = selected is None or self._page_index in selected
        try:
            if not page_selected:
                # 未选中的页:预览不加水印,盖角标直观提示
                self.preview_view.set_pixmap(_pil_to_pixmap(self._badge_unselected(base)))
                return
            if cfg.tiled:
                result = apply_image_watermark(base, cfg)
                self.preview_view.set_pixmap(_pil_to_pixmap(result))
            else:
                # 非平铺:底图与水印分层,水印可在预览里直接拖动
                element = build_element(cfg, min(base.size))
                x, y = element_position(cfg, base.width, base.height, element.size)
                self.preview_view.set_content(_pil_to_pixmap(base),
                                              _pil_to_pixmap(element), (x, y))
        except Exception as e:
            self.preview_view.set_pixmap(None, f"渲染失败:\n{e}")
            return

    def _badge_unselected(self, img: Image.Image) -> Image.Image:
        """给未选中的 PDF 页盖一个"无水印"角标,预览一眼可辨。"""
        img = img.convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        text = "本页未加水印(未选中)"
        font = load_font(max(14, min(img.size) // 30), "黑体")
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        w, h = right - left + 32, bottom - top + 16
        x, y = (img.width - w) // 2, 12
        draw.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=(0, 0, 0, 150))
        draw.text((x + 16, y + 8 - top), text, font=font, fill=(255, 255, 255, 255))
        return Image.alpha_composite(img, overlay)

    def _on_pages_edited(self):
        self._update_pages_hint()
        self._schedule_preview()

    def _open_page_picker(self):
        path = self._current_file()
        if not path or os.path.splitext(path)[1].lower() not in PDF_EXTS:
            return
        try:
            current = parse_page_spec(self.pages_edit.text().strip(), self._pdf_pages)
        except ValueError:
            current = list(range(self._pdf_pages))
        dlg = PageSelectDialog(self._pdf_pages, current, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selection is not None:
            self.pages_edit.setText(pages_to_spec(dlg.selection, self._pdf_pages))

    def _update_pages_hint(self):
        """输入框 tooltip 实时显示解析结果,写错当场可见。"""
        path = self._current_file()
        if not path or os.path.splitext(path)[1].lower() not in PDF_EXTS:
            return
        try:
            picked = parse_page_spec(self.pages_edit.text().strip(), self._pdf_pages)
            self.pages_edit.setToolTip(f"已选 {len(picked)} / {self._pdf_pages} 页")
        except ValueError as e:
            self.pages_edit.setToolTip(str(e))

    # ------------------------------------------------------------ PDF 翻页

    def _on_page_change(self, delta: int):
        path = self._current_file()
        if not path or os.path.splitext(path)[1].lower() not in PDF_EXTS:
            return
        new_page = self._page_index + delta
        if 0 <= new_page < self._pdf_pages:
            self._page_index = new_page
            self._render_preview()

    # ------------------------------------------------------------ 侧栏收缩

    def _toggle_panel(self, side: str):
        """收起 / 展开某一侧面板,预览区自动占满剩余空间。"""
        panel = self.file_panel if side == "left" else self.settings_panel
        button = self.left_toggle if side == "left" else self.right_toggle
        hiding = not panel.isHidden()
        panel.setVisible(not hiding)
        if side == "left":
            button.setIcon(FIF.CARE_RIGHT_SOLID.icon() if hiding else FIF.CARE_LEFT_SOLID.icon())
            button.setToolTip("展开文件面板" if hiding else "收起文件面板")
        else:
            button.setIcon(FIF.CARE_LEFT_SOLID.icon() if hiding else FIF.CARE_RIGHT_SOLID.icon())
            button.setToolTip("展开参数面板" if hiding else "收起参数面板")

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
            self._base_cache.clear()
            if self.file_list.currentRow() < 0:
                self.file_list.setCurrentRow(0)
            else:
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
        self._base_cache.clear()
        self._render_preview()

    def _clear_files(self):
        self.file_list.clear()
        self._files.clear()
        self._base_cache.clear()
        self._page_index = 0
        self._render_preview()

    # ------------------------------------------------------------- 参数交互

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
            self._on_mode_changed("image")

    def _reset_defaults(self):
        d = DEFAULTS
        self._on_mode_changed("text")
        self.text_edit.setText(d.text)
        self.font_combo.setCurrentIndex(list(FONT_FILES).index(d.font_name))
        self._sliders["font_size"].setValue(d.font_size_pct)
        self._color = d.color
        self._update_color_btn()
        self._sliders["image_size"].setValue(d.image_size_pct)
        self._watermark_image_path = ""
        self.image_path_label.setText("未选择(建议用带透明通道的 PNG)")
        self._sliders["opacity"].setValue(d.opacity)
        self._sliders["rotation"].setValue(d.rotation)
        self.tiled_switch.setChecked(d.tiled)
        self._sliders["tile_spacing"].setValue(d.tile_spacing)
        self.position_combo.setCurrentIndex(POSITIONS.index(d.position))
        self._sliders["margin"].setValue(d.margin_pct)
        self.format_combo.setCurrentIndex(0)
        self.pages_edit.clear()
        self._custom_pos = None
        grid_idx = POSITIONS.index(d.position)
        if self.position_combo.currentIndex() != grid_idx:
            self.position_combo.setCurrentIndex(grid_idx)
        self._schedule_preview()
        self._toast("info", "已恢复默认设置", "所有水印参数已回到初始值")

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
        self._last_out_dir = out_dir
        self.open_dir_btn.hide()
        img_format = ["keep", "png", "jpg", "webp"][self.format_combo.currentIndex()]
        cfg = self._collect_config()

        self._worker = ExportWorker(list(self._files), cfg, out_dir, img_format, self)
        self._export_errors: list[str] = []
        self._worker.progress.connect(self._on_export_progress)
        self._worker.file_failed.connect(self._on_file_failed)
        self._worker.finished_all.connect(self._on_export_finished)
        self.export_btn.setEnabled(False)
        self.progress.show()
        self.progress.setValue(0)
        self._worker.start()

    def _on_export_progress(self, current: int, total: int, name: str):
        self.progress.setMaximum(total)
        self.progress.setValue(current - 1)
        self.status_label.setText(f"正在处理 {current}/{total}:{name}")

    def _on_file_failed(self, path: str, err: str):
        self._export_errors.append(f"{os.path.basename(path)}: {err}")

    def _on_export_finished(self, ok: int, fail: int):
        self.progress.hide()
        self.export_btn.setEnabled(True)
        self._worker = None
        self.status_label.setText(f"导出完成:成功 {ok} 个,失败 {fail} 个")
        if fail:
            detail = ";".join(self._export_errors[:2])
            self._toast("warning", "部分文件导出失败",
                        f"成功 {ok} 个,失败 {fail} 个 · {detail}")
        else:
            self._toast("success", "导出完成", f"成功导出 {ok} 个文件")
        if ok:
            self.open_dir_btn.show()

    def _open_last_dir(self):
        if self._last_out_dir and os.path.isdir(self._last_out_dir) and hasattr(os, "startfile"):
            os.startfile(self._last_out_dir)

    def _toast(self, kind: str, title: str, content: str):
        show = getattr(InfoBar, kind)
        show(title=title, content=content, orient=Qt.Horizontal, isClosable=True,
             position=InfoBarPosition.TOP, duration=3000, parent=self)

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        self._save_settings()
        super().closeEvent(event)

    # ------------------------------------------------------------ 设置持久化

    def _settings(self) -> QSettings:
        app_name = os.environ.get("LITESEAL_QSETTINGS_APP", "LiteSeal")
        return QSettings("LiteSeal", app_name)

    def _save_settings(self):
        s = self._settings()
        cfg = self._collect_config()
        s.setValue("wm/mode", cfg.mode)
        s.setValue("wm/text", cfg.text)
        s.setValue("wm/font_name", cfg.font_name)
        s.setValue("wm/font_size_pct", cfg.font_size_pct)
        s.setValue("wm/color", cfg.color)
        s.setValue("wm/image_path", self._watermark_image_path)
        s.setValue("wm/image_size_pct", cfg.image_size_pct)
        s.setValue("wm/opacity", cfg.opacity)
        s.setValue("wm/rotation", cfg.rotation)
        s.setValue("wm/tiled", cfg.tiled)
        s.setValue("wm/tile_spacing", cfg.tile_spacing)
        s.setValue("wm/position", cfg.position)
        s.setValue("wm/margin_pct", cfg.margin_pct)
        s.setValue("out/format_index", self.format_combo.currentIndex())
        s.setValue("out/last_dir", self._last_out_dir)
        s.setValue("wm/pdf_pages", self.pages_edit.text().strip())
        custom = getattr(self, "_custom_pos", None)
        s.setValue("wm/custom_pos", f"{custom[0]:.4f},{custom[1]:.4f}" if custom else "")
        s.setValue("ui/geometry", self.saveGeometry())
        s.setValue("ui/left_collapsed", self.file_panel.isHidden())
        s.setValue("ui/right_collapsed", self.settings_panel.isHidden())
        s.sync()

    def _restore_settings(self):
        """启动时恢复上次的水印参数 / 输出目录 / 窗口大小,失败则用默认值。"""
        try:
            s = self._settings()
            mode = s.value("wm/mode", "text")
            if mode in ("text", "image") and mode != self._wm_mode:
                self._on_mode_changed(mode)
            if s.contains("wm/text"):
                self.text_edit.setText(s.value("wm/text"))
            font_name = s.value("wm/font_name", "")
            if font_name in FONT_FILES:
                self.font_combo.setCurrentIndex(list(FONT_FILES).index(font_name))
            for key, slider_key, default, lo, hi in (
                ("wm/font_size_pct", "font_size", DEFAULTS.font_size_pct, 3, 30),
                ("wm/image_size_pct", "image_size", DEFAULTS.image_size_pct, 3, 60),
                ("wm/opacity", "opacity", DEFAULTS.opacity, 5, 100),
                ("wm/rotation", "rotation", DEFAULTS.rotation, -90, 90),
                ("wm/tile_spacing", "tile_spacing", DEFAULTS.tile_spacing, 120, 400),
                ("wm/margin_pct", "margin", DEFAULTS.margin_pct, 0, 20),
            ):
                value = max(lo, min(hi, int(s.value(key, default, type=int))))
                self._sliders[slider_key].setValue(value)
            color = s.value("wm/color", "")
            if isinstance(color, str) and color.startswith("#"):
                self._color = color
                self._update_color_btn()
            image_path = s.value("wm/image_path", "")
            if isinstance(image_path, str) and os.path.isfile(image_path):
                self._watermark_image_path = image_path
                self.image_path_label.setText(os.path.basename(image_path))
            if s.value("wm/tiled", False, type=bool):
                self.tiled_switch.setChecked(True)
            position = s.value("wm/position", "")
            if position in POSITIONS:
                self.position_combo.setCurrentIndex(POSITIONS.index(position))
            fmt = int(s.value("out/format_index", 0, type=int))
            if 0 <= fmt < self.format_combo.count():
                self.format_combo.setCurrentIndex(fmt)
            last_dir = s.value("out/last_dir", "")
            if isinstance(last_dir, str):
                self._last_out_dir = last_dir
            pdf_pages = s.value("wm/pdf_pages", "")
            if isinstance(pdf_pages, str):
                self.pages_edit.setText(pdf_pages)
            custom = s.value("wm/custom_pos", "")
            if isinstance(custom, str) and "," in custom:
                try:
                    fx, fy = (float(v) for v in custom.split(","))
                    if 0 <= fx <= 1 and 0 <= fy <= 1:
                        self._on_wm_moved(fx, fy)
                except ValueError:
                    pass
            geometry = s.value("ui/geometry")
            if geometry is not None:
                self.restoreGeometry(geometry)
            if s.value("ui/left_collapsed", False, type=bool) != self.file_panel.isHidden():
                self._toggle_panel("left")
            if s.value("ui/right_collapsed", False, type=bool) != self.settings_panel.isHidden():
                self._toggle_panel("right")
        except Exception as e:
            print(f"[LiteSeal] 恢复设置失败: {e}")
