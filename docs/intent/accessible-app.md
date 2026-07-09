# Intent: AgentBench Accessible App (v1)

Confirmed with founder 2026-07-09.

- **Outcome:** Cross-platform desktop app — the "ChatGPT moment" for agent accountability — that auto-detects Cursor/Claude Code sessions on the machine, watches them live, and raises plain-English alerts when an agent cheats (deleted test assertion, out-of-scope file touch, network call). Zero config, no JSON, code never leaves the laptop.
- **User:** Devs who already use Cursor/Claude Code daily but would never write an oracle task file. Less-technical users (founders/PMs) come in a later phase; copy should already read plain enough for them.
- **Why now:** The advanced developer tool (CLI, oracles, CI gate) is done and tested. The accessible layer is the missing piece of the Casualstack arc and the launchable product.
- **Success:** Strangers adopt it — 5+ people the founder doesn't know install it and report it caught something or say "I'd use this."
- **Constraint:** Windows, macOS, and Linux supported from day one.
- **Out of scope (v1):** Hosted SaaS/accounts, less-technical-audience version, live LLM calls, Witness/ContextOS features. Cursor auto-detection is best-effort; Claude Code watching is the guaranteed first-class path.
