import logging
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ContentType, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor
from geopy.distance import geodesic

API_TOKEN = ''
WEB_APP_URL = 'YOUR_WEB_APP_URL_HERE'  # Например, https://your-domain.com/webapp

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Создаем подключение к базе данных SQLite
conn = sqlite3.connect('userdata.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицу для хранения данных о пользователях
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        steps INTEGER DEFAULT 0,
        registration_date TEXT
    )
''')
conn.commit()

# Инициализация глобальных переменных для отслеживания состояния пользователя
user_data = {}

# Функция для получения количества пройденных шагов пользователя
def get_user_steps(user_id):
    cursor.execute('SELECT steps FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

# Функция для увеличения количества пройденных шагов пользователя на заданное значение
def increase_user_steps(user_id, steps):
    current_steps = get_user_steps(user_id)
    cursor.execute('UPDATE users SET steps = ? WHERE user_id = ?', (current_steps + steps, user_id))
    conn.commit()

async def check_location(chat_id):
    no_steps_counter = 0
    start_time = datetime.now()

    while user_data[chat_id]['tracking']:
        if chat_id in user_data and user_data[chat_id]['last_location']:
            current_location = user_data[chat_id]['last_location']
            previous_location = user_data[chat_id]['previous_location']

            if previous_location:
                distance = geodesic(previous_location, current_location).meters
                session_steps = int(distance / 0.8)  # Предполагаем, что средняя длина шага 0.8 метра

                if session_steps > 0:
                    user_data[chat_id]['session_steps'] += session_steps
                    no_steps_counter = 0
                else:
                    no_steps_counter += 15

                if user_data[chat_id]['tracking']:
                    if 'last_message_id' in user_data[chat_id]:
                        await bot.delete_message(chat_id, user_data[chat_id]['last_message_id'])

                    message = await bot.send_message(chat_id, f'Ты прошел {user_data[chat_id]["session_steps"]} шагов за эту сессию.')
                    user_data[chat_id]['last_message_id'] = message.message_id

            user_data[chat_id]['previous_location'] = current_location

        if no_steps_counter >= 60:
            user_data[chat_id]['tracking'] = False
            await bot.send_message(chat_id, "Нет новых шагов в течение минуты. Трансляция остановлена.")
            break
        await asyncio.sleep(15)

    # Обновляем общее количество шагов после остановки трансляции
    total_steps = get_user_steps(chat_id)
    session_steps = user_data[chat_id]['session_steps']
    increase_user_steps(chat_id, session_steps)
    await bot.send_message(chat_id, f'Трансляция остановлена. Ты прошел {session_steps} шагов за эту сессию. Всего шагов: {total_steps + session_steps}')

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    if get_user_steps(user_id) == 0:
        cursor.execute('INSERT INTO users (user_id, steps, registration_date) VALUES (?, ?, ?)', (user_id, 0, datetime.now().isoformat()))
        conn.commit()
    user_data[message.chat.id] = {'last_location': None, 'previous_location': None, 'session_steps': 0, 'total_distance': 0, 'tracking': True, 'task': None}
    keyboard = InlineKeyboardMarkup()
    web_app_btn = InlineKeyboardButton(text="Open Web App", web_app=types.WebAppInfo(url=WEB_APP_URL))
    keyboard.add(web_app_btn)
    await message.reply("Привет! Отправь мне свою геолокацию, и я буду отслеживать количество пройденных шагов. Пожалуйста, включите трансляцию геопозиции.", reply_markup=keyboard)

@dp.message_handler(content_types=ContentType.LOCATION)
async def handle_location(message: types.Message):
    chat_id = message.chat.id
    user_location = message.location
    current_location = (user_location.latitude, user_location.longitude)

    if chat_id not in user_data:
        user_data[chat_id] = {'last_location': None, 'previous_location': None, 'session_steps': 0, 'total_distance': 0, 'tracking': True, 'task': None}

    user_data[chat_id]['last_location'] = current_location
    user_data[chat_id]['tracking'] = True

    if user_data[chat_id]['task'] is None:
        user_data[chat_id]['task'] = asyncio.create_task(check_location(chat_id))

@dp.message_handler(commands=['stop'])
async def stop_tracking(message: types.Message):
    chat_id = message.chat.id
    if chat_id in user_data:
        user_data[chat_id]['tracking'] = False
        if 'task' in user_data[chat_id] and user_data[chat_id]['task']:
            user_data[chat_id]['task'].cancel()
        user_data[chat_id].pop('task', None)
        total_steps = get_user_steps(chat_id)
        session_steps = user_data[chat_id]['session_steps']
        increase_user_steps(chat_id, session_steps)
        await message.reply(f"Трансляция остановлена. Ты прошел {session_steps} шагов за эту сессию. Всего шагов: {total_steps + session_steps}")

@dp.message_handler(content_types=ContentType.NEW_CHAT_MEMBERS)
async def new_chat_members(message: types.Message):
    if message.new_chat_members and bot.id in [user.id for user in message.new_chat_members]:
        await message.answer("Привет! Я готов отслеживать твою геолокацию и подсчитывать количество пройденных шагов. Пожалуйста, включи трансляцию геопозиции.")

@dp.edited_message_handler(content_types=ContentType.LOCATION)
async def handle_edited_location(message: types.Message):
    await handle_location(message)

async def on_startup(dp):
    logging.info("Bot started")

async def on_shutdown(dp):
    logging.info("Bot stopped")
    conn.close()

if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)
