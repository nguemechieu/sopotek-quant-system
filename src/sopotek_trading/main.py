import asyncio
import sys
import traceback
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop
from src.sopotek_trading.frontend.ui.app_controller import AppController




app = QApplication(sys.argv)

loop = QEventLoop(app)
asyncio.set_event_loop(loop)

window = AppController()
window.show()

with loop:
    loop.run_forever()