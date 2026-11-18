"""Public access to the prompt templates that ship inside the package.

Tools that build on ``zsum`` (for example a desktop front end that bundles
its own copy of the default prompts) should read the built-in templates
through this module rather than through the package's file layout. The
location of the files inside the wheel is an implementation detail; the
records returned here are the contract.

Only the templates shipped in the installed package are returned. The
``ZSUM_PROMPT_DIR`` overlay and a ``./prompts/`` directory, which
:func:`zsum.prompts.load_prompt` also consults, are deliberately ignored:
"built-in" means what the installed package ships.
"""

from __future__ import annotations

import hashlib
import importlib.resources as pkg_resources
from collections.abc import Iterator
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

__all__ = [
    "RESOURCE_SCHEMA_VERSION",
    "BuiltinPrompt",
    "get_builtin_prompt",
    "iter_builtin_prompts",
]

#: Version of the :class:`BuiltinPrompt` record layout. It changes only when
#: a field is removed or changes meaning; adding a field keeps it.
RESOURCE_SCHEMA_VERSION = 1

_PROMPT_SUFFIX = ".txt"


@dataclass(frozen=True)
class BuiltinPrompt:
    """One prompt template shipped with ``zsum``.

    Attributes:
        slot: Stable identifier of the template, the filename without its
            extension (for example ``"paper_card"``).
        filename: The file name ``zsum.prompts.load_prompt`` accepts for
            this template (for example ``"paper_card.txt"``).
        content: The template text, decoded as UTF-8.
        content_hash: ``"sha256:"`` followed by the hex SHA-256 digest of
            ``content`` encoded as UTF-8.
        schema_version: :data:`RESOURCE_SCHEMA_VERSION` at the time the
            record was built.
        package_version: Version of the installed ``zotero-summarizer``
            distribution, or ``"unknown"`` when it has no metadata.
    """

    slot: str
    filename: str
    content: str
    content_hash: str
    schema_version: int
    package_version: str


def _package_version() -> str:
    try:
        return _dist_version("zotero-summarizer")
    except PackageNotFoundError:
        return "unknown"


def _content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def iter_builtin_prompts() -> Iterator[BuiltinPrompt]:
    """Yield every prompt template shipped in the installed package.

    Templates are yielded in ascending ``slot`` order, so the sequence is the
    same on every platform and every call.

    Raises:
        FileNotFoundError: The package's ``prompts`` directory is missing,
            which means the installation is broken.
    """
    root = pkg_resources.files("zsum") / "prompts"
    if not root.is_dir():
        raise FileNotFoundError("zsum package data has no prompts directory")
    package_version = _package_version()
    entries = sorted(
        (e for e in root.iterdir() if e.is_file() and e.name.endswith(_PROMPT_SUFFIX)),
        key=lambda e: e.name,
    )
    for entry in entries:
        content = entry.read_text(encoding="utf-8")
        yield BuiltinPrompt(
            slot=entry.name[: -len(_PROMPT_SUFFIX)],
            filename=entry.name,
            content=content,
            content_hash=_content_hash(content),
            schema_version=RESOURCE_SCHEMA_VERSION,
            package_version=package_version,
        )


def get_builtin_prompt(slot: str) -> BuiltinPrompt:
    """Return the shipped template for ``slot`` (for example ``"paper_card"``).

    Raises:
        KeyError: No shipped template has that slot.
    """
    for prompt in iter_builtin_prompts():
        if prompt.slot == slot:
            return prompt
    raise KeyError(f"no built-in zsum prompt for slot {slot!r}")
