"""PDF 选页弹窗:网格点选页面,支持 Shift 连选、全选、奇偶页。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QColor
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, FlowLayout, PrimaryPushButton, PushButton,
                            ScrollArea)


class PageSelectDialog(QDialog):
    """每页一个可点选的页码块;单击切换,Shift+单击从上一个锚点连选一段。"""

    def __init__(self, total: int, selected: list[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择要加水印的页面")
        self.resize(600, 520)
        self._total = total
        self._anchor: int | None = None
        self.selection: list[int] | None = None  # 0 起始页索引;取消时为 None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        tip = BodyLabel("单击选中 / 取消;Shift+单击 连选一段;全部选中即等同“全部页面”。")
        tip.setTextColor(QColor(128, 128, 128), QColor(160, 160, 160))
        layout.addWidget(tip)

        quick = QHBoxLayout()
        for text, fn in (("全选", self._select_all), ("清空", self._clear_all),
                         ("奇数页", lambda: self._apply_parity(0)),
                         ("偶数页", lambda: self._apply_parity(1))):
            btn = PushButton(text)
            btn.clicked.connect(fn)
            quick.addWidget(btn)
        quick.addStretch(1)
        layout.addLayout(quick)

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(ScrollArea.Shape.NoFrame)
        container = QWidget()
        container.setStyleSheet(
            "QPushButton { min-width: 52px; min-height: 30px; padding: 2px 10px; }"
            "QPushButton:checked { background-color: #009faa; color: white; border: none; }")
        flow = FlowLayout(container)
        flow.setContentsMargins(0, 0, 0, 0)
        self._chips: list[PushButton] = []
        for i in range(total):
            chip = PushButton(str(i + 1))
            chip.setCheckable(True)
            chip.setChecked(i in selected)
            chip.clicked.connect(lambda _=False, idx=i: self._on_chip_clicked(idx))
            flow.addWidget(chip)
            self._chips.append(chip)
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        bottom = QHBoxLayout()
        self._count_label = BodyLabel("")
        bottom.addWidget(self._count_label)
        bottom.addStretch(1)
        cancel = PushButton("取消")
        cancel.clicked.connect(self.reject)
        self._ok_btn = PrimaryPushButton("确定")
        self._ok_btn.clicked.connect(self._accept)
        bottom.addWidget(cancel)
        bottom.addWidget(self._ok_btn)
        layout.addLayout(bottom)
        self._update_count()

    # ------------------------------------------------------------- 选择逻辑

    def _on_chip_clicked(self, idx: int, mods=None):
        if mods is None:
            mods = QGuiApplication.queryKeyboardModifiers()
        if self._anchor is not None and mods & Qt.KeyboardModifier.ShiftModifier:
            lo, hi = min(self._anchor, idx), max(self._anchor, idx)
            for j in range(lo, hi + 1):
                self._chips[j].setChecked(True)
        else:
            self._chips[idx].setChecked(not self._chips[idx].isChecked())
        self._anchor = idx
        self._update_count()

    def _select_all(self):
        for chip in self._chips:
            chip.setChecked(True)
        self._update_count()

    def _clear_all(self):
        for chip in self._chips:
            chip.setChecked(False)
        self._anchor = None
        self._update_count()

    def _apply_parity(self, first_index: int):
        for i, chip in enumerate(self._chips):
            chip.setChecked(i % 2 == first_index)
        self._update_count()

    def _picked(self) -> list[int]:
        return [i for i, chip in enumerate(self._chips) if chip.isChecked()]

    def _update_count(self):
        picked = self._picked()
        self._count_label.setText(f"已选 {len(picked)} / {self._total} 页")
        self._ok_btn.setEnabled(bool(picked))  # 一页都不选没有意义,禁止确定

    def _accept(self):
        self.selection = self._picked()
        self.accept()
