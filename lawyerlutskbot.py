from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 123456789  # ← вставь свой ID


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
    return (
        status is None
        or str(status).strip() == ""
        or normalize(status) == "free"
    )


# ---------- START ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📅 Записатися / Book", callback_data="book")]]

    await update.message.reply_text(
        "✨ Вас вітає приватний консультант Холлі!\n"
        "Тут ви можете записатись до мене на прийом:\n\n"
        "✨ Welcome to Holly, a private consultant!\n"
        "You can make an appointment with me here:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- TYPE ----------

async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [[
        InlineKeyboardButton("💻 Online", callback_data="online"),
        InlineKeyboardButton("🏢 Offline", callback_data="offline")
    ]]

    await query.edit_message_text(
        "Оберіть формат консультації: / Choose a consultation format:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- DATE ----------

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
        keyboard = [[InlineKeyboardButton("💬 Залишити повідомлення / 💬 Leave a message", callback_data="leave_msg")]]

        await query.edit_message_text(
            "Немає доступних дат 😔 / No dates available 😔",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    keyboard = [[InlineKeyboardButton(date, callback_data=f"date_{date}")] for date in dates]

    await query.edit_message_text(
        "Оберіть дату: / Choose a date:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- TIME ----------

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

    times = sorted(set(times))

    if not times:
        await query.edit_message_text("Немає вільного часу 😔 /No time available for appointment 😔")
        return

    keyboard = [[InlineKeyboardButton(time, callback_data=f"time_{time}")] for time in times]

    await query.edit_message_text(
        f"Оберіть час для {selected_date}: /Choose a time for {selected_date}: ",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- ASK PHONE ----------

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["time"] = query.data.replace("time_", "")

    keyboard = [[KeyboardButton("📱 Поділитися номером / 📱 Share your number", request_contact=True)]]

    await query.message.reply_text(
        "Будь ласка, поділіться номером телефону: /Please share your phone number:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )


# ---------- SAVE PHONE ----------

async def save_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.contact.phone_number

    await update.message.reply_text("Коротко опишіть ваше питання: / Briefly describe your question:")


# ---------- SAVE QUESTION ----------

async def save_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["question"] = update.message.text

    await finalize(update, context)


# ---------- FINAL ----------

async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data = context.user_data

    records = sheet.get_all_records()

    for i, row in enumerate(records, start=2):
        if (
            normalize_date(row["date"]) == data["date"]
            and normalize_time(row["time"]) == data["time"]
            and normalize(row["type"]) == data["type"]
        ):

            if not is_free(row["status"]):
                await update.message.reply_text("Слот зайнятий 😔")
                return

            sheet.update(f"D{i}", [["booked"]])
            sheet.update(f"E{i}", [[update.message.from_user.full_name]])
            sheet.update(f"F{i}", [[update.message.from_user.username or ""]])
            sheet.update(f"G{i}", [[data["phone"]]])
            sheet.update(f"H{i}", [[data["question"]]])

            await update.message.reply_text(
                f"Готово! Ви записані ✅ / Done! You are registered ✅\n",
                f"📅 {selected_date}\n" 
                f"🕐 {selected_time}\n" 
                f"📍 {consultation_type}"
            )
            
            return


# ---------- LEAVE MESSAGE ----------

async def leave_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["leave_mode"] = True

    await query.message.reply_text("Напишіть ваше повідомлення:")


async def save_free_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.user_data.get("leave_mode"):
        return

    user = update.message.from_user

    sheet.append_row([
        "-", "-", "message", "new",
        user.full_name,
        user.username or "",
        "",
        update.message.text
    ])

    await update.message.reply_text("Дякую! Ми зв'яжемось з вами 💌")

    context.user_data["leave_mode"] = False


# ---------- RUN ----------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(book, pattern="book"))
app.add_handler(CallbackQueryHandler(show_dates, pattern="online|offline"))
app.add_handler(CallbackQueryHandler(show_times, pattern="date_"))
app.add_handler(CallbackQueryHandler(ask_phone, pattern="time_"))

app.add_handler(MessageHandler(filters.CONTACT, save_phone))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_question))
app.add_handler(CallbackQueryHandler(leave_message, pattern="leave_msg"))
app.add_handler(MessageHandler(filters.TEXT, save_free_message))

app.run_polling()
