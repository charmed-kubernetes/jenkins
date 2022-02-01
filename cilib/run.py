import subprocess
import click
import shlex
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace


def make_executable(path):
    mode = os.stat(str(path)).st_mode
    mode |= (mode & 0o444) >> 2
    os.chmod(str(path), mode)


def _log_sub_out(pipe, echo):
    """Logs output from subprocess"""
    for line in iter(pipe.readline, b""):
        echo(line.decode().strip())


def script(script_data, **kwargs):
    is_single_command = len(script_data.splitlines()) == 1
    env = os.environ.copy()
    if "charm" in kwargs:
        env["CHARM"] = kwargs.pop("charm")
    if "namespace" in kwargs:
        env["NAMESPACE"] = kwargs.pop("namespace")
    echo = kwargs.pop("echo", click.echo)
    tmp_script_path = None
    if is_single_command:
        process = subprocess.Popen(
            script_data.strip(),
            shell=True,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
    else:
        if not script_data[:2] != "#!":
            script_data = "#!/bin/bash\n" + script_data
        tmp_script = tempfile.mkstemp()
        tmp_script_path = Path(tmp_script[-1])
        tmp_script_path.write_text(script_data, encoding="utf8")
        make_executable(tmp_script_path)
        os.close(tmp_script[0])
        process = subprocess.Popen(
            ["bash", str(tmp_script_path)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
    with process.stdout:
        _log_sub_out(process.stdout, echo)
    exitcode = process.wait()
    if tmp_script_path:
        subprocess.run(["rm", "-rf", str(tmp_script_path)])
    return SimpleNamespace(
        ok=bool(exitcode == 0), returncode=exitcode, stderr=process.stderr
    )


def capture(script, **kwargs):
    """capture command output"""
    env = os.environ.copy()
    if not isinstance(script, list) and "shell" not in kwargs:
        script = shlex.split(script)
    process = subprocess.run(
        script, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, **kwargs
    )
    return SimpleNamespace(
        ok=bool(process.returncode == 0),
        returncode=process.returncode,
        stdout=process.stdout,
        stderr=process.stderr,
    )


def cmd_ok(script, **kwargs):
    """Stream command, doesnt buffer and prints it all out to stdout, only
    returns exit status
    """
    env = os.environ.copy()
    check = None
    if "check" in kwargs:
        check = kwargs["check"]
        del kwargs["check"]
    echo = kwargs.pop("echo", click.echo)
    if not isinstance(script, list) and "shell" not in kwargs:
        script = shlex.split(script)
    try:
        process = subprocess.Popen(
            script, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, **kwargs
        )
    except Exception as error:
        echo(f"Error: Failed to run {script}: {error}")
        raise subprocess.CalledProcessError(1, "", "")

    with process.stdout:
        _log_sub_out(process.stdout, echo)
    exitcode = process.wait()
    if check and exitcode > 0:
        raise subprocess.CalledProcessError(exitcode, "", "")
    return SimpleNamespace(ok=bool(exitcode == 0), returncode=exitcode)
