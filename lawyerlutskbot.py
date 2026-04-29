from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials

TOKEN = "8673313827:AAGlHqmTlzGSxwOjEhkqflTzVor5S4DZCsU"

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

sheet = client.open("lawyer_schedule").sheet1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Записатися", callback_data="book")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Вітаємо! Оберіть дію:",
        reply_markup=reply_markup
    )


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


async def show_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    consultation_type = query.data
    context.user_data["type"] = consultation_type

    records = sheet.get_all_records()

    dates = sorted(set(
        row["date"]
        for row in records
        if row["status"] == "free" and row["type"] == consultation_type
    ))

    keyboard = [[InlineKeyboardButton(date, callback_data=f"date_{date}")]
                for date in dates]

    await query.edit_message_text(
        "Оберіть дату:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_date = query.data.replace("date_", "")
    context.user_data["date"] = selected_date

    consultation_type = context.user_data["type"]

    records = sheet.get_all_records()

    times = [
        row["time"]
        for row in records
        if row["status"] == "free"
        and row["date"] == selected_date
        and row["type"] == consultation_type
    ]

    keyboard = [[InlineKeyboardButton(time, callback_data=f"time_{time}")]
                for time in times]

    await query.edit_message_text(
        "Оберіть час:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_time = query.data.replace("time_", "")
    selected_date = context.user_data["date"]
    consultation_type = context.user_data["type"]

    username = query.from_user.username or "немає username"

    records = sheet.get_all_records()

    for i, row in enumerate(records, start=2):
        if (
            row["date"] == selected_date
            and row["time"] == selected_time
            and row["type"] == consultation_type
            and row["status"] == "free"
        ):
            sheet.update(f"D{i}", "booked")
            sheet.update(f"F{i}", username)
            break

    await query.edit_message_text(
        f"Ви записані:\n\n📅 {selected_date}\n🕐 {selected_time}\n📍 {consultation_type}"
    )


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(book, pattern="book"))
app.add_handler(CallbackQueryHandler(show_dates, pattern="online|offline"))
app.add_handler(CallbackQueryHandler(show_times, pattern="date_"))
app.add_handler(CallbackQueryHandler(confirm, pattern="time_"))

app.run_polling()
