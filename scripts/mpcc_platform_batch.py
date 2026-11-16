"""Explicit platform-only migration for a new validation run, preserving old runners."""

from pathlib import Path

from scripts import mpcc_adaptive_batch as batch

MIGRATED = batch.h.ROOT / "logs/mpcc-tuning/platform-prep-kernel42-20261103"


def main() -> None:
    """Verify the recorded migration and use its exact preparation manifest."""
    record = batch.h.read(MIGRATED / "migration.json")
    assert batch.h.sha(Path(__file__)) == record["wrapper_sha256"]
    assert batch.h.sha(MIGRATED / "manifest.json") == record["new_manifest_sha256"]
    assert batch.h.sha(batch.PREP / "manifest.json") == record["old_manifest_sha256"]
    batch.PREP = MIGRATED
    batch.main()


if __name__ == "__main__":
    main()
