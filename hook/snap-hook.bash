# Omarchy Snap to Agent: remembers the last FAILED command (command, exit code, directory).
#
# Installed only with your consent:  snap-to-agent install-hook
# Removed completely with:           snap-to-agent uninstall-hook
#
# Cost: one comparison per prompt. Only a failed command writes a small file, with bash
# builtins only (no subprocess). The command's output is not stored here: the plugin reads
# it from tmux when you ask for the last error.
[[ $- == *i* ]] || return 0
[[ -n ${__SNAP_HOOK_LOADED:-} ]] && return 0
__SNAP_HOOK_LOADED=1
__snap_dir="${XDG_STATE_HOME:-$HOME/.local/state}/snap-to-agent"

__snap_precmd() {
  local rc=$?
  # 130 is Ctrl+C: not an error worth sending.
  (( rc == 0 || rc == 130 )) && return $rc
  local cmd
  cmd=$(HISTTIMEFORMAT= builtin history 1) || return $rc
  cmd=${cmd#"${cmd%%[![:space:]]*}"}   # trim leading spaces
  cmd=${cmd#*[[:space:]]}              # drop the history number
  cmd=${cmd#"${cmd%%[![:space:]]*}"}
  [[ -d $__snap_dir ]] || mkdir -p -m 700 "$__snap_dir"
  local now
  printf -v now '%(%s)T' -1
  # Header lines, then the command (everything after the fifth line).
  printf 'v1\nrc=%s\ntime=%s\ncwd=%s\npane=%s\n%s\n' "$rc" "$now" "$PWD" "${TMUX_PANE:-}" "$cmd" \
    > "$__snap_dir/last-error.txt" 2>/dev/null
  return $rc
}

# Run before everything else so $? is still the command's.
if [[ $(declare -p PROMPT_COMMAND 2>/dev/null) == "declare -a"* ]]; then
  PROMPT_COMMAND=(__snap_precmd "${PROMPT_COMMAND[@]}")
else
  PROMPT_COMMAND="__snap_precmd${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
fi
