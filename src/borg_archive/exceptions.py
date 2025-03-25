"""
 Custom exceptions for the borg-archive package.

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


class BorgArchiveError(Exception):
    """Base exception for all borg-archive errors."""

    pass


class CollapseError(BorgArchiveError):
    """Raised when collapsing an expanded repository fails."""

    pass


class CommandNotFoundError(BorgArchiveError):
    """Raised when a required command (borg, tar, etc.) is not found."""

    pass


class DuplicateTagException(BorgArchiveError):
    """Raised when an update specifies a duplicate tag."""

    pass


class ArchiveError(BorgArchiveError):
    """Raised when there's an error with archive operations."""

    pass


class CreationError(BorgArchiveError):
    """Raised when an error occurs with creating a new archive."""

    pass


class MountError(BorgArchiveError):
    """Raised when there's an error mounting/unmounting an archive."""

    pass


class ValidationError(BorgArchiveError):
    """Raised when input validation fails."""

    pass


class ExpandError(BorgArchiveError):
    """Raised when expanding archive file to Borg repo fails."""

    pass


class RepoError(BorgArchiveError):
    """Raised when a supplied repository path is not a valid Borg repository."""

    pass


class ExtractError(BorgArchiveError):
    """Raised when there's an error extracting from an archive."""

    pass


class UpdateError(BorgArchiveError):
    """Raised when there's an error updating an archive."""

    pass


class ConfigurationError(BorgArchiveError):
    """Raised when there's an error with the configuration."""

    pass
