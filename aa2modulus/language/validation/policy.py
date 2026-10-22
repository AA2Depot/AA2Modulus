"""Run every policy check against the registry in a stable order."""

from __future__ import annotations

from ...metadata.snapshot import MetadataSnapshot
from ..policy import LanguagePolicy
from .literals import validate_literals
from .members import validate_member_forms
from .names import (
    configured_names,
    validate_names,
    validate_namespace_roots,
    validate_preferred_names,
    validate_protected_names,
)
from .operators import validate_action_defaults, validate_operators
from .roles import (
    validate_descriptions,
    validate_parameter_names,
    validate_parameter_roles,
    validate_result_roles,
)
from .visibility import (
    validate_acknowledgeable,
    validate_defects,
    validate_event_values,
    validate_readable,
)


def validate_policy(policy: LanguagePolicy, metadata: MetadataSnapshot) -> tuple[str, ...]:
    """Every policy error, in a stable order: native targets first, then authored choices."""

    errors = validate_operators(policy, metadata)
    errors.extend(validate_action_defaults(policy, metadata))
    errors.extend(validate_preferred_names(policy, metadata))
    names = configured_names(policy)
    errors.extend(validate_names(policy, metadata, names))
    errors.extend(validate_readable(policy, metadata))
    errors.extend(validate_defects(policy, metadata))
    errors.extend(validate_event_values(policy, metadata))
    errors.extend(validate_result_roles(policy, metadata))
    errors.extend(validate_parameter_names(policy, metadata))
    errors.extend(validate_parameter_roles(policy, metadata))
    errors.extend(validate_descriptions(policy, metadata))
    errors.extend(validate_member_forms(policy, metadata))
    errors.extend(validate_literals(policy, metadata))
    errors.extend(validate_namespace_roots(policy, names))
    errors.extend(validate_protected_names(policy, metadata, names))
    errors.extend(validate_acknowledgeable(policy))
    return tuple(errors)
