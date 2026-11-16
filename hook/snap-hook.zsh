# Omarchy Snap to Agent: remembers the last FAILED command (command, exit code, directory).
# Installed only with your consent:  snap-to-agent install-hook
# Removed completely with:           snap-to-agent uninstall-hook
[[ -o interactive ]] || return 0
[[ -n ${__SNAP_HOOK_LOADED:-} ]] && return 0
typeset -g __SNAP_HOOK_LOADED=1
zmodload zsh/datetime 2>/dev/null
typeset -g __snap_dir="${XDG_STATE_HOME:-$HOME/.local/state}/snap-to-agent"

__snap_precmd() {
  local rc=$?
  (( rc == 0 || rc == 130 )) && return $rc
  local cmd="${history[$((HISTCMD-1))]}"
  [[ -d $__snap_dir ]] || mkdir -p -m 700 "$__snap_dir"
  print -r -- "v1
rc=$rc
time=$EPOCHSECONDS
cwd=$PWD
pane=${TMUX_PANE:-}
$cmd" > "$__snap_dir/last-error.txt" 2>/dev/null
  return $rc
}

# First in the list, so $? is still the command's.
precmd_functions=(__snap_precmd $precmd_functions)
