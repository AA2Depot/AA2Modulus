"""The SIR node base class and its non-serialized annotations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Self, TypedDict

from ..core.locations import BinaryLocation, SourceSpan


class NodeAnnotations(TypedDict, total=False):
    source_span: SourceSpan | None
    binary_location: BinaryLocation | None
    raw_reference: bool


@dataclass(frozen=True, slots=True)
class SerializedNode(ABC):
    """SIR conversion contract and non-serialized diagnostic/provenance annotations."""

    source_span: SourceSpan | None = field(
        default=None,
        compare=False,
        repr=False,
        kw_only=True,
    )
    binary_location: BinaryLocation | None = field(
        default=None,
        compare=False,
        repr=False,
        kw_only=True,
    )
    raw_reference: bool = field(
        default=False,
        compare=False,
        repr=False,
        kw_only=True,
    )

    @abstractmethod
    def to_ir(self) -> dict[str, Any]: ...

    @classmethod
    @abstractmethod
    def from_ir(cls, data: Mapping[str, Any]) -> Self: ...
