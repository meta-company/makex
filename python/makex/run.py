import atexit
import os
import selectors
import signal
import subprocess
import sys
from collections import deque
from io import StringIO
from pathlib import Path
from threading import local

from makex.protocols import CommandOutput

CORRECTED_RETURN_CODE = object()

_QUEUE = deque()


def get_running_process_ids():
    return _QUEUE


def is_exe(path):
    return path.is_file() and os.access(path, os.X_OK)


def check_exec(path):
    if is_exe(path) is False:
        raise Exception(f"Command is not executable: {path}. Fix this with chmod +x {path}")


_thread_local = local()


def _kill_sub():
    process = getattr(_thread_local, "process", None)
    if process:
        print(f"Killing process {process.pid}")

        os.killpg(os.getpgid(process.pid), signal.SIGKILL)


atexit.register(_kill_sub)


def run(
    command: list[str],
    env: dict[str, str],
    capture: bool = False,
    shell: bool = False,
    cwd: Path = None,
    print=True,
    stdin=None,
    stdin_data: bytes = None,
    color_error: str = None,
    color_escape: str = None,
):
    """
    runs a command

    always outputs stdout and stderr to console.

    :param command: command to run. can be a string or list of strings.
    :param env: environment variables to use.
    :param capture: True to capture a copy of stdout/stderr
    :param shell: use shell option for Popen
    :param cwd: Path to change to before running
    :return:
    """

    #check_exec(Path(command[0]))

    with subprocess.Popen(
        command,
        stdin=stdin or subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        shell=shell,
        text=True if shell else False,
        cwd=cwd,
        # set session id to parent of child process.
        # make it a leader so signals sent to it, will pass to children.
        preexec_fn=os.setsid,
    ) as p:
        _thread_local.process = p
        _QUEUE.append(p.pid)
        sel = selectors.DefaultSelector()
        sel.register(p.stdout, selectors.EVENT_READ)
        sel.register(p.stderr, selectors.EVENT_READ)

        if stdin_data:
            p.stdin.write(stdin_data)
            #out, err = p.communicate(stdin.getvalue().encode("utf-8"))
            #print("Communicate")
        if capture:
            outputs = StringIO()
            errors = StringIO()
            for output, error in tail_out(sel, p, enable_output=print is True, color_error=color_error, color_escape=color_escape):
                if output is not None:
                    outputs.write(output)
                if error is not None:
                    errors.write(error)

            outputs = outputs.getvalue()
            errors = errors.getvalue()
        else:
            outputs = None
            errors = None
            tail_out(sel, p)

        return_code = p.wait()

        _thread_local.process = None

        _QUEUE.remove(p.pid)
        # XXX: For some reason this was returning None when everything was actually ok. (on linux,el8)
        if return_code is None:
            return_code = CORRECTED_RETURN_CODE

        return CommandOutput(return_code, outputs, errors)


def tail_out(sel, p, enable_output=True, color_error="", color_escape=""):
    while True:
        for key, _ in sel.select():
            data = key.fileobj.read1().decode()
            if not data:
                return
            if key.fileobj is p.stdout:
                if enable_output:
                    print(
                        data,
                        end="",
                        flush=True,
                    )
                yield data, None
            else:
                if enable_output:
                    print(
                        f"{color_error}ERROR OUTPUT:{color_escape} {data}",
                        end="",
                        file=sys.stderr,
                        flush=True,
                    )
                yield None, data
