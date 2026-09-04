import os
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score, precision_recall_curve
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from ml.generate_dataset import generate_synthetic_payments

FEATURE_COLS = ["amount", "amount_ratio", "velocity_1h", "ip_risk", "device_novelty", "account_age_days"]
MODEL_PATH = "ml/model.pkl"

def train_and_evaluate():
    print("Initiating reproducible training pipeline for FraudLens Risk Classifier...")
    df = generate_synthetic_payments(n_samples=7500, random_seed=42)
    
    X = df[FEATURE_COLS]
    y = df["is_fraud"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    # Scikit-learn Pipeline with lightweight Random Forest (fast CPU inference <3ms)
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", RandomForestClassifier(
            n_estimators=45,
            max_depth=6,
            min_samples_leaf=4,
            class_weight="balanced",
            random_state=42,
            n_jobs=1
        ))
    ])

    pipeline.fit(X_train, y_train)

    # Evaluation
    y_pred = pipeline.predict(X_test)
    y_prob = pipeline.predict_proba(X_test)[:, 1]

    roc_auc = roc_auc_score(y_test, y_prob)
    print("\n--- Holdout Evaluation Metrics ---")
    print(f"ROC-AUC Score: {roc_auc:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, digits=4))

    # Save artifact
    os.makedirs("ml", exist_ok=True)
    joblib.dump({
        "pipeline": pipeline,
        "feature_cols": FEATURE_COLS,
        "model_version": "v1.2.0-rf"
    }, MODEL_PATH)
    print(f"Serialized model artifact stored safely at: {MODEL_PATH}")

if __name__ == "__main__":
    train_and_evaluate()