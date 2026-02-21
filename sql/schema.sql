PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS words (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lemma TEXT NOT NULL,
  pos TEXT,
  level TEXT,
  freq REAL,
  source TEXT NOT NULL,
  license TEXT NOT NULL,
  source_ref TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(lemma, pos, source)
);

CREATE TABLE IF NOT EXISTS senses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  word_id INTEGER NOT NULL,
  sense_key TEXT,
  definition TEXT NOT NULL,
  domain TEXT,
  source TEXT NOT NULL,
  license TEXT NOT NULL,
  source_ref TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(word_id) REFERENCES words(id) ON DELETE CASCADE,
  UNIQUE(word_id, sense_key, definition)
);

CREATE TABLE IF NOT EXISTS examples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sentence TEXT NOT NULL,
  lang TEXT DEFAULT 'eng',
  level TEXT,
  source TEXT NOT NULL,
  license TEXT NOT NULL,
  source_ref TEXT,
  synthetic INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(sentence, source)
);

CREATE TABLE IF NOT EXISTS sense_examples (
  sense_id INTEGER NOT NULL,
  example_id INTEGER NOT NULL,
  source TEXT NOT NULL,
  license TEXT NOT NULL,
  source_ref TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(sense_id, example_id),
  FOREIGN KEY(sense_id) REFERENCES senses(id) ON DELETE CASCADE,
  FOREIGN KEY(example_id) REFERENCES examples(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS word_forms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  word_id INTEGER NOT NULL,
  form TEXT NOT NULL,
  form_type TEXT,
  source TEXT NOT NULL,
  license TEXT NOT NULL,
  source_ref TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(word_id) REFERENCES words(id) ON DELETE CASCADE,
  UNIQUE(word_id, form, form_type)
);

CREATE INDEX IF NOT EXISTS idx_words_lemma ON words(lemma);
CREATE INDEX IF NOT EXISTS idx_words_level ON words(level);
CREATE INDEX IF NOT EXISTS idx_senses_word_id ON senses(word_id);
CREATE INDEX IF NOT EXISTS idx_examples_level ON examples(level);
CREATE INDEX IF NOT EXISTS idx_examples_source ON examples(source);

CREATE VIRTUAL TABLE IF NOT EXISTS examples_fts USING fts5(
  sentence,
  content='examples',
  content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS examples_ai AFTER INSERT ON examples BEGIN
  INSERT INTO examples_fts(rowid, sentence) VALUES (new.id, new.sentence);
END;

CREATE TRIGGER IF NOT EXISTS examples_ad AFTER DELETE ON examples BEGIN
  INSERT INTO examples_fts(examples_fts, rowid, sentence) VALUES('delete', old.id, old.sentence);
END;

CREATE TRIGGER IF NOT EXISTS examples_au AFTER UPDATE ON examples BEGIN
  INSERT INTO examples_fts(examples_fts, rowid, sentence) VALUES('delete', old.id, old.sentence);
  INSERT INTO examples_fts(rowid, sentence) VALUES (new.id, new.sentence);
END;
