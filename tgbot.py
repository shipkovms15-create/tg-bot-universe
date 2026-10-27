import os
import random
import string
from flask import Flask, request
import telebot
from telebot import types

import firebase_admin
from firebase_admin import credentials, firestore

# Сбрасываем системные переменные прокси
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)

# === НАСТРОЙКИ ===
TOKEN = "8503313877:AAEonBkSLpmTLZ4c-aCmpOAWKnCLNZRSbgg"  
ADMIN_USERNAMES = ["molodoypacanzatazit"]
PRIVATE_CHANNEL_LINK = "https://t.me/+L6ELmXSLFw9lNjMy"

TARIFFS = {
    "30": {"days": 30, "price": 150, "name": "30 дней"},
    "90": {"days": 90, "price": 250, "name": "90 дней"},
    "365": {"days": 365, "price": 500, "name": "365 дней"},
    "lifetime": {"days": 36500, "price": 700, "name": "Навсегда"}
}

bot = telebot.TeleBot(TOKEN, threaded=False)

# === ИНИЦИАЛИЗАЦИЯ FIREBASE ===
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

# === FLASK СЕРВЕР ДЛЯ RENDER WEB SERVICE ===
app = Flask(__name__)

@app.route('/')
def index():
    return "Universe AI Bot is active and running!", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type', '').startswith('application/json'):
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

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

@bot.message_handler(commands=['start'])
def start_cmd(message):
    username = message.from_user.username
    user_id = message.from_user.id
    
    user_ref = db.collection('users').document(str(user_id))
    doc = user_ref.get()
    
    if not doc.exists:
        user_ref.set({
            'user_id': user_id,
            'username': username,
            'sub_expires': 'Не активна'
        })
    else:
        user_ref.update({'username': username})
    
    welcome_text = (
        f"👋 Привет, **{message.from_user.first_name}**!\n\n"
        f"Добро пожаловать в официальный бот управления **Universe AI**."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_menu(username))

@bot.message_handler(func=lambda m: m.text == "👤 Мой профиль")
def profile_handler(message):
    user_ref = db.collection('users').document(str(message.from_user.id))
    doc = user_ref.get()
    
    sub = "Не активна"
    if doc.exists:
        sub = doc.to_dict().get('sub_expires', 'Не активна')
        
    text = (
        f"🆔 **Твой ID:** `{message.from_user.id}`\n"
        f"👤 **Юзернейм:** @{message.from_user.username or 'отсутствует'}\n"
        f"💎 **Статус подписки:** `{sub}`"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

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
    if not tariff: return

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
            f"1. Нажми кнопку **«Оплатить счет»**.\n"
            f"2. После оплаты нажми **«Проверить оплату»**."
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
    
    if tariff:
        new_key = generate_key_code()
        days = tariff["days"]
        sub_text = f"Активна ({tariff['name']})" if days < 36500 else "Активна (Навсегда)"
        
        db.collection('users').document(str(user_id)).set({
            'user_id': user_id, 'username': username, 'sub_expires': sub_text
        }, merge=True)
        
        db.collection('keys').document(new_key).set({
            'key_code': new_key, 'duration_days': days, 'is_used': True, 'used_by': user_id
        })
        
        bot.answer_callback_query(call.id, "Оплата подтверждена!", show_alert=True)
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=(
                f"🎉 **Оплата успешно подтверждена!**\n\n"
                f"📦 **Тариф:** {tariff['name']}\n"
                f"🔑 **Твой ключ:** `{new_key}`\n\n"
                f"📥 **Скачать:** {PRIVATE_CHANNEL_LINK}"
            ), parse_mode="Markdown"
        )

@bot.message_handler(func=lambda m: m.text == "🔑 Активировать ключ")
def key_prompt_handler(message):
    msg = bot.send_message(message.chat.id, "🔑 **Введи ключ активации (UNIVERSE-...):**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_key_activation)

def process_key_activation(message):
    user_key = message.text.strip().upper()
    if not user_key.startswith("UNIVERSE-"):
        bot.send_message(message.chat.id, "❌ **Неверный формат!**", parse_mode="Markdown")
        return

    key_ref = db.collection('keys').document(user_key)
    doc = key_ref.get()
    
    if not doc.exists:
        bot.send_message(message.chat.id, "❌ **Ключ не найден!**", parse_mode="Markdown")
    else:
        data = doc.to_dict()
        if data.get('is_used'):
            bot.send_message(message.chat.id, "⚠️ **Этот ключ уже активирован!**", parse_mode="Markdown")
        else:
            duration = data.get('duration_days', 30)
            sub_desc = f"Активна ({duration} дней)" if duration < 36500 else "Активна (Навсегда)"
            
            key_ref.update({'is_used': True, 'used_by': message.from_user.id})
            db.collection('users').document(str(message.from_user.id)).set({
                'user_id': message.from_user.id, 'username': message.from_user.username, 'sub_expires': sub_desc
            }, merge=True)
            
            bot.send_message(message.chat.id, f"✅ **Ключ активирован!**\n\n📥 **Ссылка:** {PRIVATE_CHANNEL_LINK}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎲 Сгенерировать ключ (Админ)")
def generate_key_handler(message):
    username = message.from_user.username
    if not username or username.lower() not in [admin.lower() for admin in ADMIN_USERNAMES]:
        return

    new_key = generate_key_code()
    db.collection('keys').document(new_key).set({
        'key_code': new_key, 'duration_days': 30, 'is_users': False, 'used_by': None
    })
    bot.send_message(message.chat.id, f"🎲 **Новый ключ:**\n`{new_key}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "ℹ️ Помощь")
def help_handler(message):
    bot.send_message(message.chat.id, "🛠 **Поддержка Universe AI**\n\nПо всем вопросам пишите админу.", parse_mode="Markdown")

if __name__ == "__main__":
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/{TOKEN}"
        try:
            bot.remove_webhook()
        except:
            pass
        bot.set_webhook(url=webhook_url)
        print(f"[Система]: Вебхук установлен на {webhook_url}")
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
