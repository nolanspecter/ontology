# Data Model

## Nodes

- `(:Term {name, definition, formula, status, version, createdBy})` — a business term with an official definition
- `(:Draft {definition, formula, status})` — pending changes to a term (status: "pending_review")
- `(:Change {field, oldValue, newValue, changedBy, changedAt, action, reason})` — append-only audit record; `reason` added when reject flows started requiring one, see [[07 Web UI]]

## Relationships

- `(t:Term)-[:DRAFT_OF]->(d:Draft)` — a draft is an edit to term t
- `(t:Term)-[:HAS_CHANGE]->(c:Change)` — term t has an audit record c
