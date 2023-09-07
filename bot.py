import os
import random
import sqlite3
import re

import db.db as db

import csv

from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text, Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from dotenv import dotenv_values
from loguru import logger

from quiz import Quiz


class States(StatesGroup):
    INPUT_LANG = State()
    INPUT_WORD = State()
    INPUT_DEFINITION = State()
    CHOOSE_OPTION = State()
    CHOOSE_QUIZ = State()
    PROCESS_ANSWER = State()


def create_correct_definition_quiz(lang: str) -> Quiz:
    words = db.select_n_random(4, lang)
    correct_option_id = random.randrange(0, 4)
    options = [el[1][:100] for el in words]
    question = words[correct_option_id][0]
    return Quiz(
        type_='quiz',
        lang=lang,
        question=question,
        options=options,
        correct_option_id=correct_option_id
    )


def create_skipped_letters_quiz(lang: str) -> Quiz:
    res = db.select_n_random(1, lang)[0]
    word: str = res[0]
    definition: str = res[1]
    while True:
        k = random.randrange(len(word))
        if word[k] != ' ':
            break
    question = word.upper()[:k] + '_' + word.upper()[k + 1:] + ' - ' + definition
    options = word[k]
    return Quiz(
        type_='skipped',
        lang=lang,
        question=question,
        options=options
    )


def create_find_pairs_quiz(lang: str) -> Quiz:
    res = db.select_n_random(4, lang)
    words = [el[0] for el in res]
    definitions = [el[1] for el in res]
    random.shuffle(definitions)
    options = []
    for i in range(len(words)):
        options.append(f'{i + 1}{chr(definitions.index(res[i][1]) + 97)}')
    question = '\n'.join([f'{i + 1}. {words[i].upper()}' for i in range(len(words))]) + '\n\n' + '\n'.join(
        [f'{chr(i + 97)}. {definitions[i]}' for i in range(len(words))])
    return Quiz(
        type_='pairs',
        lang=lang,
        question=question,
        options=options
    )


config = dotenv_values('.env')
API_TOKEN = os.getenv('DICT_API_TOKEN') or config['TG_API']

storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=storage)

help_cmd = {
    'random_5': '5 случайных слов из словаря',
    'select': 'Получить перевод/определение слова из словаря',
    'select_5': 'Получить 5 последних слов из словаря',
    'add': 'Добавить новое слово или определение',
    'delete': 'Удалить слово',
    'quizzes': 'Викторины'
}
csv_description = 'Для добавление слов через отправку CSV файла, его необходимо назвать "язык.csv". ' \
                  'Например: eng.csv, ru.csv\nТакже слова в файле должны соответствовать шаблону: "слово, перевод" ' \
                  'Например: book, бронировать'
langs = ['eng', 'ru']
quizzes = {
    'Правильный перевод': create_correct_definition_quiz,
    'Пропуск букв': create_skipped_letters_quiz,
    'Найти пары': create_find_pairs_quiz
}
q = Quiz(
    type_='quiz',
    lang='',
    question='',
    options=[],
    correct_option_id=int()
)
quiz_count = 0
correct_count = 0


def create_keyboard(legends: list) -> types.ReplyKeyboardMarkup:
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for el in legends:
        k.add(types.KeyboardButton(el))
    return k


def prep_terms(terms: list) -> str:
    d = dict()
    for el in terms:
        if el[0] not in d:
            d[el[0]] = [el[1]]
        else:
            d[el[0]].append(el[1])
    return "\n".join(
        [word.upper() + ' - ' + '; '.join([f'{i + 1}. {defi[i]}' for i in range(len(defi))]) if len(
            defi) > 1 else word.upper() + ' - ' + defi[0] for word, defi in
         d.items()])


async def check_correct_lang(lang: str, message: types.Message) -> bool:
    if lang not in langs:
        await message.answer('Такого языка не существует. Выберите из: ' + ', '.join(langs),
                             reply_markup=create_keyboard(langs))
        await States.INPUT_LANG.set()
        return False
    return True


keyboard = create_keyboard(list(help_cmd.values()))


@dp.message_handler(Text(equals='Старт', ignore_case=True))
@dp.message_handler(commands=['start', 'help'])
async def description(message: types.message):
    s = '\n'.join(['/' + cmd + ' - ' + legend for cmd, legend in help_cmd.items()])
    await message.answer(s, reply_markup=keyboard)
    await message.answer(csv_description)


@dp.message_handler(state='*', commands='cancel')
@dp.message_handler(Text(equals='cancel', ignore_case=True), state='*')
async def cancel(message: types.message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    logger.info(f'Canceling state {current_state}')
    await state.finish()
    await message.reply('Cancelled.', reply_markup=keyboard)


@dp.message_handler(Text(equals=help_cmd.values(), ignore_case=True)
                    | Command(commands=help_cmd.keys(), ignore_case=True))
async def process_command(message: types.Message, state: FSMContext):
    command = message.get_command() or message.text
    await state.update_data(command=command)
    args = message.get_args()
    if args:
        args = args.split()
        lang = args[0]
        if not await check_correct_lang(lang, message):
            return
        if len(args) == 2:
            lang, word = args
            await state.update_data(lang=lang, word=word)
            await States.INPUT_WORD.set()
            await process_word(message, state)
        elif len(args) == 3:
            lang, word, definition = args
            await state.update_data(lang=lang, word=word, definition=definition)
            await States.INPUT_DEFINITION.set()
            await process_definition(message, state)
        else:
            await description(message)
    else:
        await message.answer('Выберите язык:', reply_markup=create_keyboard(langs))
        await States.INPUT_LANG.set()


@dp.message_handler(state=States.INPUT_LANG)
async def process_lang(message: types.Message, state: FSMContext):
    lang = message.text
    if not await check_correct_lang(lang, message):
        return
    await state.update_data(lang=lang)
    data = await state.get_data()
    command = data.get('command')
    if re.match(r'^\/select_\d+', command) or command == help_cmd['select_5']:
        words = db.select_last_n_terms(int(re.search(r'\d+', command).group()), lang)
    elif re.match(r'^\/random_\d+', command) or command == help_cmd['random_5']:
        words = db.select_n_random(int(re.search(r'\d+', command).group()), lang)
    elif command in ['/select', '/add', '/delete', help_cmd['select'], help_cmd['add'], help_cmd['delete']]:
        last_5_words = db.select_last_n_terms(5, lang)
        await message.answer("Введите слово", reply_markup=create_keyboard([el[0] for el in last_5_words]))
        await States.INPUT_WORD.set()
        await state.update_data(lang=lang)
        return
    else:  # quizzes
        if db.select_n_random(1, lang):
            await message.answer('Выберите викторину', reply_markup=create_keyboard(list(quizzes.keys())))
            await States.CHOOSE_QUIZ.set()
        else:
            await message.answer("Словарь пуст :(", reply_markup=keyboard)
            await state.finish()
        return
    if words:
        s = prep_terms(words)
    else:
        s = "Словарь пуст :("
    await message.answer(s, reply_markup=keyboard)
    await state.finish()


@dp.message_handler(state=States.INPUT_WORD)
async def process_word(message: types.message, state: FSMContext):
    data = await state.get_data()
    word = data.get('word') or message.text.lower()
    lang = data.get('lang')
    command = data.get('command')
    definitions = db.select_all_definitions(word, lang)
    if definitions:
        s = word.upper() + '\n' + '\n'.join([f'{i + 1}. {definition[0]}' for i, definition in enumerate(definitions)])
    else:
        s = None
    if command in ['/select', help_cmd['select']]:
        if not s:
            await message.answer('Такого слова нет в словаре. Хотите добавить определение?',
                                 reply_markup=create_keyboard(['Да', 'Нет']))
            await state.update_data(word=word)
            await States.CHOOSE_OPTION.set()
        else:
            await message.answer(s, reply_markup=keyboard)
            await state.finish()
    elif command in ['/delete', help_cmd['delete']]:
        db.delete(word, lang)
        await message.answer('Слово успешно удалено', reply_markup=keyboard)
        await state.finish()
    else:  # /add
        last_5_words = db.select_last_n_terms(5, lang)
        if s:
            await message.answer(s)
        await message.answer("Введите перевод/определение:",
                             reply_markup=create_keyboard([el[1] for el in last_5_words]))
        await States.INPUT_DEFINITION.set()
        await state.update_data(word=word)


@dp.message_handler(Text(equals=['да', 'нет', 'yes', 'no'], ignore_case=True), state=States.CHOOSE_OPTION)
async def process_yes_or_no(message: types.Message, state: FSMContext):
    option = message.text.lower()
    if option in ['да', 'yes']:
        await state.update_data(command='/add')
        await process_word(message, state)
    elif option in ['нет', 'no']:
        await message.answer('Нет, так нет :(', reply_markup=keyboard)
        await state.finish()


@dp.message_handler(state=States.INPUT_DEFINITION)
async def process_definition(message: types.Message, state: FSMContext):
    definition = message.text
    data = await state.get_data()
    lang = data.get('lang')
    word = data.get('word')
    db.insert(word=word.lower(), definition=definition, lang=lang)
    await state.finish()
    await message.reply("Добавлено\n" + f'{word.upper()} - {definition} ', reply_markup=keyboard)


@dp.message_handler(content_types=['document'])
async def get_csv(message: types.Message):
    document = message.document
    file_name = document.file_name
    lang = file_name.split('.csv')[0]
    if lang not in langs:
        await description(message)
        return
    file_id = document.file_id
    logger.info(f'Получен документ {file_name}')
    if message.document.mime_type == 'text/csv':
        file = await bot.get_file(file_id)
        file_path = file.file_path
        await bot.download_file(file_path, file_name)
        with open(file_name, 'r', encoding='utf-8') as file:
            csv_file = csv.reader(file, delimiter=',')
            for row in csv_file:
                db.insert(row[0].lower(), row[1], lang)
        s = 'Слова успешно добавлены'
    else:
        s = 'Бот принимает только файлы формата CSV'
    await message.answer(s, reply_markup=keyboard)


@dp.message_handler(Text(equals='Правильный перевод'), state=States.CHOOSE_QUIZ)
async def process_correct_definition(message: types.Message, state: FSMContext):
    global q
    data = await state.get_data()
    await state.finish()
    lang = data.get('lang')
    q = create_correct_definition_quiz(lang)
    await message.answer_poll(
        question=q.question,
        options=q.options,
        type=q.type_,
        correct_option_id=q.correct_option_id,
        is_anonymous=False,
        reply_markup=types.ReplyKeyboardRemove()
    )


@dp.poll_answer_handler()
async def handle_poll_answer(poll_answer: types.PollAnswer):
    global quiz_count, q, correct_count
    quiz_count += 1
    if poll_answer.option_ids[0] == q.correct_option_id:
        correct_count += 1
    await bot.send_message(poll_answer.user.id, q.question.upper() + ' - ' + q.options[q.correct_option_id])
    if quiz_count != 5:
        q = create_correct_definition_quiz(q.lang)
        await bot.send_poll(
            chat_id=poll_answer.user.id,
            question=q.question,
            options=q.options,
            type=q.type_,
            correct_option_id=q.correct_option_id,
            is_anonymous=False
        )
    else:
        await bot.send_message(poll_answer.user.id, f'Тестирование завершено. {correct_count}/{quiz_count}',
                               reply_markup=keyboard)
        quiz_count = 0
        correct_count = 0


@dp.message_handler(Text(equals=['Пропуск букв', 'Найти пары']), state=States.CHOOSE_QUIZ)
async def process_skipped_letters(message: types.Message, state: FSMContext):
    global q
    data = await state.get_data()
    print(message.text)
    q = quizzes[message.text](data.get('lang'))
    await message.answer(q.question, reply_markup=types.ReplyKeyboardRemove())
    await States.PROCESS_ANSWER.set()


@dp.message_handler(state=States.PROCESS_ANSWER)
async def process_answer(message: types.Message, state: FSMContext):
    global q, correct_count, quiz_count
    quiz_count += 1
    answer = message.text.lower()
    if q.type_ == 'skipped':
        if answer == q.options:
            await message.answer('+1')
            correct_count += 1
        else:
            await message.answer(f':( ответ: {q.options}')
        q = create_skipped_letters_quiz(q.lang)
    elif q.type_ == 'pairs':
        if answer.split() == q.options:
            await message.answer('+1')
            correct_count += 1
        else:
            await message.answer(f':( ответ: {" ".join(q.options)}')

        q = create_find_pairs_quiz(q.lang)
    if quiz_count == 5:
        await message.answer(f'Тестирование завершено. {correct_count}/{quiz_count}',
                             reply_markup=keyboard)
        correct_count = 0
        quiz_count = 0
        await state.finish()
    else:
        await message.answer(q.question, reply_markup=types.ReplyKeyboardRemove())


if __name__ == '__main__':
    try:
        db.select_n_random(1, 'eng')
    except sqlite3.OperationalError:
        db._init_db()
    executor.start_polling(dp, skip_updates=True)
