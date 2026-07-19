# Fvwm-mTabs
Fvwm-mTabs is a simplified version of KISe and myExt that uses FvwmTabs (a Python/Tk rewrite of the old Perl FVWM tabbing module). It keeps the socket/Tk design, multiple tabbers, assigned tabber IDs, a right-click menu, and autoSwallow behavior.

FVWM functions talk to FvwmTabs through the standard FvwmMFL module, and the FvwmMFL socket client is built into FvwmTabs itself.

# Main features:
* Desk Icons include:
	Iconified Thumbnails, Full-Screen Maximize, Windows Overview,
	Tiling and Tabs with FvwmMFL socket.

* Tab managers:
	Store any number of windows, each in its own tab.
	AutoSwallow automatically moves applications to a specific tab
	when they create windows. A powerful feature when combined
	with AutoMoveWindows, which moves apps and tabs to a specific
	desk/page.

* Icon/Application Panel.
* Pager/Task Panel.
* XDG menu.
* Day/Time Panel.
* 4-button Window Title Bar.
* Auto Move Windows and FvwmTabs.
* Page Indicator.

Tested on Fvwm3 and Fvwm2

# HOW TO INSTALL

Download:

* Version 2.0.1
* https://github.com/rasatpc/Fvwm-mTabs/archive/refs/heads/main.zip

Extract and copy subfolders to ~/.fvwm

When Fvwm is loaded for the first time, .fvwm/config creates a subsystem file (userExt.sys) that reads the scripts and runs the system.

* Requirements & dependencies read setup/INSTALL.md
