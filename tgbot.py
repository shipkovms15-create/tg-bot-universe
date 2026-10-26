import os

# Сбрасываем системные переменные прокси
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)

import sqlite3
import random
import string
import telebot
from telebot import types

# === НАСТРОЙКИ ===
TOKEN = "8503313877:AAEonBkSLpmTLZ4c-aCmpOAWKnCLNZRSbgg"  # Токен твоего бота от BotFather

# Твой юзернейм в Telegram (без @), чтобы получить права администратора
ADMIN_USERNAMES = ["molodoypacanzatazit"]

# Ссылка на твой закрытый канал с программой
PRIVATE_CHANNEL_LINK = "https://t.me/+L6ELmXSLFw9lNjMy"

# === ТАРИФЫ И ЦЕНЫ ===
TARIFFS = {
    "30": {"days": 30, "price": 150, "name": "30 дней"},
    "90": {"days": 90, "price": 250, "name": "90 дней"},
    "365": {"days": 365, "price": 500, "name": "365 дней"},
    "lifetime": {"days": 36500, "price": 700, "name": "Навсегда"}
}

bot = telebot.TeleBot(TOKEN)

# === ПУТЬ К БАЗЕ ДАННЫХ (теперь рядом со скриптом для хостинга) ===
DB_PATH = os.path.join(os.path.dirname(__file__), "universe_system.db")

# === ИНИЦИАЛИЗАЦИЯ И МИГРАЦИЯ БАЗЫ ДАННЫХ ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            sub_expires TEXT DEFAULT 'Не активна'
        )
    ''')
    
    # Таблица ключей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_code TEXT UNIQUE,
            duration_days INTEGER DEFAULT 0,
            is_used INTEGER DEFAULT 0,
            used_by INTEGER
        )
    ''')
    
    # Авто-миграция для старых баз данных
    try:
        cursor.execute('ALTER TABLE keys ADD COLUMN duration_days INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

def generate_key_code():
    part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"UNIVERSE-{part1}-{part2}"

# === КЛАВИАТУРА ГЛАВНОГО МЕНЮ ===
def main_menu(username):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_profile = types.KeyboardButton("👤 Мой профиль")
    btn_key = types.KeyboardButton("🔑 Активировать ключ")
    btn_buy = types.KeyboardButton("💳 Купить подписку")
    btn_help = types.KeyboardButton("ℹ️ Помощь")
    
    markup.add(btn_profile, btn_key)
    markup.add(btn_buy)
    
    if username and username.lower() in [admin.lower() for admin in ADMIN_USERNAMES]:
        btn_gen = types.KeyboardButton("🎲 Сгенерировать ключ (Админ)")
        markup.add(btn_gen)
        
    markup.add(btn_help)
    return markup

# === КОМАНДА /START ===
@bot.message_handler(commands=['start'])
def start_cmd(message):
    init_db()
    username = message.from_user.username
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', 
                   (message.from_user.id, username))
    conn.commit()
    conn.close()
    
    welcome_text = (
        f"👋 Привет, **{message.from_user.first_name}**!\n\n"
        f"Добро пожаловать в официальный бот управления **Universe AI**."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_menu(username))

# === ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ===
@bot.message_handler(func=lambda m: m.text == "👤 Мой профиль")
def profile_handler(message):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT sub_expires FROM users WHERE user_id = ?', (message.from_user.id,))
    row = cursor.fetchone()
    conn.close()
    
    sub = row[0] if row else "Не активна"
    text = (
        f"🆔 **Твой ID:** `{message.from_user.id}`\n"
        f"👤 **Юзернейм:** @{message.from_user.username or 'отсутствует'}\n"
        f"💎 **Статус подписки:** `{sub}`"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# === ПОКУПКА ПОДПИСКИ ===
@bot.message_handler(func=lambda m: m.text == "💳 Купить подписку")
def buy_handler(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, tariff in TARIFFS.items():
        markup.add(types.InlineKeyboardButton(
            f"📦 {tariff['name']} — {tariff['price']} руб.", 
            callback_data=f"select_tariff_{key}"
        ))
    
    bot.send_message(
        message.chat.id,
        "💳 **Выбери подходящий тариф подписки:**",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_tariff_"))
def tariff_selected(call):
    tariff_key = call.data.replace("select_tariff_", "")
    tariff = TARIFFS.get(tariff_key)
    
    if not tariff:
        return

    pay_url = "https://rolley.pay/invoice/example_link" 
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔗 Оплатить счет", url=pay_url))
    markup.add(types.InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_pay_{tariff_key}"))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            f"🛒 **Выбран тариф:** {tariff['name']}\n"
            f"💰 **К оплате:** `{tariff['price']} руб.`\n\n"
            f"1. Нажми кнопку **«Оплатить счет»** и соверши перевод.\n"
            f"2. После оплаты нажми **«Проверить оплату»** для автоматического получения ключа."
        ),
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_pay_"))
def verify_payment_callback(call):
    tariff_key = call.data.replace("check_pay_", "")
    tariff = TARIFFS.get(tariff_key)
    user_id = call.from_user.id
    username = call.from_user.username
    
    is_paid = True  # Заглушка успешной оплаты
    
    if is_paid and tariff:
        new_key = generate_key_code()
        days = tariff["days"]
        sub_text = f"Активна ({tariff['name']})" if days < 36500 else "Активна (Навсегда)"
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', 
            (user_id, username)
        )
        cursor.execute(
            'INSERT INTO keys (key_code, duration_days, is_used, used_by) VALUES (?, ?, 1, ?)', 
            (new_key, days, user_id)
        )
        cursor.execute(
            'UPDATE users SET sub_expires = ? WHERE user_id = ?', 
            (sub_text, user_id)
        )
        conn.commit()
        conn.close()
        
        bot.answer_callback_query(call.id, "Оплата подтверждена!", show_alert=True)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                f"🎉 **Оплата успешно подтверждена!**\n\n"
                f"📦 **Тариф:** {tariff['name']}\n"
                f"🔑 **Твой персональный ключ:** `{new_key}`\n"
                f"✅ Подписка активирована в профиле!\n\n"
                f"📥 **Ссылка на скачивание программы:** {PRIVATE_CHANNEL_LINK}"
            ),
            parse_mode="Markdown"
        )
    else:
        bot.answer_callback_query(call.id, "Оплата еще не поступила. Попробуй позже.", show_alert=True)

# === АКТИВАЦИЯ КЛЮЧА В БОТЕ ===
@bot.message_handler(func=lambda m: m.text == "🔑 Активировать ключ")
def key_prompt_handler(message):
    msg = bot.send_message(
        message.chat.id, 
        "🔑 **Введи твой ключ активации (начинается с UNIVERSE-):**", 
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_key_activation)

def process_key_activation(message):
    user_key = message.text.strip().upper()
    
    if not user_key.startswith("UNIVERSE-"):
        bot.send_message(message.chat.id, "❌ **Неверный формат!** Ключ должен начинаться с `UNIVERSE-`.", parse_mode="Markdown")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, is_used, duration_days FROM keys WHERE key_code = ?', (user_key,))
    key_data = cursor.fetchone()
    
    if not key_data:
        bot.send_message(message.chat.id, "❌ **Ключ не найден в базе!**", parse_mode="Markdown")
    elif key_data[1] == 1:
        bot.send_message(message.chat.id, "⚠️ **Этот ключ уже активирован!**", parse_mode="Markdown")
    else:
        duration = key_data[2]
        sub_desc = f"Активна ({duration} дней)" if duration < 36500 else "Активна (Навсегда)"
        
        cursor.execute('UPDATE keys SET is_used = 1, used_by = ? WHERE id = ?', (message.from_user.id, key_data[0]))
        cursor.execute('UPDATE users SET sub_expires = ? WHERE user_id = ?', (sub_desc, message.from_user.id))
        conn.commit()
        
        success_msg = (
            f"✅ **Ключ {user_key} успешно активирован!**\n\n"
            f"📥 **Ссылка на скачивание программы:** {PRIVATE_CHANNEL_LINK}"
        )
        bot.send_message(message.chat.id, success_msg, parse_mode="Markdown")
        
    conn.close()

# === АДМИНСКАЯ ГЕНЕРАЦИЯ КЛЮЧЕЙ ===
@bot.message_handler(func=lambda m: m.text == "🎲 Сгенерировать ключ (Админ)")
def generate_key_handler(message):
    username = message.from_user.username
    if not username or username.lower() not in [admin.lower() for admin in ADMIN_USERNAMES]:
        bot.send_message(message.chat.id, "❌ У тебя нет прав для выполнения этой команды.", parse_mode="Markdown")
        return

    new_key = generate_key_code()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO keys (key_code, duration_days) VALUES (?, ?)', (new_key, 30))
    conn.commit()
    conn.close()
    
    bot.send_message(
        message.chat.id, 
        f"🎲 **Сгенерирован новый ключ (30 дней):**\n`{new_key}`\n\n_Сохранен в общую базу данных._", 
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == "ℹ️ Помощь")
def help_handler(message):
    bot.send_message(message.chat.id, "🛠 **Поддержка Universe AI**\n\nПо всем вопросам обращайтесь в поддержку.", parse_mode="Markdown")

# === ЗАПУСК БОТА ===
if __name__ == "__main__":
    init_db()
    print("[Система]: Бот запущен.")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
