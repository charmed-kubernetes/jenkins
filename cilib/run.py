import subprocess
import click
import shlex
from types import SimpleNamespace


def _log_sub_out(pipe):
    """ Logs output from subprocess
    """
    for line in iter(pipe.readline, b""):
        click.echo(line.decode().strip())


def capture(script, **kwargs):
    """ capture command output
    """
    if not isinstance(script, list):
        script = shlex.split(script)
    process = subprocess.run(script, capture_output=True, **kwargs)
    return SimpleNamespace(
        ok=bool(process.returncode == 0),
        returncode=process.returncode,
        stdout=process.stdout,
        stderr=process.stderr,
    )


def cmd_ok(script, **kwargs):
    """ Stream command, doesnt buffer and prints it all out to stdout, only
    returns exit status
    """
    if not isinstance(script, list):
        script = shlex.split(script)
    process = subprocess.Popen(
        script, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs
    )

    with process.stdout:
        _log_sub_out(process.stdout)
    exitcode = process.wait()
    return SimpleNamespace(ok=bool(exitcode == 0), returncode=exitcode)
