import os
import psycopg2
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


def execute_query(func):
    def wrapper(*args, **kwargs):
        queries = func(*args, **kwargs)
        logger.info(queries)
        if isinstance(queries, str):
            queries = [queries]
        with psycopg2.connect(dbname=os.getenv('POSTGRES_DB'),
                              user=os.getenv('POSTGRES_USER'),
                              password=os.getenv('POSTGRES_PASSWORD'),
                              host=os.getenv('POSTGRES_HOST'),
                              port=os.getenv('POSTGRES_PORT'),
                              sslmode='allow') as connection:
            with connection.cursor() as cursor:
                for query in queries:
                    try:
                        cursor.execute(query)
                    except psycopg2.Error as e:
                        logger.debug(
                            f'Query: {query}. Error message - {e}')
                    connection.commit()
                if any([el in str(cursor.query) for el in ['INSERT INTO', 'DELETE FROM']]):
                    results = True
                else:
                    results = cursor.fetchall()
                logger.info(results)
        return results

    return wrapper


@execute_query
def _init_db() -> str:
    with open(os.path.join('db', "create_db.sql"), "r") as f:
        sql = f.read()
    return sql


def select_all_query(lang: str = 'eng') -> str:
    return f"""SELECT {lang}_words.word, {lang}_definitions.definition
        FROM {lang}_link
        JOIN {lang}_words ON {lang}_words.id={lang}_link.word_id
        JOIN {lang}_definitions ON {lang}_definitions.id={lang}_link.definition_id"""


@execute_query
def select_all(lang: str = 'eng') -> str:
    return select_all_query(lang) + f'ORDER BY {lang}_words.word'


@execute_query
def select_last_n_terms(n: int, lang: str = 'eng') -> str:
    return select_all_query(lang) + f' ORDER BY {lang}_words.id DESC LIMIT {n}'


@execute_query
def select_n_random(n: int, lang: str = 'eng') -> str:
    query = select_all_query(lang) + f' ORDER BY RANDOM() LIMIT {n};'
    return query


@execute_query
def select_all_definitions(word: str, lang: str = 'eng') -> str:
    return select_all_query(lang) + f" WHERE word ILIKE $${word}$$ || '%';"


@execute_query
def _select_definition(word: str, lang: str = 'eng') -> str:
    return f"""SELECT definition FROM {lang}_definitions WHERE word ILIKE $${word}$$ || '%';"""


@execute_query
def insert(word: str, definition: str, lang: str = 'eng') -> list[str]:
    logger.info(
        f'Inserting {word.upper()} - {definition} ({lang}) to {lang}_words, {lang}_definitions, {lang}_link')
    return [
        f"""INSERT INTO {lang}_words (word) VALUES ($${word}$$);""",
        f"""INSERT INTO {lang}_definitions (definition) VALUES ($${definition}$$);""",
        f"""INSERT INTO {lang}_link VALUES (
                (SELECT id FROM {lang}_words WHERE word = $${word}$$),
                (SELECT id FROM {lang}_definitions WHERE definition=$${definition}$$));"""
    ]


@execute_query
def delete(word: str, lang: str = 'eng') -> list[str]:
    logger.info(f'Deleting {word.upper()} ({lang}) ')
    return [
        f"""DELETE FROM {lang}_definitions WHERE id=
                (SELECT definition_id FROM {lang}_link WHERE word_id=
                    (SELECT id FROM {lang}_words WHERE word=$${word}$$));""",
        f"""DELETE FROM {lang}_link WHERE word_id=
                (SELECT id FROM {lang}_words WHERE word=$${word}$$);""",
        f"""DELETE FROM {lang}_words WHERE word=$${word}$$;"""
    ]


if __name__ == "__main__":
    print(select_all())
