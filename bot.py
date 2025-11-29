import requests
import logging
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)
from config import TELEGRAM_BOT_TOKEN

# === НАСТРОЙКИ ===
LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"

# Словарь для хранения истории диалога
user_contexts = {}

# Словарь для хранения ID всех сообщений (пользователь + бот)
user_messages = {}

# Логирование в консоль VS Code
logging.basicConfig(
    format="%(asctime)s — %(levelname)s — %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Привет! Я Telegram-бот, работающий на основе локальной LLM через LM Studio.\n\n"
        "Вот мои возможности:\n"
        "🧠 Я запоминаю контекст диалога\n"
        "🗑 Могу его очистить командой /clear\n"
        "🧼 Могу удалить сообщения чата через /del_message (контекст сохраняется)\n\n"
        "📌 Доступные команды:\n"
        "/start — показать справку\n"
        "/clear — очистить контекст\n"
        "/del_message — удалить сообщения из чата\n\n"
        "Можешь задавать любые вопросы!"
    )
    sent = await update.message.reply_text(text)

    user_id = update.effective_user.id
    if user_id not in user_messages:
        user_messages[user_id] = []
    user_messages[user_id].append(sent.message_id)


# === Команда /clear — очистка контекста ===
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_contexts[user_id] = ""
    sent = await update.message.reply_text("Контекст очищен! 🧹")

    if user_id not in user_messages:
        user_messages[user_id] = []
    user_messages[user_id].append(sent.message_id)


# === Команда /del_message — удаление сообщений из чата ===
async def del_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Если нет сообщений для удаления
    if user_id not in user_messages or len(user_messages[user_id]) == 0:
        msg = await update.message.reply_text("Нет сообщений для удаления.")
        user_messages.setdefault(user_id, []).append(msg.message_id)
        return

    try:
        # Удаляем ВСЕ сохранённые сообщения
        for msg_id in user_messages[user_id]:
            try:
                await context.bot.delete_message(chat_id, msg_id)
            except Exception:
                pass  # некоторые сообщения Telegram может запретить удалить

        # Очищаем список
        user_messages[user_id].clear()

        # Отправляем уведомление (и логируем его)
        confirm = await context.bot.send_message(
            chat_id,
            "🔄 Все сообщения очищены (контекст сохранён)."
        )
        user_messages[user_id].append(confirm.message_id)

    except Exception as e:
        logger.error(f"Ошибка при удалении сообщений: {e}")
        await update.message.reply_text(
            "❗ Не удалось удалить сообщения (проверьте права бота)."
        )


# === Обработка обычных сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        user_text = update.message.text

        # Инициализация хранилищ
        if user_id not in user_contexts:
            user_contexts[user_id] = ""
        if user_id not in user_messages:
            user_messages[user_id] = []

        # Записываем ID сообщения пользователя
        user_messages[user_id].append(update.message.message_id)

        # Добавляем сообщение пользователя в контекст
        user_contexts[user_id] += f"\nuser: {user_text}"

        # Запрос к LM Studio
        payload = {
            "model": "local-model",
            "messages": [
                {"role": "system", "content": "Ты — дружелюбный помощник."},
                {"role": "user", "content": user_contexts[user_id]},
            ],
            "temperature": 0.7
        }

        response = requests.post(LM_STUDIO_URL, json=payload)
        response_data = response.json()
        ai_answer = response_data["choices"][0]["message"]["content"]

        # Добавляем ответ модели в контекст
        user_contexts[user_id] += f"\nassistant: {ai_answer}"

        # Отправляем ответ бота и сохраняем message_id
        sent = await update.message.reply_text(ai_answer)
        user_messages[user_id].append(sent.message_id)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        await update.message.reply_text("⚠ Произошла ошибка при обработке сообщения.")


# === Запуск бота ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Устанавливаем команды бота (подсказки при вводе "/")
    commands = [
        BotCommand("start", "Информация о боте"),
        BotCommand("clear", "Очистить контекст"),
        BotCommand("del_message", "Удалить сообщения чата"),
    ]
    app.bot.set_my_commands(commands)

    # Обработчики команд и сообщений
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("del_message", del_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен!")
    app.run_polling()
