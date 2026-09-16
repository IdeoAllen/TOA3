# -*- coding: utf-8 -*-
"""助教打卡换装：选目录 → 选着装 → 全量换装（只换服装，保水印）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.assistant_outfit_swap.assistant_outfit_swap_service import (
    OUTFIT_PRESETS,
    BatchResult,
    list_edit_capable_profiles,
    list_images,
    pick_default_edit_profile_id,
    run_batch,
)
from widgets import (
    CheckBox,
    ComboBox,
    FormRow,
    FormSection,
    HintLabel,
    LineEdit,
    ListWidget,
    PageHeader,
    PrimaryButton,
    ProgressBar,
    ScrollPage,
    SecondaryButton,
)

_LABEL_W = 72


class _BatchWorker(QObject):
    progress = Signal(int, int, str)  # done, total, message
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        folder: str,
        preset_id: str,
        profile_id: str,
        recursive: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._folder = folder
        self._preset_id = preset_id
        self._profile_id = profile_id
        self._recursive = recursive
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            result = run_batch(
                self._folder,
                preset_id=self._preset_id,
                profile_id=self._profile_id,
                recursive=self._recursive,
                progress=lambda done, total, msg: self.progress.emit(done, total, msg),
                cancel_check=lambda: self._cancelled,
            )
            if self._cancelled:
                self.failed.emit("已取消。")
                return
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(getattr(exc, "user_message", None) or exc))


class AssistantOutfitSwapPage(BasePage):
    page_id = "assistant_outfit_swap"
    page_title = "助教打卡换装"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _BatchWorker | None = None
        self._last_out: str = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)
        root = scroll.content_layout

        root.addWidget(
            PageHeader(
                "助教打卡换装",
                "选择打卡照片目录与着装预设，目录内图片全量换装。"
                "只换服装；水印、时间戳及其它信息尽量保持不变；默认旁路输出不覆写原图。",
            )
        )

        path_box = FormSection("照片目录")
        row = QHBoxLayout()
        self._folder = LineEdit()
        self._folder.setPlaceholderText("选择助教打卡照片文件夹…")
        row.addWidget(self._folder, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        btn_scan = SecondaryButton("扫描")
        btn_scan.clicked.connect(self._reload_list)
        row.addWidget(btn_scan)
        path_box.add_layout(row)

        self._recursive = CheckBox("包含子文件夹")
        self._recursive.setChecked(False)
        self._recursive.toggled.connect(lambda _=False: self._reload_list())
        path_box.add_widget(self._recursive)
        path_box.add_widget(
            HintLabel("输出到同级「_换装_<风格>」目录；跳过已有 _换装_ 子目录，避免二次处理。")
        )
        root.addWidget(path_box)

        opt_box = FormSection("着装与模型")
        self._style = ComboBox()
        for p in OUTFIT_PRESETS:
            self._style.addItem(p.label, p.id)
        opt_box.add_widget(FormRow("着装预设", self._style, label_width=_LABEL_W))

        self._profile = ComboBox()
        self._reload_profiles()
        opt_box.add_widget(FormRow("生图模型", self._profile, label_width=_LABEL_W))
        opt_box.add_widget(
            HintLabel("须选支持「参考图编辑」的模型（如豆包 Seedream）。密钥在系统设置 · 模型库配置。")
        )
        root.addWidget(opt_box)

        list_box = FormSection("待处理图片")
        self._list = ListWidget()
        self._list.setMinimumHeight(200)
        list_box.add_widget(self._list)
        self._count = HintLabel("共 0 张")
        list_box.add_widget(self._count)
        root.addWidget(list_box, 1)

        self._progress = ProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        root.addWidget(self._progress)
        self._status = HintLabel("就绪。进页不联网探测；点「一键换装」后才提交任务。")
        root.addWidget(self._status)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._btn_run = PrimaryButton("一键换装")
        self._btn_run.clicked.connect(self._on_run)
        actions.addWidget(self._btn_run)
        self._btn_cancel = SecondaryButton("取消")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._on_cancel)
        actions.addWidget(self._btn_cancel)
        btn_open = SecondaryButton("打开输出目录")
        btn_open.clicked.connect(self._open_out)
        actions.addWidget(btn_open)
        btn_board = SecondaryButton("从看板预填根目录")
        btn_board.clicked.connect(self._prefill_board)
        actions.addWidget(btn_board)
        actions.addStretch(1)
        root.addLayout(actions)

        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._folder

    def on_enter(self) -> None:
        self._reload_profiles()
        self._try_prefill_board(silent=True)
        self.report_status("助教打卡换装")

    def _reload_profiles(self) -> None:
        current = self._profile.currentData()
        self._profile.clear()
        profiles = list_edit_capable_profiles()
        if not profiles:
            self._profile.addItem("（无可用编辑模型，请到模型库配置豆包 Seedream）", "")
            return
        default = pick_default_edit_profile_id()
        select_idx = 0
        for i, prof in enumerate(profiles):
            pid = str(prof.get("id") or "")
            label = str(prof.get("label") or pid)
            self._profile.addItem(label, pid)
            if current and pid == current:
                select_idx = i
            elif not current and pid == default:
                select_idx = i
        self._profile.setCurrentIndex(select_idx)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择助教打卡照片目录")
        if path:
            self._folder.setText(path)
            self._reload_list()

    def _reload_list(self) -> None:
        folder = self._folder.text().strip()
        self._list.clear()
        if not folder:
            self._count.setText("共 0 张")
            return
        images = list_images(folder, recursive=self._recursive.isChecked())
        for p in images:
            self._list.addItem(p.name)
        self._count.setText(f"共 {len(images)} 张")
        self.report_status(f"已扫描 {len(images)} 张图片")

    def _on_run(self) -> None:
        if self._thread is not None:
            show_warning(self, "正在换装中，请等待完成或取消。")
            return
        folder = self._folder.text().strip()
        if not folder or not Path(folder).is_dir():
            show_warning(self, "请先选择有效的照片目录。")
            return
        preset_id = str(self._style.currentData() or "")
        profile_id = str(self._profile.currentData() or "")
        if not profile_id:
            show_warning(self, "请选择支持参考图编辑的生图模型（如豆包 Seedream），并在模型库配置密钥。")
            return
        images = list_images(folder, recursive=self._recursive.isChecked())
        if not images:
            show_warning(self, "目录下没有可处理的图片。")
            return

        self._progress.setRange(0, len(images))
        self._progress.setValue(0)
        self._status.setText(f"排队处理 {len(images)} 张…")
        self._btn_run.setEnabled(False)
        self._btn_cancel.setEnabled(True)

        thread = QThread(self)
        worker = _BatchWorker(
            folder,
            preset_id,
            profile_id,
            self._recursive.isChecked(),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished_ok.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._clear_thread)
        self._thread = thread
        self._worker = worker
        thread.start()
        self.report_status("换装任务已开始", level=StatusLevel.INFO)

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._status.setText("正在取消…")
            self.report_status("正在取消换装…", level=StatusLevel.WARNING)

    def _on_progress(self, done: int, total: int, message: str) -> None:
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(min(done, total))
        self._status.setText(message)
        self.report_status(message)

    def _on_finished(self, result: object) -> None:
        self._btn_run.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        if not isinstance(result, BatchResult):
            return
        self._last_out = result.out_dir
        self._progress.setValue(result.total)
        summary = (
            f"完成：成功 {result.ok_count} · 失败 {result.fail_count} · 共 {result.total}。"
            f" 输出：{result.out_dir}"
        )
        self._status.setText(summary)
        fails = [it for it in result.items if not it.ok]
        if fails:
            detail = "；".join(f"{Path(it.source).name}: {it.error}" for it in fails[:5])
            if len(fails) > 5:
                detail += f"… 等 {len(fails)} 项"
            self.report_status(f"{summary} 失败摘要：{detail}", level=StatusLevel.WARNING)
        else:
            self.report_status(summary, level=StatusLevel.SUCCESS)
        if result.ok_count > 0 and result.out_dir:
            show_saved(
                self,
                f"换装完成：成功 {result.ok_count} 张（失败 {result.fail_count}）。\n"
                f"仅改服装；请抽查水印是否仍在。",
                result.out_dir,
            )

    def _on_failed(self, message: str) -> None:
        self._btn_run.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._status.setText(message)
        show_warning(self, message)
        self.report_status(message, level=StatusLevel.WARNING)

    def _clear_thread(self) -> None:
        self._thread = None
        self._worker = None

    def _open_out(self) -> None:
        path = self._last_out.strip()
        if not path:
            folder = self._folder.text().strip()
            style = str(self._style.currentText() or "西服")
            if folder:
                path = str(Path(folder) / f"_换装_{style}")
        if not path or not Path(path).exists():
            show_warning(self, "还没有输出目录，请先完成一次换装。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _prefill_board(self) -> None:
        if not self._try_prefill_board(silent=False):
            show_warning(self, "培训交付看板暂无根目录，请先在看板绑定班级目录。")

    def _try_prefill_board(self, *, silent: bool) -> bool:
        try:
            from services.class_session_handoff import load_session
        except Exception:
            return False
        session = load_session()
        root = str(getattr(session, "root_path", "") or "").strip()
        if not root or not Path(root).is_dir():
            return False
        if self._folder.text().strip() and silent:
            return True
        # 优先常见助教打卡子目录
        candidates = [
            Path(root) / "01-助教打卡",
            Path(root) / "02-助教打卡照片",
            Path(root) / "02-助教打卡照片-PPT",
            Path(root),
        ]
        chosen = next((p for p in candidates if p.is_dir()), Path(root))
        self._folder.setText(str(chosen))
        self._reload_list()
        if not silent:
            self.report_status(f"已预填：{chosen}")
        return True
