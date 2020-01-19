import display
import network
import time
from machine import I2C, Pin, Timer, RTC
from ip5306 import IP5306


class Monitor(object):

    def __init__(self, solar_topic, grid_topic, mqtt_broker, wifi_credentials):
        self._solar_topic = solar_topic
        self._grid_topic = grid_topic
        self._mqtt_broker = mqtt_broker
        self._wifi_credentials = wifi_credentials

        self._tft = None
        self._wlan = None
        self._mqtt = None
        
        self._battery = IP5306(I2C(scl=Pin(22), sda=Pin(21)))
        self._timer = Timer(0)
        self._rtc = RTC()

        self._solar = None
        self._usage = None
        self._grid = None
        self._importing = None
        self._prev_importing = None
        self._usage_buffer = []
        self._solar_buffer = []
        self._last_update = (0, 0, 0, 0, 0, 0)
        self._buffer_updated = False
        self._realtime_updated = False
        self._last_value_added = 0

        print('Initializing TFT...')
        self._tft = display.TFT()
        self._tft.init(self._tft.M5STACK, width=240, height=320, rst_pin=33, backl_pin=32, miso=19, mosi=23, clk=18, cs=14, dc=27, bgr=True, backl_on=1)
        self._tft.tft_writecmd(0x21)  # Invert colors
        self._tft.clear()
        self._tft.font(self._tft.FONT_Default)
        self._tft.text(0, 0, 'USAGE', self._tft.DARKGREY)
        self._tft.text(self._tft.CENTER, 0, 'IMPORTING', self._tft.DARKGREY)
        self._tft.text(self._tft.RIGHT, 0, 'SOLAR', self._tft.DARKGREY)
        self._tft.text(0, 14, 'Loading...', self._tft.DARKGREY)
        print('Initializing TFT... Done')
    
    def init(self):
        print('Connecting to wifi...')
        self._wlan = network.WLAN(network.STA_IF)
        self._wlan.active(True)
        self._wlan.connect(*self._wifi_credentials)
        while not self._wlan.isconnected():
            time.sleep(1)
        print('Connecting to wifi... Done')
        print('Connecting to MQTT...')
        if self._mqtt is not None:
            self._mqtt.unsubscribe('emon/#')
        self._mqtt = network.mqtt('emon', self._mqtt_broker, user='emonpi', password='emonpimqtt2016', data_cb=self._process_data)
        self._mqtt.start()
        self._mqtt.subscribe('emon/#')
        print('Connecting to MQTT... Done')
        print('Sync NTP...')
        self._rtc.ntp_sync(server='be.pool.ntp.org', tz='CET-1CEST-2')
        self._last_update = self._rtc.now()
        print('Sync NTP... Done')
    
    def _process_data(self, message):
        topic = message[1]
        data = float(message[2])
        if topic == self._solar_topic:
            self._solar = data
        elif topic == self._grid_topic:
            self._grid = data
        if self._solar is not None and self._grid is not None:
            self._usage = self._solar + self._grid
            self._last_update = self._rtc.now()
            self._realtime_updated = True

        if topic == self._grid_topic and self._usage is not None:
            now = time.time()
            if self._last_value_added < (now - now % 60):
                self._solar_buffer.append(self._solar)
                self._solar_buffer = self._solar_buffer[-320:]
                self._usage_buffer.append(self._usage)
                self._usage_buffer = self._usage_buffer[-320:]
                self._last_value_added = now - now % 60
                self._buffer_updated = True

    def run(self):
        self._timer.init(period=1000, mode=Timer.PERIODIC, callback=self._tick)

    def _tick(self, timer):
        _ = timer
        try:
            self._draw()
        except Exception as ex:
            print('Exception in draw: {0}'.format(ex))
        try:
            if not self._wlan.isconnected():
                self.init()
        except Exception as ex:
            print('Exception in watchdog: {0}'.format(ex))
    
    def _draw(self):
        if self._realtime_updated:
            self._tft.text(self._tft.RIGHT, 14, '          {0}W'.format(self._solar), self._tft.YELLOW)
            self._tft.text(0, 14, '{0}W          '.format(self._usage), self._tft.BLUE)
            self._importing = self._grid > 0
            if self._prev_importing != self._importing:
                if self._importing:
                    self._tft.text(self._tft.CENTER, 0, '  IMPORTING  ', self._tft.DARKGREY)
                else:
                    self._tft.text(self._tft.CENTER, 0, '  EXPORTING  ', self._tft.DARKGREY)
            if self._importing:
                self._tft.text(self._tft.CENTER, 14, '  {0}W  '.format(abs(self._grid)), self._tft.RED)
            else:
                self._tft.text(self._tft.CENTER, 14, '  {0}W  '.format(abs(self._grid)), self._tft.GREEN)
            self._prev_importing = self._importing
            self._realtime_updated = False

        if self._buffer_updated:
            if len(self._usage_buffer) > 1:
                max_value = float(max(max(*self._solar_buffer), max(*self._usage_buffer)))
            else:
                max_value = float(max(self._solar_buffer[0], self._usage_buffer[0]))
            ratio = 180.0 / max_value

            for index, usage in enumerate(self._usage_buffer):
                solar = self._solar_buffer[index]

                usage_height = int(usage * ratio)
                solar_height = int(solar * ratio)

                max_height = max(usage_height, solar_height)
                self._tft.line(index, 40, index, 220 - max_height, self._tft.BLACK)
                if usage_height > solar_height:
                    self._tft.line(index, 220 - usage_height, index, 220 - solar_height, self._tft.BLUE)
                    self._tft.line(index, 220 - solar_height, index, 220, self._tft.DARKCYAN)
                else:
                    self._tft.line(index, 220 - solar_height, index, 220 - usage_height, self._tft.YELLOW)
                    self._tft.line(index, 220 - usage_height, index, 220, self._tft.DARKCYAN)
            self._buffer_updated = False

        self._tft.text(0, self._tft.BOTTOM, 'B: {0}% - U: {1}                '.format(
            self._battery.level,
            '{0:04d}/{1:02d}/{2:02d} {3:02d}:{4:02d}:{5:02d}'.format(*self._last_update[:6])
        ), self._tft.DARKGREY)
