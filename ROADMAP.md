# Roadmap

## Next (0.4.4)

Two Low notes from the marketplace review of 0.4.3 (#15169). Neither blocked listing.

- Delete a `*-context-open.md` file (a context file holding values the user chose to send unmasked) right after the agent has started, and run the expiry cleanup on every helper call, so such a file never outlives its hour waiting for the next capture.
- Make the special-workspace detection work with both the Hyprland 0.56 and 0.57 monitor formats, and stop the capture when the format is not recognised. Test against 0.57.2.

## Later

- Tested image flags per agent, so images can go as images instead of a file path.
- Reading terminal output in kitty (`kitten @ get-text`).
- An option to always start in `~` instead of `~/Work`.
- Highlight masked placeholders inside the context text.
- More languages. Copy `i18n/en.json` and translate.
