-- Demo synonym data, on top of the migrated corpus. Everything here is tagged
-- so it can be removed without touching the real glossary:
--   entities  props->>'demo' = 'true'
--   labels    source = 'demo'
--   relation_types / categories   note = 'demo'
--
-- Teardown, in this order:
--   DELETE FROM entities WHERE props->>'demo' = 'true';   -- cascades its labels
--   DELETE FROM labels WHERE source = 'demo';
--   DELETE FROM relation_types WHERE note = 'demo';
--   DELETE FROM categories WHERE note = 'demo';
--
-- WHAT DOES NOT NEED TO BE STORED AS A SYNONYM: unaccented spellings, different
-- casing, and extra whitespace. fold() strips diacritics at query time, so
-- 'tien mat', 'TIEN MAT' and 'Tiền  mặt' all already reach 'Tiền mặt'. Store a
-- synonym only when it is a genuinely different string of words.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. English names. Grounded, not invented: the Neo4j formula on Tiền mặt is
--    literally "Cash = Available_balance - ...", so 'Cash' is that term's own
--    English name. The rest are the standard brokerage-statement translations.
-- ---------------------------------------------------------------------------
INSERT INTO labels (entity_id, text, lang, source)
SELECT e.id, x.en, 'en', 'demo'
  FROM (VALUES
    ('Tiền mặt',            'Cash'),
    ('Tổng tiền',           'Total cash'),
    ('Tiểu khoản',          'Subaccount'),
    ('Phí lưu ký',          'Custody fee'),
    ('Tiền bán chờ về',     'Pending sale proceeds'),
    ('Tiền cổ tức chờ về',  'Pending cash dividend'),
    ('Tiền trái tức chờ về','Pending bond coupon'),
    ('Tiền có thể ứng',     'Advanceable cash'),
    ('Tiền đã ứng',         'Advanced cash'),
    ('Phí ứng dự kiến',     'Expected advance fee'),
    ('Tiền mua chờ khớp',   'Cash reserved for open buy orders'),
    ('Tiền có thể rút',     'Withdrawable cash')
  ) AS x(vi, en)
  JOIN terms e ON e.name = x.vi;

-- ---------------------------------------------------------------------------
-- 2. Vietnamese alternates: how people actually write these in tickets and
--    chat. Same language, so is_preferred stays false - these are synonyms of
--    the display name, not replacements for it.
-- ---------------------------------------------------------------------------
INSERT INTO labels (entity_id, text, lang, source)
SELECT e.id, x.alt, 'vi', 'demo'
  FROM (VALUES
    ('Phí lưu ký',       'Phí LK'),
    ('Tổng tiền',        'Tổng số tiền'),
    ('Tiền có thể ứng',  'Tiền ứng trước được'),
    ('Tiền đã ứng',      'Tiền ứng trước'),
    ('Tiểu khoản',       'Loại tiểu khoản'),
    ('Tiền bán chờ về',  'Tiền chờ về T+2')
  ) AS x(vi, alt)
  JOIN terms e ON e.name = x.vi;

-- ---------------------------------------------------------------------------
-- 3. The case categories exist for: one name, two categories, two meanings.
--    'Tiền mặt' in Cash_WS is the TCBS screen balance. 'Tiền mặt' in Kế toán
--    is the accounting line item. label_unique_in_category permits both;
--    resolve_entity() hands back two candidates with their categories.
-- ---------------------------------------------------------------------------
INSERT INTO categories (name, note) VALUES ('Kế toán', 'demo');

INSERT INTO entities (kind, name, name_lang, category_id, definition, props, status, created_by)
VALUES ('Term', 'Tiền mặt', 'vi', (SELECT id FROM categories WHERE name = 'Kế toán'),
        '(demo) Chỉ tiêu tiền và tương đương tiền trên báo cáo tài chính, '
        'không phải số dư khả dụng trên tài khoản chứng khoán.',
        '{"demo": true}', 'published', 'admin@corp.com');

-- same trick in English: 'Cash' now means two things too
INSERT INTO labels (entity_id, text, lang, source)
SELECT id, 'Cash', 'en', 'demo' FROM entities
 WHERE props->>'demo' = 'true' AND category_id = (SELECT id FROM categories WHERE name = 'Kế toán');

-- ---------------------------------------------------------------------------
-- 4. Predicate synonyms. One canonical code, several names callers may write.
--    COMMENTED_ON / SAYS_ABOUT is carried as a demo predicate because it was
--    the example that prompted this; the rest are real aliases for the four
--    predicates the corpus already uses.
-- ---------------------------------------------------------------------------
INSERT INTO relation_types (code, label, note) VALUES
  ('COMMENTED_ON', 'commented on', 'demo');

SELECT add_relation_alias('DERIVED_FROM',    'COMPUTED_FROM', 'admin@corp.com');
SELECT add_relation_alias('calculated from', 'COMPUTED_FROM', 'admin@corp.com');
SELECT add_relation_alias('BASED_ON',        'COMPUTED_FROM', 'admin@corp.com');
SELECT add_relation_alias('COMPONENT_OF',    'PART_OF',       'admin@corp.com');
SELECT add_relation_alias('belongs to',      'PART_OF',       'admin@corp.com');
SELECT add_relation_alias('SEE_ALSO',        'RELATED_TO',    'admin@corp.com');
SELECT add_relation_alias('associated with', 'RELATED_TO',    'admin@corp.com');
SELECT add_relation_alias('SCOPES',          'FILTER_FOR',    'admin@corp.com');
SELECT add_relation_alias('says about',      'COMMENTED_ON',  'admin@corp.com');
SELECT add_relation_alias('talks about',     'COMMENTED_ON',  'admin@corp.com');

-- An edge written with a synonym lands under the canonical code. This one also
-- does something useful: it links the two things called 'Tiền mặt' so a reader
-- who lands on one can see the other. The subject is the demo entity, so the
-- migrated graph stays exactly 12 edges.
INSERT INTO relations (subject_id, predicate, object_id, created_by)
SELECT d.id, 'see also', r.id, 'admin@corp.com'
  FROM terms d, terms r
 WHERE d.name = 'Tiền mặt' AND d.category = 'Kế toán'
   AND r.name = 'Tiền mặt' AND r.category = 'Cash_WS';

-- ---------------------------------------------------------------------------
-- 5. A live merge, so there is a real tombstone to look at: two demo terms
--    that turn out to be the same fee. The loser keeps its row and its id, its
--    name becomes a synonym of the survivor, and both names still resolve.
-- ---------------------------------------------------------------------------
INSERT INTO categories (name, note) VALUES ('Demo', 'demo');

INSERT INTO entities (kind, name, category_id, definition, props, status, created_by) VALUES
  ('Term', 'Phí giao dịch', (SELECT id FROM categories WHERE name = 'Demo'),
   '(demo) Phí trả cho công ty chứng khoán trên mỗi lệnh khớp.',
   '{"demo": true}', 'published', 'admin@corp.com'),
  ('Term', 'Phí môi giới',  (SELECT id FROM categories WHERE name = 'Demo'),
   '(demo) Phí trả cho công ty chứng khoán trên mỗi lệnh khớp.',
   '{"demo": true}', 'published', 'admin@corp.com');

SELECT merge_entities(
  (SELECT id FROM terms WHERE name = 'Phí môi giới'),
  (SELECT id FROM terms WHERE name = 'Phí giao dịch'),
  'admin@corp.com', 'identical definition, same fee');

COMMIT;
