"""Durable, tamper-evident record of alerts AgentBench has raised."""

from agentbench.accountability.audit.chain import GENESIS, compute_hash, verify_chain

__all__ = [
    "GENESIS",
    "compute_hash",
    "verify_chain",
]
