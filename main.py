import ujson
import os
from monitor import Monitor

with open('/flash/config.json', 'r') as f:
    config = ujson.load(f)

extra_kwargs = {}
for key in ['graph_interval_s', 'update_interval_ms']:
    if key in config:
        extra_kwargs[key] = config[key]

_monitor = Monitor(solar_topic=config['solar_topic'],
                   grid_topic=config['grid_topic'],
                   mqtt_broker=config['mqtt_broker'],
                   wifi_credentials=config['wifi_credentials'],
                   **extra_kwargs)
_monitor.load()
_monitor.init()
_monitor.run()
