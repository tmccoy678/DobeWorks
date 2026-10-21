#!/bin/zsh
set -u
root="${0:A:h}"
support="$root/interface"
cd "$root"
if [[ "$OSTYPE" == darwin* && -t 1 ]]; then
  /usr/bin/osascript "$support/set_workbench_font.applescript" "$(/usr/bin/tty)" >/dev/null 2>&1 || true
fi
clear
PYTHONDONTWRITEBYTECODE=1 /usr/bin/env python3 -B "$support/command_center.py" "$@" menu
workbench_exit=$?
echo
if [[ -t 0 ]]; then
  read -k 1 "?PRESS ANY KEY TO CLOSE THE INTERFACE."
fi
echo
exit "$workbench_exit"
