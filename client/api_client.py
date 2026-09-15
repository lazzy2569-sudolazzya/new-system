"""Every network call goes through ApiWorker on the global QThreadPool so the
UI thread never blocks (plan section 2.1) -- this is the template every
future screen's API calls should copy.

Caller responsibility, not optional: keep a reference to the ApiWorker
instance (e.g. in a list on self) until its success/error signal fires.
QThreadPool.start() does not keep the Python wrapper alive on its own, so a
worker that's only a local variable can be garbage-collected mid-flight and
its signal never fires. See LoginWindow.handle_login in client/main.py for
the pattern.
"""
from __future__ import annotations

import requests
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from client.config import get_server_url

TOKEN_SERVICE = "erp-client"


class WorkerSignals(QObject):
    success = Signal(object)
    error = Signal(str)


class ApiWorker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # network/API errors surface to the caller, never crash the UI thread
            self.signals.error.emit(str(exc))
        else:
            self.signals.success.emit(result)


def login(username: str, password: str) -> dict:
    resp = requests.post(
        f"{get_server_url()}/api/v1/auth/login",
        data={"username": username, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
