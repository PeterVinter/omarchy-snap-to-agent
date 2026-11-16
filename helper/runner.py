"""One place that runs external commands, so the rest can be tested with a fake."""
import subprocess


def run(argv, timeout=15, input=None):
    """Runs a command. Returns (returncode, stdout, stderr). 127 means not installed."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, input=input)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", "not found: %s" % argv[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timed out: %s" % argv[0]
    except OSError as e:
        return 126, "", str(e)
