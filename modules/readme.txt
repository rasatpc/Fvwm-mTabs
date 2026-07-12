FvwmTabs is a Python/Tk rewrite of the old Perl FVWM tabbing module. This keeps the socket/Tk design, multiple tabbers, FVWM command functions, assigned tabber IDs, right-click menu, and autoSwallow behavior.

The FVWM module is a executable file:

  FvwmTabs

FvwmTabs is a single self-contained executable file. FVWM functions talk to FvwmTabs through the standard FvwmMFL module (see
"Command routing" below), and the FvwmMFL socket client is built into FvwmTabs itself.

Requirements:

- Python 3
- python3-tk
- FVWM3
- FvwmMFL (REQUIRED). It is the command transport between FVWM functions and the
  FvwmTabs server, and also delivers autoSwallow window events. Load it before
  FvwmTabs in StartFunction.
- xdotool
- x11-utils, which provides xprop and xwininfo

On Debian, Ubuntu, and MX Linux:

   sudo apt install python3 python3-tk fvwm3 xdotool x11-utils

Install

1. Put the FvwmTabs files in any FVWM ModulePath directory.
   For example:

   mkdir -p ~/.fvwm/modules
   cp ConfigFvwmTabs FvwmTabs FvwmTabs.conf ~/.fvwm/modules/

2. Make the module executable:

   chmod +x ~/.fvwm/FvwmTabs/FvwmTabs

3. Add the module directory to FVWM config, loading FvwmMFL first:

   Example .fvwm/config setup:

   DestroyFunc StartFunction
   AddToFunc StartFunction
   + I Module FvwmMFL
   + I ModulePath ${HOME}/.fvwm/modules:+
   + I Module FvwmTabs

FVWM starts the executable named FvwmTabs from ModulePath. During module startup, FvwmTabs reads ConfigFvwmTabs, launches its own Python/Tk server, connects to the FvwmMFL socket, and stays connected to FVWM until FVWM exits.

Note: FvwmTabs does not start FvwmMFL for you - load "Module FvwmMFL" yourself, before "Module FvwmTabs", as shown above.

#####
Manual Startup
#####

- FvwmConsole:

Module FvwmMFL
ModulePath ${HOME}/.fvwm/modules:+
Module FvwmTabs

Create Tabbers:

- Key binding: Ctrl+Meta+T
  Tabber drop-down menu, select: "Add Tabber"
  
- FvwmConsole:

   NewTabber
   NewTabber --geometry=175x70

- Key binding:
   Key T A CM NewTabber

The first new tabber is ID 1, the second is ID 2, then ID 3, and so on.

Add Windows manually

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

Change a Tabber's ID:

A tabber is identified by a numeric ID, and autoSwallow rules in FvwmTabs.conf are bound to those IDs (for example "firefox 2" sends Firefox windows to tabber ID 2). "Changing a tabber's ID" means reassigning that number - it is NOT a free-text label. Because the ID is what every by-ID command and every autoSwallow rule reads, reassigning it takes effect immediately:

  - NextTabId, PrevTabId, DestroyTabberId, and TabizeTo work with the new ID at
    once - no restart needed.
  - autoSwallow re-evaluates: any window whose rule maps to the new ID is
    swallowed into this tabber right away, exactly as if the tabber had been
    created with that ID from the start.

A new ID that is already in use by another tabber is REFUSED: an error dialog appears and nothing changes. Two tabbers can never share an ID.

- Tabber drop-down menu (the "v" button), select: "Change Tabber ID". A small
  dialog appears; type the new ID number and press OK.

- FvwmConsole:

    ChangeTabberId 5 2       reassign tabber 5 to be tabber 2
    ChangeActiveTabberId 2   reassign the currently active tabber to be 2

autoSwallow recovery example (the reason this feature exists):

  1. Tabber ID 2 is bound to an autoSwallow rule, e.g.

       autoSwallowClass=firefox 2

     so Firefox windows are routed into tabber 2.

  2. Tabber 2 gets killed by accident.

  3. You create a new tabber. It is assigned some other free ID, e.g. 5.

  4. You change that tabber's ID to 2:

       ChangeActiveTabberId 2      (or:  ChangeTabberId 5 2)

  5. Because it now IS tabber 2, autoSwallow immediately routes the matching
     Firefox windows into it - the same effect as the "Reset" behaviour, but
     for a single tabber instead of killing and recreating everything.

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

Command routing (FvwmMFL):

There is no helper program. Each FVWM function in ConfigFvwmTabs simply runs:

  Echo FvwmTabsCmd <command>

The chain is:

  FVWM function -> Echo FvwmTabsCmd <command>
      -> FVWM broadcasts an MX_ECHO packet (silent; not printed to stderr)
      -> FvwmMFL re-emits it as {"echo": {"message": "FvwmTabsCmd <command>"}}
      -> FvwmTabs server (subscribed to "echo") strips the tag and runs <command>.

The same FvwmMFL connection also carries autoSwallow window events. Because the server dispatches whatever command follows the tag, adding a new command later needs only a new "Echo FvwmTabsCmd <command>" line in ConfigFvwmTabs - no change to FvwmTabs.

Socket discovery (usually automatic):

1. $FVWMMFL_SOCKET or $FVWMMFL_SOCKET_PATH, if set (explicit override).
2. Otherwise FvwmMFL's default socket is used:
   $TMPDIR/fvwmmfl/fvwm_mfl_$DISPLAY.sock   (TMPDIR defaults to /tmp).

Environment variables:

- FVWMMFL_SOCKET
- FVWMMFL_SOCKET_PATH

Note: FvwmMFL is required.
FvwmTabs does not create any private socket or state files; the only socket it uses is FvwmMFL's own. The server's lifetime is tied to the FvwmTabs module, so nothing is left behind to clean up after FVWM Quit or Restart.

Troubleshooting

- Commands / menu do nothing:
  Confirm FvwmMFL is loaded ("Module FvwmMFL" before "Module FvwmTabs") and that
  its socket exists:
    ls -l "${TMPDIR:-/tmp}/fvwmmfl/"
  If your FvwmMFL uses a non-default socket, set FVWMMFL_SOCKET or
  FVWMMFL_SOCKET_PATH (SetEnv) before Module FvwmTabs.

- autoSwallow does not match:
  Create the target tabber first, then start the application. Use the exact
  class value with autoSwallowClass where possible. Restart FvwmTabs after
  changing rules.

- xdotool, xprop, or xwininfo errors:
  Install the missing X11 utility package for your distribution.
