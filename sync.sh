#!/bin/sh
rshell --port $1 rsync --mirror . /flash
