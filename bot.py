import os
import csv
from datetime import datetime
from flask import Flask, request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import logging
import asyncio
import nest_asyncio

# ✅ Logging base
logging.basicConfig(level=logging.INFO)

# ✅ Variabili ambiente
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # impostato da Render

CSV_FILE = "log_attivita.csv"
user_data = {}

# ✅ Flask app per Webhook
flask_app = Flask(__name__)

def log_to_csv(cf, azione, data_ora, posizione=None, nota=None):
    with open(CSV_FILE, mode="a", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([cf, azione, data_ora, posizione, nota])

# ✅ /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_data.get(user_id, {}).get("privacy_accepted") is not True:
        keyboard = [
            [InlineKeyboardButton("✅ Accetto", callback_data="accept_privacy")],
            [InlineKeyboardButton("❌ Rifiuto", callback_data="reject_privacy")]
        ]
        await update.message.reply_text(
            "📍 Questo bot utilizza la tua posizione *solo per fini lavorativi*.\n\nVuoi continuare?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("Inserisci il tuo Codice Fiscale:")

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

# ✅ Ricevi CF
async def receive_cf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not user_data.get(user_id, {}).get("privacy_accepted"):
        await update.message.reply_text("❗ Devi prima accettare la privacy con /start.")
        return

    cf = update.message.text.strip().upper()
    user_data[user_id]["cf"] = cf
    await update.message.reply_text(f"Codice Fiscale registrato: `{cf}`", parse_mode="Markdown")
    await send_main_buttons(update, context)

# ✅ Mostra pulsanti principali
async def send_main_buttons(update_or_context, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("🟢 Entrata", callback_data="entrata")],
        [InlineKeyboardButton("📍 Invia posizione", callback_data="invia_posizione")],
        [InlineKeyboardButton("🔴 Uscita", callback_data="uscita")]
    ]
    markup = InlineKeyboardMarkup(buttons)

    if isinstance(update_or_context, Update):
        if update_or_context.message:
            await update_or_context.message.reply_text("Cosa vuoi fare?", reply_markup=markup)
        elif update_or_context.callback_query:
            await update_or_context.callback_query.message.reply_text("Cosa vuoi fare?", reply_markup=markup)
    else:
        await context.bot.send_message(chat_id=update_or_context, text="Cosa vuoi fare?", reply_markup=markup)

# ✅ Handler pulsanti
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

# ✅ Richiesta posizione
async def ask_position(context, user_id):
    await context.bot.send_message(
        chat_id=user_id,
        text="📍 Premi il pulsante qui sotto per inviare la tua posizione.",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Invia posizione 📍", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

# ✅ Ricezione posizione
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
        await update.message.reply_text(f"📍 Posizione registrata: {pos}")
        user_data[user_id]["awaiting_position_after_uscita"] = False
        user_data[user_id]["awaiting_note"] = True
        await update.message.reply_text("📝 Ora scrivimi una nota: dove sei stato, cosa hai fatto...")

    else:
        log_to_csv(cf, "Posizione Generica", now, pos)
        await update.message.reply_text("📍 Posizione registrata.")
        await send_main_buttons(update, context)

# ✅ Gestione note
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data = user_data.get(user_id, {})
    cf = data.get("cf")

    if not cf:
        await receive_cf(update, context)
        return

    if data.get("awaiting_note"):
        note = update.message.text
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_to_csv(cf, "Nota", now, nota=note)
        await update.message.reply_text("📝 Nota salvata con successo!")
        user_data[user_id]["awaiting_note"] = False
        await send_main_buttons(update, context)
    else:
        await update.message.reply_text("⛔ Non ho capito. Usa i pulsanti oppure scrivi una nota quando richiesto.")

# ✅ Flask webhook (corretto)
@flask_app.route(f"/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    asyncio.create_task(application.process_update(update))
    return "ok"

# ✅ Main
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

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
    flask_app.run(host="0.0.0.0", port=10000)
