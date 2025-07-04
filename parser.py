# parser.py - Two-stage message parser for financial transactions

import os
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json"
}

def call_groq(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature
    }
    
    try:
        response = requests.post(GROQ_URL, headers=HEADERS, json=payload)
        result = response.json()
        
        if "choices" not in result:
            print("❌ Groq API Error:", result)
            raise ValueError("Invalid response from Groq API")
            
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"❌ Exception in call_groq: {e}")
        raise

class MessageParser:
    def __init__(self):
        self.rephrase_agent = RephraseAgent()
        self.classification_agent = ClassificationAgent()
    
    def parse_message(self, user_message: str) -> Dict:
        try:
            rephrased_message = self.rephrase_agent.rephrase(user_message)
            classification_result = self.classification_agent.classify(rephrased_message, user_message)
            
            classification_result['original_message'] = user_message
            classification_result['rephrased_message'] = rephrased_message
            classification_result['processing_timestamp'] = datetime.now().isoformat()
            
            return classification_result
            
        except Exception as e:
            print(f"❌ Error in parse_message: {e}")
            return {
                'error': str(e),
                'original_message': user_message,
                'processing_timestamp': datetime.now().isoformat()
            }

class RephraseAgent:
    def rephrase(self, user_message: str) -> str:
        system_prompt = """
You are a financial message standardization expert. Rephrase user messages about money transactions into clear, standardized format.

RULES:
1. Keep all important information (amount, description, people involved)
2. Use clear action words: "spent", "received", "paid", "got", "sent", "bought"
3. Use standard currency format: ₹[amount]
4. Make the message grammatically correct and clear
5. Preserve context like person names, places, categories
6. Numbers without currency symbols should be treated as rupees (₹)
7. Handle all variations of giving/receiving money

COMMON PATTERNS TO RECOGNIZE:
- "X gave me Y" = "Received ₹Y from X"
- "got Y from X" = "Received ₹Y from X"
- "X ne Y diye" = "Received ₹Y from X"
- "spent Y on X" = "Spent ₹Y on X"
- "paid Y for X" = "Paid ₹Y for X"
- "bought X for Y" = "Bought X for ₹Y"
- "sent Y to X" = "Sent ₹Y to X"

EXAMPLES:
Input: "spent 50 on coffee"
Output: "Spent ₹50 on coffee"

Input: "got 1200 from dad"
Output: "Received ₹1200 from dad"

Input: "john gave me 50"
Output: "Received ₹50 from john"

Input: "alex gave me 1000"
Output: "Received ₹1000 from alex"

Input: "mike gave me 500 rupees"
Output: "Received ₹500 from mike"

Input: "received 2000 from mom"
Output: "Received ₹2000 from mom"

Input: "papa ne 1200 diye"
Output: "Received ₹1200 from papa"

Input: "bhai ne 500 diye the"
Output: "Received ₹500 from bhai"

Input: "paid electricity bill 1300"
Output: "Paid electricity bill ₹1300"

Input: "bought groceries 200 rupees"
Output: "Spent ₹200 on groceries"

Input: "sent 300 to sister"
Output: "Sent ₹300 to sister"

Input: "gave 150 to friend"
Output: "Sent ₹150 to friend"

Input: "lent 800 to colleague"
Output: "Sent ₹800 to colleague"

Input: "borrowed 1500 from bank"
Output: "Received ₹1500 from bank"

IMPORTANT:
- Don't change the meaning or add information not present
- Keep person names exactly as mentioned (preserve case)
- Preserve the transaction type (income/expense)
- Make it sound natural but standardized
- Always treat standalone numbers as rupees (₹)
- "gave me" always means "received from"
- "gave to" always means "sent to"

Rephrase the following message into standard format:
"""
        
        try:
            rephrased = call_groq(system_prompt, user_message, temperature=0.1)
            return rephrased.strip()
        except Exception as e:
            print(f"❌ Error in rephrasing: {e}")
            return user_message

class ClassificationAgent:
    def classify(self, rephrased_message: str, original_message: str = "") -> Dict:
        message_type = self._determine_message_type(rephrased_message)
        
        if message_type == "transaction":
            return self._extract_transaction_details(rephrased_message, original_message)
        elif message_type == "query":
            return self._extract_query_details(rephrased_message, original_message)
        elif message_type == "balance":
            return self._extract_balance_query(rephrased_message, original_message)
        else:
            return {
                'type': 'unknown',
                'message': rephrased_message,
                'confidence': 'low'
            }
    
    def _determine_message_type(self, message: str) -> str:
        system_prompt = """
You are a message type classifier for financial messages. Classify the message into one of these types:

1. "transaction" - User is recording a financial transaction (income or expense)
   Examples: "Spent ₹200 on groceries", "Received ₹5000 salary", "Paid electricity bill", "Received ₹50 from john"

2. "query" - User is asking about their transaction history or patterns
   Examples: "How much did I spend on food?", "Show me expenses for June", "What did I buy yesterday?"

3. "balance" - User is asking about their current balance or financial summary
   Examples: "What's my balance?", "Show me income vs expense", "Financial summary"

4. "unknown" - Message doesn't fit above categories

Respond with only the classification type: "transaction", "query", "balance", or "unknown"
"""
        
        try:
            result = call_groq(system_prompt, message, temperature=0.1)
            return result.lower().strip()
        except:
            return "unknown"
    
    def _extract_transaction_details(self, message: str, original_message: str) -> Dict:
        system_prompt = """
You are an expert transaction parser. Extract transaction details from the message and return ONLY valid JSON.

TRANSACTION TYPES:
1. INCOME: salary, income, credited, deposited, got, received, earned, added, freelance
2. EXPENSE: spent, bought, paid, lost, donated, withdraw, sent, bill, purchase

CATEGORIES:
- food (groceries, restaurants, snacks, meals)
- transport (taxi, bus, fuel, parking, auto)
- entertainment (movies, games, subscriptions, outings)
- utilities (electricity, gas, water, mobile recharge, internet)
- shopping (clothes, electronics, household items)
- health (medicines, doctor fees, hospital)
- education (fees, courses, books)
- salary (job income)
- freelance (project income)
- investment (mutual funds, stocks)
- charity (donations)
- transfer (person-to-person transfers)
- cash (ATM withdrawals)
- bills (rent, EMI, insurance)
- miscellaneous (others)

REQUIRED JSON FORMAT:
{
    "type": "income" or "expense",
    "amount": integer (extract number only),
    "description": "brief description",
    "category": "auto-detected category",
    "confidence": "high" or "medium" or "low",
    "recipient_sender": "person/business name if mentioned" or null,
    "split_info": "split details if mentioned" or null
}

EXAMPLES:
"Spent ₹200 on groceries" → {"type": "expense", "amount": 200, "description": "groceries", "category": "food", "confidence": "high", "recipient_sender": null, "split_info": null}

"Received ₹5000 from mom" → {"type": "income", "amount": 5000, "description": "received from mom", "category": "transfer", "confidence": "high", "recipient_sender": "mom", "split_info": null}

"Received ₹50 from john" → {"type": "income", "amount": 50, "description": "received from john", "category": "transfer", "confidence": "high", "recipient_sender": "john", "split_info": null}

"Received ₹1000 from alex" → {"type": "income", "amount": 1000, "description": "received from alex", "category": "transfer", "confidence": "high", "recipient_sender": "alex", "split_info": null}

Return ONLY the JSON object.
"""
        
        try:
            result = call_groq(system_prompt, message, temperature=0.1)
            parsed = json.loads(result)
            parsed['message_type'] = 'transaction'
            return parsed
        except Exception as e:
            print(f"❌ Error extracting transaction: {e}")
            return {
                'type': 'error',
                'message': f"Could not parse transaction: {e}",
                'confidence': 'low'
            }
    
    def _extract_query_details(self, message: str, original_message: str) -> Dict:
        system_prompt = """
You are a query parser for financial transaction searches. Convert the message into structured query parameters.

QUERY TYPES:
- "list" - Show transactions
- "total" - Calculate sum
- "summary" - Show breakdown/analysis
- "search" - Find specific transactions

TIME PERIODS:
- "today", "yesterday"
- "this week", "last week"
- "this month", "last month"
- "last 7 days", "last 30 days"

REQUIRED JSON FORMAT:
{
    "intent": "list" | "total" | "summary" | "search",
    "type": "income" | "expense" | "both",
    "category": "category name" or null,
    "keywords": ["keyword1", "keyword2"] or null,
    "amount_filter": {"gt": number, "lt": number} or null,
    "start_date": "YYYY-MM-DD" or null,
    "end_date": "YYYY-MM-DD" or null,
    "confidence": "high" | "medium" | "low"
}

Return ONLY the JSON object.
"""
        
        try:
            result = call_groq(system_prompt, message, temperature=0.2)
            parsed = json.loads(result)
            parsed['message_type'] = 'query'
            parsed = self._enhance_query_dates(parsed)
            return parsed
        except Exception as e:
            print(f"❌ Error extracting query: {e}")
            return {
                'intent': 'error',
                'message': f"Could not parse query: {e}",
                'confidence': 'low'
            }
    
    def _extract_balance_query(self, message: str, original_message: str) -> Dict:
        return {
            'message_type': 'balance',
            'intent': 'balance',
            'type': 'both',
            'confidence': 'high',
            'description': 'Balance inquiry'
        }
    
    def _enhance_query_dates(self, query_data: Dict) -> Dict:
        today = datetime.now()
        
        if query_data.get('start_date'):
            start_date = query_data['start_date']
            
            if start_date == 'today':
                query_data['start_date'] = today.strftime('%Y-%m-%d')
                query_data['end_date'] = today.strftime('%Y-%m-%d')
            elif start_date == 'yesterday':
                yesterday = today - timedelta(days=1)
                query_data['start_date'] = yesterday.strftime('%Y-%m-%d')
                query_data['end_date'] = yesterday.strftime('%Y-%m-%d')
            elif start_date == 'this_week':
                start_week = today - timedelta(days=today.weekday())
                query_data['start_date'] = start_week.strftime('%Y-%m-%d')
                query_data['end_date'] = today.strftime('%Y-%m-%d')
            elif start_date == 'last_week':
                end_last_week = today - timedelta(days=today.weekday() + 1)
                start_last_week = end_last_week - timedelta(days=6)
                query_data['start_date'] = start_last_week.strftime('%Y-%m-%d')
                query_data['end_date'] = end_last_week.strftime('%Y-%m-%d')
        
        return query_data

# Legacy compatibility functions
def parse_transaction(user_message: str) -> str:
    parser = MessageParser()
    result = parser.parse_message(user_message)
    
    if result.get('message_type') == 'transaction':
        return json.dumps(result)
    else:
        raise ValueError("Not a transaction message")

def parse_query(user_message: str) -> str:
    parser = MessageParser()
    result = parser.parse_message(user_message)
    
    if result.get('message_type') == 'query':
        return json.dumps(result)
    else:
        raise ValueError("Not a query message")

def is_balance_query(user_message: str) -> bool:
    parser = MessageParser()
    result = parser.parse_message(user_message)
    return result.get('message_type') == 'balance'

def is_transaction_input(user_message: str) -> bool:
    parser = MessageParser()
    result = parser.parse_message(user_message)
    return result.get('message_type') == 'transaction'

def enhance_query_with_context(query_json: dict) -> dict:
    return query_json

def process_user_message(user_message: str) -> Dict:
    parser = MessageParser()
    return parser.parse_message(user_message)

# Test function to verify all cases work
def test_parser():
    test_cases = [
        "Got 1200 from dad",
        "naveel gave me 50",
        "naman gave me 1000",
        "john gave me 500",
        "alex gave me 2000 rupees",
        "spent 200 on groceries",
        "papa ne 1500 diye",
        "bhai ne 300 diye the",
        "received 5000 salary",
        "paid 150 for coffee",
        "sent 800 to sister"
    ]
    
    parser = MessageParser()
    
    for test_case in test_cases:
        print(f"\nTesting: {test_case}")
        result = parser.parse_message(test_case)
        print(f"Result: {result.get('message_type')} - {result.get('rephrased_message')}")
        if result.get('message_type') == 'transaction':
            print(f"Amount: ₹{result.get('amount')}, From/To: {result.get('recipient_sender')}")

if __name__ == "__main__":
    test_parser()
