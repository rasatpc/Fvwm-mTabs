Readme.txt

Functions can be used to achieve different tasks.

ComplexFunctions:
Complex functions.

FunctionContext:
In the context of the window in which they were run, but not always.

FunctionSynchronisation:
To ensure functions finish a command before running the next.

FunctionTips:
Ensuring commands are run in the correct context.

StartFunction:
As soon as Fvwm is done reading the config file. Similarly the ExitFunction is run when fvwm ends.
https://www.fvwm.org/Wiki/Config/Functions/

## Transparency

For transparency to work at a startup, this activates RootTransparent. Also, immediately when changing the wallpaper.

Test (x fvwm3-root) InfoStoreAdd VER "fvwm3-root -r"
Test (x fvwm-root) InfoStoreAdd VER "fvwm-root -r"
