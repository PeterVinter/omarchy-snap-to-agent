# Roadmap

## v0.2

- **Last terminal error.** A small bash/zsh hook (`preexec`/`precmd`) records the command, exit code and directory of failed commands only (capped, under 5 ms per prompt, installed only with consent, `snap-to-agent uninstall-hook` removes it). The output comes from the terminal: `tmux capture-pane` in tmux, `kitten @ get-text` in kitty. Terminals without a scrollback API (foot, ghostty) fall back to the command, exit code and an OCR of the window.
- **Last notification** from Omarchy's history, and **selection/clipboard** (`wl-paste -p`, `wl-paste`).
- **OCR** with tesseract for every image capture, and secret detection in the image with a "send text only (masked)" option.
- **Blocklist** of app classes and title patterns that can never be captured.

## v0.3

- History of the last 20 sends with send again and delete, auto-delete of captures after 7 days.
- Settings view and `~/.config/snap-to-agent/config.json`.
- More languages (follows Setup > Language already; only English is shipped).
- Bar menu on click, history and settings on right-click.

## Later

- Tested image flags per agent.
- An option to always start in `~` instead of `~/Work`.
