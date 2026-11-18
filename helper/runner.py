"""One place that runs external commands, so the rest can be tested with a fake."""
import subprocess
import tempfile

# Commands that leave a background process holding the output pipes open (wl-copy serves the
# clipboard from one). Reading their output through pipes would wait for that process, and time out.
_DAEMONIZING = ("wl-copy",)


def _run_daemonizing(argv, timeout, input):
    with tempfile.TemporaryFile("w+") as err:
        p = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=err, text=True, timeout=timeout, input=input)
        err.seek(0)
        return p.returncode, "", err.read()


def run(argv, timeout=15, input=None):
    """Runs a command. Returns (returncode, stdout, stderr). 127 means not installed."""
    try:
        if argv and argv[0] in _DAEMONIZING:
            return _run_daemonizing(argv, timeout, input)
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, input=input)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", "not found: %s" % argv[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timed out: %s" % argv[0]
    except OSError as e:
        return 126, "", str(e)
