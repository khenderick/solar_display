import ujson
import os
from monitor import Monitor

with open('/flash/config.json', 'r') as f:
    config = ujson.load(f)

backup = {}
if 'backup.json' in os.listdir('/flash'):
    print('Loading backup')
    with open('/flash/backup.json', 'r') as f:
        backup = ujson.load(f)
    os.remove('/flash/backup.json')

extra_kwargs = {}
for key in ['graph_interval_s', 'update_interval_ms']:
    if key in config:
        extra_kwargs[key] = config[key]

_monitor = Monitor(usage_buffer=backup.get('usage_buffer', []),
                   solar_buffer=backup.get('solar_buffer', []),
                   solar_topic=config['solar_topic'],
                   grid_topic=config['grid_topic'],
                   mqtt_broker=config['mqtt_broker'],
                   wifi_credentials=config['wifi_credentials'],
                   **extra_kwargs)
_monitor.init()
_monitor.run()
