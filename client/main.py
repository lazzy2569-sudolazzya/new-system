"""Minimal desktop shell proving out the phase-1 architecture: a login
screen that calls the API through a QThreadPool worker (never blocking the
UI thread) and stores the resulting token in the OS credential store rather
than a config file (plan section 2, "Token storage on client").
"""
import sys

import keyring
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from client.api_client import TOKEN_SERVICE, ApiWorker, login


class MainWindow(QMainWindow):
    def __init__(self, username: str):
        super().__init__()
        self.setWindowTitle("ERP")
        self.setCentralWidget(QLabel(f"Logged in as {username}"))


class LoginWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ERP - Sign in")
        self.thread_pool = QThreadPool.globalInstance()
        self.main_window: MainWindow | None = None
        # PySide/Qt can garbage-collect a QRunnable (and its signals object)
        # the moment the Python refcount to it drops to zero, even while the
        # C++ side is still running on a worker thread -- QThreadPool.start()
        # does not keep the Python wrapper alive on its own. Every in-flight
        # worker is held here until it finishes, or its success/error signal
        # can silently never fire.
        self._active_workers: list[ApiWorker] = []

        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_button = QPushButton("Sign in")
        self.login_button.clicked.connect(self.handle_login)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Username"))
        layout.addWidget(self.username_input)
        layout.addWidget(QLabel("Password"))
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def handle_login(self) -> None:
        self.login_button.setEnabled(False)
        worker = ApiWorker(login, self.username_input.text(), self.password_input.text())
        self._active_workers.append(worker)
        worker.signals.success.connect(lambda result: self._finish_worker(worker, self.on_login_success, result))
        worker.signals.error.connect(lambda message: self._finish_worker(worker, self.on_login_error, message))
        self.thread_pool.start(worker)

    def _finish_worker(self, worker: ApiWorker, handler, payload) -> None:
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        handler(payload)

    def on_login_success(self, result: dict) -> None:
        self.login_button.setEnabled(True)
        username = self.username_input.text()
        keyring.set_password(TOKEN_SERVICE, username, result["access_token"])
        self.main_window = MainWindow(username)
        self.main_window.show()
        self.close()

    def on_login_error(self, message: str) -> None:
        self.login_button.setEnabled(True)
        QMessageBox.critical(self, "Sign in failed", message)


def main() -> None:
    app = QApplication(sys.argv)
    window = LoginWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
