readme.txt

FvwmTabs user configuration is located in .fvwm/user/Tab/FvwmTabs.conf. On new install, .fvwm/tab-module/FvwmTabs.conf is moved to .fvwm/user/Tab and replaced with a symlink. Existing FvwmTabs.conf will not change.

The FvwmTabs module is capable of swallowing any Fvwm window & treating it as a tab in a tab-manager window. A tab-manager is sometimes called a tabber.

FvwmTabs is invoked by inserting the line "Module FvwmTabs" (check .fvwm/config).

Create a new tabber. The optional argument is the tabber name. No whitespace is allowed in the tabber name. Can also prefix --geometry argument.
Example: NewTabber --geometry=175x70 scottie

Specify windows to swallow automatically. These are comma-separated lists that specify the class/resource/name of a window & an optional tab-manager ID into which the window should be swallowed.

## Example:
autoSwallowClass=Chromium 0, firefox 0, thunderbird* 1
autoSwallowName=
autoSwallowResource=evolution 1, google-chrome 0

## More information, read manpage: .fvwm/tab-module/FvwmTabs.html
