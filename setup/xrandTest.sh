#!/bin/sh

## Test if sual monitor is coneceted

#cd $HOME/.fvwm/setup

xrandr | grep "HDMI-1 connected" | awk '{ print $1 }' | grep HDMI-1 > $HOME/.fvwm/setup/hdmiTest.txt



