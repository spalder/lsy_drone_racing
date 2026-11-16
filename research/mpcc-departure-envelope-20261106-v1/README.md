# Compact MPCC departure-envelope research archive

This project-local directory works without Ask-USB. Read RESULTS.md for the stopped comparison and its completed independent audit.

- `compact-evidence.tar.zst`: retained study records, telemetry, contacts, timing, source snapshots, provenance, failures and reports for v1 and v2.
- `retention-manifest.json`: every retained file’s size and SHA-256, plus the exact list of omitted bulk arrays.
- `VERIFIED.json`: complete archive-content verification receipt.
- `SHA256SUMS`: checksums of the archive and top-level reports/manifests.

Extract with `tar --zstd -xf compact-evidence.tar.zst`. Original USB data is not deleted or modified. The archive deliberately omits full horizon, warm-start and path arrays to fit the local filesystem. It is a compact export, not a lossless copy of all raw research data.

Racing has stopped. Both the completed audit and the aborted first study are preserved. Production code, controller settings, dependencies and prior studies were not changed. Nothing was staged or committed.
