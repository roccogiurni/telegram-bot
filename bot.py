import os
import logging
import csv
from datetime import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import nest_asyncio

# App Flask e config
app = Flask(__name__)
nest_asyncio.apply()

BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Set in Render > Environment Variables
WEBHOOK_PATH = "/webhook"
BASE_URL = os.environ.get("WEBHOOK_URL")  # es: https://yourapp.onrender.com
CSV_FILE = "log_attivita.csv"

logging.basicConfig(level=logging.INFO)

user_data = {}

# CSV logger
def log_to_csv(codice_fiscale, azione, data_ora, posizione=None, nota=None):
    with open(CSV_FILE, mode="a", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([codice_fiscale, azione, data_ora, posizione, nota])

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {}

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Accetto", callback_data="accetto")],
        [InlineKeyboardButton("❌ Rifiuto", callback_data="rifiuto")]
    ])
    await update.message.reply_text(
        "Benvenuto \U0001F44B\n\nQuesto bot utilizzerà la tua posizione solo per motivi lavorativi.\nVuoi continuare?",
        reply_markup=keyboard
    )

# Privacy accettazione
async def privacy_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "accetto":
        user_data[user_id]['privacy'] = True
        await query.edit_message_text("Perfetto! \U0001F4DD Inserisci ora il tuo Codice Fiscale:")
    else:
        await query.edit_message_text("Operazione annullata. \U0001F6AB")

# Codice fiscale
async def receive_codice_fiscale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_data.get(user_id, {}).get('privacy') != True:
        await update.message.reply_text("Devi prima accettare l'informativa sulla privacy con /start")
        return

    codice = update.message.text.strip().upper()
    user_data[user_id]['codice_fiscale'] = codice

    await update.message.reply_text(
        f"Codice Fiscale registrato: {codice}",
    )
    await send_main_buttons(update, context)

# Pulsanti
async def send_main_buttons(update_or_query, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001F4C5 Entrata", callback_data="entrata")],
        [InlineKeyboardButton("\U0001F4CD Invia Posizione", callback_data="posizione")],
        [InlineKeyboardButton("\U0001F6AA Uscita", callback_data="uscita")],
    ])

    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text("Scegli un'opzione:", reply_markup=keyboard)
    else:
        await update_or_query.edit_message_text("Scegli un'opzione:", reply_markup=keyboard)

# Gestione callback
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    codice = user_data.get(user_id, {}).get("codice_fiscale")
    if not codice:
        await query.edit_message_text("Inserisci prima il codice fiscale con /start")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if data == "entrata":
        log_to_csv(codice, "Entrata", now)
        user_data[user_id]['awaiting_position'] = True
        await query.edit_message_text(f"✅ Entrata registrata alle {now}. Ora invia la tua posizione.")
        await request_position(query, context)

    elif data == "uscita":
        log_to_csv(codice, "Uscita", now)
        user_data[user_id]['awaiting_position'] = True
        user_data[user_id]['awaiting_note'] = True
        await query.edit_message_text(f"✅ Uscita registrata alle {now}. Ora invia la tua posizione.")
        await request_position(query, context)

    elif data == "posizione":
        user_data[user_id]['awaiting_position'] = True
        await request_position(query, context)

# Richiesta posizione
async def request_position(query, context):
    await query.message.reply_text(
        "\U0001F4CD Premi il pulsante sotto per inviare la tua posizione:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Invia posizione \U0001F4CD", request_location=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )

# Posizione
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    codice = user_data.get(user_id, {}).get("codice_fiscale")

    if not codice:
        await update.message.reply_text("Inserisci prima il codice fiscale con /start")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    position = f"{update.message.location.latitude}, {update.message.location.longitude}"
    log_to_csv(codice, "Posizione", now, posizione=position)
    await update.message.reply_text(f"✅ Posizione registrata: {position} alle {now}")

    if user_data.get(user_id, {}).get('awaiting_note'):
        await update.message.reply_text("\U0001F4DD Scrivimi ora una nota su dove sei stato e cosa hai fatto:")
    else:
        await send_main_buttons(update, context)

    user_data[user_id]['awaiting_position'] = False

# Nota testo
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    codice = user_data.get(user_id, {}).get("codice_fiscale")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = update.message.text

    if user_data.get(user_id, {}).get('awaiting_note'):
        log_to_csv(codice, "Nota", now, nota=text)
        user_data[user_id]['awaiting_note'] = False
        await update.message.reply_text("✅ Nota salvata.")
        await send_main_buttons(update, context)
        return

    if 'codice_fiscale' not in user_data.get(user_id, {}):
        await receive_codice_fiscale(update, context)
    else:
        await update.message.reply_text("Messaggio non riconosciuto. Usa i pulsanti \U0001F447")

# Inizializzazione bot
async def setup_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(privacy_response, pattern="^(accetto|rifiuto)$"))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    await application.initialize()
    await application.bot.set_webhook(url=BASE_URL + WEBHOOK_PATH)
    app.bot_app = application
    print("Bot avviato con webhook!")

# Webhook endpoint
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.bot_app.bot)
    app.bot_app.update_queue.put_nowait(update)
    return "OK"

# Flask startup
if __name__ == '__main__':
    import asyncio
    asyncio.run(setup_bot())
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
