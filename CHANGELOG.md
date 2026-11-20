# Changelog

## 0.4.5

Listing and documentation only; the plugin's code and behavior are unchanged from 0.4.4.

- **A new preview image.** `preview.png` is now a 1920x1080 poster with three real panels: the ready state in a dark theme, the masked secrets in a screenshot, and a light theme. They are the existing screenshots in `docs/screenshots/`, made with made-up data.
- **README first screen.** The pitch line matches the manifest description ("Send a screenshot to your AI agent."), and the longer sentence follows under it. The image alt text describes the new poster.

## 0.4.4

Two Low notes from the marketplace review of 0.4.3 (#15169).

- **Unmasked context files no longer wait for the next capture.** A context file that holds a value you chose to send unmasked (`*-context-open.md`, only for prompts too large for a command line) is now removed 10 minutes after the agent has started (a detached process does it, so it also happens when you capture nothing more). The expiry sweep runs on every helper call instead of only on capture and history, and its limit is 15 minutes instead of one hour, whatever the retention setting. If the agent does not start, the file stays so you can send again, and the sweep still removes it after 15 minutes.
- **The capture guard reads both Hyprland 0.56 and 0.57.** Hyprland 0.57 identifies a workspace by `address` instead of `id` (only numbered workspaces keep an `id`, and a special workspace has none). The guard now reads either layout, so a visible special workspace still blocks a capture on 0.57. When a monitor or a visible window is in a layout it does not recognise, nothing is captured (`visibility-unknown`), instead of treating the answer as "no special workspace". The 0.57 layout was checked against the Hyprland 0.57.2 sources; it has not been run on a machine with 0.57 installed.
- **A short description.** The manifest description, which the marketplace shows on the plugin card, is now one short sentence instead of three. The README still has the full story. The README's status line now says v0.4.

## 0.4.3

- **Capture guard looks at everything the screenshot would contain.** `grim` captures the composited rectangle, so a window capture used to be able to include a blocked window overlapping the focused one. The blocklist check now runs against every visible window that overlaps the captured rectangle, for window and region captures alike. Visible special-workspace (scratchpad) windows count too. If Hyprland cannot say which windows are visible, nothing is captured (new error `visibility-unknown`) instead of treating it as "no windows".
- **Send text only really is text only.** An edited context box could still carry the screenshot path the plugin had added before the edit. With the image switched off, the path and the image notes are now removed from the final text, wherever they appear in it.
- **History and context stay masked whatever you undo for sending.** Undoing a mask used to leave the unmasked value in the question stored in the history; the history now always stores the masked question. When a prompt is too large for the command line and a value you chose to send unmasked goes into the context file, that file is named `*-context-open.md` and is deleted after one hour (also when retention is off). Fully masked context files follow the retention setting as before.

## 0.4.2

- **Old cache files are scrubbed on upgrade.** `last.json` and the history state files written by 0.3.x to 0.4.0 still held the raw captured text, and were reopened unchanged until they expired (never, with retention off). They are now masked in place, atomically and mode 600, on the first access after the upgrade: on every capture, when the history is opened, and right before Send again reads them. Scrubbing is idempotent, so files that are already masked are left alone, and a file that is not valid JSON is not touched.

## 0.4.1

- **No raw text on disk.** `last.json` and the history state files used to hold the captured clipboard, terminal, notification and OCR text as it was, before masking, which the README said never happened. They are now written with every text masked. Consequences: **Send again** shows the masked text and a mask cannot be undone on a reopened entry; the warning about secrets in the screenshot is kept (`secret_kinds`).
- `last.json` is now removed by the retention cleanup too (it was never cleaned before).
- README: says plainly that screenshot files are saved as they are and kept for the retention period.

## 0.4.0

- **The prompt goes to the clipboard by default; passing it as an argument is now an opt-in.** Reported on the marketplace review of 0.3.0/0.3.1: an agent that takes its prompt as an argument keeps the text on its own command line for the whole session, readable by other local accounts. Agents are now started empty (Claude Code still in manual permission mode, or auto mode if you turned that on) and the prompt is on the clipboard with a toast. Amp keeps taking it on stdin.
- **New setting `prompt_as_argument`** (off by default, a toggle in the settings view). On gives the old behavior: the agent starts with the prompt in place. The preview shows a red warning while it is on, and a note on the default path tells you to paste.
- The same fallback is used for prompts too large for a command line; it now keeps Claude Code's explicit permission mode instead of starting it bare.

## 0.3.1

- **The prompt no longer goes on the command line of the terminal, the launcher or a wrapper.** It is written to a private file (mode 600 in `$XDG_RUNTIME_DIR`), read and deleted by a small `bash` wrapper right before the agent starts. Before, other local accounts could read the clipboard, terminal or notification text in the prompt through procfs while the launcher ran, and for Amp (stdin adapter) the whole session. The hand-over is done by `helper/start_agent.py`, a script and not a shell one-liner: a live test with Ghostty showed that the terminal launcher re-parses the command it is given, which breaks shell syntax. The old Amp wrapper in 0.3.0 had the same weakness. An agent that takes its prompt as an argument still has it on its own command line.

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
