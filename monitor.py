import display
import network
import time
from machine import I2C, Pin, Timer, RTC
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
        self._solar_buffer = []
        self._last_update = (0, 0, 0, 0, 0, 0)
        self._data_counter = 0
        self._buffer_updated = False
        self._realtime_updated = False
        self._last_value_added = None
        self._menu_horizontal_pointer = 0
        self._blank_menu = False

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
        self._log('Connecting to MQTT...', tft=True)
        if self._mqtt is not None:
            self._mqtt.unsubscribe('emon/#')
        self._mqtt = network.mqtt('emon', self._mqtt_broker, user='emonpi', password='emonpimqtt2016', data_cb=self._process_data)
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
        self._tft.text(0, 14, ' ' * 50, self._tft.DARKGREY)  # Clear the line
    
    def _process_data(self, message):
        """ Process MQTT message """
        topic = message[1]
        data = float(message[2])
        
        # Collect data samples from solar & grid
        if topic == self._solar_topic:
            self._solar = max(0, data)
            self._data_counter += 1
        elif topic == self._grid_topic:
            self._grid = data
            self._data_counter += 1

        if self._data_counter == 2:
            # Once the data has been received, calculate realtime usage
            self._usage = self._solar + self._grid
            
            self._last_update = self._rtc.now()
            self._realtime_updated = True  # Redraw realtime values
            self._data_counter = 0

            # Process data for the graph; collect solar & grids, and every x-pixel
            # average the data out and draw them on that pixel.
            now = time.time()
            rounded_now = now - now % self._graph_interval
            if self._last_value_added is None:
                self._last_value_added = rounded_now
            self._solar_avg_buffer.append(self._solar)
            self._grid_avg_buffer.append(self._grid)
            if self._last_value_added != rounded_now and len(self._solar_avg_buffer) > 0:
                solar = sum(self._solar_avg_buffer) / len(self._solar_avg_buffer)
                self._solar_avg_buffer = []
                grid = sum(self._grid_avg_buffer) / len(self._grid_avg_buffer)
                self._grid_avg_buffer = []
                usage = solar + grid
                self._solar_buffer.append(solar)
                self._solar_buffer = self._solar_buffer[-320:]
                self._usage_buffer.append(usage)
                self._usage_buffer = self._usage_buffer[-320:]
                self._last_value_added = rounded_now
                self._buffer_updated = True  # Redraw the graph

    def run(self):
        """ Set timer """
        self._timer.init(period=self._update_interval, mode=Timer.PERIODIC, callback=self._tick)

    def _tick(self, timer):
        """ Do stuff at a regular interval """
        _ = timer
        try:
            # At avery ticket, update display's relevant parts
            self._draw()
        except Exception as ex:
            self._log('Exception in draw: {0}'.format(ex))
        try:
            # At every tick, make sure wifi is still connected
            if not self._wlan.isconnected():
                self.init()
        except Exception as ex:
            self._log('Exception in watchdog: {0}'.format(ex))
    
    def _draw(self):
        """ Update display """
        if self._realtime_updated:
            # Realtime part; current usage, importing/exporting and solar
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

        if self._buffer_updated:
            # If the graph buffers are updated, redraw the graph
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

        # And in any case, update the general information at the bottom
        if self._blank_menu:
            self._tft.rect(0, 221, 320, 240, self._tft.BLACK, self._tft.BLACK)
            self._blank_menu = False
        if self._menu_horizontal_pointer == 0:
            data = '  Updated:  {0:04d}/{1:02d}/{2:02d} {3:02d}:{4:02d}:{5:02d}  '.format(*self._last_update[:6])
        elif self._menu_horizontal_pointer == 1:
            data = '  Battery: {0}%  '.format(self._battery.level)
        elif self._menu_horizontal_pointer == 2:
            data = '  Width: {0}  '.format(self._graph_window)
        else:
            data = '  Graph entries: {0}  '.format(len(self._usage_buffer))
        self._tft.text(0, self._tft.BOTTOM, '<', self._tft.DARKGREY)
        self._tft.text(self._tft.RIGHT, self._tft.BOTTOM, '>', self._tft.DARKGREY)
        self._tft.text(self._tft.CENTER, self._tft.BOTTOM, data, self._tft.DARKGREY)

    def _button_a_pressed(self, pin, pressed):
        if pressed:
            self._menu_horizontal_pointer -= 1
            if self._menu_horizontal_pointer < 0:
                self._menu_horizontal_pointer = 3
            self._blank_menu = True

    def _button_c_pressed(self, pin, pressed):
        if pressed:
            self._menu_horizontal_pointer += 1
            if self._menu_horizontal_pointer > 3:
                self._menu_horizontal_pointer = 0
            self._blank_menu = True

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
