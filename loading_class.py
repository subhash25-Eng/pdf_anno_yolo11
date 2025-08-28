from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import logging


class LoadingDialog(QDialog):
    def __init__(self, message="Loading zones...", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Please Wait")
        self.setModal(True)
        self.setFixedSize(300, 120)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)

        # Initialize UI elements
        self.label = QLabel(message)
        self.label.setAlignment(Qt.AlignCenter)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate progress

        self.elapsed_label = QLabel("Elapsed: 0 seconds")
        self.elapsed_label.setAlignment(Qt.AlignCenter)

        # Timer setup with thread safety
        self.elapsed = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self._timer_running = False

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.progress)
        layout.addWidget(self.elapsed_label)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)
        self.setLayout(layout)

        # Style the dialog
        self.setStyleSheet("""
            QDialog {
                background-color: #f0f0f0;
                border: 2px solid #cccccc;
                border-radius: 8px;
            }
            QLabel {
                font-size: 11px;
                color: #333333;
            }
            QProgressBar {
                border: 2px solid #cccccc;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)

    def start(self):
        """Start the loading dialog and timer"""
        try:
            self.elapsed = 0
            self.elapsed_label.setText("Elapsed: 0 seconds")

            if not self._timer_running:
                self.timer.start(1000)  # Update every second
                self._timer_running = True

            self.show()
            self.raise_()  # Bring to front
            self.activateWindow()
            logging.debug("LoadingDialog started")

        except Exception as e:
            logging.warning(f"Error starting loading dialog: {e}")

    @pyqtSlot()
    def update_time(self):
        """Update elapsed time - slot method for thread safety"""
        try:
            self.elapsed += 1
            self.elapsed_label.setText(f"Elapsed: {self.elapsed} seconds")
        except Exception as e:
            logging.warning(f"Error updating time in loading dialog: {e}")

    def stop(self):
        """Stop the loading dialog safely"""
        try:
            # Check if we're on the main thread
            if QThread.currentThread() != QApplication.instance().thread():
                # If called from background thread, delegate to main thread
                QMetaObject.invokeMethod(self, "_stop_on_main_thread", Qt.QueuedConnection)
                return

            self._stop_on_main_thread()

        except Exception as e:
            logging.warning(f"Error stopping loading dialog: {e}")

    @pyqtSlot()
    def _stop_on_main_thread(self):
        """Internal method to stop dialog on main thread"""
        try:
            if self._timer_running and self.timer.isActive():
                self.timer.stop()
                self._timer_running = False
                logging.debug("Timer stopped successfully")

            self.hide()
            self.accept()
            logging.debug("LoadingDialog stopped")

        except Exception as e:
            logging.warning(f"Error in _stop_on_main_thread: {e}")

    def closeEvent(self, event):
        """Handle close event safely"""
        try:
            if self._timer_running:
                self.timer.stop()
                self._timer_running = False
        except Exception as e:
            logging.warning(f"Error in closeEvent: {e}")

        super().closeEvent(event)

    def reject(self):
        """Override reject to handle ESC key"""
        self.stop()
        super().reject()

    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key_Escape:
            self.stop()
        else:
            super().keyPressEvent(event)

    def set_message(self, message):
        """Update the loading message"""
        try:
            self.label.setText(message)
        except Exception as e:
            logging.warning(f"Error setting message: {e}")

    def __del__(self):
        """Destructor to ensure timer cleanup"""
        try:
            if hasattr(self, 'timer') and self.timer and self._timer_running:
                self.timer.stop()
        except Exception as e:
            logging.warning(f"Error in LoadingDialog destructor: {e}")
