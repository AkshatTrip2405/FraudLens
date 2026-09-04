import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.config import settings
from app.models import TransactionStatus

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high-concurrency and read-isolation
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db() -> None:
    conn = get_db_connection()
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            amount REAL NOT NULL,
            ip_address TEXT NOT NULL,
            status TEXT NOT NULL,
            risk_score REAL NOT NULL,
            risk_probability REAL NOT NULL,
            explanation TEXT NOT NULL,
            risk_factors_json TEXT NOT NULL,
            ml_used INTEGER NOT NULL,
            ml_latency_ms REAL NOT NULL,
            fallback_triggered INTEGER NOT NULL,
            fallback_reason TEXT,
            verification_attempts INTEGER DEFAULT 0,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS persistent_audit_trail (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            risk_score REAL NOT NULL,
            details_json TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions (id)
        );

        CREATE INDEX IF NOT EXISTS idx_tx_created_at ON transactions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_tx_id ON persistent_audit_trail(transaction_id);
        """)
    conn.close()

def insert_transaction(tx_data: Dict[str, Any]) -> int:
    conn = get_db_connection()
    with conn:
        cursor = conn.execute("""
            INSERT INTO transactions (
                user_id, amount, ip_address, status, risk_score, risk_probability,
                explanation, risk_factors_json, ml_used, ml_latency_ms,
                fallback_triggered, fallback_reason, verification_attempts,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_data["user_id"], tx_data["amount"], tx_data["ip_address"],
            tx_data["status"], tx_data["risk_score"], tx_data["risk_probability"],
            tx_data["explanation"], json.dumps(tx_data["risk_factors"]),
            1 if tx_data["ml_used"] else 0, tx_data["ml_latency_ms"],
            1 if tx_data["fallback_triggered"] else 0, tx_data.get("fallback_reason"),
            0, tx_data["created_at"], tx_data["created_at"]
        ))
        tx_id = cursor.lastrowid

        # Record initial creation event in persistent append-only audit trail
        conn.execute("""
            INSERT INTO persistent_audit_trail (
                transaction_id, event_type, from_state, to_state, risk_score, details_json, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_id, "TRANSACTION_EVALUATION", "PENDING", tx_data["status"],
            tx_data["risk_score"], json.dumps({
                "explanation": tx_data["explanation"],
                "ml_used": tx_data["ml_used"],
                "fallback": tx_data["fallback_triggered"]
            }), tx_data["created_at"]
        ))
    conn.close()
    return tx_id

def update_transaction_status(
    tx_id: int,
    from_state: TransactionStatus,
    to_state: TransactionStatus,
    new_attempts: int,
    audit_details: Dict[str, Any]
) -> None:
    now = datetime.utcnow()
    conn = get_db_connection()
    with conn:
        conn.execute("""
            UPDATE transactions
            SET status = ?, verification_attempts = ?, updated_at = ?
            WHERE id = ?
        """, (to_state.value, new_attempts, now, tx_id))

        # Append-only audit record
        conn.execute("""
            INSERT INTO persistent_audit_trail (
                transaction_id, event_type, from_state, to_state, risk_score, details_json, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_id, "STATE_TRANSITION", from_state.value, to_state.value,
            audit_details.get("risk_score", 0.0), json.dumps(audit_details), now
        ))
    conn.close()

def fetch_transaction(tx_id: int) -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    conn.close()
    return row

def fetch_audit_trail(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT 
            t.id as transaction_id,
            t.created_at as timestamp,
            t.user_id,
            t.amount,
            t.risk_score,
            t.risk_probability,
            t.status as action_taken,
            t.explanation,
            t.risk_factors_json,
            t.ml_used,
            t.ml_latency_ms,
            t.fallback_triggered,
            t.fallback_reason,
            t.verification_attempts
        FROM transactions t
        ORDER BY t.id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(ix) for ix in cursor.fetchall()]
    conn.close()
    for r in rows:
        r["risk_factors"] = json.loads(r["risk_factors_json"])
        r["ml_used"] = bool(r["ml_used"])
        r["fallback_triggered"] = bool(r["fallback_triggered"])
    return rows