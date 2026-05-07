import os
import re
import time
import threading
from datetime import datetime
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from curl_cffi import requests as cffi_requests

# ========== এনভায়রনমেন্ট ভেরিয়েবল ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
PORT = int(os.environ.get("PORT", 8080))

# ========== ডাটা স্টোর ==========
user_last_request = {}

# ========== হেল্পার ফাংশন ==========
def is_valid_phone(phone):
    return bool(re.match(r'^\+\d{10,15}$', phone))

def format_phone(phone):
    phone = phone.strip()
    if not phone.startswith('+'):
        if phone.startswith('0') and len(phone) == 11:
            return '+88' + phone
        return '+' + phone
    return phone

def extract_partial_info(html):
    names = re.findall(r'<div class="[^"]*">(.*?)</div>', html)
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
    if emails:
        return f"📧 আংশিক ইমেইল: {emails[0][:3]}***{emails[0][emails[0].find('@'):]}"
    if names:
        name = names[0][:3] + '***' if len(names[0]) > 3 else names[0]
        return f"📛 আংশিক নাম: {name}"
    return "✅ অ্যাকাউন্ট আছে (বিস্তারিত লুকানো)"

# ========== টেলিগ্রাম হ্যান্ডলার ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ অনুমতি নেই। শুধু অ্যাডমিন ব্যবহার করতে পারবেন।")
        return
    
    keyboard = [
        [InlineKeyboardButton("📞 OTP পাঠান", callback_data="otp"),
         InlineKeyboardButton("🔍 অ্যাকাউন্ট চেক", callback_data="check")],
        [InlineKeyboardButton("📋 একাধিক অ্যাকাউন্ট", callback_data="find"),
         InlineKeyboardButton("❓ সাহায্য", callback_data="help")],
        [InlineKeyboardButton("📊 স্ট্যাটাস", callback_data="status")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👑 *স্মার্ট ওটিপি বট লাইভ!*\n\n"
        "✅ সব ফিচার লাইভ\n"
        "✅ অটো রিট্রাই + রেট লিমিট\n"
        "✅ ব্রাউজার ইম্পারসোনেশন (Chrome 110)\n\n"
        "নিচের বাটন সিলেক্ট করুন অথবা কমান্ড ব্যবহার করুন:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def otp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ অনুমতি নেই।")
        return
    
    if not context.args:
        await update.message.reply_text("❌ সঠিক ব্যবহার:\n`/otp +8801XXXXXXXXX`", parse_mode="Markdown")
        return
    
    # রেট লিমিট চেক
    now = datetime.now()
    if user_id in user_last_request:
        diff = (now - user_last_request[user_id]).total_seconds()
        if diff < 30:
            await update.message.reply_text(f"🐢 ধীরে ধীরে করুন! {int(30-diff)} সেকেন্ড বাকি।")
            return
    
    phone = format_phone(context.args[0])
    if not is_valid_phone(phone):
        await update.message.reply_text("❌ ভুল ফরম্যাট! সঠিক: +8801XXXXXXXXX বা 018XXXXXXXX")
        return
    
    user_last_request[user_id] = now
    await update.message.chat.send_action(action="typing")
    msg = await update.message.reply_text("⏳ ওটিপি রিকোয়েস্ট পাঠানো হচ্ছে...")
    
    # ৩ বার রিট্রাই
    for attempt in range(1, 4):
        try:
            response = cffi_requests.post(
                "https://b-api.facebook.com/method/auth/send_sms_code",
                data={"phone": phone, "format": "json"},
                impersonate="chrome110",
                timeout=30
            )
            result = response.json()
            
            if "error" in result:
                if attempt < 3:
                    await msg.edit_text(f"⚠️ Retry {attempt+1}/3...")
                    time.sleep(attempt * 2)
                    continue
                await msg.edit_text(f"❌ ব্যর্থ: {result['error']}")
            else:
                await msg.edit_text(f"✅ ওটিপি রিকোয়েস্ট সফল!\n📱 {phone}\n🔐 এখন আপনার ফোন চেক করুন।")
                return
        except Exception as e:
            if attempt < 3:
                await msg.edit_text(f"⚠️ নেটওয়ার্ক সমস্যা, Retry {attempt+1}/3...")
                time.sleep(attempt * 2)
            else:
                await msg.edit_text(f"❌ নেটওয়ার্ক সমস্যা! {str(e)}")

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ অনুমতি নেই।")
        return
    
    if not context.args:
        await update.message.reply_text("❌ ব্যবহার: `/check +8801XXXXXXXXX`", parse_mode="Markdown")
        return
    
    phone = format_phone(context.args[0])
    if not is_valid_phone(phone):
        await update.message.reply_text("❌ ভুল ফরম্যাট!")
        return
    
    await update.message.chat.send_action(action="typing")
    msg = await update.message.reply_text("🔍 চেক করা হচ্ছে...")
    
    try:
        response = cffi_requests.post(
            "https://www.facebook.com/login/identify/",
            data={"email": phone, "did_submit": "1"},
            impersonate="chrome110",
            timeout=30
        )
        
        if "recovery_code" in response.text or "checkpoint" in response.text:
            partial = extract_partial_info(response.text)
            await msg.edit_text(f"✅ *অ্যাকাউন্ট আছে!*\n\n{partial}\n\nএখন `/otp {phone}` দিন ওটিপি পেতে।", parse_mode="Markdown")
        else:
            await msg.edit_text("❌ এই নম্বরে কোনো অ্যাকাউন্ট নেই।")
    except Exception as e:
        await msg.edit_text(f"❌ রিকোয়েস্ট ব্যর্থ! {str(e)}")

async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ অনুমতি নেই।")
        return
    
    if not context.args:
        await update.message.reply_text("❌ ব্যবহার: `/find +8801XXXXXXXXX`", parse_mode="Markdown")
        return
    
    phone = format_phone(context.args[0])
    if not is_valid_phone(phone):
        await update.message.reply_text("❌ ভুল ফরম্যাট!")
        return
    
    await update.message.chat.send_action(action="typing")
    msg = await update.message.reply_text("🔍 একাধিক অ্যাকাউন্ট খোঁজা হচ্ছে...")
    
    try:
        response = cffi_requests.post(
            "https://www.facebook.com/login/identify/",
            data={"email": phone, "did_submit": "1"},
            impersonate="chrome110",
            timeout=30
        )
        
        accounts = re.findall(r'<div class="[^"]*">([^<]+@[^<]+|<[^>]+>)', response.text)
        if accounts:
            unique = list(set([a for a in accounts if '@' in a or len(a) > 3]))[:5]
            if unique:
                keyboard = []
                for acc in unique:
                    btn = InlineKeyboardButton(acc[:20] + "...", callback_data=f"select_{acc[:10]}")
                    keyboard.append([btn])
                keyboard.append([InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="back_menu")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await msg.edit_text("📋 আপনার নম্বরের সাথে যুক্ত অ্যাকাউন্ট:\nকোনটা সিলেক্ট করবেন?", reply_markup=reply_markup)
                return
        await msg.edit_text("❌ একাধিক অ্যাকাউন্ট পাওয়া যায়নি। `/check` ব্যবহার করুন।")
    except Exception as e:
        await msg.edit_text(f"❌ রিকোয়েস্ট ব্যর্থ! {str(e)}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ অনুমতি নেই।")
        return
    
    uptime = datetime.now()
    await update.message.reply_text(
        "📊 *বট স্ট্যাটাস*\n\n"
        f"✅ বট চালু আছে: {uptime.strftime('%Y-%m-%d %H:%M:%S')}\n"
        "✅ রেট লিমিট: 30 সেকেন্ড\n"
        "✅ ব্রাউজার ইম্পারসোনেশন: Chrome 110\n"
        "✅ অটো রিট্রাই: ৩ বার\n\n"
        "👑 আপনি অ্যাডমিন",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ অনুমতি নেই।")
        return
    
    await update.message.reply_text(
        "📚 *সাহায্য গাইড*\n\n"
        "🔹 কমান্ড সমূহ:\n"
        "`/otp +8801XXXXXXX` - ওটিপি পাঠান\n"
        "`/check +8801XXXXXXX` - অ্যাকাউন্ট চেক\n"
        "`/find +8801XXXXXXX` - একাধিক অ্যাকাউন্ট দেখায়\n"
        "`/status` - বটের অবস্থা দেখুন\n"
        "`/start` - মেনু দেখাবে\n\n"
        "⚡ *এক্সট্রা ফিচার*\n"
        "✅ ভুল ফরম্যাট ধরাবে\n"
        "✅ ৩ বার Auto Retry\n"
        "✅ রেট লিমিট (30 সেকেন্ড)\n"
        "✅ টাইপিং ইন্ডিকেটর\n"
        "✅ সব দেশ সাপোর্ট\n"
        "✅ স্মার্ট এরর মেসেজ\n\n"
        "🔧 ব্রাউজার ইম্পারসোনেশন: Chrome 110",
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "otp":
        await query.edit_message_text("📞 নম্বর দিন: `/otp +8801XXXXXXXXX`", parse_mode="Markdown")
    elif query.data == "check":
        await query.edit_message_text("🔍 নম্বর দিন: `/check +8801XXXXXXXXX`", parse_mode="Markdown")
    elif query.data == "find":
        await query.edit_message_text("📋 নম্বর দিন: `/find +8801XXXXXXXXX`", parse_mode="Markdown")
    elif query.data == "help":
        await help_command(update, context)
    elif query.data == "status":
        await status_command(update, context)
    elif query.data == "back_menu":
        await start(update, context)
    elif query.data.startswith("select_"):
        await query.edit_message_text("✅ অ্যাকাউন্ট সিলেক্ট করা হয়েছে! এখন `/otp +8801XXXXXXXXX` দিন।")

# ========== ফ্লাস্ক অ্যাপ (Render এর জন্য পোর্ট খোলা) ==========
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "🤖 OTP Bot is running!", 200

@flask_app.route('/health')
def health():
    return "OK", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=PORT)

# ========== মেইন ==========
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN সেট করুন!")
        return
    
    # Flask থ্রেড শুরু করুন (Render এর জন্য)
    threading.Thread(target=run_flask, daemon=True).start()
    
    # টেলিগ্রাম বট শুরু করুন
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("otp", otp_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("find", find_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ সব ফিচারসহ বট চালু! (পোর্ট ঠিক করা হয়েছে)")
    print(f"🔥 Render Health Check: http://localhost:{PORT}")
    app.run_polling()

if __name__ == "__main__":
    main()
