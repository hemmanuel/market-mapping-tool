import hashlib
from typing import Any, Optional


TASK_FRAME_KEY_MAX_LENGTH = 512
PARTITION_KEY_MAX_LENGTH = 255
ARTIFACT_KEY_MAX_LENGTH = 512
HASH_PREFIX = "sha256:"


def normalize_persistence_key(value: Any, *, max_length: int) -> Optional[str]:
    """Return a stable, bounded key for persistence-only columns.

    Raw URLs and queries remain in JSON payloads and artifact metadata, while
    ledger key columns store either the original short value or a stable digest
    when the source string would overflow the schema column.
    """
    if value is None:
        return None

    sanitized = str(value).replace("\x00", "")
    if len(sanitized) <= max_length:
        return sanitized

    return f"{HASH_PREFIX}{hashlib.sha256(sanitized.encode('utf-8')).hexdigest()}"
