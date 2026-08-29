import sys, pathlib, re
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
import app.main as m
import app.presentation.main_window as mw
app = QApplication(sys.argv)

def close_via_window(self):
    QTimer.singleShot(1200, self.close)

mw.MainWindow.show = close_via_window
try:
    m.main()
except SystemExit:
    pass
cfg = pathlib.Path('config/app_config.yaml')
print('APP CLOSE OK - config exists:', cfg.exists())
text = cfg.read_text() if cfg.exists() else ''
print('window size persisted:', ('width:' in text) and ('height:' in text))
