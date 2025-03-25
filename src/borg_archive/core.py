"""Core functionality for borg-archive.

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

import os
import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional
import subprocess

from rich.console import Console
from rich.progress import Progress

from .exceptions import (
    ArchiveError,
    CollapseError,
    CreationError,
    DuplicateTagException,
    ExpandError,
    ExtractError,
    MountError,
    RepoError,
    UpdateError,
    ValidationError,
)
from .utils import (
    check_required_commands,
    get_best_archiver,
    get_best_compressor,
    run_command,
    run_pipeline,
    ensure_dir,
)

console = Console()
err_console = Console(stderr=True)

DEBUG = False


class BorgArchive:
    """Main class for handling Borg archive operations."""

    def __init__(
        self,
        archive_or_repo_path: Optional[Path] = None,
        repo_path: Optional[Path] = None,
    ):
        """
        Initialize a BorgArchive instance.

        Args:
            archive_or_repo_path: Path to the archive file or expanded borg repository (optional)
            repo_path:  Path to an expanded borg repository (use only if supplying both archive and repo). (optional)
        """
        archive_path = (
            Path(archive_or_repo_path).resolve() if archive_or_repo_path else None
        )
        # If a directory was provided in the first arg, assume a repo file.
        if archive_path is not None and archive_path.is_dir() and repo_path is None:
            repo_path = archive_or_repo_path
            archive_path = None
        self.archive_path = archive_path
        self.borg_dir = Path(repo_path).resolve() if repo_path else None

        self.temp_dir = None
        self.is_mounted = False
        self.sqfs_is_mounted = False
        check_required_commands()

    def __enter__(self):
        """Set up temporary working directory."""
        self.temp_dir = (
            Path(tempfile.mkdtemp()) if not DEBUG else Path(Path.cwd() / ".borg")
        )
        if self.borg_dir is not None:
            if self.dir_is_repo(self.borg_dir):
                self.borg_dir_is_temp = False
            else:
                raise RepoError(
                    f'Invalid repository path supplied: "{str(self.borg_dir)}"'
                )
        else:
            self.borg_dir = self.temp_dir / "borg-repo"
            self.borg_dir_is_temp = True
        ensure_dir(self.borg_dir)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Unless the archive has been mounted, clean up the temp directory."""
        if not self.is_mounted and not DEBUG:
            if self.sqfs_is_mounted:
                try:
                    run_command(["umount", self.borg_dir])
                except Exception as e:
                    err_console.print(f"Unmounting {self.borg_dir} failed: {e}")
            if self.borg_dir_is_temp:
                self.__delete_borg_repo()
            self.__remove_temp_dir()

    def __set_borg_environ(self):
        """Set environment variables needed for borg actions in this context."""
        os.environ["BORG_RELOCATED_REPO_ACCESS_IS_OK"] = "yes"
        os.environ["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"

    def __create_compressed_archive(self, repo_dir: Optional[Path] = None) -> None:
        """Create the compressed archive of the Borg repository, using squashfs if available
        or tar if squashfs is not available."""
        # Create compressed tarfile
        repo_dir = self.borg_dir if repo_dir is None else repo_dir
        best_archiver = get_best_archiver()
        if best_archiver == "tar":
            compress_cmd, _ = get_best_compressor()
            with console.status("Compressing archive..."):
                cwd = os.getcwd()
                os.chdir(repo_dir.parent)
                try:
                    with open(self.archive_path, "wb") as arch_fp:
                        run_pipeline(
                            [
                                # Use --format=pax to ensure consistent tar format
                                ["tar", "--format=pax", "-cv", repo_dir.name],
                                compress_cmd.split(),
                            ],
                            check=True,
                            stdout=arch_fp,
                            encoding=None,  # Use binary mode
                        )
                except Exception as e:
                    raise ArchiveError(f"Failed to create tar archive: {e}")
                finally:
                    os.chdir(cwd)
        elif best_archiver == "squashfs":
            # Good time/size tradeoff by using default squashfs compression
            with console.status("Compressing archive..."):
                cwd = os.getcwd()
                os.chdir(repo_dir.parent)
                try:
                    run_command(
                        [
                            "mksquashfs",
                            str(repo_dir),
                            str(self.archive_path),
                            "-quiet",
                            "-noappend",
                            "-no-xattrs",
                        ]
                    )
                except Exception as e:
                    raise ArchiveError(f"Failed to create squashfs archive: {e}")
                finally:
                    os.chdir(cwd)
        else:
            raise ArchiveError(
                f"Internal error: Unknown 'best archiver' found: {best_archiver}."
            )

    def __extract_compressed_archive(
        self, archive_path: Optional[Path] = None, repo_dir: Optional[Path] = None
    ) -> None:
        """
        Extract the compressed archive to restore a borg repository directory.
        Works with SquashFS compressed filesystems or tar archives.
        """
        archive_path = (
            Path(archive_path) if archive_path is not None else self.archive_path
        )
        repo_dir = Path(repo_dir) if repo_dir is not None else self.borg_dir

        best_archiver = get_best_archiver(archive_path)
        if best_archiver == "tar":
            # Extract the compressed tarfile
            _, decompress_cmd = get_best_compressor()
            with console.status("Extracting archive..."):
                try:
                    with open(archive_path, "rb") as arch_in:
                        run_pipeline(
                            [
                                decompress_cmd.split(),
                                [
                                    "tar",
                                    "-xf",
                                    "-",
                                    "-C",
                                    str(repo_dir),
                                    "--strip-components=1",
                                ],
                            ],
                            stdin=arch_in,
                            check=True,
                            encoding=None,
                        )
                except Exception as e:
                    raise ExpandError(f"Failed to expand tar archive: {e}")
        elif best_archiver == "squashfs":
            # Extract squashfs archive
            with console.status("Extracting archive..."):
                try:
                    run_command(
                        [
                            "unsquashfs",
                            "-no-progress",
                            "-quiet",
                            "-dest",
                            str(repo_dir),
                            str(archive_path),
                        ]
                    )
                except Exception as e:
                    raise ExpandError(f"Failed to expand squashfs archive: {e}")

    def __remove_temp_dir(self, tmp_dir_path: Optional[Path] = None) -> None:
        """Clean up temporary directory."""
        if tmp_dir_path is None:
            tmp_dir_path = self.temp_dir
        tmp_dir_path = Path(tmp_dir_path)
        if tmp_dir_path.exists():
            shutil.rmtree(tmp_dir_path)

    def __cleanup_borg_files(self, tmp_repo_path: Optional[Path] = None) -> None:
        """Clean up cache and security files associated with the repository."""

        tmp_repo_path = tmp_repo_path if tmp_repo_path is not None else self.borg_dir

        try:
            self.__set_borg_environ()
            result = run_command(
                ["borg", "info", "--error", "--json", tmp_repo_path],
                capture_output=True,
                encoding="utf-8",
                check=False,
                suppress_stderr=True,
            )

            if result.returncode != 0:
                if DEBUG:
                    console.print(
                        f"[yellow]Warning:[/yellow] Failed to get repository info: {result.stderr}"
                    )
                return

            info = json.loads(result.stdout)

            # Clean up cache directory
            if "cache" in info and "path" in info["cache"]:
                cache_path = Path(info["cache"]["path"])
                if cache_path.exists():
                    shutil.rmtree(cache_path)
                    if DEBUG:
                        console.print(f"Removed cache directory: {cache_path}")

            # Clean up security directory
            if "security_dir" in info:
                security_dir = Path(info["security_dir"])
                if security_dir.exists():
                    shutil.rmtree(security_dir)
                    if DEBUG:
                        console.print(f"Removed security directory: {security_dir}")

        except Exception as e:
            if DEBUG:
                console.print(
                    f"[yellow]Warning:[/yellow] Failed to clean up repository files: {e}"
                )

    def __delete_borg_repo(self):
        """Delete the temporary or expanded borg repo and associated files."""
        # Clean up cache and security files first
        self.__cleanup_borg_files()

        # Delete the borg repo
        try:
            self.__set_borg_environ()
            run_command(
                ["borg", "delete", "--error", "--force", self.borg_dir],
                check=False,
                suppress_stderr=True,
            )
        except Exception as e:
            if DEBUG:
                console.print(
                    f"[red]Error:[/red] Failed to delete the temporary repository: {e}"
                )

    def __unmount_squashfs(self, mounted_squashfs: Path | str):
        try:
            run_command(
                ["umount", "-t", "squashfs", mounted_squashfs],
                check=False,
                suppress_stderr=True,
            )
        except Exception as e:
            err_console.print(f"Failed to unmount squashfs at {mounted_squashfs}: {e}")

    @staticmethod
    def dir_is_repo(repo_path: Path) -> bool:
        """
        Check if a directory is a Borg repository.

        Note:
            This method is designed to be fast to reject non-Borg directories.
            It does not guarantee a valid repository in the way `borg check` would.

        Args:
            repo_path: Path to the directory to check

        Returns:
            bool: True if the directory is a Borg repository, False otherwise
        """

        try:
            # An attempt to initialize the repository should
            # FAIL with returncode = 2 and "A repository already exists at"
            # in stderr if and only if the directory is already a repository.
            subprocess.run(
                ["borg", "init", Path(repo_path), "--encryption", "none"],
                check=True,
                capture_output=True,
                encoding="utf-8",
            )
        except subprocess.CalledProcessError as e:
            if e.returncode == 2 and e.stderr.startswith(
                "A repository already exists at"
            ):
                return True
        except Exception as e:
            raise
        return False

    def create(
        self,
        source_dir: Path,
        encryption: str = "none",
        expanded: bool = False,
        borg_options: Optional[list[str]] = None,
    ) -> None:
        """
        Create a new archive.

        Args:
            source_dir: Directory to archive
            encryption: Encryption mode for borg
            expanded: Set True to create an expanded borg repo, not an archive file
            borg_options: Additional borg options
        """
        source_dir = Path(source_dir)
        if not source_dir.is_dir():
            raise ValidationError(f"Source directory '{source_dir}' does not exist")

        # if we want to create an expanded repo instead of an archive,
        # make sure we don't use a temporary directory.  The archive path
        # will hold the repo's name.
        if expanded:
            self.borg_dir = self.archive_path
            self.borg_dir_is_temp = False

        # Initialize tag tracking
        tag = "1"
        try:
            # Initialize borg repository
            cmd = ["borg", "init", "--error", "--encryption", encryption]
            if borg_options:
                cmd.extend(borg_options)
            cmd.append(str(self.borg_dir))
            run_command(cmd, encoding="utf-8")  # Use text mode for borg output
        except Exception as e:
            raise CreationError(f"Failed to initialize Borg repository: {e}")

        # Create archive
        cwd = os.getcwd()
        os.chdir(source_dir.parent)
        try:
            run_command(
                [
                    "borg",
                    "create",
                    "--compression",
                    "zstd,9",
                    "--error",
                    "--progress",
                    f"{self.borg_dir}::{tag}",
                    source_dir.name,
                ],
                encoding="utf-8",  # Use text mode for borg output
            )
        except Exception as e:
            raise CreationError(f"Failed to create repository: {e}")
        finally:
            os.chdir(cwd)
        if not expanded:
            try:
                self.__create_compressed_archive()
            except Exception as e:
                raise CreationError(f"Failed to create archive file: {e}")

    def collapse(self, repo_dir: Path, retain_repo=False) -> None:
        """
        Collapse an expanded Borg repo directory to an archive file.

        Args:
            repo_dir: Path to the expanded Borg repository directory
            retain_repo: If True, keep the repository directory after collapsing
                         If False (default), delete the repository directory

        Raises:
            CollapseError: If the directory is not a valid Borg repository
            ArchiveError: If there's an error creating the archive file
        """
        repo_dir = Path(repo_dir)
        if not self.dir_is_repo(repo_dir):
            raise CollapseError(
                f'Failed to collapse repository "{str(repo_dir)}": Not a valid repository directory.'
            )
        self.borg_dir = repo_dir
        try:
            self.__create_compressed_archive(repo_dir)
        except Exception as e:
            raise ArchiveError(f"Failed to create archive file: {e}")
        if not retain_repo:
            self.__delete_borg_repo()
            self.__remove_temp_dir(repo_dir)

    def expand(self, repo_dir: Path) -> None:
        """
        Expand the archived Borg repository into `repo_dir`.

        Args:
            repo_dir: Directory where the repository will be expanded

        Raises:
            ExpandError: If there's an error expanding the archive
        """
        repo_dir = Path(repo_dir)
        ensure_dir(repo_dir)
        try:
            self.__extract_compressed_archive(repo_dir=repo_dir)
        except Exception as e:
            raise ExpandError(f"Failed to expand archive: {e}")

    def extract(self, output_dir: Path, tag: Optional[str] = None) -> None:
        """
        Extract archive contents into a directory.

        Args:
            output_dir: Directory to extract to
            tag: Specific tag to extract (default: latest)

        Raises:
            ValidationError: If the output directory doesn't exist and can't be created
            ExtractError: If there's an error extracting the archive
            ExpandError: If there's an error expanding the archive (when using a temporary repo)
        """
        output_dir = Path(output_dir)
        ensure_dir(output_dir)

        try:
            if self.borg_dir_is_temp:
                self.expand(self.borg_dir)
        except ExpandError as e:
            raise ExtractError(f"Failed to extract archive: {e}")

        # Extract from borg archive
        cwd = Path.cwd()
        os.chdir(output_dir)
        try:
            # Get tag to extract
            if not tag:
                tag = self.get_most_recent_tag()
            self.__set_borg_environ()
            run_command(
                ["borg", "extract", "--error", "--progress", f"{self.borg_dir}::{tag}"],
                encoding="utf-8",  # Use text mode for borg output
                suppress_stderr=True,
            )
        except Exception as e:
            raise ExtractError(f"Failed to extract archive: {e}")
        finally:
            os.chdir(cwd)

    def generate_next_tag(self, tag: Optional[str] = None) -> str:
        """
        Generate a numeric tag, usually the number of current archives + 1.

        Args:
            tag: Optional custom tag to use instead of auto-generated one

        Returns:
            str: The tag to use (either the provided tag or an auto-generated one)

        Raises:
            DuplicateTagException: If the provided tag already exists in the repository
        """
        tags = set(self.get_tag_list())
        if tag is not None and str(tag) in tags:
            raise DuplicateTagException(f'Tag "{tag}" already exists.')
        elif tag is not None:
            return tag
        next_tag = len(tags) + 1  # Next counter _should_ be available
        while str(next_tag) in tags:  # unless manually set by user before
            next_tag += 1  # so skip forward until counter isn't used
        return str(next_tag)

    def get_most_recent_tag(self) -> str:
        """
        Returns the most recent tag for the currently extracted borg archive.

        Returns:
            str: The most recent tag (last in the list of tags)
        """
        return self.get_tag_list()[-1]

    def get_tag_list(self, full_output: Optional[bool] = False) -> list:
        """
        Returns all tags in the currently extracted borg archive as a list.

        Args:
            full_output: If True, includes timestamp information with each tag
                         If False, returns only the tag names

        Returns:
            list: List of tags (with timestamps if full_output=True)
        """
        # List borg archives
        format_str = "{archive:<36} {time}{NL}" if full_output else "{archive}{NL}"
        self.__set_borg_environ()
        proc1 = run_command(
            [
                "borg",
                "list",
                "--error",
                "--format",
                format_str,
                str(self.borg_dir),
            ],
            capture_output=True,
            encoding="utf-8",  # Use text mode for borg output
            suppress_stderr=True,
        )
        return proc1.stdout.splitlines()

    def list_tags(self) -> None:
        """
        List all available tags in the archive.

        Prints the tags with their timestamps to the console.
        If the archive is not already expanded, it will be extracted to a temporary directory first.

        Raises:
            ArchiveError: If there's an error reading the archive or repository
        """

        # Extract the compressed tarfile unless we are already expanded:
        if self.borg_dir_is_temp:
            try:
                self.__extract_compressed_archive()
            except Exception as e:
                raise ArchiveError(f"Failed to read archive: {e}")
        try:
            # List borg archives
            for line in self.get_tag_list(full_output=True):
                console.print(line)
        except Exception as e:
            raise ArchiveError(f"Failed to read repository: {e}")

    def mount(self, mount_dir: Path, tag: Optional[str] = None) -> None:
        """
        Mount archive contents as a read-only filesystem.

        Args:
            mount_dir: Directory to mount to
            tag: Specific tag to mount (default: latest)

        Raises:
            MountError: If there's an error mounting the archive

        Note:
            This requires FUSE to be installed on the system.
            The mounted filesystem is read-only.
        """
        mount_dir = Path(mount_dir)
        ensure_dir(mount_dir)

        # If we are using a temporary repo dir:
        if self.borg_dir_is_temp:
            # Save temp dir path for unmounting
            (mount_dir / ".borg-repo").write_text(str(self.borg_dir))
            try:
                self.__extract_compressed_archive()
            except Exception as e:
                raise MountError(f"Failed to prepare archive: {e}")

        # Mount archive
        try:
            # Get tag to extract
            if not tag:
                tag = self.get_most_recent_tag()
            self.__set_borg_environ()
            run_command(
                ["borg", "mount", "--error", f"{self.borg_dir}::{tag}", str(mount_dir)],
                encoding="utf-8",  # Use text mode for borg output
            )
            console.print(
                f"Mounted archive to [green]'{mount_dir}'[/green] (read-only)"
            )
        except Exception as e:
            raise MountError(f"Failed to mount archive: {e}")
        self.is_mounted = True

    def unmount(self, mount_dir: Path) -> None:
        """
        Unmount a previously mounted archive.

        Args:
            mount_dir: Directory where archive is mounted

        Raises:
            MountError: If there's an error unmounting the archive or if the mount directory doesn't exist
        """
        mount_dir = Path(mount_dir)
        if not mount_dir.exists():
            raise MountError(f"Mount directory '{mount_dir}' does not exist")
        try:
            run_command(
                ["borg", "umount", "--error", str(mount_dir)],
                encoding="utf-8",  # Use text mode for borg output
            )
            # If the mount was from a temporary dir, there will be a ".borg-repo"
            # path cache file there now.
            if (mount_dir / ".borg-repo").exists():
                # Get the path to the temporary Borg repo that was mounted:
                mounted_repo = Path(mount_dir / ".borg-repo").read_text()
                # Try unmounting in case it is squashfs.
                self.__unmount_squashfs(mounted_repo)
                # Clean it from caches
                self.__cleanup_borg_files(mounted_repo)
                # And remove that directory.
                self.__remove_temp_dir(mounted_repo)
                # Remove the repo path cache file
                (mount_dir / ".borg-repo").unlink()
            console.print("Unmounted archive")
        except Exception as e:
            raise MountError(f"Failed to unmount archive: {e}")

    def update(self, source_dir_or_repo: Path, tag: Optional[str] = None) -> None:
        """
        Update archive with changes from the raw dataset or from an expanded repository.

        Args:
            source_dir_or_repo: Directory containing changes or an expanded repository
            tag: Tag for the update (default: auto-increment)

        Raises:
            ValidationError: If the source directory doesn't exist
            UpdateError: If there's an error updating the archive
            DuplicateTagException: If the provided tag already exists in the repository
        """
        source_dir_or_repo = Path(source_dir_or_repo).resolve()
        if not source_dir_or_repo.is_dir():
            raise ValidationError(
                f"Source directory '{source_dir_or_repo}' does not exist"
            )

        updating_archive_from_repo = self.dir_is_repo(source_dir_or_repo)
        if updating_archive_from_repo:
            self.borg_dir = source_dir_or_repo
            self.borg_dir_is_temp = False

        updating_archive = self.archive_path is not None

        # If we are using a temporary repo dir:
        if self.borg_dir_is_temp:
            # Extract the compressed tarfile
            try:
                self.__extract_compressed_archive()
            except Exception as e:
                raise UpdateError(f"Failed to prepare archive: {e}")

        try:
            # If we are not updating the tar directly from an expanded repo,
            # we need to create a new archive in the repo first:
            if not updating_archive_from_repo:
                # Check that the repo is not mounted (locked).  If it is, we
                # cannot update it until it is unmounted.
                if os.path.isfile(self.borg_dir / "lock.roster"):
                    raise UpdateError(
                        f'\nCannot update expanded repository "{self.borg_dir.name}". '
                        f"The repository is locked, possibly due to being mounted.\n"
                        f"If you have mounted an archive, use `borg-archive unmount` "
                        f"to unmount it, then try updating again."
                    )
                # Create new borg archive (within the existing borg _repo_.)
                cwd = os.getcwd()
                os.chdir(source_dir_or_repo.parent)
                try:
                    tag = self.generate_next_tag(tag)
                    self.__set_borg_environ()
                    run_command(
                        [
                            "borg",
                            "create",
                            "--compression",
                            "zstd,9",
                            "--error",
                            "--progress",
                            f"{self.borg_dir}::{tag}",
                            source_dir_or_repo.name,
                        ],
                        encoding="utf-8",  # Use text mode for borg output
                        suppress_stderr=True,
                    )
                finally:
                    os.chdir(cwd)

            if updating_archive:
                # Create new compressed tarfile
                self.__create_compressed_archive()
        except Exception as e:
            raise UpdateError(f"Failed to update archive: {e}")
