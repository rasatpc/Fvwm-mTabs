# FvwmTabs
It is a generic tabbing module for FVWM that was included in FVWM2. It can swallow any fvwm window and treat it as a tab in a tab-manager window.

This FvwmTabs is a Python/Tk rewrite of the old Perl FVWM tabbing module. This version keeps a stable socket/Tk design: FVWM starts a small client, the client talks to a long-running Python server, and the server reparents selected X11 windows into Tk tabbers.

# INSTALL and SETUP
# Requirements

- Python 3
- python3-tk
- FVWM3 on X11
- xdotool
- x11-utils, which provides xprop and xwininfo

On Debian, Ubuntu, and MX Linux:
   sudo apt install python3 python3-tk fvwm3 xdotool x11-utils

## FVWM
# .fvwm/config

DestroyFunc StartFunction
AddToFunc StartFunction
+ I Module FvwmMFL
+ I ModulePath ${HOME}/.fvwm/modules:+
+ I Module FvwmTabs
