CREATE TABLE IF NOT EXISTS eng_words (
    id SERIAL PRIMARY KEY,
    word VARCHAR(50) NOT NULL,
    UNIQUE (word)
);

CREATE TABLE IF NOT EXISTS eng_definitions (
    id SERIAL PRIMARY KEY,
    definition VARCHAR(255) NOT NULL,
    UNIQUE (definition)
);

CREATE TABLE IF NOT EXISTS eng_link (
    word_id INTEGER NOT NULL,
    definition_id INTEGER NOT NULL,
    FOREIGN KEY (word_id) REFERENCES eng_words(id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (definition_id) REFERENCES eng_definitions(id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (word_id, definition_id)
);


CREATE TABLE IF NOT EXISTS ru_words (
    id SERIAL PRIMARY KEY,
    word VARCHAR(50) NOT NULL,
    UNIQUE (word)
);

CREATE TABLE IF NOT EXISTS ru_definitions (
    id SERIAL PRIMARY KEY,
    definition VARCHAR(255) NOT NULL,
    UNIQUE (definition)
);

CREATE TABLE IF NOT EXISTS ru_link (
    word_id INTEGER NOT NULL,
    definition_id INTEGER NOT NULL,
    FOREIGN KEY (word_id) REFERENCES ru_words(id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (definition_id) REFERENCES ru_definitions(id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (word_id, definition_id)
);

INSERT INTO eng_words(word) VALUES('book');
INSERT INTO eng_definitions (definition)
VALUES
  ('книга'),
  ('бронировать');
INSERT INTO eng_link (word_id, definition_id)
VALUES
  ((SELECT id FROM eng_words WHERE word = 'book'),
  (SELECT id FROM eng_definitions WHERE definition = 'книга')),
  ((SELECT id FROM eng_words WHERE word = 'book'),
  (SELECT id FROM eng_definitions WHERE definition = 'бронировать'));
