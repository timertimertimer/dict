# TODO: add tests and edit project structure

import os
import random
import re

import db.db as db

import csv

from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text, Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from dotenv import load_dotenv
from loguru import logger
from models import *


class States(StatesGroup):
    INPUT_LANG = State()
    INPUT_WORD = State()
    INPUT_DEFINITION = State()

    CHOOSE_OPTION = State()

    CHOOSE_QUIZ = State()
    CHOOSE_NUMBER_OF_QUESTIONS = State()
    PROCESS_ANSWER = State()


def create_correct_definition_question(lang: str = 'eng') -> Question:
    """Создание вопроса для викторины Правильный перевод"""
    words = db.select_n_random(4, lang)
    correct_option_id = random.randrange(0, 4)
    telegram_line_length_limit_in_poll = 100
    options = [el[1][:telegram_line_length_limit_in_poll] for el in words]
    question_string = words[correct_option_id][0]
    return Question(
        type_='quiz',
        lang=lang,
        question=question_string,
        options=options,
        correct_option_id=correct_option_id
    )


def create_skipped_letters_question(lang: str = 'eng') -> Question:
    """Создание вопроса для викторины Пропуск букв"""
    res = db.select_n_random(1, lang)[0]
    word: str = res[0]
    definition: str = res[1]
    while True:
        k = random.randrange(len(word))
        if word[k] != ' ':
            break
    question_string = word.upper()[:k] + '_' + \
                      word.upper()[k + 1:] + ' - ' + definition
    options = word[k]
    return Question(
        type_='skipped',
        lang=lang,
        question=question_string,
        options=options
    )


def create_find_pairs_question(lang: str = 'eng') -> Question:
    """Создание вопроса для викторины Найти пары"""
    res = db.select_n_random(4, lang)
    words = [el[0] for el in res]
    definitions = [el[1] for el in res]
    random.shuffle(definitions)
    options = []
    for i in range(len(words)):
        options.append(f'{i + 1}{chr(definitions.index(res[i][1]) + 97)}')
    question_string = '\n'.join([f'{i + 1}. {words[i].upper()}' for i in range(len(words))]) + '\n\n' + '\n'.join(
        [f'{chr(i + 97)}. {definitions[i]}' for i in range(len(words))])
    return Question(
        type_='pairs',
        lang=lang,
        question=question_string,
        options=options
    )


quizzes = {
    'Правильный перевод': create_correct_definition_question,
    'Пропуск букв': create_skipped_letters_question,
    'Найти пары': create_find_pairs_question
}
question_count = 0
correct_count = 0
number_of_questions = 5
question = Question()

load_dotenv()
API_TOKEN = os.getenv('DICT_API_TOKEN')
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


def create_keyboard(legends: list) -> types.ReplyKeyboardMarkup:
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for el in legends:
        k.add(types.KeyboardButton(el))
    return k


keyboard = create_keyboard(list(help_cmd.values()))


def prep_terms(terms: list) -> str:
    d = dict()
    for el in terms:
        if el[0] not in d:
            d[el[0]] = [el[1]]
        else:
            d[el[0]].append(el[1])
    return "\n".join(
        [word.upper() + ' - ' + '. '.join([f'{i + 1}. {defi[i]}' for i in range(len(defi))]) if len(
            defi) > 1 else word.upper() + ' - ' + defi[0] for word, defi in
         d.items()])


async def check_correct_lang(lang: str, message: types.Message) -> bool:
    if lang not in langs:
        await message.answer('Такого языка не существует. Выберите из: ' + ', '.join(langs),
                             reply_markup=create_keyboard(langs))
        await States.INPUT_LANG.set()
        return False
    return True


@dp.message_handler(Text(equals='Старт', ignore_case=True))
@dp.message_handler(commands=['start', 'help'])
async def description(message: types.message):
    s = '\n'.join(['/' + cmd + ' - ' + legend for cmd,
    legend in help_cmd.items()])
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


@dp.message_handler(Text(equals=help_cmd.values(), ignore_case=True) |
                    Command(commands=help_cmd.keys(), ignore_case=True))
async def process_command(message: types.Message, state: FSMContext):
    command = message.get_command() or message.text
    await state.update_data(command=command)
    args = message.get_args()
    if args:
        args = args.split('|', maxsplit=2)
        lang, word = args[:2]
        if not await check_correct_lang(lang, message):
            return
        if len(args) == 2:
            await state.update_data(lang=lang, word=word)
            await States.INPUT_WORD.set()
            await process_word(message, state)
        elif len(args) == 3:
            definition = args[-1]
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
        words = db.select_last_n_terms(
            int(re.search(r'\d+', command).group()), lang)
    elif re.match(r'^\/random_\d+', command) or command == help_cmd['random_5']:
        words = db.select_n_random(
            int(re.search(r'\d+', command).group()), lang)
    elif command in ['/select', '/add', '/delete', help_cmd['select'], help_cmd['add'], help_cmd['delete']]:
        last_5_words = db.select_last_n_terms(5, lang)
        await message.answer("Введите слово", reply_markup=create_keyboard([el[0] for el in last_5_words]))
        await state.update_data(lang=lang)
        await States.INPUT_WORD.set()
        return
    else:  # quizzes
        if db.select_n_random(1, lang):
            await message.answer('Выберите викторину', reply_markup=create_keyboard(quizzes))
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
    terms = db.select_all_definitions(word, lang)
    s = prep_terms(terms) if terms else None
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


@dp.message_handler(Text(equals=['да', 'нет', 'yes', 'no', 'y', 'n', 'д', 'н'], ignore_case=True),
                    state=States.CHOOSE_OPTION)
async def process_yes_or_no(message: types.Message, state: FSMContext):
    option = message.text.lower()
    if option in ['да', 'yes', 'д', 'y']:
        await state.update_data(command='/add')
        await process_word(message, state)
    elif option in ['нет', 'no', 'н', 'n']:
        await message.answer('Нет, так нет :(', reply_markup=keyboard)
        await state.finish()


@dp.message_handler(state=States.INPUT_DEFINITION)
async def process_definition(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang')
    word = data.get('word')
    definition = data.get('definition') or message.text
    if '|' in definition:
        for el in definition.split('|'):
            db.insert(word=word.lower(), definition=el, lang=lang)
    else:
        db.insert(word=word.lower(), definition=definition, lang=lang)
    await state.finish()
    await message.reply("Добавлено\n" + f'{word.upper()} - {definition}', reply_markup=keyboard)


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


@dp.message_handler(Text(equals=quizzes), state=States.CHOOSE_QUIZ)
async def process_quiz_type(message: types.Message, state: FSMContext):
    quiz_type = message.text
    await state.update_data(quiz_type=quiz_type)
    await message.answer('Количество вопросов? Введите число', reply_markup=types.ReplyKeyboardRemove())
    await States.CHOOSE_NUMBER_OF_QUESTIONS.set()


@dp.message_handler(regexp=r'\d+', state=States.CHOOSE_NUMBER_OF_QUESTIONS)
async def process_number_of_questions(message: types.Message, state: FSMContext):
    global number_of_questions, question
    number_of_questions = int(message.text)
    print(number_of_questions)
    data = await state.get_data()
    lang = data.get('lang')
    quiz_type = data.get('quiz_type')
    question = quizzes[quiz_type](lang)
    if quiz_type == 'Правильный перевод':
        await state.finish()
        await message.answer_poll(
            question='1. ' + question.question,
            options=question.options,
            type=question.type_,
            correct_option_id=question.correct_option_id,
            is_anonymous=False,
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        await message.answer(question.question, reply_markup=types.ReplyKeyboardRemove())
        await States.PROCESS_ANSWER.set()


@dp.poll_answer_handler()
async def handle_poll_answer(poll_answer: types.PollAnswer):
    global question_count, correct_count, question
    question_count += 1
    if poll_answer.option_ids[0] == question.correct_option_id:
        correct_count += 1
    await bot.send_message(poll_answer.user.id, question.question.upper() + ' - ' +
                           question.options[question.correct_option_id])
    if question_count != number_of_questions:
        question = create_correct_definition_question(question.lang)
        await bot.send_poll(
            chat_id=poll_answer.user.id,
            question=f'{question_count + 1}. ' + question.question,
            options=question.options,
            type=question.type_,
            correct_option_id=question.correct_option_id,
            is_anonymous=False
        )
    else:
        await bot.send_message(poll_answer.user.id, f'Тестирование завершено. {correct_count}/{question_count}',
                               reply_markup=keyboard)
        question_count = 0
        correct_count = 0


@dp.message_handler(state=States.PROCESS_ANSWER)
async def process_answer(message: types.Message, state: FSMContext):
    global correct_count, question_count, question
    question_count += 1
    answer = message.text.lower()
    if question.type_ == 'skipped':
        if answer == question.options:
            await message.answer('+1')
            correct_count += 1
        else:
            await message.answer(f':( ответ: {question.options}')
    elif question.type_ == 'pairs':
        if answer.split() == question.options:
            await message.answer('+1')
            correct_count += 1
        else:
            await message.answer(f':( ответ: {" ".join(question.options)}')
    if question_count == number_of_questions:
        await message.answer(f'Тестирование завершено. {correct_count}/{question_count}', reply_markup=keyboard)
        correct_count = 0
        question_count = 0
        await state.finish()
    else:
        question = quizzes[(await state.get_data())['quiz_type']](question.lang)
        await message.answer(question.question, reply_markup=types.ReplyKeyboardRemove())


if __name__ == '__main__':
    db.select_n_random(1, 'eng')
    executor.start_polling(dp, skip_updates=True)
