"""Hash-chain primitives for the audit event log.

Each row's ``record_hash`` commits to that row's own fields plus the
previous row's hash, so editing, reordering, or deleting a stored row
breaks the chain from that point forward. This module is pure and has no
SQLite dependency on purpose: ``audit/store.py`` reads rows out of SQLite
as plain dicts and hands them to ``verify_chain`` here, which keeps the
chain logic isolated and unit-testable without a database.

Scope, stated plainly (see docs/ACCOUNTABILITY.md for the full version):
this proves AgentBench's own local audit.db wasn't silently edited after
it was written. It says nothing about whether the underlying agent
session log was edited before AgentBench read it, and it is not hardened
against a determined local attacker who edits a row and recomputes the
rest of the chain to match -- plain SHA-256 chaining catches accidental
corruption and naive edits, not that.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS = "GENESIS"

# The row's own content, hashed together with the previous row's hash.
# Deliberately excludes "record_hash" (what we're computing) and
# "prev_hash" (already folded into the digest input separately below).
_HASH_FIELDS = (
    "id",
    "ts",
    "agent",
    "session_id",
    "cwd",
    "model",
    "step_index",
    "rule",
    "severity",
    "title",
    "detail",
    "path",
    "source_path",
    "source_size",
    "source_mtime",
)


def _canonical_json(row: dict[str, Any]) -> str:
    payload = {key: row.get(key) for key in _HASH_FIELDS}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(row: dict[str, Any], prev_hash: str) -> str:
    """Compute the record_hash for one row given the previous row's hash."""
    digest = hashlib.sha256()
    digest.update(prev_hash.encode("utf-8"))
    digest.update(_canonical_json(row).encode("utf-8"))
    return digest.hexdigest()


def verify_chain(rows: list[dict[str, Any]]) -> int | None:
    """Walk rows (already ordered by id) and verify each record_hash.

    Returns the id of the first row whose stored record_hash doesn't match
    what compute_hash() recomputes from its content and the actual previous
    hash, or None if the whole chain checks out. An empty chain is
    trivially intact.
    """
    prev_hash = GENESIS
    for row in rows:
        expected = compute_hash(row, prev_hash)
        actual = row.get("record_hash")
        if actual != expected:
            return row.get("id")
        prev_hash = actual
    return None
