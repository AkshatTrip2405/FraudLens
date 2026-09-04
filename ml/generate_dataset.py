import numpy as np
import pandas as pd
import os

def generate_synthetic_payments(n_samples: int = 6000, random_seed: int = 42) -> pd.DataFrame:
    """
    Generates realistic payment fraud signals:
    - Base fraud rate: ~4.5%
    - Features: amount_ratio, tx_velocity_1h, ip_risk, device_novelty, account_age
    """
    np.random.seed(random_seed)
    
    # 1. Transaction Amount
    amounts = np.random.exponential(scale=3500.0, size=n_samples) + 10.0
    
    # 2. Historical User Spending Ratio (amount / user_avg_amount)
    amount_ratios = np.random.lognormal(mean=0.0, sigma=0.6, size=n_samples)
    
    # 3. Velocity Signal (Transactions in last 1 hour)
    velocities = np.random.poisson(lam=1.2, size=n_samples)
    
    # 4. IP Risk Probability (0.0 = clean residential, 1.0 = known proxy/data-center)
    ip_risks = np.random.beta(a=0.5, b=5.0, size=n_samples)
    
    # 5. Device Novelty (0.0 = trusted primary device, 1.0 = newly observed user-agent/fingerprint)
    device_novelty = np.random.binomial(n=1, p=0.18, size=n_samples)
    
    # 6. Account Age in Days
    account_age_days = np.random.exponential(scale=365.0, size=n_samples) + 1.0

    # Latent Fraud Probability Generator
    latent_score = (
        0.35 * np.clip(amount_ratios / 5.0, 0, 3) +
        0.30 * np.clip(velocities / 6.0, 0, 2) +
        0.45 * ip_risks +
        0.25 * device_novelty -
        0.20 * np.clip(account_age_days / 365.0, 0, 2)
    )
    
    # Sigmoid mapping to generate realistic binary labels with noise
    prob = 1.0 / (1.0 + np.exp(-(latent_score - 1.6) * 3.5))
    is_fraud = (np.random.rand(n_samples) < prob).astype(int)

    df = pd.DataFrame({
        "amount": np.round(amounts, 2),
        "amount_ratio": np.round(amount_ratios, 4),
        "velocity_1h": velocities,
        "ip_risk": np.round(ip_risks, 4),
        "device_novelty": device_novelty,
        "account_age_days": np.round(account_age_days, 1),
        "is_fraud": is_fraud
    })
    
    return df

if __name__ == "__main__":
    df = generate_synthetic_payments()
    os.makedirs("ml", exist_ok=True)
    csv_path = "ml/synthetic_transactions.csv"
    df.to_csv(csv_path, index=False)
    print(f"Generated {len(df)} transactions -> {csv_path} (Fraud Rate: {df['is_fraud'].mean()*100:.2f}%)")