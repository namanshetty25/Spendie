# db.py - Database operations for transaction management

import os
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import defaultdict

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["spendie"]
transactions = db["transactions"]

def add_transaction(user_id, data):
    transaction_data = {
        "user_id": user_id,
        "timestamp": datetime.now(),
        "category": data.get("category", "miscellaneous"),
        "month": datetime.now().strftime("%Y-%m"),
        "year": datetime.now().year,
        "day_of_week": datetime.now().strftime("%A"),
        "created_at": datetime.now(),
        "type": data.get("type"),
        "amount": data.get("amount"),
        "description": data.get("description"),
        "upi_data": {
            "recipient_sender": data.get("recipient_sender"),
            "transaction_id": data.get("transaction_id"),
            "app_name": data.get("app_name"),
            "confidence": data.get("confidence"),
            "is_upi": bool(data.get("recipient_sender") or data.get("transaction_id") or data.get("app_name"))
        } if any(key in data for key in ["recipient_sender", "transaction_id", "app_name", "confidence"]) else None,
        "source": "upi_ocr" if data.get("app_name") else "manual",
        "updated_at": datetime.now()
    }
    for key, value in data.items():
        if key not in transaction_data and key not in ["recipient_sender", "transaction_id", "app_name", "confidence"]:
            transaction_data[key] = value
    return transactions.insert_one(transaction_data)

def get_balance(user_id):
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$type", "total": {"$sum": "$amount"}}}
    ]
    results = list(transactions.aggregate(pipeline))
    income, expense = 0, 0
    for r in results:
        if r["_id"] == "income":
            income = r["total"]
        elif r["_id"] == "expense":
            expense = r["total"]
    return income, expense

def query_transactions(user_id, txn_type="both", start_date=None, end_date=None, keywords=None, category=None, amount=None, upi_only=False):
    query = {"user_id": user_id}
    if txn_type != "both":
        query["type"] = txn_type
    if upi_only:
        query["upi_data.is_upi"] = True
    if start_date or end_date:
        query["timestamp"] = {}
        if start_date:
            try:
                query["timestamp"]["$gte"] = datetime.fromisoformat(start_date)
            except ValueError:
                if start_date == "today":
                    query["timestamp"]["$gte"] = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                elif start_date == "yesterday":
                    yesterday = datetime.now() - timedelta(days=1)
                    query["timestamp"]["$gte"] = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
                    query["timestamp"]["$lte"] = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
                elif start_date == "this_week":
                    start_week = datetime.now() - timedelta(days=datetime.now().weekday())
                    query["timestamp"]["$gte"] = start_week.replace(hour=0, minute=0, second=0, microsecond=0)
                elif start_date == "last_week":
                    end_last_week = datetime.now() - timedelta(days=datetime.now().weekday() + 1)
                    start_last_week = end_last_week - timedelta(days=6)
                    query["timestamp"]["$gte"] = start_last_week.replace(hour=0, minute=0, second=0, microsecond=0)
                    query["timestamp"]["$lte"] = end_last_week.replace(hour=23, minute=59, second=59, microsecond=999999)
        if end_date:
            try:
                end_datetime = datetime.fromisoformat(end_date)
                query["timestamp"]["$lte"] = end_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
            except ValueError:
                if end_date == "today":
                    query["timestamp"]["$lte"] = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    if keywords:
        keyword_patterns = []
        for keyword in keywords:
            keyword_patterns.extend([
                {"description": {"$regex": keyword, "$options": "i"}},
                {"upi_data.recipient_sender": {"$regex": keyword, "$options": "i"}},
                {"upi_data.app_name": {"$regex": keyword, "$options": "i"}},
                {"upi_data.transaction_id": {"$regex": keyword, "$options": "i"}}
            ])
        query["$or"] = keyword_patterns
    if category:
        query["category"] = {"$regex": category, "$options": "i"}
    if amount:
        query["amount"] = {}
        if "gt" in amount:
            query["amount"]["$gt"] = amount["gt"]
        if "lt" in amount:
            query["amount"]["$lt"] = amount["lt"]
        if "eq" in amount:
            query["amount"] = amount["eq"]
    return list(transactions.find(query).sort("timestamp", -1))

def get_upi_stats(user_id):
    pipeline = [
        {"$match": {"user_id": user_id, "upi_data.is_upi": True}},
        {"$group": {
            "_id": "$upi_data.app_name",
            "total_amount": {"$sum": "$amount"},
            "transaction_count": {"$sum": 1},
            "avg_amount": {"$avg": "$amount"}
        }},
        {"$sort": {"total_amount": -1}}
    ]
    app_stats = list(transactions.aggregate(pipeline))
    upi_pipeline = [
        {"$match": {"user_id": user_id, "upi_data.is_upi": True}},
        {"$group": {
            "_id": "$type",
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1}
        }}
    ]
    upi_totals = list(transactions.aggregate(upi_pipeline))
    return {
        "app_breakdown": app_stats,
        "upi_totals": upi_totals,
        "total_upi_transactions": sum(stat["transaction_count"] for stat in app_stats)
    }

def get_category_breakdown(user_id, txn_type="expense", start_date=None, end_date=None, include_upi_details=False):
    match_query = {"user_id": user_id, "type": txn_type}
    if start_date or end_date:
        match_query["timestamp"] = {}
        if start_date:
            match_query["timestamp"]["$gte"] = datetime.fromisoformat(start_date)
        if end_date:
            match_query["timestamp"]["$lte"] = datetime.fromisoformat(end_date)
    if include_upi_details:
        pipeline = [
            {"$match": match_query},
            {"$group": {
                "_id": {
                    "category": "$category",
                    "is_upi": "$upi_data.is_upi"
                },
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1}
            }},
            {"$sort": {"total": -1}}
        ]
        results = list(transactions.aggregate(pipeline))
        breakdown = {}
        for r in results:
            category = r["_id"]["category"]
            is_upi = r["_id"]["is_upi"]
            if category not in breakdown:
                breakdown[category] = {"total": 0, "upi": 0, "manual": 0}
            breakdown[category]["total"] += r["total"]
            if is_upi:
                breakdown[category]["upi"] += r["total"]
            else:
                breakdown[category]["manual"] += r["total"]
        return breakdown
    else:
        pipeline = [
            {"$match": match_query},
            {"$group": {
                "_id": "$category",
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1}
            }},
            {"$sort": {"total": -1}}
        ]
        results = list(transactions.aggregate(pipeline))
        return {r["_id"]: r["total"] for r in results if r["_id"]}

def get_daily_totals(user_id, days=7, txn_type="expense"):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    pipeline = [
        {"$match": {
            "user_id": user_id,
            "type": txn_type,
            "timestamp": {"$gte": start_date, "$lte": end_date}
        }},
        {"$group": {
            "_id": {
                "year": {"$year": "$timestamp"},
                "month": {"$month": "$timestamp"},
                "day": {"$dayOfMonth": "$timestamp"}
            },
            "total": {"$sum": "$amount"},
            "upi_total": {"$sum": {"$cond": [{"$eq": ["$upi_data.is_upi", True]}, "$amount", 0]}},
            "manual_total": {"$sum": {"$cond": [{"$ne": ["$upi_data.is_upi", True]}, "$amount", 0]}}
        }},
        {"$sort": {"_id": 1}}
    ]
    results = list(transactions.aggregate(pipeline))
    daily_totals = {}
    for r in results:
        date_obj = datetime(r["_id"]["year"], r["_id"]["month"], r["_id"]["day"])
        date_str = date_obj.strftime("%Y-%m-%d")
        daily_totals[date_str] = {
            "total": r["total"],
            "upi": r["upi_total"],
            "manual": r["manual_total"]
        }
    return daily_totals

def get_spending_patterns(user_id, days=30):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    pipeline = [
        {"$match": {
            "user_id": user_id,
            "type": "expense",
            "timestamp": {"$gte": start_date, "$lte": end_date}
        }},
        {"$group": {
            "_id": {
                "day_of_week": {"$dayOfWeek": "$timestamp"},
                "hour": {"$hour": "$timestamp"},
                "category": "$category",
                "is_upi": "$upi_data.is_upi"
            },
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1},
            "avg_amount": {"$avg": "$amount"}
        }},
        {"$sort": {"total": -1}}
    ]
    results = list(transactions.aggregate(pipeline))
    return results

def export_transactions_csv(user_id):
    import csv
    from io import StringIO
    txns = list(transactions.find({"user_id": user_id}).sort("timestamp", -1))
    csv_file = StringIO()
    writer = csv.writer(csv_file)
    writer.writerow([
        "Date", "Type", "Amount", "Description", "Category",
        "Day of Week", "Month", "Year", "Time", "Source",
        "UPI App", "Recipient/Sender", "Transaction ID", "Confidence"
    ])
    for t in txns:
        timestamp = t.get("timestamp", datetime.now())
        upi_data = t.get("upi_data", {})
        writer.writerow([
            timestamp.strftime("%Y-%m-%d"),
            t.get("type", ""),
            t.get("amount", ""),
            t.get("description", ""),
            t.get("category", "miscellaneous"),
            timestamp.strftime("%A"),
            timestamp.strftime("%B"),
            timestamp.year,
            timestamp.strftime("%H:%M:%S"),
            t.get("source", "manual"),
            upi_data.get("app_name", ""),
            upi_data.get("recipient_sender", ""),
            upi_data.get("transaction_id", ""),
            upi_data.get("confidence", "")
        ])
    csv_file.seek(0)
    return csv_file

def delete_all_transactions(user_id):
    return transactions.delete_many({"user_id": user_id})

def compare_periods(user_id, period1_start, period1_end, period2_start, period2_end):
    def get_period_stats(start, end):
        pipeline = [
            {"$match": {
                "user_id": user_id,
                "timestamp": {
                    "$gte": datetime.fromisoformat(start),
                    "$lte": datetime.fromisoformat(end)
                }
            }},
            {"$group": {
                "_id": "$type",
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1},
                "upi_total": {"$sum": {"$cond": [{"$eq": ["$upi_data.is_upi", True]}, "$amount", 0]}},
                "manual_total": {"$sum": {"$cond": [{"$ne": ["$upi_data.is_upi", True]}, "$amount", 0]}}
            }}
        ]
        results = list(transactions.aggregate(pipeline))
        stats = {
            "income": 0, "expense": 0, "income_count": 0, "expense_count": 0,
            "upi_income": 0, "upi_expense": 0, "manual_income": 0, "manual_expense": 0
        }
        for r in results:
            if r["_id"] == "income":
                stats["income"] = r["total"]
                stats["income_count"] = r["count"]
                stats["upi_income"] = r["upi_total"]
                stats["manual_income"] = r["manual_total"]
            elif r["_id"] == "expense":
                stats["expense"] = r["total"]
                stats["expense_count"] = r["count"]
                stats["upi_expense"] = r["upi_total"]
                stats["manual_expense"] = r["manual_total"]
        return stats
    period1_stats = get_period_stats(period1_start, period1_end)
    period2_stats = get_period_stats(period2_start, period2_end)
    return {
        "period1": period1_stats,
        "period2": period2_stats,
        "comparison": {
            "income_change": period2_stats["income"] - period1_stats["income"],
            "expense_change": period2_stats["expense"] - period1_stats["expense"],
            "net_change": (period2_stats["income"] - period2_stats["expense"]) -
                         (period1_stats["income"] - period1_stats["expense"]),
            "upi_change": (period2_stats["upi_income"] + period2_stats["upi_expense"]) -
                          (period1_stats["upi_income"] + period1_stats["upi_expense"])
        }
    }
