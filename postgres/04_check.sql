-- Self-check for the v3 schema. Runs against the live (migrated) database and
-- rolls everything back, so it is safe to re-run:
--   docker exec -i ontology-pg psql -U ontology -d ontology -v ON_ERROR_STOP=1 -f - < 04_check.sql
-- Silence + "CHECKS PASSED" = good. Any assert failure aborts.
--
-- Every count is restricted to what the migration produced, so 05_demo.sql may
-- or may not be loaded without changing the outcome.
BEGIN;
SET client_min_messages = warning;

DO $check$
DECLARE
  a uuid; b uuid; b2 uuid; loser uuid; p uuid; n int; t text; v int; ok boolean;
BEGIN
  -- ---- 1. the migrated corpus is intact
  SELECT count(*) INTO n FROM entities WHERE props->>'demo' IS NULL;
  ASSERT n = 21, 'expected 21 migrated entities, got ' || n;
  SELECT count(*) INTO n FROM entities WHERE props->>'demo' IS NULL AND kind <> 'Term';
  ASSERT n = 0, 'every migrated row should be kind=Term';
  SELECT count(*) INTO n FROM entities WHERE btrim(coalesce(name,'')) = '';
  ASSERT n = 0, 'every entity carries a name in its own row';
  SELECT count(*) INTO n FROM relations r WHERE NOT EXISTS (
    SELECT 1 FROM entities e
     WHERE e.id IN (r.subject_id, r.object_id) AND e.props->>'demo' = 'true');
  ASSERT n = 12, 'expected 12 migrated relations, got ' || n;
  SELECT count(*) INTO n FROM review_events WHERE action NOT IN ('merge','alias');
  ASSERT n = 48, 'expected 48 migrated events, got ' || n;
  SELECT count(*) INTO n FROM entities
   WHERE props->>'demo' IS NULL AND status <> 'published';
  ASSERT n = 0, 'every transferred entity should be published';

  -- ---- 2. a name is a column, so its absence is a column error
  BEGIN
    INSERT INTO entities (kind, name, definition, created_by)
    VALUES ('Term', NULL, 'nameless', 'admin@corp.com');
    ASSERT false, 'an entity without a name must be rejected';
  EXCEPTION WHEN not_null_violation THEN NULL;
  END;
  BEGIN
    UPDATE entities SET name = '   ' WHERE kind = 'Term' AND status = 'published';
    ASSERT false, 'a blank name must be rejected';
  EXCEPTION WHEN check_violation THEN NULL;
  END;

  -- ---- 3. resolution: diacritics folded on input, tone marks preserved in data
  SELECT entity_id, match_kind INTO a, t FROM resolve_entity('tieu khoan');
  ASSERT t = 'folded', 'ASCII query should match folded, got ' || t;
  ASSERT (SELECT name FROM entities WHERE id = a) = 'Tiểu khoản', 'wrong entity resolved';
  ASSERT (SELECT matched_canonical FROM resolve_entity('tieu khoan')),
         'that hit was on the canonical name, not a synonym';
  SELECT count(*) INTO n FROM resolve_entity('TIỂU KHOẢN  ');
  ASSERT n = 1, 'case/whitespace normalisation failed';

  -- ---- 4. one name, one thing - across BOTH halves of the name space
  -- a synonym may not take a name an entity already has
  BEGIN
    INSERT INTO labels (entity_id, text, lang)
    SELECT id, 'Tổng tiền', 'vi' FROM terms WHERE name = 'Phí lưu ký';
    ASSERT false, 'a synonym must not duplicate an entity name in the same category';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;
  -- and an entity may not be renamed onto an existing synonym
  INSERT INTO labels (entity_id, text, lang, source)
  SELECT id, 'Phí lưu ký viết tắt', 'vi', 'check' FROM terms WHERE name = 'Phí lưu ký';
  BEGIN
    UPDATE entities SET name = 'Phí lưu ký viết tắt'
     WHERE id = (SELECT id FROM terms WHERE name = 'Tổng tiền');
    ASSERT false, 'an entity must not be renamed onto an existing synonym';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;
  -- two entities may not share a name inside one category
  BEGIN
    UPDATE entities SET name = 'Tổng tiền'
     WHERE id = (SELECT id FROM terms WHERE name = 'Phí lưu ký');
    ASSERT false, 'two entities must not share a name in one category';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;

  -- ---- 5. relation type aliases resolve to canonical, only canonical is stored
  INSERT INTO relation_types (code, canonical_code) VALUES ('CHECK_ALIAS', 'COMPUTED_FROM');
  ASSERT canonical_relation('check_alias') = 'COMPUTED_FROM', 'alias did not resolve';
  INSERT INTO relations (subject_id, predicate, object_id)
  SELECT (SELECT id FROM terms WHERE name = 'Phí lưu ký'), 'CHECK_ALIAS',
         (SELECT id FROM published_terms WHERE name = 'Tiền mặt' AND category = 'Cash_WS');
  SELECT predicate INTO t FROM relations
   WHERE subject_id = (SELECT id FROM terms WHERE name = 'Phí lưu ký');
  ASSERT t = 'COMPUTED_FROM', 'alias should be stored canonical, got ' || t;
  BEGIN
    INSERT INTO relations (subject_id, predicate, object_id)
    SELECT (SELECT id FROM terms WHERE name = 'Phí lưu ký'), 'NO_SUCH_REL',
           (SELECT id FROM terms WHERE name = 'Tổng tiền');
    ASSERT false, 'unknown predicate should be rejected';
  EXCEPTION WHEN others THEN NULL;
  END;

  -- ---- 6. relation type merge is governed
  BEGIN
    PERFORM merge_relation_types('FILTER_FOR', 'RELATED_TO', 'editor@corp.com');
    ASSERT false, 'an editor must not be able to merge relation types';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;
  PERFORM merge_relation_types('FILTER_FOR', 'RELATED_TO', 'admin@corp.com');
  SELECT count(*) INTO n FROM relations WHERE predicate = 'FILTER_FOR';
  ASSERT n = 0, 'merged relation type left edges behind';
  ASSERT canonical_relation('FILTER_FOR') = 'RELATED_TO', 'merged type is not an alias';

  -- ---- 7. entity merge: the tombstone keeps its name, the survivor gains it
  SELECT id INTO a FROM terms WHERE name = 'Tiền có thể rút';   -- duplicate definition
  SELECT id INTO b FROM terms WHERE name = 'Tiền bán chờ về';
  loser := a;
  ASSERT (SELECT count(*) FROM duplicate_candidates) >= 1, 'duplicate finder found nothing';
  BEGIN
    PERFORM merge_entities(a, b, 'editor@corp.com', 'nope');
    ASSERT false, 'an editor must not be able to merge two entities';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;
  PERFORM merge_entities(a, b, 'admin@corp.com', 'identical definition');
  ASSERT (SELECT status FROM entities WHERE id = loser) = 'merged', 'loser not tombstoned';
  ASSERT (SELECT merged_into FROM entities WHERE id = loser) = b, 'loser not pointed at survivor';
  ASSERT (SELECT name FROM entities WHERE id = loser) = 'Tiền có thể rút',
         'the tombstone should keep its own name';
  SELECT count(*) INTO n FROM labels
   WHERE entity_id = b AND text = 'Tiền có thể rút' AND source = 'merge:' || loser;
  ASSERT n = 1, 'absorbed name did not become a synonym of the survivor';
  SELECT entity_id INTO a FROM resolve_entity('tien co the rut');
  ASSERT a = b, 'the old name must resolve to the survivor';
  SELECT count(*) INTO n FROM relations r WHERE loser IN (r.subject_id, r.object_id);
  ASSERT n = 0, 'merged entity still has edges';

  -- ---- 8. drafts: one pending per entity, editable fields only
  SELECT id INTO a FROM terms WHERE name = 'Tiền mặt' AND category = 'Cash_WS';
  INSERT INTO drafts (entity_id, base_version, patch, author)
  VALUES (a, 1, '{"definition":"proposed"}', 'editor@corp.com');
  BEGIN
    INSERT INTO drafts (entity_id, base_version, patch, author)
    VALUES (a, 1, '{"definition":"second"}', 'editor@corp.com');
    ASSERT false, 'an entity must not have two pending drafts';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;
  BEGIN
    INSERT INTO drafts (entity_id, base_version, patch, author)
    VALUES ((SELECT id FROM terms WHERE name = 'Phí lưu ký'), 1,
            '{"status":"published"}', 'editor@corp.com');
    ASSERT false, 'a draft must not patch non-editable fields';
  EXCEPTION WHEN check_violation THEN NULL;
  END;

  -- ---- 9. version bump + retrievable history, name included
  SELECT version INTO v FROM entities WHERE id = a;
  UPDATE entities SET definition = 'approved edit' WHERE id = a;
  ASSERT (SELECT version FROM entities WHERE id = a) = v + 1, 'version did not bump';
  ASSERT (SELECT snapshot->>'definition' FROM revisions
           WHERE entity_id = a AND version = v + 1) = 'approved edit', 'snapshot missing';
  ASSERT (SELECT snapshot->>'name' FROM revisions
           WHERE entity_id = a AND version = v + 1) = 'Tiền mặt', 'snapshot lost the name';
  -- renaming is a versioned change too
  UPDATE entities SET name = 'Tiền mặt (TCBS)' WHERE id = a;
  ASSERT (SELECT version FROM entities WHERE id = a) = v + 2, 'a rename must bump the version';
  ASSERT (SELECT snapshot->>'name' FROM revisions
           WHERE entity_id = a AND version = v + 1) = 'Tiền mặt',
         'the old name must still be readable at its old version';

  -- ---- 10. the kind registry decides what a row must carry
  INSERT INTO entities (kind, name, definition, props, created_by)
  VALUES ('Person', 'Nguyễn Văn A', NULL, '{"title":"CFO","department":"Finance"}',
          'admin@corp.com')
  RETURNING id INTO p;
  -- Person's properties are all optional, so probe the mechanism with a kind
  -- that has a required one (rolled back with everything else)
  INSERT INTO kinds (kind, requires_definition, props)
  VALUES ('Probe', false, '[{"name":"title","required":true},{"name":"department"}]');
  BEGIN
    INSERT INTO entities (kind, name, props, created_by)
    VALUES ('Probe', 'Trần Thị B', '{"department":"Finance"}', 'admin@corp.com');
    ASSERT false, 'a required kind property must not be omitted';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;
  BEGIN
    INSERT INTO entities (kind, name, definition, created_by)
    VALUES ('Term', 'Không định nghĩa', NULL, 'admin@corp.com');
    ASSERT false, 'a Term must carry a definition';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;

  -- ---- 11. one resolver over every kind, scopeable to one
  SELECT kind INTO t FROM resolve_entity('nguyen van a');
  ASSERT t = 'Person', 'cross-kind resolution failed, got ' || coalesce(t,'<none>');
  SELECT count(*) INTO n FROM resolve_entity('nguyen van a', 'Term');
  ASSERT n = 0, 'want_kind filter did not scope the search';
  SELECT count(*) INTO n FROM published_terms WHERE props->>'demo' IS NULL;
  ASSERT n = 20, 'published_terms should hold 20 migrated terms after the merge, got ' || n;

  -- ---- 12. edges cross kinds; merges do not
  INSERT INTO relations (subject_id, predicate, object_id)
  VALUES (p, 'RELATED_TO', (SELECT id FROM terms WHERE name = 'Phí lưu ký'));
  BEGIN
    PERFORM merge_entities(p, (SELECT id FROM published_terms
                                WHERE name = 'Tiền mặt (TCBS)' AND category = 'Cash_WS'),
                           'admin@corp.com');
    ASSERT false, 'a Person must not be mergeable into a Term';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;

  -- ---- 13. a Term's definition cannot be relaxed away
  BEGIN
    UPDATE kinds SET requires_definition = false WHERE kind = 'Term';
    ASSERT false, 'the Term definition rule must not be relaxable in the registry';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  SELECT count(*) INTO n FROM pg_trigger
   WHERE tgname IN ('entities_check_props','entities_name_free','labels_before_write')
     AND tgenabled = 'A';
  ASSERT n = 3, 'the name/props triggers must be ENABLE ALWAYS, got ' || n;

  -- ---- 14. relation type synonyms (own codes, so 05_demo.sql cannot clash)
  INSERT INTO relation_types (code, label) VALUES ('CHECK_SPOKE_OF', 'spoke of');
  PERFORM add_relation_alias('check said about', 'CHECK_SPOKE_OF', 'admin@corp.com');
  ASSERT canonical_relation('CHECK_SAID_ABOUT')   = 'CHECK_SPOKE_OF', 'alias did not resolve';
  ASSERT canonical_relation('check-said-about')   = 'CHECK_SPOKE_OF', 'hyphen form failed';
  ASSERT canonical_relation(' check said about ') = 'CHECK_SPOKE_OF', 'spaced form failed';
  ASSERT (SELECT synonyms FROM relation_vocabulary WHERE code = 'CHECK_SPOKE_OF')
         = ARRAY['CHECK_SAID_ABOUT'], 'vocabulary view does not list the synonym';
  INSERT INTO relations (subject_id, predicate, object_id)
  VALUES (p, 'check said about', (SELECT id FROM terms WHERE name = 'Tổng tiền'));
  ASSERT (SELECT predicate FROM relations
           WHERE subject_id = p AND object_id = (SELECT id FROM terms WHERE name = 'Tổng tiền'))
         = 'CHECK_SPOKE_OF', 'synonym was stored instead of the canonical code';
  PERFORM add_relation_alias('CHECK_SAID_ABOUT', 'CHECK_SPOKE_OF', 'admin@corp.com');
  BEGIN
    PERFORM add_relation_alias('CHECK_TALKED_OF', 'CHECK_SPOKE_OF', 'editor@corp.com');
    ASSERT false, 'an editor must not be able to register a synonym';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;
  BEGIN
    PERFORM add_relation_alias('PART_OF', 'CHECK_SPOKE_OF', 'admin@corp.com');
    ASSERT false, 'a live predicate must not become a synonym without a merge';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;
  SELECT count(*) INTO n FROM review_events
   WHERE action = 'alias' AND old_value = 'CHECK_SAID_ABOUT';
  ASSERT n = 1, 'synonym registration was not audited, got ' || n;

  -- ---- 15. the same name may mean different things in different categories
  INSERT INTO categories (name) VALUES ('Kiểm thử A'), ('Kiểm thử B'), ('Kiểm thử C');
  INSERT INTO entities (kind, name, category_id, definition, created_by)
  VALUES ('Term', 'Ký quỹ', (SELECT id FROM categories WHERE name = 'Kiểm thử A'),
          'margin deposit, trading sense', 'admin@corp.com')
  RETURNING id INTO a;
  INSERT INTO entities (kind, name, category_id, definition, created_by)
  VALUES ('Term', 'Ký quỹ', (SELECT id FROM categories WHERE name = 'Kiểm thử B'),
          'margin deposit, accounting sense', 'admin@corp.com')
  RETURNING id INTO b2;

  SELECT count(*) INTO n FROM resolve_entity('ky quy', 'Term', NULL, NULL, 0.9);
  ASSERT n = 2, 'both meanings should come back as candidates, got ' || n;
  SELECT count(DISTINCT category) INTO n FROM resolve_entity('ky quy','Term',NULL,NULL,0.9);
  ASSERT n = 2, 'the two meanings should be told apart by category';
  SELECT count(*) INTO n FROM resolve_entity('ky quy', 'Term', 'Kiểm thử A', NULL, 0.9);
  ASSERT n = 1, 'want_category did not scope the search, got ' || n;
  ASSERT (SELECT meanings FROM homonyms WHERE name = 'Ký quỹ') = 2,
         'homonyms view does not see the collision';

  -- a synonym is scoped the same way: 'Ký quỹ' is free in a third category
  INSERT INTO entities (kind, name, category_id, definition, created_by)
  VALUES ('Term', 'Ký quỹ bù trừ', (SELECT id FROM categories WHERE name = 'Kiểm thử C'),
          'clearing margin', 'admin@corp.com');
  INSERT INTO labels (entity_id, text, lang, source)
  SELECT id, 'Ký quỹ', 'vi', 'check' FROM entities WHERE name = 'Ký quỹ bù trừ';

  -- re-categorising moves the synonyms, and a move that would collide is refused
  UPDATE entities SET category_id = (SELECT id FROM categories WHERE name = 'Kiểm thử C')
   WHERE name = 'Ký quỹ bù trừ';
  BEGIN
    UPDATE entities SET category_id = (SELECT id FROM categories WHERE name = 'Kiểm thử C')
     WHERE id = a;
    ASSERT false, 'moving an entity onto an existing synonym of that category must fail';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;

  -- Nothing is deferred any more - the name rule is a column constraint - but
  -- fire whatever deferred constraints exist before rolling back, so a future
  -- one cannot hide behind the rollback.
  SET CONSTRAINTS ALL IMMEDIATE;

  RAISE WARNING 'CHECKS PASSED';
END $check$;

ROLLBACK;
