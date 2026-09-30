-- Governed vocabularies: entity kinds and relation types.
-- Only relation types the Neo4j corpus actually uses, plus the kind registry
-- from "23 Term Kinds and Properties".
BEGIN;

-- 'Term' is a kind like any other; what makes it the glossary is that it is the
-- one kind required to carry a definition.
INSERT INTO kinds (kind, requires_definition, props, note) VALUES
  ('Term',     true,  '[]',
     'a glossary entry: a defined word analysts use'),
  ('Person',   false, '[{"name":"title"},{"name":"department"}]',
     'an individual the glossary refers to; named, not defined'),
  ('Business', false, '[{"name":"ticker"},{"name":"jurisdiction"}]',
     'an organisation the glossary refers to');

INSERT INTO relation_types (code, label, inverse_code, is_symmetric, is_transitive, note) VALUES
  ('COMPUTED_FROM', 'computed from', NULL,  false, false, 'subject''s value is derived from object'),
  ('PART_OF',       'part of',       NULL,  false, true,  'component-of; transitive'),
  ('RELATED_TO',    'related to',    NULL,  true,  false, 'undirected association'),
  ('FILTER_FOR',    'filter for',    NULL,  false, false, 'subject scopes/filters the object');

COMMIT;
