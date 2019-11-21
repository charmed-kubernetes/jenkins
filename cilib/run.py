import subprocess
import click
import shlex
from types import SimpleNamespace


def _log_sub_out(pipe):
    """ Logs output from subprocess
    """
    for line in iter(pipe.readline, b""):
        click.echo(line.decode().strip())


def cmd(script, **kwargs):
    script = shlex.split(script)
    process = subprocess.Popen(
        script,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **kwargs
    )

    with process.stdout:
        _log_sub_out(process.stdout)
    exitcode = process.wait()
    return SimpleNamespace(ok=bool(exitcode == 0), exitcode=exitcode)
