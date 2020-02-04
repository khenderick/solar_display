# Solar display - Showing solar/energy production/consumption on an M5Stack
# Copyright (C) 2020 - Kenneth Henderick <kenneth@ketronic.be>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
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
