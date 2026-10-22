"""A malformed generated registry fails with file and record context."""

from __future__ import annotations

import pytest

from aa2modulus.metadata.loader import load_metadata
from aa2modulus.metadata.schema import MetadataError
from tests.support.registry import copied_registry


def test_registry_record_identity_error_names_file_and_record(tmp_path):
    def edit(document):
        document["entries"]["1"]["id"] = 999

    directory = copied_registry(tmp_path, edit, filename="actions.json")
    with pytest.raises(MetadataError) as failure:
        load_metadata(directory)
    message = str(failure.value)
    assert str(directory / "actions.json") in message
    assert "actions.json.entries.1.id does not match its key" in message


def test_unreadable_registry_json_names_the_file(tmp_path):
    directory = copied_registry(tmp_path, lambda document: None)
    path = directory / "events.json"
    path.write_text('{"entries": ', encoding="utf-8")
    with pytest.raises(MetadataError, match=r"events\.json"):
        load_metadata(directory)
