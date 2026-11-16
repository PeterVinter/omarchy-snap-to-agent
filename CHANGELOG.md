# Changelog

## 0.2.0

- **Last terminal error.** A bash/zsh hook (installed only on request with `snap-to-agent install-hook`, removed with `uninstall-hook`) records the last failed command, exit code and directory. The output is read from tmux, or from the terminal window with OCR. Under 0.3 ms per prompt.
- **Notification picker** for the eight newest notifications in Omarchy's history.
- **Selection or clipboard**: the selected text, else the clipboard text, else a copied image.
- **OCR** of every image capture with tesseract, used as text context. If the picture seems to show secrets you are warned and can send the masked text only.
- **Blocklist** of window classes and title patterns that are never captured (password managers, banking, private browsing by default). Also guards clipboard and notification captures.
- **Configuration file** `~/.config/snap-to-agent/config.json` (OCR on/off, image limits, default questions, blocklist).
- New IPC commands `capture error|notification|clipboard`; `snap-to-agent` command line.

## 0.1.0

First version.

- Region and active-window capture, scaled to 1920 px and under 2 MB.
- Context: window, workspace, monitor, directory and git branch for terminals, recent log lines, Omarchy version.
- Adapters for all 24 agents Omarchy 4.5 lists, plus a generic fallback. Agents always start in ask-before-acting mode.
- The default agent is read at send time.
- Preview panel with the target agent and directory, editable context and question, and secret masking with per-secret undo.
- Follows the active Omarchy theme live.
- IPC commands `capture`, `captureRegion`, `resend`, `toggle`, `state`.
