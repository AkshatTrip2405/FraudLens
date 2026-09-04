import os
import time
import asyncio
import joblib
from typing import Tuple, List, Dict, Any
from app.models import RiskFactor
from app.config import settings

MODEL_FILE = "ml/model.pkl"

class MLScorer:
    _instance = None

    def __init__(self):
        self.model_data = None
        self._load_or_train()

    def _load_or_train(self):
        if not os.path.exists(MODEL_FILE):
            print(f"[FraudLens-ML] Model artifact {MODEL_FILE} not found. Training inline...")
            from ml.train_model import train_and_evaluate
            train_and_evaluate()
        self.model_data = joblib.load(MODEL_FILE)
        print(f"[FraudLens-ML] Loaded {self.model_data['model_version']} successfully.")

    async def score_with_budget(
        self, features: Dict[str, Any], timeout_ms: int = 800
    ) -> Tuple[float, float, List[RiskFactor], float, bool, str]:
        """
        Executes ML inference within strict SLA budget.
        Returns: (risk_score, probability, risk_factors, latency_ms, fallback_triggered, fallback_reason)
        """
        start_time = time.perf_counter()
        
        # Check for simulated test latency trigger
        simulated_delay = features.get("_simulate_delay_sec", 0.0)

        def _infer():
            if simulated_delay > 0:
                time.sleep(simulated_delay)
            pipeline = self.model_data["pipeline"]
            cols = self.model_data["feature_cols"]
            vec = [features[c] for c in cols]
            prob = float(pipeline.predict_proba([vec])[0][1])
            return prob

        loop = asyncio.get_running_loop()
        try:
            # Enforce 800ms SLA budget
            prob = await asyncio.wait_for(
                loop.run_in_executor(None, _infer),
                timeout=timeout_ms / 1000.0
            )
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            score = round(prob * 100.0, 1)

            # Feature-Level Explainability (XAI)
            factors = []
            if features["amount_ratio"] >= 2.5:
                factors.append(RiskFactor(
                    signal="AMOUNT_DEVIATION",
                    weight_impact=0.35,
                    description=f"Transaction is {features['amount_ratio']:.1f}x higher than user 30-day baseline."
                ))
            if features["ip_risk"] >= 0.90:
                factors.append(RiskFactor(
                    signal="HIGH_RISK_IP",
                    weight_impact=0.45,
                    description=f"IP address {features['_raw_ip']} exhibits high-risk network signatures."
                ))
            elif features["ip_risk"] >= 0.50:
                factors.append(RiskFactor(
                    signal="SUSPICIOUS_IP",
                    weight_impact=0.25,
                    description=f"Unusual IP/network pattern detected for {features['_raw_ip']}."
                ))
            if features["velocity_1h"] >= 4:
                factors.append(RiskFactor(
                    signal="VELOCITY_SPIKE",
                    weight_impact=0.30,
                    description=f"High frequency of transactions detected ({features['velocity_1h']} in past 60m)."
                ))
            if features["device_novelty"] == 1:
                factors.append(RiskFactor(
                    signal="DEVICE_NOVELTY",
                    weight_impact=0.15,
                    description="Unrecognized device fingerprint detected for user session."
                ))

            return score, prob, factors, round(latency_ms, 2), False, None

        except asyncio.TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return 0.0, 0.0, [], round(latency_ms, 2), True, f"ML evaluation exceeded {timeout_ms}ms SLA budget."

ml_scorer = MLScorer()