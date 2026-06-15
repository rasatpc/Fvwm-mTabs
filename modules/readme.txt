FvwmTabs is a Python/Tk rewrite of the old Perl FVWM tabbing module. This keeps the socket/Tk design, multiple tabbers, FVWM command functions, assigned tabber IDs, right-click menu, and autoSwallow behavior.

The FVWM module is a single executable file:

  FvwmTabs

There is no separate FvwmTabs.py entrypoint. The tabber_client.py remains as the small command client used by FVWM functions, and fvwmmfl_client.py remains as the optional FvwmMFL socket/event helper.

Requirements:

- Python 3
- python3-tk
- FVWM or FVWM3
- Optional: FvwmMFL for FVWM3 event integration, only when started and
  configured by the user.
- xdotool
- x11-utils, which provides xprop and xwininfo

On Debian, Ubuntu, and MX Linux:

   sudo apt install python3 python3-tk fvwm3 xdotool x11-utils

Install

1. Put the FvwmTabs files in any FVWM ModulePath directory.
   For example:

   mkdir -p ~/.fvwm/modules
   cp FvwmTabs tabber_client.py fvwmmfl_client.py ConfigFvwmTabs FvwmTabs.conf to ~/.fvwm/modules/

2. Make the module executable:

   chmod +x ~/.fvwm/modules/FvwmTabs

3. Add the module directory to FVWM config.

   Example .fvwm/config setup:

   DestroyFunc StartFunction
   AddToFunc StartFunction
   + I ModulePath ${HOME}/.fvwm/modules:+
   + I Module FvwmTabs

FVWM starts the executable named FvwmTabs from ModulePath. During module startup, FvwmTabs reads ConfigFvwmTabs, starts the Python/Tk server through tabber_client.py, and stays connected to FVWM until FVWM exits.

Note: This startup path does not start, load, or probe FvwmMFL.

#####
Manual Startup

- FvwmConsole:

ModulePath ${HOME}/.fvwm/modules:+
Module FvwmTabs

Create Tabbers:

- Key binding: Ctrl+Meta+T
- Tabber drop-down menu, select: "Add Tabber"
- FvwmConsole:

   NewTabber
   NewTabber --geometry=175x70

- Key binding:
   Key T A CM NewTabber

The first new tabber is ID 1, the second is ID 2, then ID 3, and so on.

Add Windows Manually

- Key binding: Ctrl+Meta+W, then click windows to add them to tabber 1.
- Tabber drop-down menu, select: "Add Window(s)".
- FvwmConsole:

  Tabize
  TabizeActive
  TabizeTo 2

- Key binding:

  Key W A CM Tabize
  Key Right A CM NextTab
  Key Left A CM PrevTab

Tab Commands:

- FvwmConsole and Tabber drop-down menu:

  NextTab
  PrevTab
  DestroyTabber

Currently active tabber (FvwmConsole):

  NextTabActive
  PrevTabActive
  DestroyActiveTabber

Explicit tabber ID (FvwmConsole):

  NextTabId 2
  PrevTabId 2
  DestroyTabberId 2

AutoSwallow:

If an autoSwallow window appears and its assigned tabber does not yet exist, it automatically creates the tabber before routing the window into it.
Default: false — window is silently ignored until the user creates the tabber.

Example FvwmTabs.conf:

  autoSwallowClass=firefox 1, thunderbird* 2
  autoSwallowResource=xterm 3
  autoSwallowName=*Images* 2

Matching is case-insensitive and supports shell-style wildcards with *.

Use FvwmIdent to identify the windows:

- Name: matched by autoSwallowName
- Class: matched by autoSwallowClass
- Resource: matched by autoSwallowResource

Temporary Files:

FvwmTabs uses per-display state files under ~/.fvwm:

  .fvwmtabs-DISPLAY.sock
  .fvwmtabs-DISPLAY.pid
  .fvwmtabs-DISPLAY.module

The server closes its socket on exit, but FVWM Quit/Exit does not try to remove runtime files. Stale socket files are replaced on the next startup; PID and module-token files are overwritten as needed.

Optional FvwmMFL Socket:

FvwmTabs does not start FvwmMFL. It also doesn't scan default /tmp socket locations. To opt in to FvwmMFL event integration, start FvwmMFL from your own FVWM config and provide one of these environment variables before loading.
FvwmTabs:

- FVWMMFL_SOCKET
- FVWMMFL_SOCKET_PATH

Reset Stale State:

If the client reports that the server does not answer and FVWM is not running, remove stale socket state:

  rm -f ~/.fvwm/.fvwmtabs-*.sock ~/.fvwm/.fvwmtabs-*.pid

Troubleshooting

- When FvwmMFL is used:
  Verify that your FVWM config starts FvwmMFL separately and exports
  FVWMMFL_SOCKET or FVWMMFL_SOCKET_PATH before Module FvwmTabs.

- autoSwallow does not match:
  Create the target tabber first, then start the application. Use the exact
  class value with autoSwallowClass where possible. Restart FvwmTabs after
  changing rules.

- xdotool, xprop, or xwininfo errors:
  Install the missing X11 utility package for your distribution.
