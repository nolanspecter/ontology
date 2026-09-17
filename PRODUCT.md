# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Three groups, one internal org:

- **Editors** — any employee with edit rights; propose new terms and edits to existing ones (definitions, formulas, relationships, categories, typed "kind" properties).
- **Reviewers/Admins** — a small, trusted set of maintainers who approve or reject proposed changes before they go live; admins additionally bypass review for their own changes and can delete terms.
- **Read audience** — the whole org (any logged-in employee) browsing published terms, plus AI agents connecting over MCP (read-only, published-only, no login).

## Product Purpose

A shared corporate glossary/knowledge base for business and financial terms (e.g. "Cash", "Receivable Cash", "Yield") — definitions, formulas, categories, typed properties, and typed relationships between terms (e.g. `COMPUTED_FROM`). Exists to replace an Obsidian vault that couldn't support multi-user editing or a review gate. Success = the org has one trustworthy, current source of truth for term definitions, safe to let many people edit because nothing reaches readers (human or agent) without a reviewer's sign-off.

## Positioning

Not a wiki and not a database admin panel: it's the one place term definitions carry an enforced draft → pending_review → published state machine plus a full audit trail, and the same published data is queryable by AI agents (via MCP) with zero risk of an agent ever seeing an unapproved edit.

## Operating Context

Runs as a normal internal web app (FastAPI + Jinja2 + HTMX, no SPA framework) alongside a separate, unauthenticated read-only MCP/HTTP surface for agents. In dev, auth is a stubbed shared-password login (no real SSO yet). Core workflows: search/browse terms, view a term's detail (definition, formula, category, related terms, kind + extra properties, pending-edit callout, change history), create/edit a term, add/remove relationships and categories, and — for reviewers — work a review queue with old-vs-new diffs and approve/reject.

## Capabilities and Constraints

- Term fields: name, definition, formula (optional), an optional structured "kind" (e.g. Person) with defined properties, plus arbitrary extra name/value properties, a category, and any number of typed relationships to other terms.
- Draft terms are only visible to their creator (and admins) until submitted and approved; published terms are visible to everyone.
- Edits to published terms are version-locked (stale-edit conflict banner) and go through the same review gate as new terms, unless the editor is an admin.
- Every approval/rejection/edit is recorded in a per-term history log, visible on the term's detail page.
- No real SSO yet — auth is a known constraint, not a design input.
- Read surface for agents (MCP) has no UI of its own; only the human-facing web UI is in scope for this redesign.

## Brand Commitments

None. "Corporate KB" is a placeholder name; no existing logo, palette, or brand identity constrains this redesign — visual direction is fully open.

## Evidence on Hand

No real content beyond what's already seeded in the dev database (test terms like "Cash", "Yield"). No testimonials, case studies, or press — none should be fabricated.

## Product Principles

1. Nothing reaches a reader (person or agent) without going through the draft → review → published gate — the UI must always make current state (draft/pending/published) legible, never ambiguous.
2. Small trusted reviewer group, wide editor and reader group — the UI should make the reviewer's job (compare, approve/reject with reason) fast and low-risk, since they're the bottleneck protecting data quality.
3. This is an internal operating tool, not a marketing surface — clarity, scanability, and task speed outrank visual flourish, but "internal tool" is not an excuse for a generic, uninspired look.
4. Every entity (term, relationship, category, kind/property) is user-defined and open-ended (arbitrary extra properties, arbitrary relation types) — the UI must stay legible even as the schema-free parts grow unpredictably.

## Accessibility & Inclusion

No specific compliance target (WCAG or otherwise) was set; follow good general accessibility practice by default.
