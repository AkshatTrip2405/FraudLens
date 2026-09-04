from datetime import datetime
from typing import Dict, Any, Tuple
from app.config import settings
from app.models import CheckoutRequest, CheckoutResponse, TransactionStatus, RiskFactor
from app.risk.feature_extractor import FeatureExtractor
from app.risk.ml_scorer import ml_scorer
from app.risk.deterministic import DeterministicRiskEngine
from app.state_machine import TransactionStateMachine

class HybridRiskEngine:
    """
    Coordinates Feature Extraction -> ML Inference (800ms) -> Deterministic Signals -> Policy Decision
    """
    @staticmethod
    async def evaluate_transaction(payload: CheckoutRequest, simulate_delay_sec: float = 0.0) -> Dict[str, Any]:
        features = FeatureExtractor.extract_features(payload)
        features["_simulate_delay_sec"] = simulate_delay_sec

        # 1. Evaluate Deterministic Signals
        rule_score, rule_factors, _ = DeterministicRiskEngine.evaluate_signals(features)

        # 2. Evaluate ML with 800ms Circuit Breaker
        ml_score, prob, ml_factors, latency_ms, fallback_triggered, fallback_reason = (
            await ml_scorer.score_with_budget(features, timeout_ms=settings.ML_TIMEOUT_MS)
        )

        all_factors = rule_factors + ml_factors

        # 3. Decision Orchestration
        if fallback_triggered:
            # Graceful degradation path
            final_score, explanation, fallback_factors = DeterministicRiskEngine.evaluate_fallback(
                features, fallback_reason
            )
            all_factors.extend(fallback_factors)
            ml_used = False
            prob = final_score / 100.0
        else:
            ml_used = True
            # Weighted hybrid blend
            final_score = round(
                (settings.WEIGHT_ML * ml_score) + (settings.WEIGHT_DETERMINISTIC * rule_score), 1
            )
            
            # --- ENTERPRISE OVERRIDE LOGIC ---
            if rule_score >= 80.0:
                final_score = rule_score
                
            final_score = min(100.0, max(0.0, final_score))
            
            # Construct Explainable AI rationale
            if all_factors:
                reasons = [f.description for f in all_factors]
                explanation = f"Risk Score: {final_score:.0f}/100. Contributing signals: {' | '.join(reasons)}"
            else:
                explanation = f"Risk Score: {final_score:.0f}/100. Standard transaction profile within normal bounds."

        # 4. State Machine Policy Execution
        if final_score < settings.LOW_RISK_THRESHOLD:
            decision = TransactionStatus.APPROVED
            requires_verification = False
        elif final_score >= settings.HIGH_RISK_THRESHOLD:
            decision = TransactionStatus.REJECTED
            requires_verification = False
        else:
            decision = TransactionStatus.GATED
            requires_verification = True
            explanation += " [ACTION REQUIRED: Contextual challenge issued to rescue revenue]."

        # Validate transition from PENDING -> Decision
        TransactionStateMachine.validate_transition(TransactionStatus.PENDING, decision)

        return {
            "user_id": payload.user_id,
            "amount": payload.amount,
            "ip_address": payload.ip_address,
            "status": decision.value,
            "risk_score": final_score,
            "risk_probability": round(prob, 4),
            "explanation": explanation,
            "risk_factors": [f.dict() for f in all_factors],
            "requires_verification": requires_verification,
            "ml_used": ml_used,
            "ml_latency_ms": latency_ms,
            "fallback_triggered": fallback_triggered,
            "fallback_reason": fallback_reason,
            "created_at": datetime.utcnow()
        }