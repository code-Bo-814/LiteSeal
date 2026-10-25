"""后台导出线程,避免批量处理时卡死界面。"""

from __future__ import annotations

import os

from PySide6.QtCore import QThread, Signal

from app.core.exporter import export_file
from app.core.models import WatermarkConfig


class ExportWorker(QThread):
    progress = Signal(int, int, str)      # 当前序号, 总数, 文件名
    file_done = Signal(str, str)          # 文件路径, 输出路径(失败时为 "")
    file_failed = Signal(str, str)        # 文件路径, 错误信息
    finished_all = Signal(int, int)       # 成功数, 失败数

    def __init__(self, files: list[str], cfg: WatermarkConfig, out_dir: str,
                 img_format: str = "keep", parent=None):
        super().__init__(parent)
        self._files = files
        self._cfg = cfg
        self._out_dir = out_dir
        self._img_format = img_format
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        ok = fail = 0
        total = len(self._files)
        for i, path in enumerate(self._files, 1):
            if self._cancelled:
                break
            self.progress.emit(i, total, os.path.basename(path))
            try:
                out = export_file(path, self._cfg, self._out_dir, self._img_format)
                self.file_done.emit(path, out)
                ok += 1
            except Exception as e:  # 单个文件失败不中断批次
                self.file_failed.emit(path, str(e))
                fail += 1
        self.finished_all.emit(ok, fail)
