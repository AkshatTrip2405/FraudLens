import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db
from app.config import settings

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()

client = TestClient(app)

def test_01_low_risk_transaction_approved():
    res = client.post("/api/checkout", json={
        "user_id": "usr_safe",
        "amount": 250.0,
        "ip_address": "203.0.113.10",
        "user_avg_amount_30d": 300.0,
        "tx_count_last_1h": 0
    })
    assert res.status_code == 201
    data = res.json()
    assert data["decision"] == "APPROVED"
    assert data["risk_score"] < settings.LOW_RISK_THRESHOLD
    assert data["requires_verification"] is False

def test_02_medium_risk_transaction_gated():
    # Spiking baseline + Suspicious IP + Device Novelty + Velocity triggers GATED
    res = client.post("/api/checkout", json={
        "user_id": "usr_anomaly",
        "amount": 55000.0,
        "ip_address": "198.51.100.25",
        "user_avg_amount_30d": 1500.0,
        "tx_count_last_1h": 4,
        "device_id": "dev_new_session_88"
    })
    assert res.status_code == 201
    data = res.json()
    assert data["decision"] == "GATED"
    assert settings.LOW_RISK_THRESHOLD <= data["risk_score"] < settings.HIGH_RISK_THRESHOLD
    assert data["requires_verification"] is True

def test_03_high_risk_transaction_rejected():
    # Simulated Malicious Blocklist IP triggers deterministic hard-block
    res = client.post("/api/checkout", json={
        "user_id": "usr_attacker",
        "amount": 80000.0,
        "ip_address": "203.0.113.66",
        "tx_count_last_1h": 8,
        "user_avg_amount_30d": 1000.0
    })
    assert res.status_code == 201
    data = res.json()
    assert data["decision"] == "REJECTED"
    assert data["risk_score"] >= settings.HIGH_RISK_THRESHOLD

def test_04_successful_gated_verification():
    # 1. Trigger Gated
    create_res = client.post("/api/checkout", json={
        "user_id": "usr_to_verify",
        "amount": 55000.0,
        "ip_address": "198.51.100.25",
        "user_avg_amount_30d": 1500.0,
        "tx_count_last_1h": 4,
        "device_id": "dev_new_session_88"
    })
    tx_id = create_res.json()["transaction_id"]
    
    # 2. Verify with valid secret
    verify_res = client.post("/api/verify-gated", json={
        "transaction_id": tx_id,
        "verification_answer": "smith"
    })
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["new_state"] == "APPROVED"
    assert v_data["verification_success"] is True

def test_05_failed_verification_remains_gated():
    create_res = client.post("/api/checkout", json={
        "user_id": "usr_fail_verify",
        "amount": 55000.0,
        "ip_address": "198.51.100.25",
        "user_avg_amount_30d": 1500.0,
        "tx_count_last_1h": 4,
        "device_id": "dev_new_session_88"
    })
    tx_id = create_res.json()["transaction_id"]

    verify_res = client.post("/api/verify-gated", json={
        "transaction_id": tx_id,
        "verification_answer": "wrong_password"
    })
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["new_state"] == "GATED"
    assert v_data["verification_success"] is False
    assert v_data["attempts_remaining"] == settings.MAX_VERIFICATION_ATTEMPTS - 1

def test_06_max_verification_attempts_rejected():
    create_res = client.post("/api/checkout", json={
        "user_id": "usr_lockout",
        "amount": 55000.0,
        "ip_address": "198.51.100.25",
        "user_avg_amount_30d": 1500.0,
        "tx_count_last_1h": 4,
        "device_id": "dev_new_session_88"
    })
    tx_id = create_res.json()["transaction_id"]

    # Burn max attempts
    for _ in range(settings.MAX_VERIFICATION_ATTEMPTS):
        res = client.post("/api/verify-gated", json={
            "transaction_id": tx_id,
            "verification_answer": "wrong_credential"
        })
    
    v_data = res.json()
    assert v_data["new_state"] == "REJECTED"
    assert v_data["attempts_remaining"] == 0

def test_07_invalid_state_transition_prevented():
    # Cannot verify an already APPROVED transaction
    res = client.post("/api/checkout", json={
        "user_id": "usr_instant_approve",
        "amount": 100.0,
        "ip_address": "203.0.113.10"
    })
    tx_id = res.json()["transaction_id"]

    err_res = client.post("/api/verify-gated", json={
        "transaction_id": tx_id,
        "verification_answer": "smith"
    })
    assert err_res.status_code == 400
    assert "is in 'APPROVED' state" in err_res.json()["detail"]

def test_08_ml_timeout_fallback_enforced():
    # Force timeout past SLA budget
    res = client.post("/api/checkout?simulate_timeout=true", json={
        "user_id": "usr_timeout_test",
        "amount": 800.0,
        "ip_address": "203.0.113.10",
        "user_avg_amount_30d": 800.0
    })
    assert res.status_code == 201
    data = res.json()
    assert data["fallback_triggered"] is True
    assert data["ml_used"] is False
    assert "800ms SLA budget" in data["fallback_reason"]
    # Fallback should gracefully evaluate safe transaction
    assert data["decision"] == "APPROVED"

def test_09_persistent_audit_trail_integrity():
    res = client.get("/api/audit-trail?limit=5")
    assert res.status_code == 200
    records = res.json()
    assert len(records) > 0
    top = records[0]
    assert "transaction_id" in top
    assert "ml_latency_ms" in top
    assert "risk_factors" in top

def test_10_defensive_input_validation():
    # Negative amount rejected by Pydantic
    res = client.post("/api/checkout", json={
        "user_id": "usr_bad_payload",
        "amount": -50.0,
        "ip_address": "203.0.113.10"
    })
    assert res.status_code == 422