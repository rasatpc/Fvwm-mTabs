#!/bin/sh
## By Trilby (Arch Linux)
## 30 December 2022

## Values to change at restart/refresh
## RESOLUTION  PANEL
#: 3840x2160   1688
#: 2560x1440   1048
#: 1920x1200   728
#: 1920x1080   728
#: 1600x900    568
#: 1360x768    448
#: 1280x1024   408
#: 1280x720    408

res=$(xdpyinfo | awk '/dimensions:/{print $2}')
path="/home/$USER/.fvwm"

set -- $(grep -Fm 1 "#: $res" "$0")

sed -i "/464x32/c\*DeskTitleIcon: Geometry 464x32-$3+10" "$path/core/deskIcons.sys"
