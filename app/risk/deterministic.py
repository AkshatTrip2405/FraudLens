from typing import Dict, Any, Tuple, List
from app.models import RiskFactor

class DeterministicRiskEngine:
    """
    Evaluates rule-based signals and serves as the graceful degradation fallback.
    Never blindly approves; applies defensive payment bounds.
    """
    @staticmethod
    def evaluate_signals(features: Dict[str, Any]) -> Tuple[float, List[RiskFactor], List[str]]:
        deterministic_score = 10.0
        factors: List[RiskFactor] = []
        rules_triggered: List[str] = []

        # Rule 1: Malicious IP Blocklist
        if features["ip_risk"] >= 0.90:
            deterministic_score += 85.0
            rules_triggered.append("RULE_MALICIOUS_IP_DETECTED")
            factors.append(RiskFactor(
                signal="IP_REPUTATION_BLOCK",
                weight_impact=0.80,
                description=f"Known malicious IP ({features['_raw_ip']}) matched simulated threat-intelligence blocklist."
            ))

        # Rule 2: Extreme velocity spike
        if features["velocity_1h"] >= 6:
            deterministic_score += 45.0
            rules_triggered.append("RULE_EXTREME_VELOCITY")
            factors.append(RiskFactor(
                signal="VELOCITY_CIRCUIT",
                weight_impact=0.50,
                description=f"Extreme velocity ({features['velocity_1h']} requests/hour) exceeds safe thresholds."
            ))

        # Rule 3: Extreme volume deviation
        if features["amount_ratio"] >= 10.0 and features["amount"] > 10_000.0:
            deterministic_score += 65.0  # Increased from 40.0 to securely anchor moderate risk
            rules_triggered.append("RULE_UNPRECEDENTED_AMOUNT")
            factors.append(RiskFactor(
                signal="VOLUMETRIC_DEVIATION",
                weight_impact=0.40,
                description="Transaction value is >10x baseline and exceeds ₹10,000 threshold."
            ))

        final_rule_score = min(100.0, deterministic_score)
        return final_rule_score, factors, rules_triggered

    @staticmethod
    def evaluate_fallback(features: Dict[str, Any], reason: str) -> Tuple[float, str, List[RiskFactor]]:
        """
        Graceful degradation path when ML model is degraded or times out.
        """
        rule_score, rule_factors, rules = DeterministicRiskEngine.evaluate_signals(features)
        
        # Defensive fallback: If deterministic rules indicate any risk, gate it; don't blind approve
        if rule_score >= 70.0:
            explanation = f"FALLBACK REJECT: {reason}. Deterministic rules triggered hard block: {', '.join(rules)}."
        elif rule_score >= 35.0:
            explanation = f"FALLBACK GATED: {reason}. Deterministic rules placed transaction in review: {', '.join(rules)}."
        else:
            explanation = f"FALLBACK APPROVED (Graceful Degradation): {reason}. Deterministic checks verified safe."

        return rule_score, explanation, rule_factors