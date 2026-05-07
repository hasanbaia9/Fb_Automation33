import os
import re
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from curl_cffi import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

user_last_request = {}

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ অনুমতি নেই।")
        return
    
    keyboard = [
        [InlineKeyboardButton("📞 OTP পাঠান", callback_data="otp")],
        [InlineKeyboardButton("🔍 অ্যাকাউন্ট চেক", callback_data="check")],
        [InlineKeyboardButton("📋 একাধিক অ্যাকাউন্ট", callback_data="find")],
        [InlineKeyboardButton("❓ সাহায্য", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👑 *স্মার্ট ওটিপি বট লাইভ!*\n\n"
        "✅ সব ফিচার লাইভ (curl_cffi)\n"
        "✅ অটো রিট্রাই + রেট লিমিট\n\n"
        "নিচের বাটন সিলেক্ট করুন:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def otp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ অনুমতি নেই।")
        return
    
    if not context.args:
        await update.message.reply_text("❌ সঠিক ব্যবহার: `/otp +8801XXXXXXXXX`")
        return
    
    # রেট লিমিট চেক
    now = datetime.now()
    if user_id in user_last_request:
        diff = (now - user_last_request[user_id]).total_seconds()
        if diff < 30:
            await update.message.reply_text(f"🐢 {int(30-diff)} সেকেন্ড অপেক্ষা করুন।")
            return
    
    phone = format_phone(context.args[0])
    if not is_valid_phone(phone):
        await update.message.reply_text("❌ ভুল ফরম্যাট! সঠিক: +8801XXXXXXXXX")
        return
    
    user_last_request[user_id] = now
    await update.message.chat.send_action(action="typing")
    
    msg = await update.message.reply_text("⏳ ওটিপি রিকোয়েস্ট পাঠানো হচ্ছে...")
    
    # ৩ বার রিট্রাই
    for attempt in range(1, 4):
        try:
            response = requests.post(
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
        await update.message.reply_text("❌ ব্যবহার: `/check +8801XXXXXXXXX`")
        return
    
    phone = format_phone(context.args[0])
    if not is_valid_phone(phone):
        await update.message.reply_text("❌ ভুল ফরম্যাট!")
        return
    
    await update.message.chat.send_action(action="typing")
    msg = await update.message.reply_text("🔍 চেক করা হচ্ছে...")
    
    try:
        response = requests.post(
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
        await update.message.reply_text("❌ ব্যবহার: `/find +8801XXXXXXXXX`")
        return
    
    phone = format_phone(context.args[0])
    if not is_valid_phone(phone):
        await update.message.reply_text("❌ ভুল ফরম্যাট!")
        return
    
    await update.message.chat.send_action(action="typing")
    msg = await update.message.reply_text("🔍 একাধিক অ্যাকাউন্ট খোঁজা হচ্ছে...")
    
    try:
        response = requests.post(
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
                    btn = InlineKeyboardButton(acc[:20], callback_data=f"select_{acc[:10]}")
                    keyboard.append([btn])
                keyboard.append([InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="back_menu")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await msg.edit_text("📋 আপনার নম্বরের সাথে যুক্ত অ্যাকাউন্ট:\nকোনটা সিলেক্ট করবেন?", reply_markup=reply_markup)
                return
        await msg.edit_text("❌ একাধিক অ্যাকাউন্ট পাওয়া যায়নি। `/check` ব্যবহার করুন।")
    except Exception as e:
        await msg.edit_text(f"❌ রিকোয়েস্ট ব্যর্থ! {str(e)}")

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
        await query.edit_message_text(
            "📚 *সাহায্য*\n\n"
            "`/otp +8801XXXXXXX` - ওটিপি পাঠান\n"
            "`/check +8801XXXXXXX` - অ্যাকাউন্ট চেক\n"
            "`/find +8801XXXXXXX` - সব অ্যাকাউন্ট দেখাবে\n\n"
            "⚡ ফিচার: অটো রিট্রাই, রেট লিমিট, টাইপিং ইন্ডিকেটর\n"
            "🔧 ব্রাউজার ইম্পারসোনেশন: Chrome 110",
            parse_mode="Markdown"
        )
    elif query.data == "back_menu":
        await start(update, context)
    elif query.data.startswith("select_"):
        await query.edit_message_text("✅ অ্যাকাউন্ট সিলেক্ট করা হয়েছে! এখন `/otp +8801XXXXXXX` দিন।")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ অনুমতি নেই।")
        return
    await update.message.reply_text(
        "📚 *সাহায্য*\n\n"
        "`/otp +8801XXXXXXX` - ওটিপি পাঠান\n"
        "`/check +8801XXXXXXX` - অ্যাকাউন্ট চেক\n"
        "`/find +8801XXXXXXX` - সব অ্যাকাউন্ট দেখাবে\n"
        "`/start` - মেনু দেখাবে\n\n"
        "⚡ ফিচার: অটো রিট্রাই, রেট লিমিট, টাইপিং ইন্ডিকেটর",
        parse_mode="Markdown"
    )

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN সেট করুন!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("otp", otp_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("find", find_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ সব ফিচারসহ বট চালু! (curl_cffi + ব্রাউজার ইম্পারসোনেশন)")
    app.run_polling()

if __name__ == "__main__":
    main()
