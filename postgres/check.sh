#!/bin/sh
# One runnable check for the v3 ontology schema. Exits non-zero on any failure.
set -e
PSQL="docker exec -i ontology-pg psql -U ontology -d ontology -v ON_ERROR_STOP=1 -q"

$PSQL -f - < 04_check.sql 2>&1 | grep -q 'CHECKS PASSED' \
  || { echo "FAIL: 04_check.sql"; exit 1; }

# term_needs_definition is a table CHECK, not the registry trigger. Prove it by
# switching the trigger off - needs a transaction with no pending trigger events.
$PSQL -c "BEGIN; ALTER TABLE entities DISABLE TRIGGER entities_check_props;
          INSERT INTO entities (kind, name, definition, created_by)
          VALUES ('Term', 'Không có định nghĩa', NULL, 'admin@corp.com');
          ROLLBACK;" 2>&1 | grep -q 'term_needs_definition' \
  || { echo "FAIL: a Term survived without a definition once the trigger was off"; exit 1; }

echo "CHECKS PASSED"
