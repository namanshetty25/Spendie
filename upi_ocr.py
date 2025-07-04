# upi_ocr.py - Simplified OCR processing 
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
    print("✅ OCR libraries loaded successfully")
except ImportError as e:
    TESSERACT_AVAILABLE = False
    print(f"⚠️ Warning: OCR libraries not available - {e}")

from parser import call_groq

def extract_text_from_image(image_path_or_bytes):
    """Extract text from image using pytesseract without color effects"""
    if not TESSERACT_AVAILABLE:
        raise ImportError("pytesseract and cv2 are required for OCR functionality")
    
    try:
        if isinstance(image_path_or_bytes, str):
            image = cv2.imread(image_path_or_bytes)
        else:
            image = cv2.imdecode(np.frombuffer(image_path_or_bytes, np.uint8), cv2.IMREAD_COLOR)
        
        # Convert to grayscale only, no color inversion or thresholding
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Try multiple OCR configurations for better results
        configs = [
            r'--oem 3 --psm 6',  # Default
            r'--oem 3 --psm 4',  # Single column text
            r'--oem 3 --psm 3',  # Fully automatic page segmentation
            r'--oem 1 --psm 6'   # Different OCR engine
        ]
        
        best_text = ""
        for config in configs:
            try:
                text = pytesseract.image_to_string(gray, config=config)
                if len(text.strip()) > len(best_text.strip()):
                    best_text = text
            except:
                continue
        
        return best_text.strip()
    except Exception as e:
        print(f"OCR Error: {e}")
        return ""

def parse_upi_screenshot(extracted_text, user_description=""):
    """Parse any screenshot text using enhanced AI model"""
    
    system_prompt = """
You are an expert transaction parser. Extract transaction details from any screenshot text and return ONLY valid JSON.

Your job is to:
1. Look for any amount mentioned (₹, Rs, numbers like 10.00, 10, etc.)
2. Determine if money was paid/sent (expense) or received (income)
3. Extract any person/business names mentioned
4. Detect the app name if possible
5. Create a reasonable description

TRANSACTION TYPES:
- EXPENSE: paid, sent, transferred, spent, bought, bill payment, "to [person]"
- INCOME: received, credited, got, earned, "from [person]"

CATEGORIES:
- food, transport, shopping, utilities, entertainment, health, education
- salary, freelance, transfer, bills, miscellaneous

REQUIRED JSON FORMAT:
{
    "type": "income" or "expense",
    "amount": integer (extract number only, remove decimals),
    "description": "brief description of transaction",
    "category": "auto-detected category",
    "recipient_sender": "person/business name if found" or null,
    "transaction_id": "any ID found" or null,
    "app_name": "detected app name" or null,
    "confidence": "high" or "medium" or "low"
}

ENHANCED EXTRACTION RULES:
- If you see "10.00" or "₹10" → amount: 10
- If you see "Paid to [Name]" → type: "expense", recipient_sender: "[Name]"
- If you see "Received from [Name]" → type: "income", recipient_sender: "[Name]"
- If you see partial text like "Vishwa", "Shetty" → combine as "Vishwa Shetty"
- If you see "PhonePe", "Paytm", "GPay" → app_name
- If unclear direction, assume "expense" for most UPI transactions

IMPORTANT:
- Extract ANY number that could be an amount
- Make reasonable assumptions from partial text
- If you find fragments, combine them logically
- Don't worry about perfect OCR - work with what you have
- Always return a valid JSON even if confidence is low

Return ONLY the JSON object.
"""
    
    user_prompt = f"""
Screenshot Text (may be incomplete due to OCR):
{extracted_text}

User Description (if provided):
{user_description}

Extract transaction details from this text. Even if the text is fragmented or unclear, try to identify:
- Any numbers (could be amounts)
- Any names (could be recipients)
- Any payment direction indicators
- Any app names

Return JSON with your best interpretation.
"""
    
    try:
        result = call_groq(system_prompt, user_prompt, temperature=0.1)
        parsed = json.loads(result)
        
        # Ensure amount is integer
        if 'amount' in parsed:
            try:
                # Convert decimal amounts to integers (₹10.00 → 10)
                parsed['amount'] = int(float(parsed['amount']))
            except:
                parsed['amount'] = 0
        
        return parsed
    except Exception as e:
        print(f"Parsing error: {e}")
        # Return a basic structure if parsing fails
        return {
            "type": "expense",
            "amount": 0,
            "description": "Could not parse screenshot",
            "category": "miscellaneous",
            "confidence": "low",
            "recipient_sender": None,
            "transaction_id": None,
            "app_name": None
        }

def validate_upi_transaction(transaction_data):
    """Simplified validation - just check if amount exists"""
    if not transaction_data:
        return False, "No transaction data"
    
    # Only check if amount is present and greater than 0
    try:
        amount = int(transaction_data.get('amount', 0))
        if amount <= 0:
            return False, "No valid amount found"
    except (ValueError, TypeError):
        return False, "Invalid amount format"
    
    return True, "Transaction processed"

def enhance_upi_description(transaction_data, user_description=""):
    """Enhance transaction description"""
    base_description = transaction_data.get('description', '')
    
    upi_context = []
    
    if transaction_data.get('recipient_sender'):
        if transaction_data['type'] == 'expense':
            upi_context.append(f"to {transaction_data['recipient_sender']}")
        else:
            upi_context.append(f"from {transaction_data['recipient_sender']}")
    
    if transaction_data.get('app_name'):
        upi_context.append(f"via {transaction_data['app_name']}")
    
    final_description = base_description
    
    if user_description:
        final_description = f"{user_description} ({base_description})"
    
    if upi_context:
        final_description += f" [{', '.join(upi_context)}]"
    
    return final_description

def extract_text_online_ocr(image_bytes):
    """Extract text using online OCR service as fallback"""
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
            'OCREngine': '2'
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
