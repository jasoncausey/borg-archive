"""
 Utility functions for the borg-archive package.

 MIT License

 Copyright 2025 Jason L. Causey

 Permission is hereby granted, free of charge, to any person obtaining a copy of
 this software and associated documentation files (the “Software”), to deal in
 the Software without restriction, including without limitation the rights to
 use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
 of the Software, and to permit persons to whom the Software is furnished to do
 so, subject to the following conditions:

 The above copyright notice and this permission notice shall be included in all
 copies or substantial portions of the Software.

 THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
 FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
 COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
 IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
 CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import shutil, sys
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Union, TextIO, BinaryIO

from rich.console import Console
from rich.prompt import Confirm

from .exceptions import CommandNotFoundError

console = Console()


def check_required_commands() -> None:
    """
    Check if all required commands (borg, tar, zstd) are available.
    Raises CommandNotFoundError if any required command is missing.
    """
    required_commands = ["borg", "tar", "zstd"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            raise CommandNotFoundError(f"Required command '{cmd}' not found in PATH")


def get_best_compressor(archiver: str = "tar") -> Tuple[str, str]:
    """
    Determine the best available compression command and its decompression counterpart.

    Args:
        archiver: The archiver to get compression commands for, either 'tar' (default) or 'squashfs'

    Returns:
        Tuple[str, str]: A tuple of (compress_cmd, decompress_cmd)

    Note:
        Prefers compression tools in this order:
        - For tar: zstd > pigz > gzip
        - For squashfs: zstd > gzip

    Raises:
        CommandNotFoundError: If no supported compression command is found
        RuntimeError: If an invalid archiver type is specified
    """
    if archiver == "tar":
        if shutil.which("zstd"):
            return "zstd -9", "zstd -d"
        elif shutil.which("pigz"):
            return "pigz -9", "pigz -d"
        elif shutil.which("gzip"):
            return "gzip -9", "gzip -d"
        else:
            raise CommandNotFoundError(
                "No supported compression command found (tried: zstd, pigz, gzip)"
            )
    elif archiver == "squashfs":
        if shutil.which("zstd"):
            return "-comp zstd -Xcompression-level 9", "-comp zstd"
        elif shutil.which("gzip"):
            return "-comp gzip -Xcompression-level 9", "-comp gzip"
        else:
            raise CommandNotFoundError(
                "No supported compression command found (tried: zstd, gzip)"
            )
    else:
        raise RuntimeError(
            f"Bad archiver type in `for_archiver`: {archiver} (must be 'tar' or 'squashfs')."
        )


def get_best_archiver(file_path: Optional[Path] = None) -> str:
    """
    Determines best archiver (either 'tar' or 'squashfs').

    Args:
        file_path: If provided, detects which archiver was used to create the archive
                  If not provided, returns the best available archiver on the system

    Returns:
        str: Either 'tar' or 'squashfs'
    """
    # If they are asking about an existing archive, try to detect the format.
    is_squashfs = False
    if file_path is not None and file_path.is_file():
        with open(file_path, "rb") as fin:
            if fin.read(4) == b"hsqs":
                is_squashfs = True
    has_squashfs = bool(shutil.which("mksquashfs"))
    is_squashfs = is_squashfs if is_squashfs is not None else has_squashfs

    if file_path is not None:
        if is_squashfs:
            return "squashfs"
    elif has_squashfs:
        return "squashfs"
    return "tar"


def run_command(
    cmd: list[str],
    check: bool = True,
    capture_output: bool = False,
    input: Optional[bytes] = None,
    encoding: Optional[str] = "utf-8",
    suppress_stderr=False,
) -> subprocess.CompletedProcess:
    """
    Run a single command and handle its output.

    Args:
        cmd: Command and arguments as a list
        check: Whether to check the return code
        capture_output: Whether to capture the command output
        input: Optional bytes to pass as stdin
        encoding: Text encoding to use, or None for binary mode
        suppress_stderr: Whether to mute standard error output

    Returns:
        CompletedProcess instance
    """
    try:
        return subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            stderr=(
                subprocess.DEVNULL if suppress_stderr and (not capture_output) else None
            ),
            input=input,
            text=encoding is not None,
            encoding=encoding,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running command:[/red] {' '.join(cmd)}")
        if e.stdout:
            console.print("[yellow]stdout:[/yellow]", e.stdout)
        if e.stderr:
            console.print("[red]stderr:[/red]", e.stderr)
        raise


def run_pipeline(
    cmds: list[list[str]],
    check: bool = True,
    stdin: Optional[Union[TextIO, BinaryIO]] = None,
    stdout: Optional[Union[TextIO, BinaryIO]] = None,
    encoding: Optional[str] = "utf-8",
    suppress_stderr: bool = False,
) -> subprocess.CompletedProcess:
    """
    Run a pipeline of commands, connecting stdout of each to stdin of the next.

    Args:
        cmds: List of command lists, each in same format as run_command() cmd param
        check: Whether to check the return codes
        stdin: Optional file object to use as stdin for the first command
        stdout: Optional file object to use as stdout for the last command
        encoding: Text encoding to use, or None for binary mode
        suppress_stderr: Whether to mute standard error output

    Returns:
        CompletedProcess instance with output from final command

    Raises:
        ValueError: If cmds is empty
        subprocess.CalledProcessError: If any command in the pipeline fails and check=True
    """
    if not cmds:
        raise ValueError("Pipeline requires at least one command")

    processes = []
    stderr = subprocess.DEVNULL if suppress_stderr else subprocess.PIPE

    # Start first process
    first_proc = subprocess.Popen(
        cmds[0],
        stdin=stdin if stdin is not None else None,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=encoding is not None,
        encoding=encoding,
    )
    processes.append(first_proc)

    # Create middle pipeline processes
    for cmd in cmds[1:-1]:
        proc = subprocess.Popen(
            cmd,
            stdin=processes[-1].stdout,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=encoding is not None,
            encoding=encoding,
        )
        processes.append(proc)
        # Close previous process's stdout to avoid deadlocks
        processes[-2].stdout.close()

    # Start last process if there are multiple commands
    if len(cmds) > 1:
        last_proc = subprocess.Popen(
            cmds[-1],
            stdin=processes[-1].stdout,
            stdout=stdout if stdout is not None else None,
            stderr=stderr,
            text=encoding is not None,
            encoding=encoding,
        )
        processes.append(last_proc)
        processes[-2].stdout.close()

    # Collect output and wait for completion
    stdout = stderr_output = None
    return_codes = []

    for proc in processes:
        out, err = proc.communicate()
        return_codes.append(proc.returncode)
        if proc == processes[-1] and not stdout:
            stdout = out
        stderr_output = ""
        if proc == processes[-1] and not suppress_stderr:
            stderr_output = err

    # Check return codes if requested
    if check and any(code != 0 for code in return_codes):
        failed_cmd = cmds[
            return_codes.index(next(code for code in return_codes if code != 0))
        ]
        error = subprocess.CalledProcessError(
            return_codes[-1], failed_cmd, stdout, stderr_output
        )
        console.print(f"[red]Error in pipeline command:[/red] {' '.join(failed_cmd)}")
        if stdout:
            console.print("[yellow]stdout:[/yellow]", stdout)
        if stderr_output:
            console.print("[red]stderr:[/red]", stderr_output)
        raise error

    # Return CompletedProcess instance
    return subprocess.CompletedProcess(
        cmds[-1], return_codes[-1], stdout, stderr_output
    )


def ensure_dir(path: Path) -> None:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        path: Path to the directory
    """
    path.mkdir(parents=True, exist_ok=True)


def confirm_overwrite(path: Path) -> bool:
    """
    Ask for confirmation before overwriting a path.

    Args:
        path: Path to check

    Returns:
        True if user confirms, False otherwise
    """
    if not path.exists():
        return True

    response = Confirm.ask(
        f"[yellow]{path}[/yellow] already exists. Contents will be overwritten if you continue.\n"
        "Are you sure?",
        default=False,
    )

    return response
