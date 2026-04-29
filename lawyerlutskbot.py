from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

TOKEN = "8673313827:AAHJj9Bv-FGg0_GaIrPSev6ts9X146QAw4E"


# ---------- GOOGLE SHEETS AUTH ----------

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

client = gspread.authorize(creds)
sheet = client.open("lawyer_schedule").sheet1


# ---------- HELPERS ----------

def normalize(value):
    """Нормалізує текст із таблиці"""
    return str(value).strip().lower()


def normalize_time(value):
    """Обрізає секунди якщо вони є"""
    return str(value)[:5]


def normalize_date(value):
    """Уніфікує формат дати"""
    return str(value).strip()


# ---------- START ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Записатися", callback_data="book")]
    ]

    await update.message.reply_text(
        "Вітаємо! Оберіть дію:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- TYPE SELECT ----------

async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton("💻 Онлайн", callback_data="online"),
            InlineKeyboardButton("🏢 Офлайн", callback_data="offline")
        ]
    ]

    await query.edit_message_text(
        "Оберіть формат консультації:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- DATE SELECT ----------

async def show_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    consultation_type = normalize(query.data)
    context.user_data["type"] = consultation_type

    records = sheet.get_all_records()

    dates = sorted(set(
        normalize_date(row["date"])
        for row in records
        if normalize(row["status"]) == "free"
        and normalize(row["type"]) == consultation_type
    ))

    if not dates:
        await query.edit_message_text("Немає доступних дат 😔")
        return

    keyboard = [
        [InlineKeyboardButton(date, callback_data=f"date_{date}")]
        for date in dates
    ]

    await query.edit_message_text(
        "Оберіть дату:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- TIME SELECT ----------

async def show_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_date = query.data.replace("date_", "")
    context.user_data["date"] = selected_date

    consultation_type = context.user_data["type"]

    records = sheet.get_all_records()

    times = [
        normalize_time(row["time"])
        for row in records
        if normalize(row["status"]) == "free"
        and normalize_date(row["date"]) == selected_date
        and normalize(row["type"]) == consultation_type
    ]

    if not times:
        await query.edit_message_text("На цю дату немає вільного часу 😔")
        return

    keyboard = [
        [InlineKeyboardButton(time, callback_data=f"time_{time}")]
        for time in times
    ]

    await query.edit_message_text(
        "Оберіть час:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- CONFIRM BOOKING ----------

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_time = query.data.replace("time_", "")
    selected_date = context.user_data["date"]
    consultation_type = context.user_data["type"]

    username = query.from_user.username or "немає username"
    fullname = query.from_user.full_name

    records = sheet.get_all_records()

    for i, row in enumerate(records, start=2):
        if (
            normalize_date(row["date"]) == selected_date
            and normalize_time(row["time"]) == selected_time
            and normalize(row["type"]) == consultation_type
        ):

            # Перевірка чи слот ще вільний
            if normalize(row["status"]) != "free":
                await query.edit_message_text("Цей слот вже зайнятий 😔")
                return

            sheet.update(f"D{i}", "booked")
            sheet.update(f"E{i}", fullname)
            sheet.update(f"F{i}", username)

            await query.edit_message_text(
                f"Ви записані:\n\n"
                f"📅 {selected_date}\n"
                f"🕐 {selected_time}\n"
                f"📍 {consultation_type}"
            )
            return

    await query.edit_message_text("Помилка запису. Спробуйте ще раз.")


# ---------- RUN BOT ----------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(book, pattern="book"))
app.add_handler(CallbackQueryHandler(show_dates, pattern="online|offline"))
app.add_handler(CallbackQueryHandler(show_times, pattern="date_"))
app.add_handler(CallbackQueryHandler(confirm, pattern="time_"))

app.run_polling()
