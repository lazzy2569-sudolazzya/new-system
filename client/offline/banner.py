"""Offline status banner (plan section 1.5: "clearly banner-marked
'Offline, showing data as of 14:32'"). Polls connectivity on a timer via
the same QThreadPool worker pattern as every other network call, so this
check never blocks the UI thread either.
"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel

from client.api_client import ApiWorker
from client.offline.connectivity import is_online

POLL_INTERVAL_MS = 15_000


class OfflineBanner(QLabel):
    def __init__(self, thread_pool, parent=None):
        super().__init__(parent)
        self._thread_pool = thread_pool
        self.setStyleSheet(
            "background-color: #b45309; color: white; padding: 4px; font-weight: bold;"
        )
        self.hide()

        # Same lifetime gotcha as LoginWindow.handle_login: a QRunnable with
        # no surviving Python reference can be garbage-collected mid-flight,
        # so every in-flight check is held here until its signal fires.
        self._active_workers: list[ApiWorker] = []

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_now)
        self._timer.start(POLL_INTERVAL_MS)
        self._check_now()

    def _check_now(self) -> None:
        worker = ApiWorker(is_online)
        self._active_workers.append(worker)
        worker.signals.success.connect(lambda online: self._finish(worker, online))
        worker.signals.error.connect(lambda _msg: self._finish(worker, False))
        self._thread_pool.start(worker)

    def _finish(self, worker: ApiWorker, online: bool) -> None:
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        self._on_result(online)

    def _on_result(self, online: bool) -> None:
        if online:
            self.hide()
        else:
            import datetime as dt

            self.setText(f"Offline, showing data as of {dt.datetime.now():%H:%M}")
            self.show()
