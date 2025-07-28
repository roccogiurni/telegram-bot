import os
import csv
import logging
from datetime import datetime
from flask import Flask, request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, Application
)

# ✅ Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# ✅ Variabili d’ambiente da Render
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# ✅ Flask app per webhook
flask_app = Flask(__name__)

# ✅ File CSV per log attività
CSV_FILE = "log_attivita.csv"
user_data = {}

# ✅ Scrittura log su file
def log_to_csv(cf, azione, data_ora, posizione=None, nota=None):
    with open(CSV_FILE, mode="a", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([cf, azione, data_ora, posizione, nota])

# ✅ Start handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not user_data.get(user_id, {}).get("privacy_accepted"):
        keyboard = [
            [InlineKeyboardButton("✅ Accetto", callback_data="accept_privacy")],
            [InlineKeyboardButton("❌ Rifiuto", callback_data="reject_privacy")]
        ]
        await update.message.reply_text(
            "📍 Questo bot usa la tua posizione *solo per fini lavorativi*. Vuoi continuare?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("✅ Inserisci il tuo Codice Fiscale:")

# ✅ Risposta privacy
async def privacy_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "accept_privacy":
        user_data[user_id] = {"privacy_accepted": True}
        await query.edit_message_text("✅ Grazie! Ora inviami il tuo Codice Fiscale:")
    else:
        await query.edit_message_text("❌ Non puoi usare il bot senza accettare la privacy.")

# ✅ Salva CF
async def receive_cf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not user_data.get(user_id, {}).get("privacy_accepted"):
        await update.message.reply_text("❗ Devi prima accettare la privacy con /start.")
        return

    cf = update.message.text.strip().upper()
    user_data[user_id]["cf"] = cf
    await update.message.reply_text(f"📄 Codice Fiscale registrato: `{cf}`", parse_mode="Markdown")
    await send_main_buttons(update, context)

# ✅ Pulsanti principali
async def send_main_buttons(update_or_context, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("🟢 Entrata", callback_data="entrata")],
        [InlineKeyboardButton("📍 Invia posizione", callback_data="invia_posizione")],
        [InlineKeyboardButton("🔴 Uscita", callback_data="uscita")]
    ]
    markup = InlineKeyboardMarkup(buttons)

    if isinstance(update_or_context, Update):
        if update_or_context.message:
            await update_or_context.message.reply_text("Scegli un'opzione:", reply_markup=markup)
        elif update_or_context.callback_query:
            await update_or_context.callback_query.message.reply_text("Scegli un'opzione:", reply_markup=markup)
    else:
        await context.bot.send_message(chat_id=update_or_context, text="Scegli un'opzione:", reply_markup=markup)

# ✅ Gestione pulsanti
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    data = user_data.get(user_id, {})
    cf = data.get("cf")

    if not cf:
        await query.edit_message_text("❗ Prima inserisci il tuo Codice Fiscale con /start")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if query.data == "entrata":
        log_to_csv(cf, "Entrata", now)
        user_data[user_id]["awaiting_position_after_entrata"] = True
        await query.edit_message_text(f"🟢 Entrata registrata il {now}. Ora invia la tua posizione 📍.")
        await ask_position(context, user_id)

    elif query.data == "uscita":
        log_to_csv(cf, "Uscita", now)
        user_data[user_id]["awaiting_position_after_uscita"] = True
        await query.edit_message_text(f"🔴 Uscita registrata il {now}. Ora invia la tua posizione 📍.")
        await ask_position(context, user_id)

    elif query.data == "invia_posizione":
        await ask_position(context, user_id)

# ✅ Chiede posizione
async def ask_position(context, user_id):
    await context.bot.send_message(
        chat_id=user_id,
        text="📍 Premi il pulsante sotto per inviare la posizione.",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Invia posizione 📍", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

# ✅ Gestione posizione
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data = user_data.get(user_id, {})
    cf = data.get("cf")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pos = f"{update.message.location.latitude}, {update.message.location.longitude}"

    if not cf:
        await update.message.reply_text("❗ Inserisci prima il Codice Fiscale con /start.")
        return

    if data.get("awaiting_position_after_entrata"):
        log_to_csv(cf, "Posizione Entrata", now, pos)
        await update.message.reply_text(f"📍 Posizione registrata: {pos}")
        user_data[user_id]["awaiting_position_after_entrata"] = False
        await send_main_buttons(update, context)

    elif data.get("awaiting_position_after_uscita"):
        log_to_csv(cf, "Posizione Uscita", now, pos)
        user_data[user_id]["awaiting_position_after_uscita"] = False
        user_data[user_id]["awaiting_note"] = True
        await update.message.reply_text("📝 Ora scrivi cosa hai fatto e dove sei stato...")
    else:
        log_to_csv(cf, "Posizione", now, pos)
        await update.message.reply_text("📍 Posizione salvata.")
        await send_main_buttons(update, context)

# ✅ Note
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data = user_data.get(user_id, {})
    cf = data.get("cf")

    if not cf:
        await receive_cf(update, context)
        return

    if data.get("awaiting_note"):
        nota = update.message.text
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_to_csv(cf, "Nota", now, nota=nota)
        await update.message.reply_text("📝 Nota registrata con successo.")
        user_data[user_id]["awaiting_note"] = False
        await send_main_buttons(update, context)
    else:
        await update.message.reply_text("❗ Usa i pulsanti o scrivi solo quando richiesto.")

# ✅ Webhook route Flask
@flask_app.route("/webhook", methods=["POST"])
async def webhook():
    try:
        data = request.get_json(force=True)
        logger.info(f"📩 Webhook ricevuto: {data}")
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        logger.error(f"❌ Errore nel webhook: {e}")
        return "error", 500
    return "ok", 200

# ✅ Main async
async def main():
    global application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(privacy_response, pattern="^(accept_privacy|reject_privacy)$"))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(entrata|uscita|invia_posizione)$"))
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    print("✅ Bot avviato con Webhook")

# ✅ Avvio Flask + App
if __name__ == "__main__":
    import nest_asyncio
    import asyncio

    nest_asyncio.apply()
    asyncio.run(main())

    flask_app.run(host="0.0.0.0", port=10000)
