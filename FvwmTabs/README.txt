FvwmTabs is a Python/Tk rewrite of the old Perl FVWM tabbing module. This keeps the socket/Tk design, multiple tabbers, FVWM command functions, assigned tabber IDs, right-click menu, and autoSwallow behavior.

The FVWM module is a single executable file:

   FvwmTabs

There is no separate FvwmTabs.py entrypoint. The tabber_client.py remains as the small command client used by FVWM functions, and fvwmmfl_client.py remains as the optional FvwmMFL socket/event helper.

Requirements:

- Python 3
- python3-tk
- FVWM or FVWM3 on X11
- Optional: FvwmMFL for FVWM3 event integration, only when started and
  configured by the user
- xdotool
- x11-utils, which provides xprop and xwininfo

On Debian, Ubuntu, and MX Linux:

   sudo apt install python3 python3-tk fvwm3 xdotool x11-utils

Install

1. Put the FvwmTabs files in any FVWM ModulePath directory.
   For example:

   mkdir -p ~/.fvwm/modules
   cp FvwmTabs tabber_client.py fvwmmfl_client.py ConfigFvwmTabs FvwmTabs.conf to ~/.fvwm/modules/

2. Make sure the module is executable:

   chmod +x ~/.fvwm/modules/FvwmTabs

3. Add the module directory to FVWM config.

   Example .fvwm/config setup:

   DestroyFunc StartFunction
   AddToFunc StartFunction
   + I ModulePath ${HOME}/.fvwm/modules:+
   + I Module FvwmTabs

FVWM starts the executable named FvwmTabs from ModulePath. During module startup, FvwmTabs reads ConfigFvwmTabs, starts the Python/Tk server through tabber_client.py, and stays connected to FVWM until FVWM exits.

This startup path does not start, load, or probe FvwmMFL.

Manual Startup

Standard FVWM module loading is the supported startup path. For troubleshooting or legacy manual use, set FVWMTABS_DIR before reading ConfigFvwmTabs:

   SetEnv FVWMTABS_DIR ${HOME}/.fvwm/modules
   Read ${HOME}/.fvwm/modules/ConfigFvwmTabs
   Function FvwmTabsStart

From a shell:

   python3 ~/.fvwm/modules/tabber_client.py start
   python3 ~/.fvwm/modules/tabber_client.py quit

Create Tabbers

- Key binding: Ctrl+Meta+T
- FVWM root menu: right-click root window, then FvwmTabs -> Create New Tabber
- FvwmConsole:

   Function NewTabber

The first new tabber is ID 1, the second is ID 2, then ID 3, and so on.

Add Windows Manually

- Key binding: Ctrl+Meta+W, then click windows to add them to tabber 1.
- FVWM root menu: FvwmTabs -> Add Window(s). This targets the currently
  active tabber, falling back to tabber 1 if no active tabber is known.
- From a tabber dropdown: Add Window(s) adds to that same tabber.
- FvwmConsole:

   Function Tabize
   Function TabizeActive
   Function TabizeTo 2

Tab Commands

Default tabber 1:

   Function NextTab
   Function PrevTab
   Function DestroyTabber

Currently active tabber:

   Function NextTabActive
   Function PrevTabActive
   Function DestroyActiveTabber

Explicit tabber ID:

   Function NextTabId 2
   Function PrevTabId 2
   Function DestroyTabberId 2

AutoSwallow

autoSwallow watches newly managed X11 client windows and adds matching windows
to already-existing configured tabbers. If the user has already started FvwmMFL
and explicitly provided its socket path, FvwmTabs receives FVWM JSON events for
new/map/destroy window activity and uses them as an early detection source. The
existing _NET_CLIENT_LIST/_NET_CLIENT_LIST_STACKING xprop watcher and periodic
scan remain active as fallback.

Example FvwmTabs.conf:

   theme=black
   logging=false
   verbose=false
   debug=false
   autoSwallowClass=firefox 1, thunderbird* 2, XTerm 3, Xfce4-terminal 3
   autoSwallowResource=xterm 3
   autoSwallowName=*Images* 2

Matching is case-insensitive and supports shell-style wildcards with *.
If a rule points to a tabber ID, that tabber must already exist. autoSwallow
does not create a tabber only because a rule matched that ID.

WM_CLASS has two strings:

- Resource/instance: first string, matched by autoSwallowResource
- Class: second string, matched by autoSwallowClass

autoSwallowName matches _NET_WM_NAME first, then WM_NAME.

Logging And Debugging

Default behavior is quiet:

   logging=false
   verbose=false
   debug=false

With those defaults, FvwmTabs does not create a log file for normal startup and
does not run debug probes. Fatal startup errors still go to stderr so FVWM can
show or capture them.

Enable logging only while troubleshooting:

- logging=true writes warnings and errors to ~/.fvwm/.fvwmtabs-DISPLAY.log.
- verbose=true writes normal runtime flow messages and implies log creation.
- debug=true writes detailed retry/protocol messages and implies log creation.

To dump the current autoSwallow state to the log from FvwmConsole, enable
logging or debug first, then run:

   Function DumpAutoSwallow

Temporary Files

FvwmTabs uses per-display state files under ~/.fvwm:

   .fvwmtabs-DISPLAY.sock
   .fvwmtabs-DISPLAY.pid
   .fvwmtabs-DISPLAY.module
   .fvwmtabs-DISPLAY.log

The server closes its socket on exit, but FVWM Quit/Exit does not try to remove
runtime files. Stale socket files are replaced on the next startup; PID and
module-token files are overwritten as needed. Opt-in log files are kept for
troubleshooting.

Optional FvwmMFL Socket

FvwmTabs never starts FvwmMFL. It also does not scan default /tmp socket
locations. To opt in to FvwmMFL event integration, start FvwmMFL from your own
FVWM config and provide one of these environment variables before loading
FvwmTabs:

- FVWMMFL_SOCKET
- FVWMMFL_SOCKET_PATH

If no explicit socket is configured, FvwmTabs keeps working with the stable v12
xprop watcher. Manual loading with only ModulePath and Module FvwmTabs will not
trigger FvwmMFL startup.

Reset Stale State

If the client reports that the server does not answer and FVWM is not running,
remove stale socket state:

   rm -f ~/.fvwm/.fvwmtabs-*.sock ~/.fvwm/.fvwmtabs-*.pid

Troubleshooting

- No tabber appears after login:
  Run Function FvwmTabsStart from FvwmConsole, then Function NewTabber.

- FvwmMFL is not used:
  Verify that your FVWM config starts FvwmMFL separately and exports
  FVWMMFL_SOCKET or FVWMMFL_SOCKET_PATH before Module FvwmTabs.

- autoSwallow does not match:
  Create the target tabber first, then start the application. Use the exact
  class value with autoSwallowClass where possible. Restart FvwmTabs after
  changing rules.

- xdotool, xprop, or xwininfo errors:
  Install the missing X11 utility package for your distribution. These tools
  are still required by the v12 tabber/reparenting implementation.
