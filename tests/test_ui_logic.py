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
    w.pages_edit.setText("1-2")
    w._reset_defaults()
    cfg = w._collect_config()
    assert cfg.mode == "text" and cfg.text == "LiteSeal"
    assert cfg.opacity == 40 and cfg.rotation == -30 and cfg.tiled is False
    assert cfg.image_path == "" and cfg.tile_spacing == 200 and cfg.margin_pct == 4
    assert cfg.pdf_pages == ""

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
    w.pages_edit.setText("2-3")
    w._on_wm_moved(0.3, 0.6)
    w._save_settings()
    w2 = MainWindow()
    c2 = w2._collect_config()
    assert c2.opacity == 77, c2
    assert c2.text == "夜班测试"
    assert c2.tiled is True and c2.mode == "text"
    assert c2.font_name == "黑体"
    assert c2.pdf_pages == "2-3"
    assert c2.custom_pos == (0.3, 0.6)
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

    # 11b) ExportWorker 真线程:信号跨线程投递、事件循环收尾
    from PySide6.QtCore import QEventLoop, QTimer
    thr_dir = os.path.join(OUT, "export_thread")
    os.makedirs(thr_dir, exist_ok=True)
    worker = ExportWorker([photo_path, pdf], w._collect_config(), thr_dir, "keep")
    loop = QEventLoop()
    result = {}
    worker.finished_all.connect(lambda ok, fail: (result.update(ok=ok, fail=fail), loop.quit()))
    worker.start()
    QTimer.singleShot(30000, loop.quit)
    loop.exec()
    worker.wait()
    assert result.get("ok") == 2, result
    assert len(os.listdir(thr_dir)) == 2

    # 12) PDF 选页:宽容解析 + 预览实时同步 + 导出落盘
    from app.core.exporter import export_file
    from app.core.pdf_wm import parse_page_spec
    assert parse_page_spec("", 3) == [0, 1, 2]
    assert parse_page_spec("全部", 3) == [0, 1, 2]
    assert parse_page_spec("1,3", 3) == [0, 2]
    assert parse_page_spec("2-4", 3) == [1, 2]  # 超出页数裁掉
    assert parse_page_spec("1，3", 3) == [0, 2]  # 中文逗号
    assert parse_page_spec("第1、3页", 3) == [0, 2]  # 中文序数写法
    assert parse_page_spec("１～３", 3) == [0, 1, 2]  # 全角数字 + 波浪范围
    assert parse_page_spec("1 3", 3) == [0, 2]  # 空格分隔
    assert parse_page_spec("1;3", 3) == [0, 2]  # 分号分隔
    assert parse_page_spec("奇数页", 3) == [0, 2]
    assert parse_page_spec("偶数", 4) == [1, 3]
    try:
        parse_page_spec("abc", 3)
        assert False, "非法页码应抛 ValueError"
    except ValueError:
        pass

    # 选页改走弹窗点选:输入框只读,选页窗支持单击/Shift 连选/奇偶页
    from PySide6.QtCore import Qt as QtMods
    from app.core.pdf_wm import pages_to_spec
    from app.ui.page_picker import PageSelectDialog
    assert w.pages_edit.isReadOnly(), "页码框应只读,选页走弹窗"
    assert pages_to_spec([0, 2], 3) == "1,3"
    assert pages_to_spec([1, 2, 3], 5) == "2-4"
    assert pages_to_spec([0, 1, 2], 3) == "", "全选应回写为全部"
    dlg = PageSelectDialog(5, [0, 2])
    assert dlg._picked() == [0, 2]
    dlg._on_chip_clicked(1, QtMods.KeyboardModifier.NoModifier)  # 单击 => 选中第 2 页
    assert dlg._picked() == [0, 1, 2]
    dlg._on_chip_clicked(3, QtMods.KeyboardModifier.ShiftModifier)  # Shift 连选 2-4 页
    assert dlg._picked() == [0, 1, 2, 3]
    dlg._clear_all()
    assert dlg._picked() == [] and not dlg._ok_btn.isEnabled(), "空选不允许确定"
    dlg._apply_parity(0)
    assert dlg._picked() == [0, 2, 4]
    dlg._select_all()
    dlg._accept()
    assert dlg.selection == [0, 1, 2, 3, 4]

    w.tiled_switch.setChecked(False)
    w.pages_edit.setText("1,3")
    w.file_list.setCurrentRow(1)
    assert w._pdf_pages == 3
    w._render_preview()
    assert w.preview_view._wm_item.isVisible(), "第 1 页被选中,应有水印层"
    assert "已选 2 / 3" in (w.pages_edit.toolTip() or ""), "tooltip 应显示解析结果"
    w._on_page_change(1)
    assert not w.preview_view._wm_item.isVisible(), "第 2 页未选中,不应有水印"
    assert w.preview_view._pix_item.isVisible(), "未选中页显示底图 + 角标"
    w._on_page_change(1)
    assert w.preview_view._wm_item.isVisible(), "第 3 页被选中"

    pages_dir = os.path.join(OUT, "export_pages")
    os.makedirs(pages_dir, exist_ok=True)
    out_pdf = export_file(pdf, w._collect_config(), pages_dir)
    with fitz.open(out_pdf) as d:
        assert len(d) == 3, "选页不应减少总页数"
        assert len(d[0].get_images()) == 1, "第 1 页应有水印"
        assert len(d[1].get_images()) == 0, "第 2 页不应有水印"
        assert len(d[2].get_images()) == 1, "第 3 页应有水印"

    w.pages_edit.setText("abc")
    w._render_preview()
    assert not w.preview_view._pix_item.isVisible(), "写错页码时预览应当场报错"
    w.pages_edit.clear()

    # 13) 侧栏收缩:两侧都可收起/展开,且状态随设置持久化
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

    # 14) 单枚水印自由拖放:custom_pos 生效、九宫格清除、平铺隐藏水印层
    from app.core.image_wm import element_position
    from app.core.models import WatermarkConfig
    assert element_position(WatermarkConfig(custom_pos=(0.5, 0.5)), 1000, 800, (100, 50)) == (450, 375)
    assert element_position(WatermarkConfig(custom_pos=(0.0, 0.0)), 1000, 800, (100, 50)) == (0, 0)
    assert element_position(WatermarkConfig(position="top-left"), 1000, 800, (100, 50)) == (32, 32)

    w.tiled_switch.setChecked(False)
    w._on_mode_changed("text")
    w.file_list.setCurrentRow(0)  # 图片文件
    w._render_preview()
    assert w.preview_view._wm_item.isVisible(), "非平铺应有可拖动水印层"
    w._on_wm_moved(0.25, 0.75)
    assert w._collect_config().custom_pos == (0.25, 0.75)
    assert w.position_combo.currentData() == "custom", "拖动后位置框应显示自定义"
    w.position_combo.setCurrentIndex(0)  # 选回左上 => 清除自定义
    assert w._collect_config().custom_pos is None
    w.tiled_switch.setChecked(True)
    w._render_preview()
    assert not w.preview_view._wm_item.isVisible(), "平铺是合成图,无独立水印层"
    w.tiled_switch.setChecked(False)
    w._render_preview()
    assert w.preview_view._wm_item.isVisible()

    print("UI LOGIC TESTS PASSED")


if __name__ == "__main__":
    main()
