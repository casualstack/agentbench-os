"""Durable, tamper-evident record of alerts AgentBench has raised."""

from agentbench.accountability.audit.chain import GENESIS, compute_hash, verify_chain
from agentbench.accountability.audit.store import AuditStore, default_db_path, record_from_alert

__all__ = [
    "GENESIS",
    "AuditStore",
    "compute_hash",
    "default_db_path",
    "record_from_alert",
    "verify_chain",
]
