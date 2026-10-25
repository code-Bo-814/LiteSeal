"""UI 逻辑回归测试(离屏运行,不弹窗):python tests/test_ui_logic.py

覆盖:模式切换配置收集、图片水印渲染、PDF 翻页、恢复默认、预览缩放。
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LITESEAL_QSETTINGS_APP", "LiteSealTest")  # 持久化测试隔离,不污染真实设置

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf as fitz
from PIL import Image
from PySide6.QtWidgets import QApplication

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)


def make_logo():
    path = os.path.join(OUT, "logo.png")
    Image.new("RGBA", (64, 64), (255, 0, 0, 200)).save(path)
    return path


def make_photo():
    path = os.path.join(OUT, "photo.png")
    Image.new("RGB", (800, 600), (30, 90, 160)).save(path)
    return path


def make_pdf():
    path = os.path.join(OUT, "doc.pdf")
    doc = fitz.open()
    for i in range(3):
        doc.new_page(width=595, height=842).insert_text((72, 100), f"page {i + 1}")
    doc.save(path)
    doc.close()
    return path


def main():
    app = QApplication([])
    from app.ui.main_window import MainWindow
    w = MainWindow()

    # 1) 初始状态:文字水印 + 默认参数
    cfg = w._collect_config()
    assert cfg.mode == "text", cfg.mode
    assert cfg.text == "LiteSeal" and cfg.opacity == 40 and cfg.tiled is False

    # 2) 图片水印:切换模式 + 设置路径后,配置必须指向图片模式(修复 currentItem() 坑)
    logo = make_logo()
    w._watermark_image_path = logo
    w._on_mode_changed("image")
    cfg = w._collect_config()
    assert cfg.mode == "image" and cfg.image_path == logo, cfg

    # 3) 图片水印预览真实渲染(以前在这里静默抛异常 => 功能"失效")
    photo_path = make_photo()
    w.add_files([photo_path])
    w._render_preview()
    assert not w.preview_view._pix_item.pixmap().isNull(), "图片水印预览未渲染"

    # 4) 未选水印图时给提示而不是抛异常
    w._watermark_image_path = ""
    w._render_preview()
    assert not w.preview_view._pix_item.isVisible(), "未选水印图时应显示提示"

    # 5) PDF 页数识别 + 翻页
    pdf = make_pdf()
    w.add_files([pdf])
    w.file_list.setCurrentRow(1)  # 选中 PDF
    assert w._pdf_pages == 3, w._pdf_pages
    assert not w.page_bar.isHidden(), "PDF 应显示翻页栏"
    assert w.page_label.text() == "1 / 3"
    w._on_page_change(1)
    assert w._page_index == 1 and w.page_label.text() == "2 / 3"
    w._on_page_change(1)
    w._on_page_change(1)  # 已是最后一页,不应越界
    assert w._page_index == 2 and w.page_label.text() == "3 / 3"
    w._on_page_change(-5)  # 越界拒绝,停在当前页
    assert w._page_index == 2

    # 6) 图片文件不显示翻页栏
    w.file_list.setCurrentRow(0)
    assert w.page_bar.isHidden()
    # 7) 预览缩放
    scale_before = w.preview_view.transform().m11()
    w.preview_view.zoom_in()
    assert w.preview_view.transform().m11() > scale_before
    w.preview_view.zoom_out()
    w.preview_view.fit_view()
    assert abs(w.preview_view.transform().m11() - scale_before) < 0.05

    # 8) 恢复默认设置
    w._sliders["opacity"].setValue(90)
    w.text_edit.setText("XXX")
    w.tiled_switch.setChecked(True)
    w._sliders["rotation"].setValue(66)
    w._reset_defaults()
    cfg = w._collect_config()
    assert cfg.mode == "text" and cfg.text == "LiteSeal"
    assert cfg.opacity == 40 and cfg.rotation == -30 and cfg.tiled is False
    assert cfg.image_path == "" and cfg.tile_spacing == 200 and cfg.margin_pct == 4

    # 9) 字体选择:全部可选字体渲染无异常
    from app.core.image_wm import FONT_FILES
    for name in FONT_FILES:
        w._on_font_changed(list(FONT_FILES).index(name))
        w._render_preview()
    assert w._collect_config().font_name == list(FONT_FILES)[-1]

    # 10) 设置持久化:保存后新窗口应恢复(独立 QSettings 命名空间)
    from PySide6.QtCore import QSettings
    QSettings("LiteSeal", "LiteSealTest").clear()
    w._sliders["opacity"].setValue(77)
    w.text_edit.setText("夜班测试")
    w.tiled_switch.setChecked(True)
    w._on_font_changed(1)  # 黑体
    w._save_settings()
    w2 = MainWindow()
    c2 = w2._collect_config()
    assert c2.opacity == 77, c2
    assert c2.text == "夜班测试"
    assert c2.tiled is True and c2.mode == "text"
    assert c2.font_name == "黑体"
    QSettings("LiteSeal", "LiteSealTest").clear()

    # 11) 导出全链路:ExportWorker 同步跑,图片 + PDF 都要落盘
    from app.ui.workers import ExportWorker
    out_dir = os.path.join(OUT, "export_e2e")
    os.makedirs(out_dir, exist_ok=True)
    worker = ExportWorker([photo_path, pdf], w._collect_config(), out_dir, "png")
    results = {"done": [], "fail": []}
    worker.file_done.connect(lambda p, out: results["done"].append(out))
    worker.file_failed.connect(lambda p, err: results["fail"].append(err))
    worker.run()  # 同步执行,不起线程
    assert not results["fail"], results["fail"]
    assert len(results["done"]) == 2, results
    assert os.path.isfile(os.path.join(out_dir, "photo_watermarked.png"))
    assert os.path.isfile(os.path.join(out_dir, "doc_watermarked.pdf"))

    # 12) 侧栏收缩:两侧都可收起/展开,且状态随设置持久化
    assert not w.file_panel.isHidden() and not w.settings_panel.isHidden()
    w._toggle_panel("left")
    w._toggle_panel("right")
    assert w.file_panel.isHidden() and w.settings_panel.isHidden()
    w._toggle_panel("left")
    w._toggle_panel("right")
    assert not w.file_panel.isHidden() and not w.settings_panel.isHidden()
    w._toggle_panel("left")
    w._toggle_panel("right")
    w._save_settings()
    w3 = MainWindow()
    assert w3.file_panel.isHidden() and w3.settings_panel.isHidden(), "收起状态应被恢复"
    QSettings("LiteSeal", "LiteSealTest").clear()

    print("UI LOGIC TESTS PASSED")


if __name__ == "__main__":
    main()
