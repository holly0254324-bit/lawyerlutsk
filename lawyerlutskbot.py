from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

TOKEN = os.getenv("BOT_TOKEN")


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
    return str(value).strip().lower()


def normalize_time(value):
    return str(value)[:5]


def normalize_date(value):
    return str(value).strip()


def is_free(status):
    """Перевіряє чи слот вільний"""
    return (
        status is None
        or str(status).strip() == ""
        or normalize(status) == "free"
    )


# ---------- START ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Записатися", callback_data="book")]
    ]

   await update.message.reply_text(
       "✨ Вас вітає приватний консультант Холлі! Тут ви можете записатись до мене на прийом:"
       "✨ Welcome to Holly, a private consultant!\n"
       "You can make an appointment with me here:",
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
        if is_free(row["status"])
        and normalize(row["type"]) == consultation_type
    ))

    if not dates:
        await query.edit_message_text("Немає доступних дат 😔/ No dates available 😔")
        return

    keyboard = [
        [InlineKeyboardButton(date, callback_data=f"date_{date}")]
        for date in dates
    ]

    await query.edit_message_text(
        "Оберіть дату: / Choose a date:",
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
        if is_free(row["status"])
        and normalize_date(row["date"]) == selected_date
        and normalize(row["type"]) == consultation_type
    ]

    times = sorted(set(times))  # защита от дублей

    if not times:
        await query.edit_message_text("На цю дату немає вільного часу 😔 / No free time on this date 😔")
        return

    keyboard = [
        [InlineKeyboardButton(time, callback_data=f"time_{time}")]
        for time in times
    ]

    await query.edit_message_text(
        f"Оберіть час для / Choose a time for {selected_date}:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- CONFIRM BOOKING ----------

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_time = query.data.replace("time_", "")
    selected_date = context.user_data.get("date")
    consultation_type = context.user_data.get("type")

    if not selected_date or not consultation_type:
        await query.edit_message_text(
            "Сесія застаріла. Натисніть /start ще раз. /The session is out of date. Press /start again."
        )
        return

    username = query.from_user.username or "немає username"
    fullname = query.from_user.full_name

    records = sheet.get_all_records()

    for i, row in enumerate(records, start=2):
        if (
            normalize_date(row["date"]) == selected_date
            and normalize_time(row["time"]) == selected_time
            and normalize(row["type"]) == consultation_type
        ):

            if not is_free(row["status"]):
                await query.edit_message_text("Цей слот вже зайнятий 😔 /This slot is already taken 😔")
                return

            sheet.update(f"D{i}", [["booked"]])
            sheet.update(f"E{i}", [[fullname]])
            sheet.update(f"F{i}", [[username]])

            await query.edit_message_text(
                f"Вітаю! Ви записані до мене на приватну консультацію. Підготуйте свої питання та беріть з собою гарний настрій. З нетерпінням чекаю нашої зустрічі 🤩 / Congratulations! You have been booked in for a private consultation with me. Prepare your questions and bring a good mood. I look forward to our meeting 🤩 \n\n"
                f"📅 {selected_date}\n"
                f"🕐 {selected_time}\n"
                f"📍 {consultation_type}"
            )
            return

    await query.edit_message_text("Помилка запису. Спробуйте ще раз. / Write error. Please try again.")


# ---------- RUN BOT ----------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(book, pattern="book"))
app.add_handler(CallbackQueryHandler(show_dates, pattern="online|offline"))
app.add_handler(CallbackQueryHandler(show_times, pattern="date_"))
app.add_handler(CallbackQueryHandler(confirm, pattern="time_"))

app.run_polling()
