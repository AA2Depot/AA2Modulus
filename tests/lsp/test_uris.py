"""Canonical native file identities and portable file-URI parsing."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aa2modulus.lsp.protocol.uris import file_identity, file_uri_path, identity_uri


def test_file_identity_decodes_and_canonicalizes_native_file_uri(tmp_path):
    target = tmp_path / "folder with space" / "snowman-☃.aa2m"
    uri = target.as_uri()

    assert file_identity(uri) == str(target.resolve())
    localhost_uri = uri.replace("file:///", "file://localhost/", 1)
    assert file_identity(localhost_uri) == str(target.resolve())


@pytest.mark.skipif(os.name != "nt", reason="needs a case-insensitive Windows filesystem")
def test_file_identity_keeps_on_disk_casing_for_case_variant_uri(tmp_path):
    target = tmp_path / "Library.aa2mi"
    target.write_text("", encoding="utf-8")

    assert file_identity(Path(str(target).lower()).as_uri()) == str(target.resolve())


@pytest.mark.parametrize(
    "uri",
    [
        "untitled:Untitled-1",
        "https://example.test/a.aa2m",
        "file:relative/path",
        "file:///a%ZZ",
        "file:///bad%FFname",
        "file:///a?query=1",
        "file:///a#fragment",
        "file:///bad%00name",
        "file://bad%00host/share/a.aa2m",
    ],
)
def test_file_identity_rejects_nonlocal_or_malformed_uri(uri):
    assert file_identity(uri) is None


def test_file_uri_path_parses_windows_drive_and_unc_independent_of_host():
    assert file_uri_path("file:///C:/folder/a%20b.aa2m", windows=True) == ("C:\\folder\\a b.aa2m")
    assert file_uri_path("file://server/share/folder/a.aa2m", windows=True) == (
        "\\\\server\\share\\folder\\a.aa2m"
    )
    assert file_uri_path("file:///C:/folder/a.aa2m") is None
    assert file_uri_path("file://server/share/a", windows=False) is None
    if os.name != "nt":
        assert file_identity("file://server/share/a.aa2m") is None


def test_identity_uri_emits_a_canonical_encoded_native_file_uri(tmp_path):
    target = tmp_path / "a folder" / "file#name.aa2m"
    canonical = str(target.resolve())

    assert identity_uri(canonical) == Path(canonical).as_uri()
    assert file_identity(identity_uri(canonical)) == canonical


def test_uri_helpers_reject_wrong_types_and_nul_identities():
    with pytest.raises(TypeError, match="identity"):
        identity_uri(None)
    with pytest.raises(ValueError, match="NUL"):
        identity_uri("a\x00b")
    assert file_uri_path("file:///bad\x00path") is None
