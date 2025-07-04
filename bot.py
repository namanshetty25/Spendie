# bot.py - Simplified webhook implementation that works

import os
import json
import tempfile
import asyncio
import threading
from flask import Flask, request, jsonify
from telegram import Update, Bot, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
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
    enhance_upi_description, TESSERACT_AVAILABLE
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Flask app
app = Flask(__name__)

# Global bot application
bot_app = None

@app.route("/")
def home():
    return "🤖 Spendie Bot is running!"

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "bot": "running"})

@app.route("/ping")
def ping():
    return "pong"

@app.route(f"/webhook/{TOKEN}", methods=['POST'])
def webhook():
    """Handle incoming webhook updates from Telegram - SIMPLIFIED"""
    try:
        update_data = request.get_json()
        if not update_data:
            return "No data", 400
            
        update = Update.de_json(update_data, bot_app.bot)
        
        # Process update synchronously in a new thread
        def process_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(bot_app.process_update(update))
            except Exception as e:
                print(f"Error processing update: {e}")
            finally:
                loop.close()
        
        # Start processing in background thread
        thread = threading.Thread(target=process_in_thread)
        thread.daemon = True
        thread.start()
        
        return "OK", 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return "Error", 500

# All your existing handler functions remain exactly the same
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to Spendie Bot!*\n\n"
        "💸 *Add Transactions:*\n"
        "• 'Spent ₹200 on groceries'\n"
        "• 'Got ₹5000 salary'\n"
        "• 'Got 1200 from dad' (informal amounts work!)\n"
        "• 'John gave me 1000' (person names work!)\n"
        "• 'Papa ne 1200 diye' (Hindi also works!)\n\n"
        "📱 *Screenshots:*\n"
        "• Send any payment screenshot\n"
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

async def handle_transaction(update: Update, result: dict, user_id: int):
    try:
        if result.get('type') == 'error':
            await update.message.reply_text(
                f"❌ *Error parsing transaction:*\n{result.get('message', 'Unknown error')}",
                parse_mode="Markdown"
            )
            return
        
        if not all(key in result for key in ['type', 'amount', 'description']):
            await update.message.reply_text(
                "⚠️ *Incomplete transaction data*\n"
                "Please provide amount and description.\n"
                "Example: 'Got 1200 from dad' or 'Papa ne 1200 diye'",
                parse_mode="Markdown"
            )
            return
        
        add_transaction(user_id, result)
        
        emoji = "💰" if result['type'] == 'income' else "💸"
        confidence_emoji = "✅" if result.get('confidence') == 'high' else "⚠️"
        
        success_message = f"{confidence_emoji} *Transaction Added:*\n\n"
        success_message += f"{emoji} *{result['type'].title()}:* ₹{result['amount']:,}\n"
        success_message += f"📝 *Description:* {result['description']}\n"
        success_message += f"🏷️ *Category:* {result.get('category', 'miscellaneous')}\n"
        
        if result.get('recipient_sender'):
            success_message += f"👤 *Contact:* {result['recipient_sender']}\n"
        
        if result.get('split_info'):
            success_message += f"🔄 *Split:* {result['split_info']}\n"
        
        if result.get('confidence') == 'low':
            success_message += "\n💡 *Note:* Low confidence - please verify details"
        
        if result.get('rephrased_message') != result.get('original_message'):
            success_message += f"\n\n🔄 *Understood as:* {result['rephrased_message']}"
        
        await update.message.reply_text(success_message, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Transaction handling error: {e}")
        await update.message.reply_text(
            "❌ *Error adding transaction*\n"
            "Something went wrong. Please try again.",
            parse_mode="Markdown"
        )

async def handle_query(update: Update, result: dict, user_id: int):
    try:
        if result.get('intent') == 'error':
            await update.message.reply_text(
                f"❌ *Error parsing query:*\n{result.get('message', 'Unknown error')}",
                parse_mode="Markdown"
            )
            return
        
        intent = result.get('intent', 'list')
        txn_type = result.get('type', 'both')
        category = result.get('category')
        keywords = result.get('keywords')
        amount_filter = result.get('amount_filter')
        start_date = result.get('start_date')
        end_date = result.get('end_date')
        
        transactions = query_transactions(
            user_id=user_id,
            txn_type=txn_type,
            start_date=start_date,
            end_date=end_date,
            keywords=keywords,
            category=category,
            amount=amount_filter
        )
        
        if not transactions:
            await update.message.reply_text(
                "📭 *No transactions found*\n"
                "No transactions match your query criteria.",
                parse_mode="Markdown"
            )
            return
        
        if intent == 'total':
            total = sum(t['amount'] for t in transactions)
            response = f"💰 *Total {txn_type}:* ₹{total:,}\n"
            response += f"📊 *Transactions found:* {len(transactions)}"
            
        elif intent == 'list':
            response = f"📋 *Transaction List:*\n\n"
            for i, txn in enumerate(transactions[:10], 1):
                emoji = "💰" if txn['type'] == 'income' else "💸"
                date = txn['timestamp'].strftime('%m/%d')
                response += f"{i}. {emoji} ₹{txn['amount']:,} - {txn['description']} ({date})\n"
            
            if len(transactions) > 10:
                response += f"\n... and {len(transactions) - 10} more transactions"
                
        elif intent == 'summary':
            total_amount = sum(t['amount'] for t in transactions)
            categories = {}
            for txn in transactions:
                cat = txn.get('category', 'miscellaneous')
                categories[cat] = categories.get(cat, 0) + txn['amount']
            
            response = f"📊 *Summary:*\n"
            response += f"💰 *Total:* ₹{total_amount:,}\n"
            response += f"📈 *Transactions:* {len(transactions)}\n\n"
            response += "*Top Categories:*\n"
            
            sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
            for cat, amount in sorted_cats[:5]:
                response += f"• {cat}: ₹{amount:,}\n"
        
        else:
            response = f"📋 *Found {len(transactions)} transactions*"
        
        await update.message.reply_text(response, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Query handling error: {e}")
        await update.message.reply_text(
            "❌ *Error processing query*\n"
            "Something went wrong. Please try again.",
            parse_mode="Markdown"
        )

async def handle_balance_query(update: Update, user_id: int):
    try:
        income, expense = get_balance(user_id)
        net = income - expense
        
        category_breakdown = get_category_breakdown(user_id, "expense")
        top_category = max(category_breakdown.items(), key=lambda x: x[1]) if category_breakdown else ("N/A", 0)
        
        await update.message.reply_text(
            f"💸 *Your Balance Summary:*\n"
            f"🟢 Income: ₹{income:,}\n"
            f"🔴 Expense: ₹{expense:,}\n"
            f"🧾 Net: ₹{net:,}\n"
            f"📊 Top Category: {top_category[0]} (₹{top_category[1]:,})",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Balance query error: {e}")
        await update.message.reply_text(
            "❌ *Error getting balance*\n"
            "Something went wrong. Please try again.",
            parse_mode="Markdown"
        )

async def handle_unknown_message(update: Update, result: dict):
    await update.message.reply_text(
        "🤔 *I didn't understand that*\n\n"
        "Try:\n"
        "• 'Spent ₹200 on groceries' (for transactions)\n"
        "• 'Got 1200 from dad' (informal amounts work!)\n"
        "• 'Papa ne 1200 diye' (Hindi also works!)\n"
        "• 'How much did I spend on food?' (for queries)\n"
        "• 'What's my balance?' (for balance)\n"
        "• Send a payment screenshot\n\n"
        "Or use /start to see all options.",
        parse_mode="Markdown"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_description = update.message.caption or ""
    
    processing_msg = await update.message.reply_text(
        "🔍 *Processing screenshot...*\n"
        "⏳ Extracting transaction details...",
        parse_mode="Markdown"
    )
    
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
            await file.download_to_drive(tmp_file.name)
            image_path = tmp_file.name
        
        extracted_text = ""
        if TESSERACT_AVAILABLE:
            extracted_text = extract_text_from_image(image_path)
        else:
            with open(image_path, 'rb') as img_file:
                image_bytes = img_file.read()
            extracted_text = extract_text_online_ocr(image_bytes)
        
        os.unlink(image_path)
        
        transaction_data = parse_upi_screenshot(extracted_text, user_description)
        
        if not transaction_data or transaction_data.get('amount', 0) <= 0:
            await processing_msg.edit_text(
                "⚠️ *Could not find transaction details*\n"
                "No amount or transaction information found in the image.",
                parse_mode="Markdown"
            )
            return
        
        is_valid, validation_message = validate_upi_transaction(transaction_data)
        if not is_valid:
            await processing_msg.edit_text(
                f"❌ *Could not process transaction*\n{validation_message}",
                parse_mode="Markdown"
            )
            return
        
        enhanced_description = enhance_upi_description(transaction_data, user_description)
        transaction_data['description'] = enhanced_description
        
        add_transaction(user_id, transaction_data)
        
        emoji = "💰" if transaction_data['type'] == 'income' else "💸"
        confidence_emoji = "✅" if transaction_data.get('confidence') == 'high' else "⚠️"
        
        success_message = f"{confidence_emoji} *Transaction Added from Screenshot:*\n\n"
        success_message += f"{emoji} *{transaction_data['type'].title()}:* ₹{transaction_data['amount']:,}\n"
        success_message += f"📝 *Description:* {transaction_data['description']}\n"
        success_message += f"🏷️ *Category:* {transaction_data.get('category', 'miscellaneous')}\n"
        
        if transaction_data.get('recipient_sender'):
            success_message += f"👤 *Contact:* {transaction_data['recipient_sender']}\n"
        
        if transaction_data.get('app_name'):
            success_message += f"📱 *App:* {transaction_data['app_name'].title()}\n"
        
        if transaction_data.get('confidence') == 'low':
            success_message += "\n💡 *Note:* Low confidence - please verify details"
        
        await processing_msg.edit_text(success_message, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Photo processing error: {e}")
        await processing_msg.edit_text(
            "❌ *Error processing screenshot*\n"
            "Something went wrong while processing your image.",
            parse_mode="Markdown"
        )

# Command handlers
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await handle_balance_query(update, user_id)

async def categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    breakdown = get_category_breakdown(user_id, "expense")
    
    if not breakdown:
        await update.message.reply_text("📭 No expense categories found.")
        return
    
    response = "📊 *Spending by Category:*\n"
    sorted_categories = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
    
    for category, amount in sorted_categories[:10]:
        response += f"• {category}: ₹{amount:,}\n"
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def patterns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    daily_totals = get_daily_totals(user_id, days=7)
    
    if not daily_totals:
        await update.message.reply_text("📭 No spending patterns found.")
        return
    
    response = "📈 *Last 7 Days Spending:*\n"
    total_week = 0
    
    for date, data in daily_totals.items():
        amount = data['total'] if isinstance(data, dict) else data
        response += f"• {date}: ₹{amount:,}\n"
        total_week += amount
    
    avg_daily = total_week / 7 if total_week > 0 else 0
    response += f"\n📊 *Weekly Total:* ₹{total_week:,}\n"
    response += f"📈 *Daily Average:* ₹{avg_daily:,.0f}"
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    csv_file = export_transactions_csv(user_id)
    
    await update.message.reply_document(
        InputFile(csv_file, filename="transactions.csv"),
        caption="📊 Your transaction history exported!"
    )

async def delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    result = delete_all_transactions(user_id)
    await update.message.reply_text(f"🗑️ Deleted {result.deleted_count} transactions.")

async def ocr_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_message = "🔍 *OCR Service Status:*\n\n"
    
    if TESSERACT_AVAILABLE:
        status_message += "✅ Tesseract OCR: Available\n"
        status_message += "📱 Screenshot support: Enabled\n"
    else:
        status_message += "❌ Tesseract OCR: Not installed\n"
        status_message += "📱 Screenshot support: Limited\n"
    
    ocr_api_key = os.getenv("OCR_SPACE_API_KEY")
    if ocr_api_key:
        status_message += "🌐 Online OCR: Configured\n"
    else:
        status_message += "🌐 Online OCR: Not configured\n"
    
    await update.message.reply_text(status_message, parse_mode="Markdown")

def main():
    """Main function - simplified"""
    global bot_app
    
    # Initialize bot
    bot_app = ApplicationBuilder().token(TOKEN).build()
    
    # Add handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("balance", balance))
    bot_app.add_handler(CommandHandler("categories", categories))
    bot_app.add_handler(CommandHandler("patterns", patterns))
    bot_app.add_handler(CommandHandler("export", export))
    bot_app.add_handler(CommandHandler("delete_all", delete_all))
    bot_app.add_handler(CommandHandler("ocr_status", ocr_status))
    
    bot_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Set webhook in a separate thread
    def set_webhook():
        if WEBHOOK_URL:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                webhook_url = f"{WEBHOOK_URL}/webhook/{TOKEN}"
                loop.run_until_complete(bot_app.bot.set_webhook(webhook_url))
                print(f"✅ Webhook set to: {webhook_url}")
            except Exception as e:
                print(f"Error setting webhook: {e}")
            finally:
                loop.close()
    
    # Initialize bot
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_app.initialize())
    loop.close()
    
    # Set webhook
    webhook_thread = threading.Thread(target=set_webhook)
    webhook_thread.daemon = True
    webhook_thread.start()
    
    # Run Flask app
    port = int(os.environ.get('PORT', 8080))
    print(f"🚀 Starting Spendie Bot on port {port}...")
    print("📡 Webhook mode enabled")
    
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

if __name__ == "__main__":
    main()
