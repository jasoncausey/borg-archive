# borg-archive

A Python tool for creating single-file compressed archives using [Borg
Backup](https://www.borgbackup.org/).

---

**WARNING:** This tool is still in an early state. Please consider it "alpha"
quality software at this point and always keep a backup of your data using
another means in addition to `borg-archive`.

---

This tool allows you to create, extract, mount, and update Borg archives that
are stored as single compressed files. It's particularly useful for sharing and
archiving versioned datasets for research purposes.

## Features

- Create single-file compressed archives using Borg Backup
- Extract archives to a directory
- Mount archives read-only (requires FUSE)
- Update archives with new changes
- List available versions/tags in an archive
- Automatic compression using zstd
- Modern CLI with rich terminal output

## Requirements

- Python 3.12 or later
- [Borg Backup](https://www.borgbackup.org/)
- [SquashFS](https://github.com/plougher/squashfs-tools) (optional, but recommended)
  - `tar` (usually pre-installed) if SquashFS is not installed.
- `zstd`, `gzip` (`pigz` is optional but recommended if `tar` is used)
- FUSE (optional, required for mount functionality)
  - For macOS: [macFuse](https://macfuse.github.io/)

## Installation

This project not not currently distributed in PyPI, since it is an alpha
version.  You can install it by cloning this repository, then using the wheel
file in the `dist` directory to install, as follows:

**Recommended Method:** You can use `uv tool` to install:

```bash
uv tool install dist/borg_archive-0.1.0-py3-none-any.whl
```

Or use [pipx](https://pypa.github.io/pipx/):

```bash
pipx install dist/borg_archive-0.1.0-py3-none-any.whl
```

Or, you can install `borg-archive` using pip:

```bash
pip install --user dist/borg_archive-0.1.0-py3-none-any.whl
```

## Usage

### Create a New Archive File

```bash
borg-archive create archive.baz /path/to/data
```

### Extract an Archive File

Latest version:

```bash
borg-archive extract archive.baz /path/to/output
```

Specific version:

```bash
borg-archive extract archive.baz /path/to/output --tag selected-tag
```

### List Available Tags

```bash
borg-archive list archive.baz
```

### Mount an Archive (Read-only)

```bash
borg-archive mount archive.baz /path/to/mount
```

### Unmount an Archive

```bash
borg-archive umount /path/to/mount
```

### Update an Archive

```bash
borg-archive update archive.baz /path/to/data
```

With a specific tag:

```bash
borg-archive update archive.baz /path/to/data --tag custom-tag
```

### Create a repository working directory (not an Archive file)

If you will be performing a series of operations on a dataset (`list`, `update`,
`extract`, `mount`), it is much more time-efficient to create a
repository directory first, then collapse to an Archive file when you are 
finished.

You can do this with the following command:

```bash
borg-archive create-expanded repo-dir /path/to/data
```

At this point the `repo-dir` directory can be used for `list`, `extract`,
`update`, and `mount` in the place of an Archive file.  This repository
directory is also a valid [Borg Backup](https://www.borgbackup.org/) repository,
and all `borg` operations may be performed on it.

### Expand an Archive into a repository directory

If you will be performing a series of operations on a dataset (`list`, `update`,
`extract`, `mount`), it is much more time-efficient to extract the archive to a
repository directory first.  You can do this with the following command:

```bash
borg-archive expand archive.baz repo-dir
```

At this point the `repo-dir` directory can be used for `list`, `extract`,
`update`, and `mount` in the place of an Archive file.  This repository
directory is also a valid [Borg Backup](https://www.borgbackup.org/) repository,
and all `borg` operations may be performed on it.

### Collapse an expanded repository directory into an Archive file

If you are working with an expanded repository directory and want to collapse it
into an archive file, use the command:

```bash
borg-archive collapse repo-dir archive.baz
```

To keep the repository directory after the collapse, use the `--keep-repo`
option, otherwise the repository directory will be removed after collapsing.

## Python API

You can also use borg-archive as a Python library:

```python
from pathlib import Path
from borg_archive import BorgArchive

# Create a new archive
with BorgArchive(Path("archive.baz")) as archive:
    archive.create(Path("/path/to/data"))

# Extract an archive
with BorgArchive(Path("archive.baz")) as archive:
    archive.extract(Path("/path/to/output"))

# List tags
with BorgArchive(Path("archive.baz")) as archive:
    archive.list_tags()

# Mount an archive
with BorgArchive(Path("archive.baz")) as archive:
    archive.mount(Path("/path/to/mount"))

# Update an archive
with BorgArchive(Path("archive.baz")) as archive:
    archive.update(Path("/path/to/data"))
```

For more API functionality, do:

```python
from borg_archive import BorgArchive
help(BorgArchive)
```

## License

MIT License - see LICENSE.md for details.

## Acknowledgments

This project was inspired by the need for a better way to store and share
versioned datasets, and builds upon the excellent [Borg
Backup](https://www.borgbackup.org/) tool.
