"""Starts an agent with a prompt that was handed over in a private file.

usage: start_agent.py (--arg | --stdin) PROMPT_FILE COMMAND [ARGS...]

The prompt must not appear on the command line of the terminal, the launcher or this wrapper
(other local accounts can read process arguments), so launch.py writes it to a file with mode 600
and passes only the file's name. This script reads the file, deletes it, and then
  --arg    replaces PROMPT_MARKER in the arguments with the text and runs the command, or
  --stdin  runs the command with the text and a newline as its standard input.

It is a script and not a shell one-liner on purpose: terminal launchers re-parse the command
they are given, which breaks shell syntax such as ${x%%y} and "${a[@]}".
"""
import os
import sys

MARKER = "@@SNAP_TO_AGENT_PROMPT@@"


def main(argv):
    if len(argv) < 3 or argv[0] not in ("--arg", "--stdin"):
        sys.stderr.write("usage: start_agent.py (--arg | --stdin) PROMPT_FILE COMMAND [ARGS...]\n")
        return 2
    mode, path, command = argv[0], argv[1], argv[2:]
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write("snap-to-agent: cannot read the prompt: %s\n" % e)
        return 1
    try:
        os.unlink(path)
    except OSError:
        pass
    try:
        if mode == "--arg":
            command = [c.replace(MARKER, text) if MARKER in c else c for c in command]
        else:
            r, w = os.pipe()
            data = (text + "\n").encode("utf-8")
            if len(data) <= 60_000:  # fits the pipe buffer: no helper process needed
                os.write(w, data)
                os.close(w)
            else:
                if os.fork() == 0:
                    os.close(r)
                    with os.fdopen(w, "wb") as out:
                        out.write(data)
                    os._exit(0)
                os.close(w)
            os.dup2(r, 0)
            os.close(r)
        os.execvp(command[0], command)
    except OSError as e:
        sys.stderr.write("snap-to-agent: cannot start %s: %s\n" % (command[0], e))
        return 127


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
