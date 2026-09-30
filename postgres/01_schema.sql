-- Ontology schema, v3. Single file, run against an empty database.
--
--   entities        one row per thing, CARRYING ITS OWN CANONICAL NAME
--   labels          the other names that thing answers to (synonyms only)
--   relation_types  governed predicate vocabulary, aliases included
--   relations       the graph
--   kinds           what a row of each kind must carry
--   drafts / revisions / review_events   workflow, state history, audit
--
-- Names: the canonical name is a NOT NULL column on entities, so a valid named
-- row is a single INSERT and "everything has a name" is enforced by the column
-- itself rather than a deferred constraint trigger. `labels` holds only the
-- alternates. The cost of that choice, stated plainly: the set of all names
-- now spans two tables, so "one name means one thing in one category" is two
-- unique indexes plus two cross-checking triggers instead of one index.
--
-- Run: psql -U ontology -d ontology -f 01_schema.sql

BEGIN;

DROP SCHEMA public CASCADE;
CREATE SCHEMA public;

CREATE EXTENSION citext   WITH SCHEMA public;
CREATE EXTENSION unaccent WITH SCHEMA public;
CREATE EXTENSION pg_trgm  WITH SCHEMA public;

-- ---------------------------------------------------------------- normalisation
-- norm(): what uniqueness is judged on. Case- and whitespace-insensitive but
-- DIACRITIC-SENSITIVE, because Vietnamese tone marks are semantic.
CREATE FUNCTION norm(t text) RETURNS text
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT lower(regexp_replace(btrim(t), '\s+', ' ', 'g')) $$;

-- fold(): what search matches on. ASCII-folded, so a US keyboard reaches an
-- accented name. Never unique - collisions are resolved by ranked candidates.
CREATE FUNCTION fold(t text) RETURNS text
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT public.unaccent('public.unaccent', norm(t)) $$;

-- The match tiers, defined once and used over both name sources.
CREATE FUNCTION match_tier(n text, f text, q text) RETURNS text
  LANGUAGE sql STABLE AS
$$ SELECT CASE WHEN n = norm(q)              THEN 'exact'
               WHEN f = fold(q)              THEN 'folded'
               WHEN f LIKE fold(q) || '%'    THEN 'prefix'
               ELSE 'fuzzy' END $$;

CREATE FUNCTION match_score(n text, f text, q text) RETURNS real
  LANGUAGE sql STABLE AS
$$ SELECT CASE WHEN n = norm(q)              THEN 1.0
               WHEN f = fold(q)              THEN 0.9
               WHEN f LIKE fold(q) || '%'    THEN 0.75
               ELSE similarity(f, fold(q)) END::real $$;

-- ---------------------------------------------------------------------- enums
CREATE TYPE user_role     AS ENUM ('viewer', 'editor', 'reviewer', 'admin');
CREATE TYPE entity_status AS ENUM ('draft', 'pending_review', 'published', 'deprecated', 'merged');
CREATE TYPE draft_status  AS ENUM ('draft', 'pending_review');

-- ---------------------------------------------------------------------- people
CREATE TABLE users (
  email      citext    PRIMARY KEY CHECK (email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
  role       user_role NOT NULL DEFAULT 'viewer',
  created_at timestamptz NOT NULL DEFAULT now()
);

-- -------------------------------------------------------------------- taxonomy
-- Categories are the disambiguation context: the same name may mean different
-- things in two of them, so they are what name uniqueness is scoped to.
CREATE TABLE categories (
  id   int  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL UNIQUE CHECK (name = btrim(name) AND name <> ''),
  note text
);

CREATE TABLE kinds (
  kind                text    PRIMARY KEY CHECK (kind ~ '^[A-Z][A-Za-z0-9]*$'),
  requires_definition boolean NOT NULL DEFAULT true,
  props               jsonb   NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(props) = 'array'),
  note                text,
  CONSTRAINT term_is_always_defined CHECK (kind <> 'Term' OR requires_definition)
);

-- -------------------------------------------------------------------- entities
CREATE TABLE entities (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind        text NOT NULL REFERENCES kinds(kind),
  name        text NOT NULL CHECK (btrim(name) <> ''),
  name_lang   text NOT NULL DEFAULT 'vi' CHECK (name_lang ~ '^[a-z]{2}$'),
  category_id int  REFERENCES categories(id),
  definition  text CHECK (definition IS NULL OR btrim(definition) <> ''),
  formula     text CHECK (formula IS NULL OR btrim(formula) <> ''),
  props       jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(props) = 'object'),
  status      entity_status NOT NULL DEFAULT 'draft',
  version     int  NOT NULL DEFAULT 1 CHECK (version >= 1),
  created_by  citext NOT NULL REFERENCES users(email),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  merged_into uuid REFERENCES entities(id),
  name_norm text GENERATED ALWAYS AS (norm(name)) STORED,
  name_fold text GENERATED ALWAYS AS (fold(name)) STORED,
  CONSTRAINT merged_has_target CHECK ((status = 'merged') = (merged_into IS NOT NULL)),
  CONSTRAINT no_self_merge     CHECK (merged_into IS DISTINCT FROM id),
  -- A glossary term MUST be defined. Duplicated from the kind registry on
  -- purpose: a CHECK cannot be skipped by session_replication_role, cannot be
  -- turned off with DISABLE TRIGGER, and does not rely on a registry row.
  CONSTRAINT term_needs_definition CHECK (kind <> 'Term' OR definition IS NOT NULL)
);
-- Half one of name uniqueness: canonical names, scoped to language + category.
-- Partial, because a merged tombstone keeps its name as history and must not go
-- on claiming it - the survivor takes that name over as a synonym.
CREATE UNIQUE INDEX entity_name_in_category
  ON entities (name_lang, name_norm, category_id) NULLS NOT DISTINCT
  WHERE status <> 'merged';
CREATE INDEX entities_kind       ON entities (kind);
CREATE INDEX entities_status     ON entities (kind, status);
CREATE INDEX entities_category   ON entities (category_id);
CREATE INDEX entities_merged     ON entities (merged_into) WHERE merged_into IS NOT NULL;
CREATE INDEX entities_name_fold  ON entities (name_fold);
CREATE INDEX entities_name_trgm  ON entities USING gin (name_fold gin_trgm_ops);

CREATE FUNCTION check_entity_props() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE needs_def boolean; spec jsonb; missing text;
BEGIN
  SELECT requires_definition, props INTO needs_def, spec FROM kinds WHERE kind = NEW.kind;
  IF needs_def AND coalesce(btrim(NEW.definition), '') = '' THEN
    RAISE EXCEPTION 'a % entity requires a definition', NEW.kind;
  END IF;
  SELECT string_agg(p->>'name', ', ' ORDER BY p->>'name') INTO missing
    FROM jsonb_array_elements(spec) p
   WHERE coalesce((p->>'required')::boolean, false)
     AND coalesce(btrim(NEW.props->>(p->>'name')), '') = '';
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION '% entity is missing required properties: %', NEW.kind, missing;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER entities_check_props
  BEFORE INSERT OR UPDATE OF kind, props, definition ON entities
  FOR EACH ROW EXECUTE FUNCTION check_entity_props();

-- ---------------------------------------------------------------------- labels
-- The OTHER names: synonyms, abbreviations, translations. The canonical name is
-- not in here - it is entities.name - so there is exactly one row per name in
-- the database and nothing to keep in sync.
CREATE TABLE labels (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  entity_id   uuid   NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  text        text   NOT NULL CHECK (btrim(text) <> ''),
  lang        text   NOT NULL DEFAULT 'vi' CHECK (lang ~ '^[a-z]{2}$'),
  source      text,                      -- 'demo', 'merge:<uuid>', 'manual', ...
  -- copied from the owning entity by trigger, never by the caller; it exists so
  -- synonym uniqueness can be scoped to a category the same way names are
  category_id int REFERENCES categories(id),
  norm text GENERATED ALWAYS AS (norm(text)) STORED,
  fold text GENERATED ALWAYS AS (fold(text)) STORED
);
-- Half two of name uniqueness: synonyms, same scope.
CREATE UNIQUE INDEX label_unique_in_category
  ON labels (lang, norm, category_id) NULLS NOT DISTINCT;
CREATE INDEX label_entity    ON labels (entity_id);
CREATE INDEX label_fold      ON labels (fold);
CREATE INDEX label_fold_trgm ON labels USING gin (fold gin_trgm_ops);

-- --------------------------------------------- the two halves, joined by hand
-- The unique indexes above cannot see each other, so these triggers close the
-- cross terms: a canonical name may not equal a synonym in the same language
-- and category, and vice versa. ENABLE ALWAYS below, so a bulk load running as
-- session_replication_role = 'replica' does not skip them.
CREATE FUNCTION entity_name_free() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = 'merged' THEN RETURN NEW; END IF;   -- a tombstone claims nothing
  IF EXISTS (SELECT 1 FROM labels l
              WHERE l.lang = NEW.name_lang
                AND l.norm = norm(NEW.name)
                AND l.category_id IS NOT DISTINCT FROM NEW.category_id
                AND l.entity_id <> NEW.id) THEN
    RAISE EXCEPTION '% is already a synonym in this category', NEW.name;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER entities_name_free
  BEFORE INSERT OR UPDATE OF name, name_lang, category_id ON entities
  FOR EACH ROW EXECUTE FUNCTION entity_name_free();

-- One BEFORE trigger does both jobs on labels, so their order is not a
-- question of which trigger name sorts first.
CREATE FUNCTION label_before_write() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  SELECT category_id INTO NEW.category_id FROM entities WHERE id = NEW.entity_id;
  IF EXISTS (SELECT 1 FROM entities e
              WHERE e.name_lang = NEW.lang
                AND e.name_norm = norm(NEW.text)
                AND e.category_id IS NOT DISTINCT FROM NEW.category_id
                AND e.status <> 'merged'
                AND e.id <> NEW.entity_id) THEN
    RAISE EXCEPTION '% is already the name of an entity in this category', NEW.text;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER labels_before_write
  BEFORE INSERT OR UPDATE OF entity_id, text, lang, category_id ON labels
  FOR EACH ROW EXECUTE FUNCTION label_before_write();

-- Re-categorising an entity moves its synonyms with it, which re-runs the
-- check above against the new category.
CREATE FUNCTION recategorise_labels() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE labels SET category_id = NEW.category_id WHERE entity_id = NEW.id;
  RETURN NULL;
END $$;
CREATE TRIGGER entities_recategorise AFTER UPDATE OF category_id ON entities
  FOR EACH ROW EXECUTE FUNCTION recategorise_labels();

-- ------------------------------------------------------------- relation types
CREATE TABLE relation_types (
  code           text PRIMARY KEY CHECK (code ~ '^[A-Z][A-Z0-9_]*$'),
  label          text,
  canonical_code text REFERENCES relation_types(code) ON UPDATE CASCADE,
  inverse_code   text REFERENCES relation_types(code),
  is_symmetric   boolean NOT NULL DEFAULT false,
  is_transitive  boolean NOT NULL DEFAULT false,
  note           text,
  CONSTRAINT alias_not_self CHECK (canonical_code IS DISTINCT FROM code),
  CONSTRAINT alias_is_bare  CHECK (canonical_code IS NULL
      OR (inverse_code IS NULL AND NOT is_symmetric AND NOT is_transitive)),
  CONSTRAINT symmetric_has_no_inverse CHECK (NOT is_symmetric OR inverse_code IS NULL)
);
CREATE INDEX relation_type_canonical ON relation_types (canonical_code) WHERE canonical_code IS NOT NULL;

-- Codes are typed by humans: 'says about', 'says-about' and 'SAYS_ABOUT' are
-- the same code.
CREATE FUNCTION norm_code(c text) RETURNS text
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT upper(regexp_replace(btrim(c), '[\s-]+', '_', 'g')) $$;

-- ponytail: recursive walk, no depth cap. Alias chains are shallow by
-- construction; add a cycle guard if aliases become user-editable in bulk.
CREATE FUNCTION canonical_relation(c text) RETURNS text
  LANGUAGE sql STABLE AS
$$ WITH RECURSIVE walk AS (
     SELECT code, canonical_code FROM relation_types WHERE code = norm_code(c)
     UNION ALL
     SELECT rt.code, rt.canonical_code
       FROM relation_types rt JOIN walk w ON rt.code = w.canonical_code
   )
   SELECT code FROM walk WHERE canonical_code IS NULL $$;

-- ------------------------------------------------------------------- relations
CREATE TABLE relations (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  subject_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  predicate  text NOT NULL REFERENCES relation_types(code),
  object_id  uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  created_by citext REFERENCES users(email),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT no_self_relation CHECK (subject_id <> object_id),
  UNIQUE (subject_id, predicate, object_id)
);
CREATE INDEX relations_inbound ON relations (object_id, predicate);

CREATE FUNCTION canonicalize_predicate() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c text;
BEGIN
  c := canonical_relation(NEW.predicate);
  IF c IS NULL THEN RAISE EXCEPTION 'unknown relation type: %', NEW.predicate; END IF;
  NEW.predicate := c;
  RETURN NEW;
END $$;
CREATE TRIGGER relations_canonical BEFORE INSERT OR UPDATE OF predicate ON relations
  FOR EACH ROW EXECUTE FUNCTION canonicalize_predicate();

-- ---------------------------------------------------------------------- drafts
CREATE TABLE drafts (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id    uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  base_version int  NOT NULL CHECK (base_version >= 1),
  patch        jsonb NOT NULL,
  status       draft_status NOT NULL DEFAULT 'pending_review',
  author       citext NOT NULL REFERENCES users(email),
  created_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT patch_is_object CHECK (jsonb_typeof(patch) = 'object' AND patch <> '{}'::jsonb),
  CONSTRAINT patch_fields_known
    CHECK (patch - ARRAY['name','definition','formula','props'] = '{}'::jsonb)
);
CREATE UNIQUE INDEX one_pending_draft_per_entity ON drafts (entity_id) WHERE status = 'pending_review';

-- ------------------------------------------------------------------- versioning
CREATE TABLE revisions (
  entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  version   int  NOT NULL,
  snapshot  jsonb NOT NULL,
  actor     citext REFERENCES users(email),
  reason    text,
  at        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_id, version)
);

-- Content changes bump the version; a status move alone (submit, publish,
-- reject) does not, so a term published unedited is still version 1. Its
-- snapshot for that version is rewritten in place with the new status.
CREATE FUNCTION bump_entity_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.name, NEW.definition, NEW.formula, NEW.props, NEW.kind, NEW.category_id)
     IS DISTINCT FROM
     (OLD.name, OLD.definition, OLD.formula, OLD.props, OLD.kind, OLD.category_id)
     AND NEW.version = OLD.version THEN
    NEW.version := OLD.version + 1;
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER entities_bump_version BEFORE UPDATE ON entities
  FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

-- actor: the app sets `SET LOCAL ontology.actor = 'who@corp.com'` inside the
-- approve/merge transaction; unset falls back to the entity's creator.
CREATE FUNCTION write_entity_snapshot(eid uuid) RETURNS void LANGUAGE sql AS $$
  INSERT INTO revisions (entity_id, version, snapshot, actor)
  SELECT e.id, e.version,
         to_jsonb(e) || jsonb_build_object('synonyms', coalesce(
           (SELECT jsonb_agg(jsonb_build_object('text', l.text, 'lang', l.lang) ORDER BY l.text)
              FROM labels l WHERE l.entity_id = e.id), '[]'::jsonb)),
         coalesce(nullif(current_setting('ontology.actor', true), '')::citext, e.created_by)
    FROM entities e WHERE e.id = eid
  ON CONFLICT (entity_id, version) DO UPDATE SET snapshot = EXCLUDED.snapshot
$$;

CREATE FUNCTION snapshot_entity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME = 'entities' THEN
    PERFORM write_entity_snapshot(NEW.id);
  ELSIF TG_OP = 'DELETE' THEN
    PERFORM write_entity_snapshot(OLD.entity_id);
  ELSE
    PERFORM write_entity_snapshot(NEW.entity_id);
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER entities_snapshot AFTER INSERT OR UPDATE ON entities
  FOR EACH ROW EXECUTE FUNCTION snapshot_entity();
CREATE TRIGGER labels_snapshot AFTER INSERT OR UPDATE OR DELETE ON labels
  FOR EACH ROW EXECUTE FUNCTION snapshot_entity();

-- ------------------------------------------------------------- workflow audit
CREATE TABLE review_events (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  entity_id   uuid REFERENCES entities(id) ON DELETE SET NULL,
  entity_name text,
  action      text NOT NULL CHECK (action IN ('submit_new','approve_new','reject_new',
                                              'submit_edit','approve_edit','reject_edit',
                                              'merge','alias','deprecate','delete')),
  field       text,
  old_value   text,
  new_value   text,
  reason      text,
  actor       citext REFERENCES users(email),
  at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX review_events_entity ON review_events (entity_id, at DESC);
CREATE INDEX review_events_at     ON review_events (at DESC);

ALTER TABLE entities ENABLE ALWAYS TRIGGER entities_check_props;
ALTER TABLE entities ENABLE ALWAYS TRIGGER entities_name_free;
ALTER TABLE labels   ENABLE ALWAYS TRIGGER labels_before_write;

-- ------------------------------------------------------------------------ views
CREATE VIEW entities_v AS
SELECT e.*, c.name AS category FROM entities e LEFT JOIN categories c ON c.id = e.category_id;

CREATE VIEW terms AS SELECT * FROM entities_v WHERE kind = 'Term';
CREATE VIEW published_terms AS SELECT * FROM terms WHERE status = 'published';

-- every name in the database, canonical and alternate, in one place to read
CREATE VIEW all_names AS
SELECT e.id AS entity_id, e.name AS text, e.name_lang AS lang, true AS is_canonical,
       e.name_norm AS norm, e.name_fold AS fold, e.category_id, NULL::text AS source
  FROM entities e
UNION ALL
SELECT l.entity_id, l.text, l.lang, false, l.norm, l.fold, l.category_id, l.source
  FROM labels l;

-- --------------------------------------------------------------- resolution API
-- Ranked candidates over both name sources, never a silent single pick.
-- ponytail: trigram scores, not BM25. Swap the fuzzy tier for ts_rank/BM25 over
-- a tsvector column if the corpus reaches the thousands; the tiers stay.
CREATE FUNCTION resolve_entity(q text, want_kind text DEFAULT NULL,
                               want_category text DEFAULT NULL,
                               want_lang text DEFAULT NULL, min_score real DEFAULT 0.3)
RETURNS TABLE (entity_id uuid, kind text, name text, category text, lang text,
               status entity_status, matched text, matched_canonical boolean,
               match_kind text, score real)
-- plpgsql, not sql: an inlinable SQL function loses its ORDER BY at the call site.
LANGUAGE plpgsql STABLE AS $$
BEGIN
  RETURN QUERY
  WITH hit AS (
    SELECT n.entity_id, n.text AS matched, n.lang, n.is_canonical,
           match_tier(n.norm, n.fold, q)  AS match_kind,
           match_score(n.norm, n.fold, q) AS score
      FROM all_names n
     WHERE (want_lang IS NULL OR n.lang = want_lang)
       AND (n.norm = norm(q) OR n.fold = fold(q)
            OR n.fold LIKE fold(q) || '%' OR n.fold % fold(q))
  ),
  survivor AS (
    SELECT coalesce(e.merged_into, e.id) AS entity_id,
           h.matched, h.lang, h.is_canonical, h.match_kind, h.score
      FROM hit h JOIN entities e ON e.id = h.entity_id
  ),
  best AS (
    SELECT DISTINCT ON (s.entity_id)
           s.entity_id, v.kind, v.name, v.category, s.lang, v.status,
           s.matched, s.is_canonical, s.match_kind, s.score
      FROM survivor s JOIN entities_v v ON v.id = s.entity_id
     WHERE s.score >= min_score
       AND (want_kind IS NULL OR v.kind = want_kind)
       AND (want_category IS NULL OR v.category = want_category)
     ORDER BY s.entity_id, s.score DESC, s.is_canonical DESC, s.matched
  )
  SELECT * FROM best ORDER BY best.score DESC, best.name;
END $$;

-- ---------------------------------------------------------------- entity merge
-- The absorbed entity's name becomes a synonym of the survivor; its own row
-- keeps its id AND its name, so the tombstone still reads.
CREATE FUNCTION merge_entities(loser uuid, winner uuid, actor citext, reason text DEFAULT NULL)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE l_name text; l_lang text; l_kind text; w_kind text;
BEGIN
  IF actor IS NULL OR NOT EXISTS (SELECT 1 FROM users
        WHERE email = actor AND role IN ('reviewer','admin')) THEN
    RAISE EXCEPTION 'merge_entities requires a reviewer or admin, got %', actor;
  END IF;
  IF loser = winner THEN RAISE EXCEPTION 'cannot merge an entity into itself'; END IF;
  SELECT name, name_lang, kind INTO l_name, l_lang, l_kind FROM entities WHERE id = loser;
  IF l_name IS NULL THEN RAISE EXCEPTION 'no such entity: %', loser; END IF;
  SELECT kind INTO w_kind FROM entities WHERE id = winner AND status <> 'merged';
  IF w_kind IS NULL THEN RAISE EXCEPTION 'survivor % missing or itself merged', winner; END IF;
  IF l_kind <> w_kind THEN
    RAISE EXCEPTION 'cannot merge a % into a %', l_kind, w_kind;
  END IF;

  -- Tombstone first: that releases the loser's claim on its own name so the
  -- survivor can adopt it. The loser keeps the name on its row as history.
  UPDATE entities SET status = 'merged', merged_into = winner WHERE id = loser;

  -- the loser's name becomes a synonym of the survivor, unless the survivor
  -- already answers to it
  INSERT INTO labels (entity_id, text, lang, source)
  SELECT winner, l_name, l_lang, 'merge:' || loser
   WHERE NOT EXISTS (
     SELECT 1 FROM all_names n
      WHERE n.entity_id = winner AND n.lang = l_lang AND n.norm = norm(l_name));

  -- the loser's synonyms follow, minus any the survivor already holds
  DELETE FROM labels l
   WHERE l.entity_id = loser
     AND EXISTS (SELECT 1 FROM all_names n
                  WHERE n.entity_id = winner AND n.lang = l.lang AND n.norm = l.norm);
  UPDATE labels SET entity_id = winner, source = 'merge:' || loser WHERE entity_id = loser;

  -- edges repoint, duplicates and self-loops dropped
  UPDATE relations r SET subject_id = winner
   WHERE r.subject_id = loser AND r.object_id <> winner
     AND NOT EXISTS (SELECT 1 FROM relations x
                      WHERE x.subject_id = winner AND x.predicate = r.predicate
                        AND x.object_id = r.object_id);
  UPDATE relations r SET object_id = winner
   WHERE r.object_id = loser AND r.subject_id <> winner
     AND NOT EXISTS (SELECT 1 FROM relations x
                      WHERE x.object_id = winner AND x.predicate = r.predicate
                        AND x.subject_id = r.subject_id);
  DELETE FROM relations WHERE loser IN (subject_id, object_id);

  DELETE FROM drafts WHERE entity_id = loser;

  INSERT INTO review_events (entity_id, entity_name, action, old_value, new_value, reason, actor)
  VALUES (loser, l_name, 'merge', loser::text, winner::text, reason, actor);
END $$;

-- -------------------------------------------------- relation type governance
CREATE FUNCTION merge_relation_types(loser text, winner text, actor citext)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE l text := norm_code(loser); w text := norm_code(winner);
BEGIN
  IF actor IS NULL OR NOT EXISTS (SELECT 1 FROM users
        WHERE email = actor AND role IN ('reviewer','admin')) THEN
    RAISE EXCEPTION 'merge_relation_types requires a reviewer or admin, got %', actor;
  END IF;
  IF canonical_relation(l) IS NULL OR canonical_relation(w) IS NULL THEN
    RAISE EXCEPTION 'unknown relation type in merge % -> %', l, w;
  END IF;
  IF canonical_relation(l) = canonical_relation(w) THEN RETURN; END IF;

  UPDATE relations r SET predicate = w
   WHERE r.predicate = l
     AND NOT EXISTS (SELECT 1 FROM relations x
                      WHERE x.subject_id = r.subject_id AND x.object_id = r.object_id
                        AND x.predicate = w);
  DELETE FROM relations WHERE predicate = l;
  UPDATE relation_types
     SET canonical_code = w, inverse_code = NULL, is_symmetric = false, is_transitive = false
   WHERE code = l;
  INSERT INTO review_events (action, old_value, new_value, reason, actor)
  VALUES ('merge', l, w, 'relation type merged', actor);
END $$;

CREATE FUNCTION add_relation_alias(alias text, canonical text, actor citext)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE a text := norm_code(alias); c text := canonical_relation(canonical);
BEGIN
  IF actor IS NULL OR NOT EXISTS (SELECT 1 FROM users
        WHERE email = actor AND role IN ('reviewer','admin')) THEN
    RAISE EXCEPTION 'add_relation_alias requires a reviewer or admin, got %', actor;
  END IF;
  IF c IS NULL THEN RAISE EXCEPTION 'unknown relation type: %', canonical; END IF;
  IF a !~ '^[A-Z][A-Z0-9_]*$' THEN RAISE EXCEPTION 'not a usable relation code: %', alias; END IF;
  IF a = c THEN RAISE EXCEPTION 'a relation type cannot be its own synonym'; END IF;
  IF EXISTS (SELECT 1 FROM relation_types WHERE code = a) THEN
    IF canonical_relation(a) = c THEN RETURN; END IF;
    RAISE EXCEPTION '% already exists; use merge_relation_types() to retire it into %', a, c;
  END IF;
  INSERT INTO relation_types (code, canonical_code) VALUES (a, c);
  INSERT INTO review_events (action, old_value, new_value, reason, actor)
  VALUES ('alias', a, c, 'relation type synonym registered', actor);
END $$;

CREATE VIEW relation_vocabulary AS
SELECT t.code, t.label, t.is_symmetric, t.is_transitive, t.inverse_code,
       coalesce(array_agg(a.code ORDER BY a.code)
                FILTER (WHERE a.code IS NOT NULL), '{}') AS synonyms,
       (SELECT count(*) FROM relations r WHERE r.predicate = t.code) AS edges,
       t.note
  FROM relation_types t
  LEFT JOIN relation_types a
         ON a.canonical_code IS NOT NULL AND canonical_relation(a.code) = t.code
 WHERE t.canonical_code IS NULL
 GROUP BY t.code, t.label, t.is_symmetric, t.is_transitive, t.inverse_code, t.note;

-- ------------------------------------------------------------------ homonyms
-- The deliberate collisions: one name, two categories, two meanings.
CREATE VIEW homonyms AS
SELECT n.text AS name, n.lang, count(DISTINCT n.entity_id) AS meanings,
       array_agg(DISTINCT coalesce(c.name, '(uncategorised)') ORDER BY
                 coalesce(c.name, '(uncategorised)')) AS categories,
       array_agg(DISTINCT e.kind) AS kinds
  FROM all_names n
  JOIN entities e ON e.id = n.entity_id AND e.status <> 'merged'
  LEFT JOIN categories c ON c.id = n.category_id
 GROUP BY n.text, n.lang
HAVING count(DISTINCT n.entity_id) > 1;

-- ----------------------------------------------------------- duplicate finder
CREATE VIEW duplicate_candidates AS
SELECT a.id AS entity_a, a.name AS name_a, b.id AS entity_b, b.name AS name_b, a.kind,
       CASE WHEN norm(a.definition) = norm(b.definition) THEN 1.0
            ELSE similarity(a.definition, b.definition) END::real AS definition_score
  FROM entities a
  JOIN entities b ON b.id > a.id AND b.kind = a.kind
 WHERE a.status = 'published' AND b.status = 'published'
   AND a.definition IS NOT NULL AND b.definition IS NOT NULL
   AND (norm(a.definition) = norm(b.definition)
        OR similarity(a.definition, b.definition) >= 0.6);

-- ------------------------------------------------------------------ BM25 search
-- Ranked full-text search over published entities, BM25 in plain SQL (ts_rank
-- has no IDF, so a word in every term would count as much as a rare one).
-- Tokens are accent-folded on both sides, so 'tien mat' matches 'tiền mặt'.
-- Field boosts stand in for BM25F: name 3, synonyms 2, definition 1.
-- ponytail: plain views, recomputed per query, so nothing goes stale and there
-- is nothing to refresh. Measured ~130 ms per query at 5k published entities
-- with long definitions. Past that, make bm25_tokens a materialized view
-- refreshed on publish.
CREATE VIEW bm25_tokens AS
SELECT e.id AS entity_id, x.lexeme,
       coalesce(array_length(x.positions, 1), 1) AS tf,
       CASE WHEN 'A' = ANY(x.weights) THEN 3.0
            WHEN 'B' = ANY(x.weights) THEN 2.0 ELSE 1.0 END AS field_boost
  FROM entities e,
       unnest(setweight(to_tsvector('simple', fold(e.name)), 'A')
           || setweight(to_tsvector('simple', coalesce(fold(
                (SELECT string_agg(l.text, ' ') FROM labels l WHERE l.entity_id = e.id)), '')), 'B')
           || setweight(to_tsvector('simple', coalesce(fold(e.definition), '')), 'C')) AS x
 WHERE e.status = 'published';

-- k1: term-frequency saturation; b: length normalisation. Tunable per call.
CREATE FUNCTION bm25_search(p_query text, p_limit int DEFAULT 10,
                            k1 numeric DEFAULT 1.2, b numeric DEFAULT 0.75)
RETURNS TABLE (entity_id uuid, entity_name text, score numeric, matched_lexemes text[])
LANGUAGE sql STABLE AS $$
  WITH tk AS MATERIALIZED (SELECT * FROM bm25_tokens),
  dl AS (SELECT t.entity_id, sum(t.tf * t.field_boost) AS len FROM tk t GROUP BY t.entity_id),
  c  AS (SELECT count(*)::numeric AS n_docs, avg(len) AS avgdl FROM dl),
  q  AS (SELECT DISTINCT x.lexeme FROM unnest(to_tsvector('simple', fold(p_query))) AS x),
  df AS (SELECT t.lexeme, count(DISTINCT t.entity_id)::numeric AS df
           FROM tk t JOIN q ON q.lexeme = t.lexeme GROUP BY t.lexeme),
  scored AS (
    SELECT t.entity_id,
           sum(ln(1 + (c.n_docs - df.df + 0.5) / (df.df + 0.5))                -- IDF
               * (t.tf * t.field_boost * (k1 + 1))
               / (t.tf * t.field_boost
                  + k1 * (1 - b + b * dl.len / nullif(c.avgdl, 0)))) AS score, -- length norm
           array_agg(DISTINCT t.lexeme) AS lexemes
      FROM tk t
      JOIN df ON df.lexeme = t.lexeme
      JOIN dl ON dl.entity_id = t.entity_id
      CROSS JOIN c
     GROUP BY t.entity_id
  ),
  -- the query IS one of the entity's names or synonyms (case, spacing and
  -- accents ignored): BM25 alone can rank a longer name above it
  exact AS (SELECT DISTINCT n.entity_id FROM all_names n WHERE n.fold = fold(p_query)),
  top AS (SELECT max(score) AS score FROM scored)
  -- an exact match gets the best BM25 score in this result set added, so it
  -- sorts first while scores stay in descending order; ties among exact
  -- matches (homonyms) are still settled by BM25
  SELECT s.entity_id, e.name,
         round(s.score + CASE WHEN x.entity_id IS NULL THEN 0 ELSE top.score END, 4) AS score,
         s.lexemes
    FROM scored s JOIN entities e ON e.id = s.entity_id
    LEFT JOIN exact x ON x.entity_id = s.entity_id
    CROSS JOIN top
   ORDER BY 3 DESC, e.name LIMIT p_limit
$$;

COMMIT;
