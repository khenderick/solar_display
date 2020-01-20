#!/bin/sh
rshell --port /dev/ttyUSB0 rsync --mirror . /flash
