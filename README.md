# Solar monitor display

This repo contains some experimental software written in (micro)python, creating a battery powered display for an OpenEnergyMonitor dashboard. It displays my home's solar installation.

### M5Stack

M5Stack is a small battery powered display with as core an ESP32. See https://m5stack.com/. I used the M5Stack Grey kit.

### OpenEnergyMonitor

OpenEnergyMonitor is an open-source energy monitoring platform. It comes in some different variants, but I used the emonPi. See https://openenergymonitor.org/.

For this project, it's madatory to have two feeds measuring the feed from the solar panels, and the feed from/to the grid. These need to be available on the emonPi's MQTT broker.

### MicroPython

I flashed the Loboris MicroPython port for ESP32. Using the guide on https://github.com/loboris/MicroPython_ESP32_psRAM_LoBo it's fairly straightforward to create a build for the M5Stack.

### Configuration

Add a `config.json` JSON file in the project's root with following content:
* `solar_topic`: The MQTT topic holding the realtime data for the solar feed
* `grid_topic`: The MQTT topic holding the realtime data for the grid feed
* `mqtt_broker`: The MQTT broker endpoint (ip address from the emonPi)
* `wifi_credentials`: A list holding the SSID as first element, and the password as second

### Installation

1. Copy the files over to the M5Stack and reset/reboot the device: `rshell --port /dev/ttyUSB0 rsync --mirror . /flash`
2. Soft restart the M5Stack: Open the REPL with `screen /dev/ttyUSB0 115200` and soft restart with `CTRL+D`

Tip: You can exit the screen by pressing `CTRL+A`, then `k` and then `y`.

### License

All code is licensed under MIT except for files stating differently

### Notices

This project uses and/or relies on following software:
* Loboris ESP32 MicroPython fork
* Mika Tuupola's IP5306 I2C driver

Let me know if I miss anything
