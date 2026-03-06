#!/bin/sh

## Copy to new location
# userExtSAMPLE.sys
# TMenu
# SimpleButton to core/user
# autoMoveW.sys to core/user
#
## Check for FvwmTabs.conf.
# If it exist and create symlink.
##

cd $HOME/.fvwm

## Check if userExt.sys does not exist.

FILEu=userExt.sys
if [ ! -f "$FILEu" ]; then
    cp setup/userExtSAMPLE.sys userExt.sys
    rm userExtSAMPLE.sys
fi

## Check if TMenu does not exist in core/user.

cd $HOME/.fvwm/user/TMenu
FILEm=tMenu.sys
if [ ! -f "$FILEm" ]; then
    cp -r $HOME/.fvwm/core/4Menus/TMenu $HOME/.fvwm/user/
fi

## Check if SimpleButton does not exist in core/user.

cd $HOME/.fvwm/user/SimpleButton
FILEs=simpleB.sys
if [ ! -f "$FILEs" ]; then
    cp -r $HOME/.fvwm/core/7Modules/SimpleButton $HOME/.fvwm/user/
fi

## Check if Auto Move Windows does not exist in core/user.

cd $HOME/.fvwm/user
FILEa=autoMoveW.sys
if [ ! -f "$FILEa" ]; then
    cp -r $HOME/.fvwm/core/1Functions/autoMoveW.sys $HOME/.fvwm/user/
fi

## Check if FvwmTabs.conf does not exist in .fvwm/user/Backup/.
## Create FvwmTabs.conf symlink does in .fvwm/tab-module/.

cd $HOME/.fvwm/user/Backup
FILEt=FvwmTabs.conf
if [ ! -f "$FILEt" ]; then
	cp -r $HOME/.fvwm/tab-module/FvwmTabs.conf $HOME/.fvwm/user/Backup/
	cd $HOME/.fvwm/tab-module/
	rm FvwmTabs.conf
	ln -s $HOME/.fvwm/user/Backup/FvwmTabs.conf FvwmTabs.conf
fi
