import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# 🔑 Kalitlaringiz
OPENROUTER_API_KEY = "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"
TELEGRAM_BOT_TOKEN = "7067962523:AAHG948FcFpKz70fOx5pTpnadKNs6uX6nSI"

# 🧠 Model (ChatGPT’ga eng o‘xshash)
MODEL = "gpt-4o-mini"  # Juda tez va aqlli model

# /start komandasi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.first_name
    await update.message.reply_text(f"Salom, {user}! 😊\nMen ChatGPT’ga o‘xshash AI botman. Savolingizni yozing!")

# So‘rovlarni AI’ga yuborish
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Siz aqlli, kulgili va foydali yordamchisiz. Foydalanuvchining ismi Yahyobek."},
            {"role": "user", "content": user_text}
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        res_json = response.json()
        reply = res_json["choices"][0]["message"]["content"]
    except Exception as e:
        reply = f"❌ Xatolik: {e}"

    await update.message.reply_text(reply)

# 🔹 Botni ishga tushirish
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

print("✅ AI bot ishga tushdi — ChatGPT uslubida ishlayapti!")
app.run_polling()