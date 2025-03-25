"""
Command-line interface for borg-archive, a wrapper that allows Borg Backup to
    be used to create single-file compressed archives.  Basic functions are
    supported such as creating, mount/extract, and update of the archive.

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

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from .core import BorgArchive
from .exceptions import BorgArchiveError
from .utils import confirm_overwrite

console = Console()

CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "max_content_width": 100,
}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option()
def main():
    """
    A tool for creating single-file compressed archives using Borg Backup.

    This tool allows you to create, extract, mount, and update Borg
    repositories that are stored as single compressed files.
    """
    pass


@main.command()
@click.argument("repo_directory", type=click.Path())
@click.argument("archive_file", type=click.Path())
@click.option(
    "--keep-repo",
    is_flag=True,
    help="Retain the expanded repository directory after the collapse operation.",
)
def collapse(repo_directory: str, archive_file: str, keep_repo: bool = False):
    """Collapse REPO_DIRECTORY from `expand` command back into a single-file archive.

    REPO_DIRECTORY is the expanded repo from the `expand` command.

    ARCHIVE_FILE is the path to the single-file archive.  If the file exists,
    it will be replaced, otherwise it is created.

    The repository REPO_DIRECTORY will be removed after archiving unless
    the --keep-repo option is provided.
    """
    try:
        with BorgArchive(Path(archive_file)) as archive:
            archive.collapse(repo_directory, retain_repo=keep_repo)
    except BorgArchiveError as e:
        console.print(f"Failed to collapse the repository: {e}")


@main.command()
@click.argument("archive_file", type=click.Path())
@click.argument(
    "source_dir", type=click.Path(exists=True, file_okay=False, dir_okay=True)
)
@click.argument("borg_options", nargs=-1, type=click.UNPROCESSED)
def create(
    archive_file: str,
    source_dir: str,
    borg_options: tuple = (),
):
    """
    Create a new archive from SOURCE_DIR.

    ARCHIVE_FILE is the path where the new archive will be created.

    SOURCE_DIR is the directory to archive.

    Any additional BORG_OPTIONS are passed directly to the borg create command.
    """
    try:
        archive_path = Path(archive_file)
        if archive_path.exists() and not confirm_overwrite(archive_path):
            sys.exit(0)

        with BorgArchive(archive_path) as archive:
            archive.create(
                source_dir=Path(source_dir),
                encryption="none",
                borg_options=list(borg_options) if borg_options else None,
            )
    except BorgArchiveError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command(name="create-expanded")
@click.argument("repo_directory", type=click.Path())
@click.argument(
    "source_dir", type=click.Path(exists=True, file_okay=False, dir_okay=True)
)
@click.argument("borg_options", nargs=-1, type=click.UNPROCESSED)
def create_expanded(
    repo_directory: str,
    source_dir: str,
    borg_options: tuple = (),
):
    """
    Create a new expanded archive from SOURCE_DIR.  Expanded archives support
    efficient `update` operations and may be collapsed into an archive file
    with the `collapse` command.

    REPO_DIRECTORY is the path where the expanded archive will be created.

    SOURCE_DIR is the directory to archive.

    Any additional BORG_OPTIONS are passed directly to the borg create command.
    """
    try:
        archive_path = Path(repo_directory)
        if archive_path.exists() and not confirm_overwrite(archive_path):
            sys.exit(0)

        with BorgArchive(archive_path) as archive:
            archive.create(
                source_dir=Path(source_dir),
                encryption="none",
                expanded=True,
                borg_options=list(borg_options) if borg_options else None,
            )
    except BorgArchiveError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("archive_file", type=click.Path(exists=True))
@click.argument("repo_directory", type=click.Path())
def expand(archive_file: str, repo_directory: str):
    """
    Expand the compressed archive ARCHIVE_FILE into a repository REPO_DIRECTORY
    for faster list and update operations.

    If REPO_DIRECTORY exists and is non-empty, this command will fail.
    """
    try:
        repo_path = Path(repo_directory)
        with BorgArchive(Path(archive_file)) as archive:
            archive.expand(repo_path)
    except BorgArchiveError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("archive_file", type=click.Path(exists=True))
@click.argument("output_dir", type=click.Path())
@click.option("--tag", help="Specific tag to extract (default: latest)")
def extract(archive_file: str, output_dir: str, tag: Optional[str]):
    """
    Extract ARCHIVE_FILE to OUTPUT_DIR.

    If OUTPUT_DIR exists, you will be prompted before overwriting its contents.
    """
    try:
        output_path = Path(output_dir)
        if output_path.exists() and not confirm_overwrite(output_path):
            sys.exit(0)
        with BorgArchive(Path(archive_file)) as archive:
            archive.extract(output_path, tag)
    except BorgArchiveError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("archive_or_repo", type=click.Path(exists=True))
def list(archive_or_repo: str):
    """List all available tags in ARCHIVE_OR_REPO, which is either an archive file or an expanded repository directory."""
    try:
        archive_path = Path(archive_or_repo)
        repo_path = None
        if archive_path.is_dir():
            repo_path = archive_path
            archive_path = None

        with BorgArchive(
            archive_or_repo_path=archive_path, repo_path=repo_path
        ) as archive:
            archive.list_tags()
    except BorgArchiveError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("archive_file", type=click.Path(exists=True))
@click.argument("mount_dir", type=click.Path())
@click.option("--tag", help="Specific tag to mount (default: latest)")
def mount(archive_file: str, mount_dir: str, tag: Optional[str]):
    """
    Mount ARCHIVE_FILE to MOUNT_DIR (read-only).

    MOUNT_DIR will be created if it does not exist.
    """
    try:
        with BorgArchive(Path(archive_file)) as archive:
            archive.mount(Path(mount_dir), tag)
    except BorgArchiveError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


def do_unmount(mount_dir: str):
    """Perform the work for unmounting a previously mounted archive from MOUNT_DIR."""
    try:
        with BorgArchive() as ba:
            ba.unmount(Path(mount_dir))
    except BorgArchiveError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("mount_dir", type=click.Path(exists=True))
def umount(mount_dir: str):
    """Unmount a previously mounted archive from MOUNT_DIR."""
    do_unmount(mount_dir)


# We publish `umount` as the official command, but let this
# common type work as well.
@main.command(hidden=True)
@click.argument("mount_dir", type=click.Path(exists=True))
def unmount(mount_dir: str):
    """Alias for `umount`."""
    do_unmount(mount_dir)


@main.command()
@click.argument("archive_or_repo", type=click.Path(exists=True))
@click.argument(
    "source_dir_or_repo", type=click.Path(exists=True, file_okay=False, dir_okay=True)
)
@click.option("--tag", help="Tag for this update (default: auto-numbering)")
def update(archive_or_repo: str, source_dir_or_repo: str, tag: Optional[str]):
    """
    Update ARCHIVE_OR_REPO with changes from SOURCE_DIR_OR_REPO.

    Creates a new tag in the ARCHIVE or expanded REPO containing
    the current state of SOURCE_DIR, or updates the expanded REPO
    to match the current state of SOURCE_DIR, or updates the ARCHIVE file
    to match the current state of the REPO.

    IMPORTANT:  You cannot use an expanded repository path for both
    ARCHIVE_OR_REPO and SOURCE_DIR_OR_REPO simultaneously.

    Examples:

    Update archive file to reflect changes to local data files:

        borg-archive update my-data-archive.baz my-data


    Update expanded repository to reflect changes to local data files:

        borg-archive update my-expanded-repo my-data

    Update archive to reflect changes to expanded repository:

        borg-archive update my-data-archive.baz my-expanded-repo
    """
    archive_or_repo = Path(archive_or_repo)
    source_dir_or_repo = Path(source_dir_or_repo)

    # Enforce that both arguments cannot simultaneously reference a repositories.
    if (
        archive_or_repo.is_dir()
        and source_dir_or_repo.is_dir()
        and BorgArchive.dir_is_repo(source_dir_or_repo)
    ):
        console.print(
            f"[red]Error:[/red] Only one of ARCHIVE_OR_REPO or SOURCE_DIR_OR_REPO may be an expanded repository directory."
        )
        sys.exit(1)
    try:
        with BorgArchive(Path(archive_or_repo)) as archive:
            archive.update(Path(source_dir_or_repo), tag)
    except BorgArchiveError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
