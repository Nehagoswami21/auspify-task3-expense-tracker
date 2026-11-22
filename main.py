from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import sqlite3
import os
app = FastAPI(
    title="FinPulse Financial Engine",
    description="Internal Enterprise Financial Ledger API",
    version="2.0.0",
    docs_url="/admin/docs",  # Moved from public /docs to private /admin/docs
    redoc_url=None
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


DB_NAME = "expenses.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            tx_type TEXT NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            payment_method TEXT DEFAULT 'UPI / NetBanking',
            notes TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

class TransactionCreate(BaseModel):
    title: str = Field(..., example="AWS / Cloud Infrastructure")
    amount: float = Field(..., gt=0, example=1499.0)
    tx_type: str = Field(..., example="expense")
    category: str = Field(..., example="Dev Tools & Servers")
    date: str = Field(..., example="2026-11-22")
    payment_method: Optional[str] = "UPI / NetBanking"
    notes: Optional[str] = ""

class TransactionResponse(TransactionCreate):
    id: int

@app.get("/api/transactions", response_model=List[TransactionResponse], tags=["Transactions"])
def list_transactions(
    tx_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None
):
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    if tx_type and tx_type != "all":
        query += " AND tx_type = ?"
        params.append(tx_type.lower())
    if category and category != "all":
        query += " AND category = ?"
        params.append(category)
    if search:
        query += " AND (title LIKE ? OR notes LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY date DESC, id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/transactions", response_model=TransactionResponse, status_code=201, tags=["Transactions"])
def add_transaction(t: TransactionCreate):
    if t.tx_type.lower() not in ["income", "expense"]:
        raise HTTPException(status_code=400, detail="tx_type must be either 'income' or 'expense'")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO transactions (title, amount, tx_type, category, date, payment_method, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (t.title.strip(), t.amount, t.tx_type.lower(), t.category.strip(), t.date, t.payment_method, t.notes)
    )
    conn.commit()
    inserted_id = cursor.lastrowid
    conn.close()
    return {**t.model_dump(), "id": inserted_id}

@app.delete("/api/transactions/{tx_id}", status_code=204, tags=["Transactions"])
def delete_transaction(tx_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM transactions WHERE id = ?", (tx_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction ID not found")
    cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()
    return

@app.get("/api/analytics/summary", tags=["Analytics Telemetry"])
def get_analytics_summary():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT tx_type, SUM(amount) as total FROM transactions GROUP BY tx_type")
    totals = {row["tx_type"]: row["total"] for row in cursor.fetchall()}
    income = totals.get("income", 0.0)
    expense = totals.get("expense", 0.0)
    net_savings = income - expense
    savings_rate = round((net_savings / income * 100), 1) if income > 0 else 0.0

    cursor.execute(
        "SELECT category, SUM(amount) as total FROM transactions WHERE tx_type = 'expense' GROUP BY category ORDER BY total DESC"
    )
    category_breakdown = {row["category"]: row["total"] for row in cursor.fetchall()}

    conn.close()
    return {
        "total_income": income,
        "total_expense": expense,
        "net_savings": net_savings,
        "savings_rate_percent": savings_rate,
        "category_breakdown": category_breakdown
    }

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", include_in_schema=False)
def serve_home():
    return FileResponse("static/index.html")