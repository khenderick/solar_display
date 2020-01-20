#
# This file is part of MicroPython M5Stack package
# Copyright (c) 2017 Mika Tuupola
#
# Licensed under the MIT license:
#   http://www.opensource.org/licenses/mit-license.php
#
# Project home:
#   https://github.com/tuupola/micropython-m5stack
#
# Changes to the original:
# * 2020-01-20 by Kenneth Henderick: Merged part of the above repo's m5stack.py contents into this file

"""
Handle io pin as a digital input.
"""

# pylint: disable=import-error
import machine
from machine import Pin
# pylint: enable=import-error

BUTTON_A_PIN = 39
BUTTON_B_PIN = 38
BUTTON_C_PIN = 37

class DigitalInput(object):

    def __init__(self, pin, callback=None, trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING):
        self._register = bytearray([0b11111111])
        self._user_callback = callback
        self._current_state = False
        self._previous_state = False
        self._pin = pin
        self._pin.init(self._pin.IN, trigger=trigger, handler=self._callback)

    def _callback(self, pin):
        irq_state = machine.disable_irq()

        while True:
            self._register[0] <<= 1
            self._register[0] |= pin.value()

            #print("{:08b}".format(self._register[0]))
            # All bits set, button has been released for 8 loops
            if self._register[0] is 0b11111111:
                self._current_state = False
                break

            # All bits unset, button has been pressed for 8 loops
            if self._register[0] is 0b00000000:
                self._current_state = True
                break

        # Handle edge case of two consequent rising interrupts
        if self._current_state is not self._previous_state:
            self._previous_state = self._current_state
            self._user_callback(self._pin, self._current_state)

        machine.enable_irq(irq_state)

class ButtonA(DigitalInput):
    def __init__(self, callback=None, trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING):
        pin = Pin(BUTTON_A_PIN, Pin.IN)
        DigitalInput.__init__(self, pin, callback=callback, trigger=trigger)

class ButtonB(DigitalInput):
    def __init__(self, callback=None, trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING):
        pin = Pin(BUTTON_B_PIN, Pin.IN)
        DigitalInput.__init__(self, pin, callback=callback, trigger=trigger)

class ButtonC(DigitalInput):
    def __init__(self, callback=None, trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING):
        pin = Pin(BUTTON_C_PIN, Pin.IN)
        DigitalInput.__init__(self, pin, callback=callback, trigger=trigger)
        