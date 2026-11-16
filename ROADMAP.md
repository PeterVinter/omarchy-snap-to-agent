# Roadmap

## Next, and first: exact terminal output in every common terminal

Today only **tmux** gives the plugin the exact text of a failed command. In any other terminal it captures the window and reads it with OCR, which makes mistakes (a `ls:` can come out as `1s:`). Omarchy 4.5 ships foot (the default), alacritty, kitty and ghostty, and people switch between them, so this has to work whichever one is the default, or the README has to say plainly what to do.

| Terminal | Today | Plan |
|---|---|---|
| tmux (inside any terminal) | exact text (`tmux capture-pane`) | keep |
| kitty | OCR | `kitten @ get-text` over Omarchy's own socket; no configuration expected |
| ghostty | OCR | a keybind for `write_screen_file` / `write_scrollback_file`, which the plugin presses and reads back |
| foot | OCR | a `pipe-visible` / `pipe-scrollback` key binding that writes the screen to a file, same idea |
| alacritty | OCR | no way to read its screen; use tmux, the wrapper below, or OCR |
| any terminal | OCR | `snap-to-agent run <command>`: runs a command in a pty, keeps its last output (200 lines, 64 KB) and records failures like the hook; needs no configuration |

Steps, in order:

1. Document in the README what each terminal gives today and what the user can do (the table above, as it really behaves).
2. Build `snap-to-agent run`, since it works everywhere.
3. Build one adapter per terminal, each with a `snap-to-agent terminal-setup` step that shows the one configuration line it needs and asks before writing it (like the hook does).
4. Choose the best source at capture time: tmux, then the terminal's own adapter, then the last `run` output, then OCR.
5. Test in every terminal by switching the default with `omarchy default terminal <name>` and switching back afterwards. foot and ghostty are installed here; kitty and alacritty have to be installed first.

## Later

- Tested image flags per agent, so images can go as images instead of a file path, and a real test that agents read the screenshot.
- An option to always start in `~` instead of `~/Work`.
- Highlight masked placeholders inside the context text.
- Keybindings written into `bindings.lua` with the user's consent.
- More languages. Copy `i18n/en.json` and translate.
