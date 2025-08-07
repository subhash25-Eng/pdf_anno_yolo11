from PyQt5.QtWidgets import *
from PyQt5.QtCore import *


class LoadingDialog(QDialog):
    def __init__(self, message="Loading zones...", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Please Wait")
        self.setModal(True)
        self.setFixedSize(300, 120)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)

        self.label = QLabel(message)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)

        self.elapsed_label = QLabel("Elapsed: 0 seconds")
        self.elapsed = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.progress)
        layout.addWidget(self.elapsed_label)
        self.setLayout(layout)

    def start(self):
        self.elapsed = 0
        self.timer.start(1000)
        self.show()

    def update_time(self):
        self.elapsed += 1
        self.elapsed_label.setText(f"Elapsed: {self.elapsed} seconds")

    def stop(self):
        self.timer.stop()
        self.accept()