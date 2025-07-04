# upi_ocr.py - OCR processing for UPI transaction screenshots

import os
import requests
from PIL import Image
from io import BytesIO
import re
from datetime import datetime
import json

try:
    import pytesseract
    import cv2
    import numpy as np
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    print("⚠️ Warning: pytesseract and cv2 not installed. OCR functionality will be limited.")

from parser import call_groq

def extract_text_from_image(image_path_or_bytes):
    if not TESSERACT_AVAILABLE:
        raise ImportError("pytesseract and cv2 are required for OCR functionality")
    
    try:
        if isinstance(image_path_or_bytes, str):
            image = cv2.imread(image_path_or_bytes)
        else:
            image = cv2.imdecode(np.frombuffer(image_path_or_bytes, np.uint8), cv2.IMREAD_COLOR)
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        denoised = cv2.medianBlur(thresh, 5)
        
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz₹.,:-/ '
        text = pytesseract.image_to_string(denoised, config=custom_config)
        
        return text.strip()
    except Exception as e:
        print(f"OCR Error: {e}")
        return ""

def parse_upi_screenshot(extracted_text, user_description=""):
    system_prompt = """
You are an expert UPI transaction parser for Indian payment apps. Extract transaction details from OCR text and return ONLY valid JSON.

Common UPI apps: PhonePe, Paytm, Google Pay, BHIM, Amazon Pay, Cred, WhatsApp Pay, etc.

UPI Transaction patterns to look for:
1. AMOUNT: ₹123, Rs 123, INR 123, 123.00, 123/-
2. TRANSACTION TYPE:
   - PAID/SENT: "Paid to", "Sent to", "Payment successful", "Money sent", "Transferred"
   - RECEIVED: "Received from", "Money received", "Payment received", "Credited"
3. RECIPIENT/SENDER: Names, phone numbers, UPI IDs
4. TRANSACTION ID: Usually alphanumeric codes
5. DATE/TIME: Various formats
6. STATUS: Success, Failed, Pending

Extract these details:
{
    "type": "income" or "expense",
    "amount": integer (extract number only),
    "description": "brief description of transaction",
    "category": "auto-detected category",
    "recipient_sender": "person/business name",
    "transaction_id": "UPI transaction ID if found",
    "app_name": "detected UPI app name",
    "confidence": "high" or "medium" or "low"
}

Categories for UPI transactions:
- food (restaurants, food delivery, groceries)
- transport (taxi, fuel, parking)
- shopping (online/offline purchases)
- utilities (electricity, gas, water, mobile recharge)
- entertainment (movies, games, subscriptions)
- health (medicines, doctor fees)
- education (fees, courses)
- transfer (person-to-person transfers)
- bills (rent, EMI, insurance)
- miscellaneous (others)

If user has provided additional description, incorporate it into the transaction description.
Return ONLY the JSON object. If transaction details cannot be clearly determined, set confidence to "low".
"""
    
    user_prompt = f"""
OCR Extracted Text:
{extracted_text}

User Description (if provided):
{user_description}

Parse this UPI transaction and return JSON with extracted details.
"""
    
    try:
        result = call_groq(system_prompt, user_prompt)
        return json.loads(result)
    except Exception as e:
        print(f"UPI parsing error: {e}")
        return None

def validate_upi_transaction(transaction_data):
    if not transaction_data:
        return False, "Could not parse transaction data"
    
    required_fields = ['type', 'amount', 'description']
    for field in required_fields:
        if field not in transaction_data or not transaction_data[field]:
            return False, f"Missing required field: {field}"
    
    try:
        amount = int(transaction_data['amount'])
        if amount <= 0:
            return False, "Invalid amount"
    except (ValueError, TypeError):
        return False, "Invalid amount format"
    
    if transaction_data['type'] not in ['income', 'expense']:
        return False, "Invalid transaction type"
    
    confidence = transaction_data.get('confidence', 'low')
    if confidence == 'low':
        return True, "Low confidence in parsing - please verify"
    
    return True, "Valid transaction"

def enhance_upi_description(transaction_data, user_description=""):
    base_description = transaction_data.get('description', '')
    
    upi_context = []
    
    if transaction_data.get('recipient_sender'):
        if transaction_data['type'] == 'expense':
            upi_context.append(f"paid to {transaction_data['recipient_sender']}")
        else:
            upi_context.append(f"received from {transaction_data['recipient_sender']}")
    
    if transaction_data.get('app_name'):
        upi_context.append(f"via {transaction_data['app_name']}")
    
    final_description = base_description
    
    if user_description:
        final_description = f"{user_description} ({base_description})"
    
    if upi_context:
        final_description += f" [{', '.join(upi_context)}]"
    
    return final_description

def extract_text_online_ocr(image_bytes):
    try:
        OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY")
        if not OCR_SPACE_API_KEY:
            return "OCR service not configured"
        
        url = "https://api.ocr.space/parse/image"
        files = {
            'file': ('screenshot.jpg', image_bytes, 'image/jpeg')
        }
        
        data = {
            'apikey': OCR_SPACE_API_KEY,
            'language': 'eng',
            'detectOrientation': 'true',
            'isCreateSearchablePdf': 'false',
            'isSearchablePdfHideTextLayer': 'false',
            'OCREngine': '2',
            'isTable': 'false'
        }
        
        response = requests.post(url, files=files, data=data)
        result = response.json()
        
        if result.get('IsErroredOnProcessing'):
            return "OCR processing failed"
        
        parsed_text = ""
        for parsed_result in result.get('ParsedResults', []):
            parsed_text += parsed_result.get('ParsedText', '')
        
        return parsed_text.strip()
        
    except Exception as e:
        print(f"Online OCR error: {e}")
        return "OCR service unavailable"

def detect_upi_app(text):
    upi_apps = {
        'phonepe': ['phonepe', 'phone pe', 'purple app'],
        'paytm': ['paytm', 'pay tm'],
        'googlepay': ['google pay', 'gpay', 'tez'],
        'bhim': ['bhim', 'bhim upi'],
        'amazonpay': ['amazon pay', 'amazon'],
        'cred': ['cred', 'cred pay'],
        'whatsapp': ['whatsapp', 'whatsapp pay'],
        'freecharge': ['freecharge', 'free charge'],
        'mobikwik': ['mobikwik', 'mobi kwik'],
        'airtel': ['airtel money', 'airtel payments'],
        'jio': ['jio money', 'jio pay'],
        'sbi': ['sbi pay', 'yono sbi'],
        'icici': ['icici', 'imobile'],
        'hdfc': ['hdfc', 'paymentapp']
    }
    
    text_lower = text.lower()
    for app_name, keywords in upi_apps.items():
        for keyword in keywords:
            if keyword in text_lower:
                return app_name
    
    return "unknown"

def extract_upi_amount(text):
    amount_patterns = [
        r'₹\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
        r'rs\.?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
        r'inr\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
        r'(\d+(?:,\d+)*(?:\.\d{2})?)\s*/-',
        r'paid\s*.*?(\d+(?:,\d+)*(?:\.\d{2})?)',
        r'sent\s*.*?(\d+(?:,\d+)*(?:\.\d{2})?)',
        r'received\s*.*?(\d+(?:,\d+)*(?:\.\d{2})?)',
    ]
    
    for pattern in amount_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            amount_str = matches[0].replace(',', '').replace('.', '')
            try:
                return int(amount_str)
            except ValueError:
                continue
    
    return None

def is_upi_screenshot(text):
    upi_indicators = [
        'upi', 'payment', 'transaction', 'paid', 'received', 'sent',
        'successful', 'phonepe', 'paytm', 'google pay', 'gpay',
        'bhim', 'amazon pay', 'cred', 'whatsapp pay', '₹', 'rupees',
        'transaction id', 'reference number', 'to:', 'from:'
    ]
    
    text_lower = text.lower()
    matches = sum(1 for indicator in upi_indicators if indicator in text_lower)
    
    return matches >= 2
