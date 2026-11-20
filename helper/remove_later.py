"""Removes one unmasked context file after a delay.

usage: remove_later.py SECONDS PATH

Started detached by history.remove_open_file_later once the agent is running. It only removes a
`*-context-open.md` file inside the plugin's cache folder (history.remove_open_file checks).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history  # noqa: E402


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: remove_later.py SECONDS PATH\n")
        return 2
    try:
        delay = max(0, min(int(argv[0]), 3600))
    except ValueError:
        return 2
    time.sleep(delay)
    history.remove_open_file(argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
