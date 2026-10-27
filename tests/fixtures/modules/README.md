# Native module inputs

Nine extensionless AAUnlimited modules are compatibility inputs for the format
documented against pinned revision `312c658b256f41771a5488fbf79a677d7b4551a8`.
`sha256.json` records their input integrity hashes. The hashes protect these
original files from accidental edits; they do not provide decoded expectations.

The test suite compares a hand-authored Race-Human source module with its native
bytes, and exercises decompile/recompile identity for each fixture. Observer is the only
fixture whose description spans several CRLF-separated lines. Expected
wire details come from the source format evidence and explicit wire-building
cases in `tests/binary/`.

Run `mise run test -m binary` for binary codec and fixture checks. These tests use
committed resources without a source checkout.
