from datetime import datetime
from fastapi import FastAPI, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.models import (
    CheckoutRequest, CheckoutResponse, VerificationRequest, 
    VerificationResponse, TransactionStatus
)
from app.database import (
    init_db, insert_transaction, fetch_transaction, 
    update_transaction_status, fetch_audit_trail
)
from app.risk.hybrid_engine import HybridRiskEngine
from app.state_machine import TransactionStateMachine, InvalidStateTransitionError

# Initialize Database and WAL Mode on startup
init_db()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Adaptive Payment Risk Engine featuring Hybrid AI Scoring, Contextual Gating, and 800ms SLA Fallback.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post(
    f"{settings.API_V1_STR}/checkout",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate checkout payload and determine risk policy"
)
async def checkout(payload: CheckoutRequest, simulate_timeout: bool = Query(False)):
    delay = 1.1 if simulate_timeout else 0.0
    eval_result = await HybridRiskEngine.evaluate_transaction(payload, simulate_delay_sec=delay)
    
    tx_id = insert_transaction(eval_result)
    eval_result["transaction_id"] = tx_id
    eval_result["decision"] = TransactionStatus(eval_result["status"])
    
    return eval_result

@app.post(
    f"{settings.API_V1_STR}/verify-gated",
    response_model=VerificationResponse,
    summary="Submit contextual challenge verification for a gated transaction"
)
def verify_gated(payload: VerificationRequest):
    row = fetch_transaction(payload.transaction_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Transaction #{payload.transaction_id} not found.")

    current_state = TransactionStatus(row["status"])
    attempts = row["verification_attempts"] + 1

    if current_state != TransactionStatus.GATED:
        raise HTTPException(
            status_code=400,
            detail=f"Transaction #{payload.transaction_id} is in '{current_state.value}' state. Only GATED transactions can be verified."
        )

    answer_clean = payload.verification_answer.strip().lower()
    is_valid = (answer_clean == settings.DEMO_VERIFICATION_SECRET or answer_clean == settings.DEMO_OTP_SECRET)

    if is_valid:
        new_state = TransactionStatus.APPROVED
        TransactionStateMachine.validate_transition(current_state, new_state)
        update_transaction_status(
            tx_id=payload.transaction_id,
            from_state=current_state,
            to_state=new_state,
            new_attempts=attempts,
            audit_details={
                "result": "VERIFICATION_SUCCESS",
                "risk_score": row["risk_score"],
                "reason": "Correct contextual challenge token submitted. Revenue unlocked."
            }
        )
        return VerificationResponse(
            transaction_id=payload.transaction_id,
            previous_state=current_state,
            new_state=new_state,
            verification_success=True,
            attempts_remaining=settings.MAX_VERIFICATION_ATTEMPTS - attempts,
            explanation="Contextual challenge verified successfully. Transaction approved.",
            timestamp=datetime.utcnow()
        )
    else:
        # Invalid attempt
        remaining = settings.MAX_VERIFICATION_ATTEMPTS - attempts
        if remaining <= 0:
            new_state = TransactionStatus.REJECTED
            TransactionStateMachine.validate_transition(current_state, new_state)
            update_transaction_status(
                tx_id=payload.transaction_id,
                from_state=current_state,
                to_state=new_state,
                new_attempts=attempts,
                audit_details={
                    "result": "MAX_ATTEMPTS_EXCEEDED",
                    "risk_score": row["risk_score"],
                    "reason": "Max contextual verification attempts exhausted. Hard block enforced."
                }
            )
            return VerificationResponse(
                transaction_id=payload.transaction_id,
                previous_state=current_state,
                new_state=new_state,
                verification_success=False,
                attempts_remaining=0,
                explanation="Maximum verification attempts exceeded. Transaction permanently rejected.",
                timestamp=datetime.utcnow()
            )
        else:
            # Remains in GATED state
            update_transaction_status(
                tx_id=payload.transaction_id,
                from_state=current_state,
                to_state=current_state,
                new_attempts=attempts,
                audit_details={
                    "result": "ATTEMPT_FAILED",
                    "attempts": attempts,
                    "remaining": remaining
                }
            )
            return VerificationResponse(
                transaction_id=payload.transaction_id,
                previous_state=current_state,
                new_state=current_state,
                verification_success=False,
                attempts_remaining=remaining,
                explanation=f"Incorrect challenge answer. {remaining} attempt(s) remaining before lockout.",
                timestamp=datetime.utcnow()
            )

@app.get(f"{settings.API_V1_STR}/audit-trail", summary="Fetch persistent audit records and telemetry")
def get_audit_trail(limit: int = Query(50, ge=1, le=200)):
    return fetch_audit_trail(limit=limit)

@app.get(f"{settings.API_V1_STR}/telemetry", summary="Aggregate gateway telemetry metrics")
def get_telemetry():
    records = fetch_audit_trail(limit=200)
    total = len(records)
    if total == 0:
        return {
            "total_analyzed": 0, "approved": 0, "gated_pending": 0, "rejected": 0,
            "avg_risk_score": 0.0, "avg_latency_ms": 0.0, "fallback_count": 0, "rescued_volume": 0.0
        }

    # Direct approvals (never gated)
    approved = sum(1 for r in records if r["action_taken"] == "APPROVED" and r["verification_attempts"] == 0)
    
    # Currently Gated (awaiting verification)
    gated_pending = sum(1 for r in records if r["action_taken"] == "GATED")
    
    # Rejected
    rejected = sum(1 for r in records if r["action_taken"] == "REJECTED")
    
    # Rescued: Transactions that are now APPROVED, but had > 0 verification attempts (meaning they were GATED)
    rescued_volume = sum(r["amount"] for r in records if r["action_taken"] == "APPROVED" and r["verification_attempts"] > 0)
    
    avg_score = sum(r["risk_score"] for r in records) / total
    avg_latency = sum(r["ml_latency_ms"] for r in records) / total
    fallback_count = sum(1 for r in records if r["fallback_triggered"])

    return {
        "total_analyzed": total,
        "approved": approved,
        "gated_pending": gated_pending,
        "rejected": rejected,
        "avg_risk_score": round(avg_score, 1),
        "avg_latency_ms": round(avg_latency, 2),
        "fallback_count": fallback_count,
        "rescued_volume": round(rescued_volume, 2)
    }

# Mount static web dashboard
app.mount("/", StaticFiles(directory="static", html=True), name="static")