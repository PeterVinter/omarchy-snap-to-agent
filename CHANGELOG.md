# Changelog

## 0.3.1

- **The prompt no longer goes on the command line of the terminal, the launcher or a wrapper.** It is written to a private file (mode 600 in `$XDG_RUNTIME_DIR`), read and deleted by a small `bash` wrapper right before the agent starts. Before, other local accounts could read the clipboard, terminal or notification text in the prompt through procfs while the launcher ran, and for Amp (stdin adapter) the whole session. An agent that takes its prompt as an argument still has it on its own command line.

## 0.3.0

First public release. It contains everything from 0.1 and 0.2 below, plus:

- **History** of the last 20 sends with thumbnail, agent, folder, time and question. Send again (opens the preview, never sends by itself) and delete. Right-click on the bar icon, or `history` over IPC.
- **Settings view** in the panel: OCR, whether agents may act without asking, retention, image limits, default question per mode, blocklist and the terminal-error hook (with a confirmation). Saved to `~/.config/snap-to-agent/config.json`. Long sections fold and the lists scroll inside the panel.
- **Optional auto mode** (`agent_auto`, off by default): agents are started the way Omarchy's own launcher does, with their auto-approve option where one is known. The preview warns in red while it is on. With it off, Claude Code is started in manual mode, because a fresh install of 2.1.325 started in auto mode.
- **Region capture uses `omasnap`**, Omarchy's own selector, with `slurp` as the fallback (`region_tool` in the settings file). `slurp` 1.5.0 drew nothing on Hyprland 0.56, so the first design never started. Tested with a real mouse drag.
- **Automatic cleanup**: captures, context files and history entries older than the retention period (7 days by default) are removed.
- **Languages**: the panel follows Setup > Language. English and Swedish are included; missing strings fall back to English. A test checks that every language has every key, matching placeholders and text for every error code.
- Default questions are translated in the panel; a question from the settings file is used as written.
- Plural forms for the number of masked secrets.
- IPC commands `history` and `settings`.
- The context box is taller and shows a scroll bar; the settings page shows the real state of the terminal-error hook.

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
