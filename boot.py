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
import os
from machine import Pin

SD_FOLDER = '/sd'
FLASH_FOLDER = '/flash'
UPDATE_FOLDER = '{0}/update'.format(SD_FOLDER)
FLASH_FILE = '{0}/{{0}}'.format(FLASH_FOLDER)
UPDATE_FILE = '{0}/{{0}}'.format(UPDATE_FOLDER)
BACKUP_FILE = 'backup.json'
RUNTIME_CONFIG_FILE = 'runtime_config.json'


def _try_update():
    os.sdconfig(os.SDMODE_SPI, clk=Pin(18), mosi=Pin(23), miso=Pin(19), cs=Pin(4))
    try:
        os.mountsd()
        print('SD card mounted')
    except OSError:
        print('SD card not found')
        return
    directories = os.listdir(SD_FOLDER)
    if 'update' not in directories:
        print('No update folder found')
        return
    print('Update folder found. Updating...')
    for filename in os.listdir(FLASH_FOLDER):
        if filename in [BACKUP_FILE, RUNTIME_CONFIG_FILE]:
            continue
        os.remove(filename)
        print('- removed {0}'.format(filename))
    for filename in os.listdir(UPDATE_FOLDER):
        with open(UPDATE_FILE.format(filename), 'r') as source:
            content = '\n'.join(source.readlines())
        with open(FLASH_FILE.format(filename), 'w') as destination:
            destination.write(content)
        print('- added {0}'.format(filename))
    for filename in os.listdir(UPDATE_FOLDER):
        os.remove(UPDATE_FILE.format(filename))
    os.rmdir(UPDATE_FOLDER)
    os.umountsd()
    print('Update completed')


_try_update()
