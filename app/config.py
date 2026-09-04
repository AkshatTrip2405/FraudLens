import os
from pydantic import BaseModel

class Settings(BaseModel):
    PROJECT_NAME: str = "FraudLens: Adaptive Payment Risk Engine"
    API_V1_STR: str = "/api"
    DB_PATH: str = os.getenv("FRAUDLENS_DB_PATH", "fraudlens.db")
    
    ML_TIMEOUT_MS: int = 800
    
    # --- THE FIX: Adjusted Scoring Contribution ---
    WEIGHT_ML: float = 0.40
    WEIGHT_DETERMINISTIC: float = 0.60
    
    # STRICT POLICY THRESHOLDS
    LOW_RISK_THRESHOLD: float = 40.0   # Score < 40 -> APPROVE
    HIGH_RISK_THRESHOLD: float = 75.0  # Score >= 75 -> REJECT
    # 40.0 <= Score < 75.0 -> GATED VERIFICATION
    
    MAX_VERIFICATION_ATTEMPTS: int = 3
    DEMO_VERIFICATION_SECRET: str = "smith"
    DEMO_OTP_SECRET: str = "4829"

settings = Settings()