import time
import _thread
from monitor import Monitor

_monitor = Monitor()
_monitor.init()
_monitor.run()