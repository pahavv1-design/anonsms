import telebot
from telebot import types
import sqlite3
import os
import time

# ================= НАСТРОЙКИ (ИЗ ПАНЕЛИ BOTHOST) =================
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID')) if os.getenv('ADMIN_ID') else 0
CHANNEL_ID = os.getenv('CHANNEL_ID') # Например: @mychannel
CHANNEL_URL = os.getenv('CHANNEL_URL') # Например: https://t.me/mychannel
SUPPORT_LINK = os.getenv('SUPPORT_LINK') # Ссылка на твой аккаунт для поддержки
# =============================================================

bot = telebot.TeleBot(BOT_TOKEN)

# База данных
conn = sqlite3.connect('anon_bot.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                  (user_id INTEGER PRIMARY KEY, received_count INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS messages 
                  (msg_id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id INTEGER, recipient_id INTEGER, bot_msg_id INTEGER)''')
conn.commit()

def is_subscribed(user_id):
    if not CHANNEL_ID: return True
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except: return True

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🔗 Моя ссылка", "👤 Профиль")
    markup.add("🆘 Поддержка", "⚙️ Инфо")
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

    if not is_subscribed(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✨ Подписаться", url=CHANNEL_URL))
        bot.send_message(user_id, "🔔 <b>Чтобы пользоваться ботом, подпишись на наш канал!</b>", reply_markup=markup, parse_mode="HTML")
        return

    args = message.text.split()
    if len(args) > 1:
        target_id = args[1]
        if target_id == str(user_id):
            bot.send_message(user_id, "❌ Нельзя писать самому себе!", reply_markup=main_menu())
        else:
            welcome_text = (f"🌟 <b>Вы перешли по анонимной ссылке!</b>\n\n"
                          f"Приготовьте что-то крутое:\n"
                          f"✍️ Напишите текст\n"
                          f"🎬 Отправьте видео\n"
                          f"🖼 Прикрепите фото\n"
                          f"🎙 Запишите голосовое\n\n"
                          f"<i>Владелец не узнает, кто вы. Пишите прямо сейчас!</i> 👇")
            msg = bot.send_message(user_id, welcome_text, parse_mode="HTML")
            bot.register_next_step_handler(msg, process_anon_message, target_id)
        return

    bot.send_message(user_id, "🚀 <b>Бот готов к работе!</b>\nСоздай ссылку и получай анонимные сообщения.", reply_markup=main_menu(), parse_mode="HTML")

# Обработка анонимного сообщения
def process_anon_message(message, target_id):
    try:
        # Уведомляем получателя
        cursor.execute("UPDATE users SET received_count = received_count + 1 WHERE user_id = ?", (target_id,))
        
        # Кнопки для получателя (Ответ, Удаление, Реакции)
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_reply = types.InlineKeyboardButton("💬 Ответить", callback_data=f"reply_{message.chat.id}")
        btn_del = types.InlineKeyboardButton("🗑 Удалить", callback_data="delete_msg")
        btn_like = types.InlineKeyboardButton("❤️", callback_data=f"react_like_{message.chat.id}")
        btn_up = types.InlineKeyboardButton("👍", callback_data=f"react_up_{message.chat.id}")
        markup.add(btn_reply, btn_del, btn_like, btn_up)

        sent_msg = None
        header = "📩 <b>Вам новое сообщение:</b>"

        if message.content_type == 'text':
            sent_msg = bot.send_message(target_id, f"{header}\n\n{message.text}", reply_markup=markup, parse_mode="HTML")
        elif message.content_type == 'photo':
            sent_msg = bot.send_photo(target_id, message.photo[-1].file_id, caption=header, reply_markup=markup, parse_mode="HTML")
        elif message.content_type == 'video':
            sent_msg = bot.send_video(target_id, message.video.file_id, caption=header, reply_markup=markup, parse_mode="HTML")
        elif message.content_type == 'voice':
            sent_msg = bot.send_voice(target_id, message.voice.file_id, caption=header, reply_markup=markup, parse_mode="HTML")

        # Сохраняем в БД для связи
        cursor.execute("INSERT INTO messages (sender_id, recipient_id, bot_msg_id) VALUES (?, ?, ?)", 
                       (message.chat.id, target_id, sent_msg.message_id))
        conn.commit()

        bot.send_message(message.chat.id, "✅ Сообщение доставлено анонимно!", reply_markup=main_menu())
    except:
        bot.send_message(message.chat.id, "❌ Ошибка. Возможно, бот заблокирован.")

# Колбэки (Кнопки под сообщением)
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith("reply_"):
        sender_id = call.data.split("_")[1]
        msg = bot.send_message(call.message.chat.id, "📝 <b>Введите ваш ответ:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, send_reply, sender_id)
        bot.answer_callback_query(call.id)

    elif call.data == "delete_msg":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "Сообщение удалено")

    elif call.data.startswith("react_"):
        _, type, sender_id = call.data.split("_")
        emoji = "❤️" if type == "like" else "👍"
        try:
            bot.send_message(sender_id, f"👤 Получатель отреагировал на ваше сообщение: {emoji}")
            bot.answer_callback_query(call.id, "Реакция отправлена!")
        except:
            bot.answer_callback_query(call.id, "Не удалось отправить реакцию")

# Функция ответа
def send_reply(message, sender_id):
    try:
        header = "💬 <b>Вам пришел ответ на ваше анонимное сообщение:</b>"
        bot.send_message(sender_id, f"{header}\n\n{message.text}", parse_mode="HTML")
        bot.send_message(message.chat.id, "✅ Ответ отправлен!", reply_markup=main_menu())
    except:
        bot.send_message(message.chat.id, "❌ Не удалось отправить ответ.")

@bot.message_handler(func=lambda message: message.text == "🆘 Поддержка")
def support(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Написать админу", url=SUPPORT_LINK))
    bot.send_message(message.chat.id, "У вас возникли вопросы или предложения? Нажмите кнопку ниже:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🔗 Моя ссылка")
def get_link(message):
    bot_name = bot.get_me().username
    link = f"https://t.me/{bot_name}?start={message.chat.id}"
    bot.send_message(message.chat.id, f"💬 <b>Твоя персональная ссылка:</b>\n\n<code>{link}</code>\n\nРазмести её в описании профиля!", parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "👤 Профиль")
def profile(message):
    cursor.execute("SELECT received_count FROM users WHERE user_id = ?", (message.chat.id,))
    res = cursor.fetchone()
    count = res[0] if res else 0
    bot.send_message(message.chat.id, f"👤 <b>Твой профиль:</b>\n\n🆔 Твой ID: <code>{message.chat.id}</code>\n📩 Получено сообщений: {count}", parse_mode="HTML")

# Админка (упрощенная)
@bot.message_handler(commands=['admin'])
def admin(message):
    if message.chat.id != ADMIN_ID: return
    cursor.execute("SELECT COUNT(*) FROM users")
    bot.send_message(message.chat.id, f"📊 Юзеров в базе: {cursor.fetchone()[0]}\nИспользуйте /broadcast для рассылки.")

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if message.chat.id != ADMIN_ID: return
    msg = bot.send_message(message.chat.id, "Введите текст рассылки:")
    bot.register_next_step_handler(msg, run_broadcast)

def run_broadcast(message):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    for u in users:
        try: bot.send_message(u[0], message.text); time.sleep(0.05)
        except: pass
    bot.send_message(message.chat.id, "✅ Готово!")

if __name__ == '__main__':
    bot.infinity_polling()
