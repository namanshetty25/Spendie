# upi_ocr.py - UPI Screenshot Extraction using Groq VLM (Vision-Language Model) 

import os
import base64
import json
from dotenv import load_dotenv

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
    prompt = (
        "You are an expert at reading Indian UPI payment screenshots and extracting structured data.\n"
        "Given the attached payment screenshot, extract and return a JSON object with these fields:\n"
        "- type: \"income\" or \"expense\" (did the user pay or receive?)\n"
        "- amount: integer, in rupees (extract from ₹, Rs, or numbers like 10.00)\n"
        "- description: what is this payment for? (e.g., 'Paid to Vishwanath D Shetty')\n"
        "- category: best guess (food, transfer, shopping, bill, etc.)\n"
        "- recipient_sender: name of the person or business paid to or received from\n"
        "- transaction_id: transaction/reference ID if visible, else null\n"
        "- app_name: payment app if visible (e.g., PhonePe, Paytm, GPay)\n"
        "- confidence: \"high\", \"medium\", or \"low\" (how sure are you?)\n"
        "If a field is not visible or cannot be inferred, set it to null.\n"
        "Use context and keywords like 'Paid to', 'Received from', 'credited', etc. to infer direction.\n"
        "If the screenshot is a payment success page, infer direction from the layout and text.\n"
        "If the user provided a description, use it to improve the result: "
        f"{user_description}\n"
        "Return ONLY the JSON object, no extra text."
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
    try:
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        print(f"VLM JSON parsing error: {e}")
        return None

def parse_upi_screenshot(image_path, user_description=""):
    """
    Main interface: Use VLM only, no fallback OCR.
    Returns a dict with transaction details.
    """
    if GROQ_API_KEY and GROQ_SDK_AVAILABLE:
        try:
            result = extract_upi_details_vlm(image_path, user_description)
            if result and result.get("amount"):
                return result
        except Exception as e:
            print(f"VLM extraction failed: {e}")
    # If VLM fails, return minimal fallback
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
