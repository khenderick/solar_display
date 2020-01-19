import time
import _thread
import ujson
from monitor import Monitor

with open('/flash/config.json', 'r') as f:
    config = ujson.load(f)

_monitor = Monitor(solar_topic=config['solar_topic'],
                   grid_topic=config['grid_topic'],
                   mqtt_broker=config['mqtt_broker'],
                   wifi_credentials=config['wifi_credentials'])
_monitor.init()
_monitor.run()