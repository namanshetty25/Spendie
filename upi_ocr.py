# upi_ocr.py - UPI Screenshot Extraction using Groq VLM (Vision-Language Model) with fallback OCR

import os
import base64
import json
from dotenv import load_dotenv

# Optional: Classic OCR fallback
try:
    import pytesseract
    import cv2
    import numpy as np
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

# --- Groq VLM setup ---
try:
    from groq import Groq
    GROQ_SDK_AVAILABLE = True
except ImportError:
    GROQ_SDK_AVAILABLE = False

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode("utf-8")

def extract_upi_details_vlm(image_path, user_description=""):
    """
    Use Groq's Vision-Language Model to extract UPI transaction details as JSON.
    """
    if not GROQ_API_KEY or not GROQ_SDK_AVAILABLE:
        raise RuntimeError("Groq API key or SDK not set")
    client = Groq(api_key=GROQ_API_KEY)
    image_b64 = encode_image_to_base64(image_path)
    prompt = ("This is a screenshot of a UPI transaction confirmation. First, extract all visible text exactly as it appears in the image."

"Then, classify the extracted information into the following JSON format:

{
  "type": "income or expense",
  "amount": number (in rupees),
  "description": "brief description of what this payment is for, if known or inferable",
  "category": "e.g., food, transfer, shopping, bill, etc.",
  "recipient_sender": "name of the person or business the money was sent to or received from",
  "transaction_id": null (if not visible),
  "app_name": null (if not visible),
  "confidence": "high / medium / low"
}"

"Use context and keywords like "Paid to", "Received from", etc. to infer direction and fill the fields. If information is not explicitly stated or cannot be reasonably inferred, use null."
        f"User description: {user_description}"
    )
    completion = client.chat.completions.create(
        model=GROQ_VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ],
        temperature=0.1,
        max_tokens=1024,
        response_format={"type": "json_object"}
    )
    # Parse the JSON result
    try:
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        print(f"VLM JSON parsing error: {e}")
        return None

# --- Classic OCR fallback (optional) ---
def preprocess_image(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    denoised = cv2.medianBlur(thresh, 3)
    return denoised

def extract_text_from_image(image_path):
    if not TESSERACT_AVAILABLE:
        return ""
    img = preprocess_image(image_path)
    if img is None:
        return ""
    configs = [
        r'--oem 3 --psm 6',
        r'--oem 3 --psm 4',
        r'--oem 3 --psm 3',
        r'--oem 1 --psm 6'
    ]
    best_text = ""
    for config in configs:
        try:
            text = pytesseract.image_to_string(img, config=config)
            if len(text.strip()) > len(best_text.strip()):
                best_text = text
        except Exception:
            continue
    return best_text.strip()

# --- Main interface ---
def parse_upi_screenshot(image_path, user_description=""):
    """
    Main interface: Try VLM first, fallback to OCR+minimal result if needed.
    Returns a dict with transaction details.
    """
    # Try VLM extraction first
    if GROQ_API_KEY and GROQ_SDK_AVAILABLE:
        try:
            result = extract_upi_details_vlm(image_path, user_description)
            if result and result.get("amount"):
                return result
        except Exception as e:
            print(f"VLM extraction failed: {e}")

    # Fallback: classic OCR (returns only minimal result for now)
    try:
        extracted_text = extract_text_from_image(image_path)
    except Exception as e:
        print(f"OCR extraction failed: {e}")
        extracted_text = ""
    # Optionally, you could add LLM-based parsing of extracted_text here.
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
    """Extract text using online OCR service as fallback (not implemented)"""
    return "OCR service unavailable"
