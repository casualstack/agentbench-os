"""Tests for the pure hash-chain primitives (no SQLite involved)."""

from __future__ import annotations

from agentbench.accountability.audit.chain import GENESIS, compute_hash, verify_chain


def _row(id_, **overrides):
    row = {
        "id": id_,
        "ts": "2026-07-15T00:00:00Z",
        "agent": "claude-code",
        "session_id": "s1",
        "cwd": "C:\\work\\myrepo",
        "model": "claude-x",
        "step_index": 0,
        "rule": "deleted_assertion",
        "severity": "critical",
        "title": "Deleted a test assertion",
        "detail": "The agent removed a check.",
        "path": "tests/test_calc.py",
        "source_path": "C:\\home\\.claude\\projects\\p\\s1.jsonl",
        "source_size": 1234,
        "source_mtime": 1700000000.0,
    }
    row.update(overrides)
    return row


def _chain(*rows_without_hash):
    """Build a valid chained sequence from raw row dicts (mutates copies)."""
    chained = []
    prev_hash = GENESIS
    for row in rows_without_hash:
        row = dict(row)
        row["prev_hash"] = prev_hash
        row["record_hash"] = compute_hash(row, prev_hash)
        chained.append(row)
        prev_hash = row["record_hash"]
    return chained


def test_compute_hash_is_deterministic():
    row = _row(1)
    assert compute_hash(row, GENESIS) == compute_hash(row, GENESIS)


def test_compute_hash_changes_when_a_field_changes():
    row = _row(1)
    other = _row(1, detail="different detail")
    assert compute_hash(row, GENESIS) != compute_hash(other, GENESIS)


def test_compute_hash_changes_when_prev_hash_changes():
    row = _row(1)
    assert compute_hash(row, GENESIS) != compute_hash(row, "some-other-hash")


def test_verify_chain_empty_is_intact():
    assert verify_chain([]) is None


def test_verify_chain_intact_multi_row_chain():
    rows = _chain(_row(1), _row(2), _row(3, severity="warning"))
    assert verify_chain(rows) is None


def test_verify_chain_first_row_uses_genesis():
    rows = _chain(_row(1))
    assert rows[0]["prev_hash"] == GENESIS
    assert verify_chain(rows) is None


def test_verify_chain_detects_content_tamper():
    rows = _chain(_row(1), _row(2), _row(3))
    rows[1]["detail"] = "edited after the fact"  # tamper row id=2, no rehash
    assert verify_chain(rows) == 2


def test_verify_chain_detects_tamper_at_first_broken_row_not_a_later_one():
    rows = _chain(_row(1), _row(2), _row(3), _row(4))
    rows[2]["detail"] = "edited"  # id=3 is the first break
    assert verify_chain(rows) == 3


def test_verify_chain_detects_hash_field_tamper():
    rows = _chain(_row(1), _row(2))
    rows[0]["record_hash"] = "0" * 64
    assert verify_chain(rows) == 1
