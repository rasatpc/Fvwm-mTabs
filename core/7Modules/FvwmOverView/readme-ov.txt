# readme-ov.txt

To install or edit .fvwm/userExt.sys

## Add the below line below "Load 7.Modules".
Read $[CORE_DIR]/7Modules/FvwmOverView/Oview.sys

Test screen resolution:
xdpyinfo | awk '/dimensions:/{print $2}'

