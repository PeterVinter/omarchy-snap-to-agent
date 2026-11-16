<div align="center">

# Omarchy Snap to Agent

**Send what is on your screen to your default AI agent, with the context it needs to help right away.**

Capture a region, a window, your last terminal error, a notification or the clipboard, check the preview, press Enter. Your agent opens in the right folder with the screenshot or text, the app and window title and, for a terminal, its folder and git branch already attached. No copying, no pasting, no explaining.

<img src="preview.png" alt="The Snap to Agent panel in a dark and a light Omarchy theme: thumbnail, target agent and folder, question, masked secrets and context" width="900">

</div>

## Why you will want it

- **It uses the agent you already chose.** It reads Omarchy's default agent every time you send, so changing it in Setup takes effect at once. Claude Code, Codex, Grok, OpenCode and all the others Omarchy lists have an adapter; anything new falls back gracefully.
- **It asks before it acts.** The agent starts in its normal ask-first mode. Omarchy's own launcher adds auto-approve flags to most agents; this plugin never does.
- **You see everything before it leaves.** The preview shows who gets it and in which folder. Likely secrets (API keys, tokens, passwords, private keys) are masked first, and you can undo each mask with one click. If a screenshot itself seems to show secrets, you are warned and can send the masked text only.
- **Some windows are never captured.** Password managers, banking and private browser windows are on a blocklist you can edit.
- **It looks like Omarchy.** Colours, fonts, corners and spacing come from your theme, and switching theme updates the panel live.

## In your theme

| Tokyo Night | Catppuccin Latte | Ristretto |
|---|---|---|
| ![Tokyo Night](docs/screenshots/01-ready-tokyo-night.png) | ![Catppuccin Latte](docs/screenshots/02-ready-catppuccin-latte.png) | ![Ristretto](docs/screenshots/03-ready-ristretto.png) |

## Install

```bash
omarchy plugin add https://github.com/PeterVinter/omarchy-snap-to-agent.git --yes
omarchy plugin enable io.github.petervinter.snap-to-agent --section right
```

Then bind a key (see [Suggested keybindings](#suggested-keybindings)) and it is one keystroke from anywhere. Requires Omarchy 4.x; everything else it needs ships with Omarchy. No sudo.

> **Status: v0.2.** Five capture modes, OCR, a blocklist and the optional shell hook. History, a settings view and more languages are planned for v0.3, see [ROADMAP.md](ROADMAP.md).

## What it does

1. You capture a region or the active window.
2. A panel shows a thumbnail, **who gets it and where** ("Sending to: Claude Code in ~/Work"), a question field with a sensible default, and the context block, which you can edit.
3. Likely secrets are masked before you see the text. Click a mask to send that one unmasked.
4. **Send** (Enter) starts your default agent in its own terminal window, in the right directory, with the prompt. **Copy** (Ctrl+Enter) only copies the text. Nothing is sent until you confirm.

Context attached automatically: app class and window title, workspace and monitor, working directory and git branch (for terminals), recent log lines of the window's process, Omarchy version and time. The screenshot is stored in `~/.cache/snap-to-agent/`, scaled to at most 1920 px on the long side and under 2 MB.

## Agent safety

Agents are always started in their normal, **ask-before-acting** mode. Omarchy's own `omarchy-agent` adds auto-approve flags to most agents; this plugin deliberately does not. A test fails if any adapter ever emits one.

## Install

```bash
omarchy plugin add https://github.com/PeterVinter/omarchy-snap-to-agent.git --yes
omarchy plugin enable io.github.petervinter.snap-to-agent --section right
```

Requires Omarchy 4.x, Python 3, `grim`, `slurp`, `wl-clipboard` and ImageMagick (`magick`), which Omarchy ships. `tesseract` is optional (OCR), `tmux` is optional (terminal output). No sudo.

## Remove

```bash
omarchy plugin remove io.github.petervinter.snap-to-agent
rm -rf ~/.cache/snap-to-agent
```

The plugin writes nothing else: captures and `last.json` in `~/.cache/snap-to-agent/`. It makes no network calls of its own; only the agent you choose does.

## Capture modes

| Mode | Command | What the agent gets |
|---|---|---|
| Region | `capture region` | A screenshot of the area you drag, plus the window under it |
| Window | `capture window` | A screenshot of the focused window |
| Last terminal error | `capture error` | The failed command, its exit code, directory and output (see below) |
| Notification | `capture notification` | A notification you pick from the latest eight |
| Selection or clipboard | `capture clipboard` | The selected text, else the clipboard text, else a copied image |

Every command is `omarchy-shell io.github.petervinter.snap-to-agent <command>`.

### Last terminal error

A failed command's output cannot be fetched afterwards without getting in the terminal's way, so the plugin uses two cheap parts:

1. **A small shell hook** (optional, installed only if you ask) remembers the last *failed* command, its exit code and its directory. It costs one comparison per prompt, and under 0.3 ms when a command fails; measured in bash and zsh.
2. **The output comes from the terminal.** In tmux it is read with `tmux capture-pane` (capped at 200 lines and 64 KB). Anywhere else (the plugin has no way to read the scrollback of foot or ghostty) it captures the terminal window and reads it with OCR.

```bash
snap-to-agent install-hook      # asks first; adds a marked block to ~/.bashrc (and ~/.zshrc if it exists)
snap-to-agent uninstall-hook    # removes the block and the recorded file
snap-to-agent hook-status
```

`snap-to-agent` is in the plugin folder (`~/.config/omarchy/plugins/io.github.petervinter.snap-to-agent/snap-to-agent`); link it into your `PATH` if you like. The hook records the last failure from any shell that loaded it. Ctrl+C is not counted as an error.

![No failed command recorded](docs/screenshots/05-no-error-recorded.png)

### Secrets in the screenshot

Every image capture is read with `tesseract`. If the text in the picture looks like a key, token or password, the preview warns you and offers **Send text only (masked)**: the image stays on your machine and the agent gets the masked text. Without `tesseract` everything still works, you are just told that no text was read.

![Warning about secrets in a screenshot](docs/screenshots/04-secrets-in-the-image.png)

### Blocklist and configuration

The plugin refuses to capture a window whose class or title matches the blocklist, including when it is only partly under your region, and it refuses clipboard and notification captures while such a window has focus. Matching is a case-insensitive substring; a website is only recognised when its name is in the window title.

Settings live in `~/.config/snap-to-agent/config.json` (see [config.example.json](config.example.json)): `ocr`, `image` limits, per-mode default `questions`, and the `blocklist` lists. A missing or broken file means the defaults. The settings view comes in v0.3.

## Use

Click the bar icon for the capture menu, or call the commands below from a keybinding.

| Command | What it does |
|---|---|
| `omarchy-shell io.github.petervinter.snap-to-agent capture region` | Select a region with the mouse |
| `omarchy-shell io.github.petervinter.snap-to-agent capture window` | Capture the active window |
| `omarchy-shell io.github.petervinter.snap-to-agent capture error` | Send the last failed terminal command |
| `omarchy-shell io.github.petervinter.snap-to-agent capture notification` | Pick a recent notification |
| `omarchy-shell io.github.petervinter.snap-to-agent capture clipboard` | Send the selection or clipboard |
| `omarchy-shell io.github.petervinter.snap-to-agent captureRegion "x,y WxH"` | A fixed area, for scripts |
| `omarchy-shell io.github.petervinter.snap-to-agent resend` | Open the last capture again |
| `omarchy-shell io.github.petervinter.snap-to-agent toggle` | Open or close the panel |
| `omarchy-shell io.github.petervinter.snap-to-agent state` | Current state as JSON |

Keys in the panel: **Enter** sends, **Ctrl+Enter** copies, **Esc** cancels, **Tab** moves to the context section (Enter opens it).

### Suggested keybindings

Add to `~/.config/hypr/bindings.lua`. `SUPER + ALT + S` is taken by Omarchy ("Move window to scratchpad"), so region uses `A` for agent. W, E, N and C are free in a default Omarchy 4.5 and in `~/.config/hypr/bindings.lua` of the tested setup.

```lua
o.bind("SUPER + ALT + A", "Snap to agent (region)", "omarchy-shell io.github.petervinter.snap-to-agent capture region")
o.bind("SUPER + ALT + W", "Snap to agent (window)", "omarchy-shell io.github.petervinter.snap-to-agent capture window")
o.bind("SUPER + ALT + E", "Snap to agent (last terminal error)", "omarchy-shell io.github.petervinter.snap-to-agent capture error")
o.bind("SUPER + ALT + N", "Snap to agent (notification)", "omarchy-shell io.github.petervinter.snap-to-agent capture notification")
o.bind("SUPER + ALT + C", "Snap to agent (selection or clipboard)", "omarchy-shell io.github.petervinter.snap-to-agent capture clipboard")
```

## Supported agents

All 24 agents that `omarchy-default-agent` lists in Omarchy 4.5 have an adapter. An agent not in this table, for example one added in a newer Omarchy, gets the **generic fallback**: it starts the way Omarchy starts it, the prompt goes to the clipboard, and a toast tells you to paste.

Images: no agent has a tested image flag yet, so every agent gets the screenshot as a **file path** in the prompt (and, from v0.2, the OCR text). The preview says so. A flag will be added per agent only after it has been tested.

| Agent | Name | How the prompt reaches it | Image |
|---|---|---|---|
| Amp | `amp` | Prompt typed in as first message | Path in prompt |
| Antigravity | `agy` | Prompt on the command line | Path in prompt |
| Claude Code | `claude` | Prompt on the command line | Path in prompt |
| Codex | `codex` | Prompt on the command line | Path in prompt |
| Command Code | `commandcode` | Prompt on the command line | Path in prompt |
| Crush | `crush` | Starts empty, prompt on the clipboard | Path in prompt |
| Cursor CLI | `cursor-agent` | Prompt on the command line | Path in prompt |
| DeepSeek Harness | `dsh` | Starts empty, prompt on the clipboard | Path in prompt |
| Devin CLI | `devin` | Prompt on the command line | Path in prompt |
| Freebuff | `freebuff` | Starts empty, prompt on the clipboard | Path in prompt |
| GitHub Copilot | `copilot` | Prompt on the command line | Path in prompt |
| Grok | `grok` | Prompt on the command line | Path in prompt |
| Hermes | `hermes` | Prompt on the command line | Path in prompt |
| Kilo | `kilo` | Prompt on the command line | Path in prompt |
| Kimi | `kimi` | Starts empty, prompt on the clipboard | Path in prompt |
| Kiro CLI | `kiro-cli` | Prompt on the command line | Path in prompt |
| MiniMax Code | `mcode` | Prompt on the command line | Path in prompt |
| Muse Code | `muse` | Prompt on the command line | Path in prompt |
| Oh My Pi | `omp` | Prompt on the command line | Path in prompt |
| OpenClaw | `openclaw` | Prompt on the command line | Path in prompt |
| OpenCode | `opencode` | Prompt on the command line | Path in prompt |
| Ori | `ori` | Prompt on the command line | Path in prompt |
| Pi | `pi` | Prompt on the command line | Path in prompt |
| Qwen Code | `qwen` | Prompt on the command line | Path in prompt |

## Where the agent starts

In the terminal's directory when the capture comes from a terminal. Otherwise in `~/Work` if it exists, else `~`: agents do not remember folder trust for `$HOME` and would ask on every start (the same rule as `omarchy-agent`).

## Privacy

- Nothing is sent without the preview and your confirmation.
- Text is masked for private keys, JWTs, AWS, GitHub, Anthropic, OpenAI, Slack, Google and Stripe keys, Bearer tokens, URL passwords and `password=`/`token=`-style assignments. Masking is pattern based and not a guarantee: read the preview.
- The originals of masked values never leave the helper process and are never written to disk.
- If the prompt is long, the context goes to a file in the cache and the agent is told to read it.

## Development

```bash
for t in tests/test_*.py; do python3 -I "$t"; done
/usr/lib/qt6/bin/qmllint -I /usr/share/omarchy/shell Panel.qml
```

All capture, context, masking and agent logic is in `helper/` (standard library only) and can be run without the shell. `Panel.qml` only draws.

MIT licensed.
