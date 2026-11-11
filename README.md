# CodeLineage

**Role:** the source→destination identity and ownership record.

This repository is the durable specification and memory for the CodeLineage role in the
WatchCodes factory. Read this file before doing anything here.

---

## Responsibility

CodeLineage answers one question with evidence: **can we prove this destination is the
branded descendant of that source, and that we own it?**

1. Record a `RepositoryMapping` for every verified destination:
   `source`, `destination`, `sha`, `license`, `status`, `verified_at`.
2. Verify that the destination really exists under the declared owner, at the declared
   SHA, with the declared licence.
3. Keep the upstream URL of every mapping. Branding the destination must never erase the
   source it came from.
4. Provide the mapping table the rest of the factory reads. `100ways` must be able to stop
   preserving an unmapped foreign URL only because a mapping here says the destination is
   verified.

## Why it exists separately

The brander in `NastechResearch/100Ways` currently preserves any GitHub identifier whose
owner is not ours, because rewriting one produces a 404. That preservation is correct and
it is also a blind spot: the inherited name survives. A mapping table is what lets the
brander replace a preserved URL with a real destination **only once that destination is
verified**. Order is always: destination verified → mapping recorded → URL rewritten →
gate.

## What it never does

- Never creates, brands, verifies or publishes a repository.
- Never records a mapping it has not verified.
- Never deletes history. A superseded mapping is marked superseded, not removed.

## Contracts

| Direction | Contract | Minimum fields |
|---|---|---|
| produces | `RepositoryMapping` | `source`, `destination`, `sha`, `license`, `status`, `verified_at` |
| consumes | `MigrationReport` | to learn what was actually created and verified |

## Status it owns

Not a rung on the creation ladder. It mirrors the status it verifies and refuses to
record `VERIFIED` without evidence.

## Build order

Deliberately last. The design note is explicit: build it as an independent record **only
when a second consumer exists**. The first consumer is the brander's mapping table; until
then, mappings live with the reports that produced them.

## Related repositories

- `WatchCodes/RepoAtlas` — decides and names the destination
- `WatchCodes/CodeFoundry` — proves the destination exists
- `WatchCodes/SourceSentinel` — watches the upstream this record names
- `WatchCodes/NastechBridge` — stores the reports these records are derived from
- `NastechResearch/100Ways` — the brander that consumes the mapping table
