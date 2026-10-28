import os
import json
import time
import random
import string
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

# Сброс системных прокси
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)

# === 1. ВСТРОЕННЫЙ ВЕБ-СЕРВЕР ДЛЯ RENDER ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write("UniverseAI Telegram Bot is ONLINE 24/7 via Firebase!".encode('utf-8'))

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"[Web-Server]: Сервер запущен на порту {port} для Render.")
    server.serve_forever()

threading.Thread(target=start_health_server, daemon=True).start()

# === 2. НАСТРОЙКИ ===
TOKEN = os.environ.get("BOT_TOKEN", "8503313877:AAEonBkSLpmTLZ4c-aCmpOAWKnCLNZRSbgg")
FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL", "https://universeai-1e63b-default-rtdb.europe-west1.firebasedatabase.app/")
ADMIN_USERNAMES = [u.strip().lower() for u in os.environ.get("ADMIN_USERNAMES", "molodoypacanzatazit").split(",")]
PRIVATE_CHANNEL_LINK = os.environ.get("PRIVATE_CHANNEL_LINK", "https://t.me/+L6ELmXSLFw9lNjMy")

TARIFFS = {
    "30": {"days": 30, "price": 150, "name": "30 дней"},
    "90": {"days": 90, "price": 250, "name": "90 дней"},
    "365": {"days": 365, "price": 500, "name": "365 дней"},
    "lifetime": {"days": 36500, "price": 700, "name": "Навсегда (Lifetime)"}
}

# === 3. ИНИЦИАЛИЗАЦИЯ FIREBASE ===
try:
    import firebase_admin
    from firebase_admin import credentials, db
except ImportError:
    raise ImportError("Установите: pip install firebase-admin")

def init_firebase():
    if firebase_admin._apps:
        return

    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        "/etc/secrets/firebase_service_account.json",
        "/etc/secrets/firebase_key.json",
        os.path.join(base_dir, "firebase_service_account.json"),
        os.path.join(base_dir, "firebase_key.json"),
        "firebase_service_account.json",
        "firebase_key.json"
    ]
    key_path = next((p for p in candidates if os.path.exists(p)), None)

    if key_path:
        print(f"[Firebase]: Читаем файл ключа: {key_path}")
        cred = credentials.Certificate(key_path)
    else:
        env_creds_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
        if env_creds_json:
            print("[Firebase]: Читаем переменную FIREBASE_CREDENTIALS_JSON...")
            cred_dict = json.loads(env_creds_json)
            if "private_key" in cred_dict:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
        else:
            raise FileNotFoundError("Файл ключа не найден ни в /etc/secrets/, ни в папке проекта!")

    firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})
    print(f"[Firebase]: УСПЕШНОЕ ПОДКЛЮЧЕНИЕ К БАЗЕ: {FIREBASE_DB_URL}")

init_firebase()

bot = telebot.TeleBot(TOKEN)

# === 4. РАБОТА С БАЗОЙ ДАННЫХ ===
def generate_key_code():
    part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"UNIVERSE-{part1}-{part2}"

def create_license_in_firebase(key_code: str, duration_days: int, tariff_name: str, created_by: str) -> dict:
    key_clean = key_code.strip().upper()
    data = {
        "key_code": key_clean,
        "duration_days": duration_days,
        "tariff_name": tariff_name,
        "is_used": 0,
        "created_by": str(created_by),
        "created_at": int(time.time()),
        "tg_claimed_by": None,
        "tg_claimed_username": None,
        "activated_at": None
    }
    db.reference(f"licenses/{key_clean}").set(data)
    return data

def get_user_from_firebase(user_id: int):
    return db.reference(f"users/{user_id}").get()

def save_or_update_user(user_id: int, username: str, sub_expires: str = None, active_key: str = None):
    ref = db.reference(f"users/{user_id}")
    user_data = ref.get() or {}
    user_data["user_id"] = user_id
    user_data["username"] = username or user_data.get("username", "Unknown")
    user_data["last_seen"] = int(time.time())
    
    if sub_expires:
        user_data["sub_expires"] = sub_expires
    elif "sub_expires" not in user_data:
        user_data["sub_expires"] = "Не активна"
        
    if active_key:
        user_data["active_key"] = active_key
        
    ref.set(user_data)
    return user_data

# === 5. МЕНЮ ===
def main_menu(username):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_profile = types.KeyboardButton("👤 Мой профиль")
    btn_key = types.KeyboardButton("🔑 Активировать ключ")
    btn_buy = types.KeyboardButton("💳 Купить подписку")
    btn_help = types.KeyboardButton("ℹ️ Помощь")
    
    markup.add(btn_profile, btn_key)
    markup.add(btn_buy)
    
    if username and username.lower() in ADMIN_USERNAMES:
        btn_gen = types.KeyboardButton("🎲 Сгенерировать ключ (Админ)")
        markup.add(btn_gen)
        
    markup.add(btn_help)
    return markup

# === 6. ОБРАБОТЧИКИ СООБЩЕНИЙ ===
@bot.message_handler(commands=['start'])
def start_cmd(message):
    username = message.from_user.username
    save_or_update_user(message.from_user.id, username)
    welcome_text = (
        f"👋 Привет, **{message.from_user.first_name}**!\n\n"
        f"Добро пожаловать в бота управления **Universe AI**.\n"
        f"Здесь вы можете приобрести и активировать ключ для настольной программы."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_menu(username))

@bot.message_handler(func=lambda m: m.text == "👤 Мой профиль")
def profile_handler(message):
    user_data = get_user_from_firebase(message.from_user.id)
    sub = user_data.get("sub_expires", "Не активна") if user_data else "Не активна"
    active_key = user_data.get("active_key", "Отсутствует") if user_data else "Отсутствует"
    text = (
        f"🆔 **Твой ID:** `{message.from_user.id}`\n"
        f"👤 **Юзернейм:** @{message.from_user.username or 'отсутствует'}\n"
        f"💎 **Статус подписки:** `{sub}`\n"
        f"🔑 **Последний ключ:** `{active_key}`"
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
    if not tariff:
        return

    pay_url = "https://t.me/molodoypacanzatazit"
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # Ссылки на документы пользователя
    markup.add(
        types.InlineKeyboardButton("📜 Пользовательское соглашение", url="https://telegra.ph/PUBLICHNAYA-OFERTA-08-12-15"),
        types.InlineKeyboardButton("🔒 Политика конфиденциальности", url="https://telegra.ph/POLITIKA-KONFIDENCIALNOSTI-08-12-99")
    )
    # Кнопки оплаты
    markup.add(types.InlineKeyboardButton("🔗 Оплатить счет", url=pay_url))
    markup.add(types.InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_pay_{tariff_key}"))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            f"🛒 **Выбран тариф:** {tariff['name']}\n"
            f"💰 **К оплате:** `{tariff['price']} руб.`\n\n"
            f"⚠️ *Нажимая кнопку оплаты, вы подтверждаете свое согласие с Пользовательским соглашением и Политикой конфиденциальности.*\n\n"
            f"1. Нажмите **«Оплатить счет»**.\n"
            f"2. После перевода нажмите **«Проверить оплату»** для получения ключа."
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
    is_paid = True
    
    if is_paid and tariff:
        new_key = generate_key_code()
        days = tariff["days"]
        sub_text = f"Активна ({tariff['name']})" if days < 36500 else "Активна (Навсегда)"
        
        # Сразу привязываем купленный ключ к покупателю
        create_license_in_firebase(new_key, days, tariff['name'], str(user_id))
        db.reference(f"licenses/{new_key}").update({
            "tg_claimed_by": user_id,
            "tg_claimed_username": username or "Unknown"
        })
        save_or_update_user(user_id, username, sub_expires=sub_text, active_key=new_key)
        
        bot.answer_callback_query(call.id, "Оплата подтверждена!", show_alert=True)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                f"🎉 **Оплата подтверждена!**\n\n"
                f"📦 **Тариф:** {tariff['name']}\n"
                f"🔑 **Твой ключ для ПК:**\n`{new_key}`\n\n"
                f"Вставьте этот ключ в окно программы UniverseAI на компьютере.\n"
                f"📥 **Скачать программу:** {PRIVATE_CHANNEL_LINK}"
            ),
            parse_mode="Markdown"
        )

@bot.message_handler(func=lambda m: m.text == "🔑 Активировать ключ")
def key_prompt_handler(message):
    msg = bot.send_message(message.chat.id, "🔑 **Введи лицензионный ключ (UNIVERSE-XXXX-XXXX):**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_key_activation)

def process_key_activation(message):
    user_key = message.text.strip().upper()
    user_id = message.from_user.id
    
    if not user_key.startswith("UNIVERSE-"):
        bot.send_message(message.chat.id, "❌ **Неверный формат ключа!** Ключ должен начинаться с `UNIVERSE-`.", parse_mode="Markdown")
        return

    try:
        ref = db.reference(f"licenses/{user_key}")
        key_data = ref.get()
        
        if not key_data:
            bot.send_message(message.chat.id, "❌ **Ключ не найден в базе Firebase!**", parse_mode="Markdown")
            return
            
        # 1. Проверяем, не занят ли ключ другим пользователем
        claimed_by = key_data.get("tg_claimed_by")
        if claimed_by:
            if str(claimed_by) == str(user_id):
                bot.send_message(
                    message.chat.id, 
                    f"ℹ️ **Вы уже активировали этот ключ ранее!**\n\nОн привязан к вашему профилю. Скопируйте его и вставьте в программу UniverseAI на ПК.", 
                    parse_mode="Markdown"
                )
            else:
                bot.send_message(
                    message.chat.id, 
                    "❌ **Этот ключ уже активирован другим пользователем Telegram!**\nКаждый ключ индивидуален.", 
                    parse_mode="Markdown"
                )
            return

        # 2. Проверяем статус в программе на ПК
        if key_data.get("is_used", 0) == 1:
            bot.send_message(message.chat.id, "⚠️ **Этот ключ уже использован в программе на ПК!**", parse_mode="Markdown")
            return

        # 3. Привязываем ключ к пользователю в облаке
        tariff_name = key_data.get("tariff_name", "Подписка")
        ref.update({
            "tg_claimed_by": user_id,
            "tg_claimed_username": message.from_user.username or "Unknown",
            "tg_claimed_at": int(time.time())
        })
        
        save_or_update_user(user_id, message.from_user.username, sub_expires=f"Активна ({tariff_name})", active_key=user_key)
        
        success_text = (
            f"✅ **Ключ `{user_key}` успешно привязан к вашему профилю!**\n\n"
            f"📦 **Тариф:** {tariff_name}\n"
            f"💻 Теперь скопируйте его и вставьте в программу **UniverseAI** на ПК для полной разблокировки.\n\n"
            f"📥 **Скачать программу:** {PRIVATE_CHANNEL_LINK}"
        )
        bot.send_message(message.chat.id, success_text, parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка Firebase: {e}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎲 Сгенерировать ключ (Админ)")
def generate_key_handler(message):
    username = message.from_user.username
    if not username or username.lower() not in ADMIN_USERNAMES:
        bot.send_message(message.chat.id, "❌ У вас нет прав администратора.", parse_mode="Markdown")
        return

    new_key = generate_key_code()
    create_license_in_firebase(new_key, 30, "30 дней (Админ)", f"admin_{username}")
    bot.send_message(
        message.chat.id,
        f"🎲 **Новый ключ (30 дней):**\n`{new_key}`\n\n✅ _Записан в Firebase, готов к вводу на ПК._",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == "ℹ️ Помощь")
def help_handler(message):
    bot.send_message(message.chat.id, "🛠 **Поддержка Universe AI:** @molodoypacanzatazit", parse_mode="Markdown")

# === 7. ГЛАВНЫЙ ЦИКЛ 24/7 ===
if __name__ == "__main__":
    print("[Бот]: Запущен и слушает Telegram...")
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=10, skip_pending=True)
        except Exception as e:
            print(f"[Сеть]: {e}. Переподключение через 5 сек...")
            time.sleep(5)
