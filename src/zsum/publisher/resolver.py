"""Wikilink + filename resolution for the published Obsidian vault.

This module is the **single source of truth** for how zsum names files in the
vault. Other tools that browse or render the vault (e.g. Wocket's vault
preview) must import from here so wikilinks are resolved identically to what
the publisher actually wrote to disk.

Public surface:
  - :func:`safe_filename`  — sanitise a name for use as an Obsidian filename.
  - :class:`FilenameTracker` — tracks assigned filenames per directory and
    auto-numbers collisions deterministically.
  - :func:`resolve_paper_wikilink` — paper notes are written as ``@<citekey>``.
  - :func:`resolve_collection_wikilink` — collection notes use the sanitised
    collection name.

Behaviour preserved verbatim from the previous private ``_FilenameTracker`` /
``_safe_filename`` implementations.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def safe_filename(name: str) -> str:
    """Convert a string to a safe filename for Obsidian.

    Replaces the Obsidian-unsafe characters ``<>:"\\/|?*`` with underscores,
    then strips leading/trailing whitespace and dots. Raises ``ValueError`` if
    the result would be empty.
    """
    unsafe_chars = '<>:"\\/|?*'
    result = name
    for ch in unsafe_chars:
        result = result.replace(ch, "_")
    result = result.strip().strip(".")
    if not result:
        raise ValueError(f"Cannot create safe filename from: {name!r}")
    return result


class FilenameTracker:
    """Track assigned filenames per directory to detect and resolve collisions.

    Calling ``resolve(name)`` returns a unique safe filename. The first call
    for a given input returns ``safe_filename(name)``; later calls with a
    different input that sanitises to the same string get auto-numbered
    suffixes (``_2``, ``_3``, …). Re-calling with the same input returns the
    previously resolved value.
    """

    def __init__(self) -> None:
        self._assigned: dict[str, str] = {}  # safe_name -> original name (first use)
        self._collisions: list[tuple[str, str, str]] = []  # (original, collided_with, resolved)
        self._name_to_safe: dict[str, str] = {}  # original name -> resolved safe name

    def resolve(self, name: str) -> str:
        """Return a unique safe filename, auto-numbering on collision."""
        if name in self._name_to_safe:
            return self._name_to_safe[name]

        safe = safe_filename(name)
        if safe not in self._assigned:
            self._assigned[safe] = name
            self._name_to_safe[name] = safe
            return safe

        n = 2
        while f"{safe}_{n}" in self._assigned:
            n += 1
        resolved = f"{safe}_{n}"
        self._assigned[resolved] = name
        self._collisions.append((name, self._assigned[safe], resolved))
        logger.warning(
            "Filename collision: %r → %r (collides with %r), resolved to %r",
            name,
            safe,
            self._assigned[safe],
            resolved,
        )
        self._name_to_safe[name] = resolved
        return resolved

    def get_safe_name(self, name: str) -> str:
        """Return the previously resolved safe name for an original name.

        Raises ``KeyError`` if the name was never registered via :meth:`resolve`.
        """
        try:
            return self._name_to_safe[name]
        except KeyError:
            raise KeyError(f"Name {name!r} was never registered via resolve()") from None

    def log_summary(self) -> None:
        """Log a summary of all collisions, if any occurred."""
        if self._collisions:
            logger.warning(
                "%d filename collision(s) detected and auto-numbered",
                len(self._collisions),
            )


def resolve_paper_wikilink(citekey: str) -> str:
    """Return the safe filename used for the paper note for ``citekey``.

    Papers are stored as ``Papers/@<citekey>.md`` after sanitising the
    ``@<citekey>`` form.
    """
    return safe_filename(f"@{citekey}")


def resolve_collection_wikilink(name: str) -> str:
    """Return the safe filename used for the collection note named ``name``.

    Collections are stored as ``Collections/<safe_name>.md``.
    """
    return safe_filename(name)
