FvwmTabs v12-stable

FvwmTabs is a Python/Tk rewrite of the old Perl FVWM tabbing module. This
version keeps the stable v12 socket/Tk design: FVWM starts a small client,
the client talks to a long-running Python server, and the server reparents
selected X11 windows into Tk tabbers.

Requirements

- Python 3
- python3-tk
- FVWM3 on X11
- xdotool
- x11-utils, which provides xprop and xwininfo

On Debian, Ubuntu, and MX Linux:

   sudo apt install python3 python3-tk fvwm3 xdotool x11-utils

Install

1. Extract the release under your FVWM user directory:

   unzip FvwmTabs-v12-final-clean.zip -d ~/.fvwm/

2. Add this line to your main FVWM config:

   Read $[FVWM_USERDIR]/FvwmTabs/ConfigFvwmTabs

3. Add this to your FVWM startup function if you want FvwmTabs to start with FVWM:

   AddToFunc StartFunction
   + I Function FvwmTabsStart

If you already have a StartFunction, add only this line inside the existing
function:

   + I Function FvwmTabsStart

4. Restart FVWM, or run this from FvwmConsole:

   Restart

Install Path

ConfigFvwmTabs defaults to:

   SetEnv FVWMTABS_DIR $[FVWM_USERDIR]/FvwmTabs

You may install FvwmTabs anywhere. If you do, edit ConfigFvwmTabs and set the
directory explicitly, for example:

   SetEnv FVWMTABS_DIR ~/.fvwm/FvwmTabs

or:

   SetEnv FVWMTABS_DIR /opt/FvwmTabs

Start and Restart

Start manually from FvwmConsole:

   Function FvwmTabsStart

Or start it from a shell:

   python3 ~/.fvwm/FvwmTabs/tabber_client.py start

To stop the server:

   python3 ~/.fvwm/FvwmTabs/tabber_client.py quit

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

The root-menu and tabber-dropdown Add Window(s) actions both use the server's
xdotool picker. The older Tabize/TabizeTo FVWM functions still use FVWM Pick.
In both cases the cursor appearance comes from FVWM, xdotool, and the X11
cursor theme; FvwmTabs does not reliably control whether it appears as + or [+].

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
to configured tabbers. The recommended rule type is autoSwallowClass because
the class field of WM_CLASS is usually the most stable application identity.

Example FvwmTabs.conf:

   theme=black
   debug=false
   autoSwallowOnStartup=false

   autoSwallowClass=firefox 1, thunderbird* 2, XTerm 3, Xfce4-terminal 3
   autoSwallowResource=xterm 3
   autoSwallowName=*Images* 2

Matching is case-insensitive and supports shell-style wildcards with *.

WM_CLASS has two strings:

- Resource/instance: first string, matched by autoSwallowResource
- Class: second string, matched by autoSwallowClass

autoSwallowName matches _NET_WM_NAME first, then WM_NAME.

Inspect Window Identity

To inspect a window before writing autoSwallow rules:

   xprop WM_CLASS WM_NAME _NET_WM_NAME

Then click the target window. WM_CLASS is printed as:

   WM_CLASS(STRING) = "resource", "class"

autoSwallowResource matches the first value. autoSwallowClass matches the
second value. Common examples include firefox/Firefox, Navigator/firefox,
thunderbird/Thunderbird, xterm/XTerm, xfce4-terminal/Xfce4-terminal, and
Alacritty/Alacritty.

Startup AutoSwallow

By default, newly created windows are considered. FvwmTabs also runs a one-time
500ms safety scan after the first tabber is created when autoSwallow rules are
configured, even when autoSwallowOnStartup is false. To also keep the broader
startup scan behavior enabled:

   autoSwallowOnStartup=true

Architecture Limitations

This v12-stable release intentionally keeps the non-native FVWM module design.
autoSwallow relies on polling _NET_CLIENT_LIST and _NET_CLIENT_LIST_STACKING
through X11 tools instead of receiving FVWM module packets directly. Extremely
short-lived windows may be missed between polling intervals. Windows whose
WM_CLASS or title appears only after the bounded retry window may not be
matched automatically.

Debug Logs

Logs are written to:

   ~/.fvwm/fvwmtabs.log

Important autoSwallow detection, match, no-match, skip, and route results are
logged at INFO level. Enable detailed retry and polling logs in FvwmTabs.conf:

   debug=true

To dump the current autoSwallow state to the log from FvwmConsole:

   Function DumpAutoSwallow

Reset Stale State

If the client reports that the server does not answer, stop FVWM or quit the
server, then remove stale socket state:

   rm -f ~/.fvwm/.fvwmtabs-*.sock ~/.fvwm/.fvwmtabs-*.pid

Key Bindings

ConfigFvwmTabs includes optional key bindings:

   Key T A CM Function NewTabber
   Key W A CM Function Tabize
   Key Right A CM Function NextTab
   Key Left A CM Function PrevTab
   Mouse 3 R A Menu TabbersMenu

Comment them out if they conflict with your existing FVWM configuration,
especially if you already use a right-click root menu.

Troubleshooting

- No tabber appears after login:
  Run Function FvwmTabsStart from FvwmConsole, then Function NewTabber.
  FvwmTabsStart starts the hidden server; NewTabber creates the visible tabber
  window.

- Commands do nothing:
  Check ~/.fvwm/fvwmtabs.log and verify that ConfigFvwmTabs points to the
  installed directory.

- autoSwallow does not match:
  Start the application, then inspect the logged resource/class/name values or
  run Function DumpAutoSwallow. Use the exact class value with
  autoSwallowClass where possible. Restart FvwmTabs after changing rules.

- xdotool, xprop, or xwininfo errors:
  Install the missing X11 utility package for your distribution. These tools
  are required by the current v12-stable architecture.

- Menus or dialogs are swallowed:
  This version skips detectable transient, menu, dialog, tooltip, splash, and
  override-redirect windows. Some applications expose unusual metadata; use
  debug logs to inspect them.
