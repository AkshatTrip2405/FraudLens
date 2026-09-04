from typing import Dict, Any, List
import numpy as np
from app.models import CheckoutRequest

SIMULATED_MALICIOUS_IPS = {"203.0.113.66", "203.0.113.99"}
SIMULATED_SUSPICIOUS_PREFIXES = ("198.51.100.",)

class FeatureExtractor:
    @staticmethod
    def extract_features(payload: CheckoutRequest) -> Dict[str, Any]:
        baseline = payload.user_avg_amount_30d if payload.user_avg_amount_30d > 0 else payload.amount
        amount_ratio = float(payload.amount / baseline)
        device_novelty = 1 if payload.device_id.startswith("dev_new_") or payload.device_id == "dev_default" else 0

        # Tiered IP Risk Logic
        if payload.ip_address in SIMULATED_MALICIOUS_IPS:
            ip_risk = 0.95  # Malicious (Forces Reject)
        elif any(payload.ip_address.startswith(prefix) for prefix in SIMULATED_SUSPICIOUS_PREFIXES):
            ip_risk = 0.60  # Suspicious (Contributes to Gated)
        else:
            ip_risk = 0.05  # Normal

        return {
            "amount": float(payload.amount),
            "amount_ratio": round(amount_ratio, 4),
            "velocity_1h": int(payload.tx_count_last_1h),
            "ip_risk": round(ip_risk, 4),
            "device_novelty": device_novelty,
            "account_age_days": float(payload.user_account_age_days),
            "_raw_ip": payload.ip_address,
            "_raw_user_id": payload.user_id
        }

    @staticmethod
    def to_vector(features: Dict[str, Any], feature_names: List[str]) -> np.ndarray:
        vector = [features[name] for name in feature_names]
        return np.array([vector])