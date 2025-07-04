# bot.py - Updated for Webhook deployment on Render

import os
import json
import tempfile
from flask import Flask, request, jsonify
from telegram import Update, Bot, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, Application
from dotenv import load_dotenv

from parser import (
    process_user_message, parse_transaction, parse_query, 
    is_balance_query, is_transaction_input, enhance_query_with_context
)

from db import (
    add_transaction, get_balance, query_transactions,
    export_transactions_csv, delete_all_transactions,
    get_category_breakdown, get_spending_patterns,
    get_daily_totals, compare_periods
)

from upi_ocr import (
    extract_text_from_image, extract_text_online_ocr,
    parse_upi_screenshot, validate_upi_transaction,
    enhance_upi_description, is_upi_screenshot,
    TESSERACT_AVAILABLE
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Your Render app URL

# Flask app for webhook
app = Flask(__name__)

# Initialize bot application
bot_app = None

async def initialize_bot():
    global bot_app
    bot_app = ApplicationBuilder().token(TOKEN).build()
    
    # Add all handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("balance", balance))
    bot_app.add_handler(CommandHandler("categories", categories))
    bot_app.add_handler(CommandHandler("patterns", patterns))
    bot_app.add_handler(CommandHandler("export", export))
    bot_app.add_handler(CommandHandler("delete_all", delete_all))
    bot_app.add_handler(CommandHandler("ocr_status", ocr_status))
    
    bot_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    await bot_app.initialize()
    
    # Set webhook
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/webhook/{TOKEN}"
        await bot_app.bot.set_webhook(webhook_url)
        print(f"✅ Webhook set to: {webhook_url}")

@app.route("/")
def home():
    return "🤖 Spendie Bot is running with webhooks!"

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "mode": "webhook"})

@app.route(f"/webhook/{TOKEN}", methods=['POST'])
async def webhook():
    """Handle incoming webhook updates from Telegram"""
    try:
        update_data = request.get_json()
        update = Update.de_json(update_data, bot_app.bot)
        
        # Process the update
        await bot_app.process_update(update)
        
        return "OK", 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return "Error", 500

@app.route("/set_webhook", methods=['POST'])
async def set_webhook():
    """Manually set webhook (for testing)"""
    try:
        webhook_url = f"{WEBHOOK_URL}/webhook/{TOKEN}"
        await bot_app.bot.set_webhook(webhook_url)
        return jsonify({"status": "Webhook set successfully", "url": webhook_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# All your existing handler functions remain the same
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to Spendie Bot!*\n\n"
        "💸 *Add Transactions:*\n"
        "• 'Spent ₹200 on groceries'\n"
        "• 'Got ₹5000 salary'\n"
        "• 'Got 1200 from dad' (informal amounts work!)\n"
        "• 'John gave me 1000' (person names work!)\n"
        "• 'Papa ne 1200 diye' (Hindi also works!)\n\n"
        "📱 *UPI Screenshots:*\n"
        "• Send UPI payment screenshots\n"
        "• Add optional description with photo\n"
        "• Bot will auto-extract transaction details\n\n"
        "📊 *Ask Questions:*\n"
        "• 'What's my current balance?'\n"
        "• 'How much did I spend this week?'\n"
        "• 'Show me all expenses for June'\n"
        "• 'What's my biggest spending category?'\n\n"
        "⚙️ *Commands:*\n"
        "/balance - Current balance\n"
        "/export - Download CSV\n"
        "/delete_all - Clear all data\n"
        "/categories - Show spending by category\n"
        "/patterns - Show spending patterns\n"
        "/ocr_status - Check OCR service status",
        parse_mode="Markdown"
    )

# Keep all your existing handler functions (handle_message, handle_transaction, etc.)
# Just copy them from your current bot.py - they remain unchanged

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.message.from_user.id
    
    result = process_user_message(user_text)
    
    if result.get('message_type') == 'transaction':
        await handle_transaction(update, result, user_id)
    elif result.get('message_type') == 'query':
        await handle_query(update, result, user_id)
    elif result.get('message_type') == 'balance':
        await handle_balance_query(update, user_id)
    else:
        await handle_unknown_message(update, result)

# ... (include all your other handler functions here)

if __name__ == "__main__":
    import asyncio
    
    # Initialize bot in async context
    asyncio.run(initialize_bot())
    
    # Run Flask app
    port = int(os.environ.get('PORT', 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
