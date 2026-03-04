#!/bin/sh

res=$(xrandr | grep '*' | awk 'NR==1{print $1}')
width=$(xrandr | grep '*' | awk 'NR==1{print $1}' | sed 's|[x,]|x0 |g' | awk '{print $1}')

# Example:
# xrandr --output eDP-1 --mode 1920x1080 --pos 1920x0 --rotate normal --output HDMI-1 --primary --mode 1920x1080 --pos 0x0 --rotate normal

xrandr --output eDP-1 --mode $res --pos $width --rotate normal --output HDMI-1 --primary --mode $res --pos 0x0 --rotate normal
