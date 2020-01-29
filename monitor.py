import display
import network
import time
import ubinascii
from math import sqrt
from machine import I2C, Pin, Timer, RTC, Neopixel
from ip5306 import IP5306
from buttons import ButtonA, ButtonC


class Monitor(object):

    def __init__(
        self,
        solar_topic, grid_topic, mqtt_broker, wifi_credentials,
        graph_interval_s=60, update_interval_ms=1000
    ):
        self._solar_topic = solar_topic
        self._grid_topic = grid_topic
        self._mqtt_broker = mqtt_broker
        self._wifi_credentials = wifi_credentials
        self._graph_interval = graph_interval_s
        self._update_interval = update_interval_ms
        self._graph_window = Monitor._shorten(self._graph_interval * 320)

        self._tft = None
        self._wlan = None
        self._mqtt = None
        self._neopixel = None

        self._battery = IP5306(I2C(scl=Pin(22), sda=Pin(21)))
        self._timer = Timer(0)
        self._rtc = RTC()
        self._button_a = ButtonA(callback=self._button_a_pressed)
        self._button_c = ButtonC(callback=self._button_c_pressed)

        self._solar = None
        self._usage = None
        self._grid = None
        self._importing = None
        self._prev_importing = None
        self._solar_avg_buffer = []
        self._grid_avg_buffer = []
        self._usage_buffer = []
        self._usage_buffer_max = 0
        self._usage_buffer_min = 0
        self._usage_buffer_avg = 0
        self._usage_buffer_stddev = 0
        self._solar_buffer = []
        self._solar_buffer_max = 0
        self._solar_buffer_min = 0
        self._solar_buffer_avg = 0
        self._solar_buffer_stddev = 0
        self._last_update = (0, 0, 0, 0, 0, 0)
        self._data_received = [False, False]
        self._buffer_updated = False
        self._realtime_updated = False
        self._last_value_added = None
        self._graph_max = 0
        self._menu_horizontal_pointer = 0
        self._menu_tick = 0
        self._menu_tick_divider = 0
        self._blank_menu = False
        self._ticks = {'M': 0,  # MQTT message
                       'D': 0,  # Data sample (solar + grid)
                       'R': 0,  # Remaining time for next graph update
                       'G': 0,  # Graph datapoint added
                       'B': 0,  # Button press
                       'E': 0}  # Exceptions
        self._tick_keys = ['M', 'D', 'G', 'B', 'R', 'E']
        self._last_exception = 'None'

        self._log('Initializing TFT...')
        self._tft = display.TFT()
        self._tft.init(self._tft.M5STACK, width=240, height=320, rst_pin=33, backl_pin=32, miso=19, mosi=23, clk=18, cs=14, dc=27, bgr=True, backl_on=1)
        self._tft.tft_writecmd(0x21)  # Invert colors
        self._tft.clear()
        self._tft.font(self._tft.FONT_Default)
        self._tft.text(0, 0, 'USAGE', self._tft.DARKGREY)
        self._tft.text(self._tft.CENTER, 0, 'IMPORTING', self._tft.DARKGREY)
        self._tft.text(self._tft.RIGHT, 0, 'SOLAR', self._tft.DARKGREY)
        self._tft.text(0, 14, 'Loading...', self._tft.DARKGREY)
        self._log('Initializing TFT... Done')

    def init(self):
        """ Init logic; connect to wifi, connect to MQTT and setup RTC/NTP """
        self._log('Connecting to wifi ({0})... '.format(self._wifi_credentials[0]), tft=True)
        self._wlan = network.WLAN(network.STA_IF)
        self._wlan.active(True)
        self._wlan.connect(*self._wifi_credentials)
        safety = 10
        while not self._wlan.isconnected() and safety > 0:
            # Wait for the wifi to connect, max 10s
            time.sleep(1)
            safety -= 1
        self._log('Connecting to wifi ({0})... {1}'.format(self._wifi_credentials[0], 'Done' if safety else 'Fail'))
        mac_address = ubinascii.hexlify(self._wlan.config('mac'), ':').decode()
        self._log('Connecting to MQTT...', tft=True)
        if self._mqtt is not None:
            self._mqtt.unsubscribe('emon/#')
        self._mqtt = network.mqtt('emon', self._mqtt_broker, user='emonpi', password='emonpimqtt2016', clientid=mac_address, data_cb=self._process_data)
        self._mqtt.start()
        safety = 5
        while self._mqtt.status()[0] != 2 and safety > 0:
            # Wait for MQTT connection, max 5s
            time.sleep(1)
            safety -= 1
        self._mqtt.subscribe('emon/#')
        self._log('Connecting to MQTT... {0}'.format('Done' if safety else 'Fail'))
        self._log('Sync NTP...', tft=True)
        self._rtc.ntp_sync(server='be.pool.ntp.org', tz='CET-1CEST-2')
        safety = 5
        while not self._rtc.synced() and safety > 0:
            # Wait for NTP time sync, max 5s
            time.sleep(1)
            safety -= 1
        self._last_update = self._rtc.now()
        self._log('Sync NTP... {0}'.format('Done' if safety else 'Fail'))
        self._log('Initializing Neopixels...', tft=True)
        try:
            self._neopixel = Neopixel(Pin(15), 10, Neopixel.TYPE_RGB)
            self._neopixel.clear()
        except Exception:
            self._neopixel = None
        self._log('Initializing Neopixels... {0}'.format('Available' if self._neopixel is not None else 'Unavailable'))
        self._tft.text(0, 14, ' ' * 50, self._tft.DARKGREY)  # Clear the line

    def _process_data(self, message):
        """ Process MQTT message """
        try:
            topic = message[1]
            data = float(message[2])
            self._ticks['M'] += 1

            # Collect data samples from solar & grid
            if topic == self._solar_topic:
                self._solar = max(0.0, data)
                self._data_received[0] = True
            elif topic == self._grid_topic:
                self._grid = data
                self._data_received[1] = True

            if self._data_received[0] and self._data_received[1]:
                self._ticks['D'] += 1
                # Once the data has been received, calculate realtime usage
                self._usage = self._solar + self._grid

                self._last_update = self._rtc.now()
                self._realtime_updated = True  # Redraw realtime values
                self._data_received = [False, False]

                # Process data for the graph; collect solar & grids, and every x-pixel
                # average the data out and draw them on that pixel.
                now = time.time()
                rounded_now = int(now - now % self._graph_interval)
                if self._last_value_added is None:
                    self._last_value_added = rounded_now
                self._ticks['R'] = int(rounded_now + self._graph_interval - now)
                self._solar_avg_buffer.append(int(self._solar))
                self._grid_avg_buffer.append(int(self._grid))
                if self._last_value_added != rounded_now:
                    self._ticks['G'] += 1
                    solar, usage = self._read_avg_buffer(reset=True)
                    self._solar_buffer.append(solar)
                    self._solar_buffer = self._solar_buffer[-319:]  # Keep one pixel for moving avg
                    self._calculate_buffer_stats('solar', solar)
                    self._usage_buffer.append(usage)
                    self._usage_buffer = self._usage_buffer[-319:]  # Keep one pixel for moving avg
                    self._calculate_buffer_stats('usage', solar)
                    self._last_value_added = rounded_now
                    self._buffer_updated = True  # Redraw the complete graph
        except Exception as ex:
            self._last_exception = str(ex)
            self._ticks['E'] += 1
            self._log('Exception in process data: {0}'.format(ex))

    def _calculate_buffer_stats(self, buffer_type, single_value):
        buffer = getattr(self, '_{0}_buffer'.format(buffer_type))
        if len(buffer) == 0:
            return
        setattr(self, '_{0}_buffer_max'.format(buffer_type), single_value if len(buffer) == 1 else max(*buffer))
        setattr(self, '_{0}_buffer_min'.format(buffer_type), single_value if len(buffer) == 1 else min(*buffer))
        setattr(self, '_{0}_buffer_avg'.format(buffer_type), sum(buffer) / len(buffer))
        setattr(self, '_{0}_buffer_stddev'.format(buffer_type), Monitor._stddev(buffer))

    def _read_avg_buffer(self, reset):
        solar_avg_buffer_length = len(self._solar_avg_buffer)
        grid_avg_buffer_length = len(self._grid_avg_buffer)
        if solar_avg_buffer_length == 0 or grid_avg_buffer_length == 0:
            return 0, 0
        solar = int(sum(self._solar_avg_buffer) / solar_avg_buffer_length)
        grid = int(sum(self._grid_avg_buffer) / grid_avg_buffer_length)
        usage = solar + grid
        if reset:
            self._solar_avg_buffer = []
            self._grid_avg_buffer = []
        return solar, usage

    def run(self):
        """ Set timer """
        self._timer.init(period=self._update_interval, mode=Timer.PERIODIC, callback=self._tick)

    def _tick(self, timer):
        """ Do stuff at a regular interval """
        _ = timer
        self._draw()
        try:
            # At every tick, make sure wifi is still connected
            if not self._wlan.isconnected():
                self.init()
        except Exception as ex:
            self._last_exception = str(ex)
            self._ticks['E'] += 1
            self._log('Exception in watchdog: {0}'.format(ex))

    def _draw(self):
        """ Update display """
        try:
            self._draw_realtime()
        except Exception as ex:
            self._last_exception = str(ex)
            self._ticks['E'] += 1
            self._log('Exception in draw realtime: {0}'.format(ex))
        try:
            self._draw_graph()
        except Exception as ex:
            self._last_exception = str(ex)
            self._ticks['E'] += 1
            self._log('Exception in draw graph: {0}'.format(ex))
        try:
            self._draw_menu()
        except Exception as ex:
            self._last_exception = str(ex)
            self._ticks['E'] += 1
            self._log('Exception in draw menu: {0}'.format(ex))
        try:
            self._draw_rgb()
        except Exception as ex:
            self._last_exception = str(ex)
            self._ticks['E'] += 1
            self._log('Exception in draw rgb: {0}'.format(ex))

    def _draw_rgb(self):
        """ Uses the neopixel leds (if available) to indicate how "good" our power consumption is. """
        if self._neopixel is None:
            return
        if len(self._solar_buffer) == 0 or self._usage is None:
            self._neopixel.clear()
            return

        high_usage = self._usage > self._usage_buffer_avg + (self._usage_buffer_stddev * 2)
        if self._grid < 0:
            # Feeding back to the grid
            score = 0
            if self._grid < -500:
                score += 1
            if self._grid < -1000:
                score += 1
            if high_usage:
                score -= 1
            colors = [Neopixel.GREEN, Neopixel.LIME, Neopixel.YELLOW]
            self._neopixel.set(0, colors[max(0, score)], num=10)
        else:
            score = 0
            if high_usage:
                score += 1
            if self._solar == 0:
                score += 1
            colors = [Neopixel.BLUE, Neopixel.PURPLE, Neopixel.RED]
            self._neopixel.set(0, colors[max(0, score)], num=10)

    def _draw_realtime(self):
        """ Realtime part; current usage, importing/exporting and solar """
        if not self._realtime_updated:
            return

        self._tft.text(self._tft.RIGHT, 14, '          {0:.2f}W'.format(self._solar), self._tft.YELLOW)
        self._tft.text(0, 14, '{0:.2f}W          '.format(self._usage), self._tft.BLUE)
        self._importing = self._grid > 0
        if self._prev_importing != self._importing:
            if self._importing:
                self._tft.text(self._tft.CENTER, 0, '  IMPORTING  ', self._tft.DARKGREY)
            else:
                self._tft.text(self._tft.CENTER, 0, '  EXPORTING  ', self._tft.DARKGREY)
        if self._importing:
            self._tft.text(self._tft.CENTER, 14, '  {0:.2f}W  '.format(abs(self._grid)), self._tft.RED)
        else:
            self._tft.text(self._tft.CENTER, 14, '  {0:.2f}W  '.format(abs(self._grid)), self._tft.GREEN)
        self._prev_importing = self._importing
        self._realtime_updated = False

    def _draw_graph(self):
        """ Draw the graph part """
        solar_moving_avg, usage_moving_avg = self._read_avg_buffer(reset=False)
        max_value = float(max(self._solar_buffer_max, self._usage_buffer_max, solar_moving_avg, usage_moving_avg))
        if max_value != self._graph_max:
            self._graph_max = max_value
            self._buffer_updated = True
        ratio = 1 if max_value == 0 else (180.0 / max_value)

        if self._buffer_updated:
            for index, usage in enumerate(self._usage_buffer):
                solar = self._solar_buffer[index]
                self._draw_graph_line(index, solar, usage, ratio)
            self._buffer_updated = False
        self._draw_graph_line(len(self._usage_buffer), solar_moving_avg, usage_moving_avg, ratio)

    def _draw_graph_line(self, index, solar, usage, ratio):
        usage_height = int(usage * ratio)
        solar_height = int(solar * ratio)
        max_height = max(usage_height, solar_height)
        self._tft.line(index, 40, index, 220 - max_height, self._tft.BLACK)
        if usage_height > solar_height:
            self._tft.line(index, 220 - usage_height, index, 220 - solar_height, self._tft.BLUE)
            if solar_height > 0:
                self._tft.line(index, 220 - solar_height, index, 220, self._tft.DARKCYAN)
        else:
            self._tft.line(index, 220 - solar_height, index, 220 - usage_height, self._tft.YELLOW)
            if usage_height > 0:
                self._tft.line(index, 220 - usage_height, index, 220, self._tft.DARKCYAN)

    def _draw_menu(self):
        if self._blank_menu:
            self._tft.rect(0, 221, 320, 240, self._tft.BLACK, self._tft.BLACK)
            self._blank_menu = False
        if self._menu_horizontal_pointer == 0:
            data = '  Updated:  {0:04d}/{1:02d}/{2:02d} {3:02d}:{4:02d}:{5:02d}  '.format(*self._last_update[:6])
        elif self._menu_horizontal_pointer == 1:
            data = '  Battery: {0}%  '.format(self._battery.level)
        elif self._menu_horizontal_pointer == 2:
            data = '  Graph: {0} {1}, max {2:.2f}W  '.format(len(self._usage_buffer), self._graph_window, self._graph_max)
        elif self._menu_horizontal_pointer in [3, 4]:
            data_type = 'solar' if self._menu_horizontal_pointer == 3 else 'usage'
            solar, usage = self._read_avg_buffer(reset=False)
            if self._menu_tick == 0:
                value = min(
                    getattr(self, '_{0}_buffer_min'.format(data_type)),
                    solar if data_type == 'solar' else usage,
                    self._solar if data_type == 'solar' else self._usage
                )
                info = 'min'
            elif self._menu_tick == 1:
                value = getattr(self, '_{0}_buffer_avg'.format(data_type))
                info = 'avg'
            elif self._menu_tick == 2:
                value = getattr(self, '_{0}_buffer_avg'.format(data_type)) + (getattr(self, '_{0}_buffer_stddev'.format(data_type)) * 2)
                info = 'high'
            else:
                value = max(
                    getattr(self, '_{0}_buffer_max'.format(data_type)),
                    solar if data_type == 'solar' else usage,
                    self._solar if data_type == 'solar' else self._usage
                )
                info = 'max'
            data = '    {0}{1} stats: {2:.2f}W {3}    '.format(data_type[0].upper(), data_type[1:], value, info)
        elif self._menu_horizontal_pointer == 5:
            data = '  Time: {0}  '.format(time.time())
        elif self._menu_horizontal_pointer == 6:
            data = '  Exception: {0}  '.format(self._last_exception[:20])
        else:
            data = '  Ticks: {0}  '.format(', '.join('{0}'.format(self._ticks[key]) for key in self._tick_keys))
        self._tft.text(0, self._tft.BOTTOM, '<', self._tft.DARKGREY)
        self._tft.text(self._tft.RIGHT, self._tft.BOTTOM, '>', self._tft.DARKGREY)
        self._tft.text(self._tft.CENTER, self._tft.BOTTOM, data, self._tft.DARKGREY)
        self._menu_tick_divider += 1
        if self._menu_tick_divider == 3:  # Increase menu tick every X seconds
            self._menu_tick += 1
            if self._menu_tick == 4:
                self._menu_tick = 0
            self._menu_tick_divider = 0

    def _button_a_pressed(self, pin, pressed):
        _ = pin
        if pressed:
            self._ticks['B'] += 1
            self._menu_horizontal_pointer -= 1
            if self._menu_horizontal_pointer < 0:
                self._menu_horizontal_pointer = 7
            self._blank_menu = True

    def _button_c_pressed(self, pin, pressed):
        _ = pin
        if pressed:
            self._ticks['B'] += 1
            self._menu_horizontal_pointer += 1
            if self._menu_horizontal_pointer > 7:
                self._menu_horizontal_pointer = 0
            self._blank_menu = True

    @staticmethod
    def _stddev(entries):
        """ returns the standard deviation of lst """
        avg = sum(entries) / len(entries)
        variance = sum([(e - avg) ** 2 for e in entries]) / len(entries)
        return sqrt(variance)

    @staticmethod
    def _shorten(seconds):
        """ Converts seconds to a `xh ym ys` notation """
        parts = []
        seconds_hour = 60 * 60
        seconds_minute = 60
        if seconds >= seconds_hour:
            hours = int((seconds - seconds % seconds_hour) / seconds_hour)
            seconds = seconds - (hours * seconds_hour)
            parts.append('{0}h'.format(hours))
        if seconds >= seconds_minute:
            minutes = int((seconds - seconds % seconds_minute) / seconds_minute)
            seconds = seconds - (minutes * seconds_minute)
            parts.append('{0}m'.format(minutes))
        if seconds > 0:
            parts.append('{0}s'.format(seconds))
        return ' '.join(parts)

    def _log(self, message, tft=False):
        """ Logs a message to the console and (optionally) to the display """
        print(message)
        if tft:
            self._tft.text(0, 14, '{0}{1}'.format(message, ' ' * 50), self._tft.DARKGREY)
