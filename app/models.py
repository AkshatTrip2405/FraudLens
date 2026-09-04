from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, IPvAnyAddress

class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    GATED = "GATED"
    REJECTED = "REJECTED"

class CheckoutRequest(BaseModel):
    user_id: str = Field(..., min_length=3, max_length=64, example="usr_razorpay_101")
    amount: float = Field(..., gt=0.0, le=1_000_000.0, example=4500.0)
    ip_address: str = Field(..., example="198.51.100.42")
    device_id: Optional[str] = Field(default="dev_default", example="dev_macbook_pro_01")
    user_account_age_days: Optional[int] = Field(default=180, ge=0)
    user_avg_amount_30d: Optional[float] = Field(default=2500.0, gt=0.0)
    tx_count_last_1h: Optional[int] = Field(default=1, ge=0)

class VerificationRequest(BaseModel):
    transaction_id: int = Field(..., gt=0, example=16)
    verification_answer: str = Field(..., min_length=1, max_length=128, example="smith")

class RiskFactor(BaseModel):
    signal: str
    weight_impact: float
    description: str

class CheckoutResponse(BaseModel):
    transaction_id: int
    user_id: str
    amount: float
    risk_score: float
    risk_probability: float
    decision: TransactionStatus
    explanation: str
    risk_factors: List[RiskFactor]
    requires_verification: bool
    ml_used: bool
    ml_latency_ms: float
    fallback_triggered: bool
    fallback_reason: Optional[str] = None
    created_at: datetime

class VerificationResponse(BaseModel):
    transaction_id: int
    previous_state: TransactionStatus
    new_state: TransactionStatus
    verification_success: bool
    attempts_remaining: int
    explanation: str
    timestamp: datetime