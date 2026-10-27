"""Immutable per-operation context shared by the source compiler pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..language.catalog.build import language_catalog
from ..language.catalog.model import LanguageCatalog
from ..language.loader import load_language_policy
from ..language.policy import LanguagePolicy
from ..metadata.loader import load_metadata
from ..metadata.snapshot import MetadataSnapshot
from .limits import SourceLimits, resolve_source_limits
from .resolver import SourceResolver


@dataclass(frozen=True, slots=True)
class SourceContext:
    """Resolved inputs shared by parse, bind, lower, validate, and write."""

    metadata: MetadataSnapshot
    source_policy: LanguagePolicy
    filename: str = "<source>"
    source_limits: SourceLimits = field(default_factory=SourceLimits)
    import_base: Path | None = None
    source_resolver: SourceResolver | None = None
    _catalog: LanguageCatalog | None = field(default=None, repr=False, compare=False, kw_only=True)

    @property
    def catalog(self) -> LanguageCatalog:
        assert self._catalog is not None
        return self._catalog

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_limits", resolve_source_limits(self.source_limits))
        if self.import_base is not None and self.source_resolver is not None:
            raise ValueError("import_base and source_resolver cannot be supplied together")
        if self.import_base is not None:
            object.__setattr__(self, "import_base", Path(self.import_base).resolve())
        if not self.filename:
            raise ValueError("filename cannot be empty")
        if (
            self._catalog is None
            or self._catalog.metadata is not self.metadata
            or self._catalog.policy is not self.source_policy
        ):
            object.__setattr__(
                self, "_catalog", language_catalog(self.metadata, self.source_policy)
            )

    @classmethod
    def create(
        cls,
        *,
        filename: str = "<source>",
        metadata: MetadataSnapshot | None = None,
        source_limits: SourceLimits | None = None,
        import_base: str | Path | None = None,
        source_resolver: SourceResolver | None = None,
    ) -> SourceContext:
        if not filename:
            raise ValueError("filename must be a non-empty string")
        resolved_metadata = load_metadata() if metadata is None else metadata
        return cls(
            resolved_metadata,
            load_language_policy(metadata=resolved_metadata),
            filename,
            resolve_source_limits(source_limits),
            None if import_base is None else Path(import_base),
            source_resolver,
        )

    @classmethod
    def resolve(
        cls,
        context: SourceContext | None = None,
        *,
        filename: str | None = None,
        metadata: MetadataSnapshot | None = None,
        source_limits: SourceLimits | None = None,
        import_base: str | Path | None = None,
        source_resolver: SourceResolver | None = None,
    ) -> SourceContext:
        """Reuse an operation context, rejecting conflicting explicit inputs.

        Matching object identities and equal filenames/limits are allowed.
        """

        if context is None:
            return cls.create(
                filename="<source>" if filename is None else filename,
                metadata=metadata,
                source_limits=source_limits,
                import_base=import_base,
                source_resolver=source_resolver,
            )
        for name, conflict in (
            (
                "import_base",
                import_base is not None and Path(import_base).resolve() != context.import_base,
            ),
            (
                "source_resolver",
                source_resolver is not None and source_resolver is not context.source_resolver,
            ),
            ("filename", filename is not None and filename != context.filename),
            ("metadata", metadata is not None and metadata is not context.metadata),
            (
                "source_limits",
                source_limits is not None
                and resolve_source_limits(source_limits) != context.source_limits,
            ),
        ):
            if conflict:
                raise ValueError(f"{name} conflicts with the supplied SourceContext")
        return context
