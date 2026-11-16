# Changelog

## 0.1.0

First version.

- Region and active-window capture, scaled to 1920 px and under 2 MB.
- Context: window, workspace, monitor, directory and git branch for terminals, recent log lines, Omarchy version.
- Adapters for all 24 agents Omarchy 4.5 lists, plus a generic fallback. Agents always start in ask-before-acting mode.
- The default agent is read at send time.
- Preview panel with the target agent and directory, editable context and question, and secret masking with per-secret undo.
- Follows the active Omarchy theme live.
- IPC commands `capture`, `captureRegion`, `resend`, `toggle`, `state`.
