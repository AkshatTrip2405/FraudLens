# ▲ FraudLens: Agentic Risk Manager
**Built for the Razorpay AI Buildathon**

FraudLens is a real-time, agentic risk engine designed to dynamically gate checkout anomalies and capture revenue. Instead of relying on static, binary rules (Approve/Reject) that cause high false-positive declines, FraudLens introduces **Dynamic Gated Verification**. 

By evaluating risk probabilistically and enforcing actions deterministically, it halts suspicious transactions and requests contextual user verification to unlock the payment, protecting merchant conversion rates.

## 🧠 System Architecture & "The Signal"

This system was designed with enterprise-grade resilience and observability in mind, specifically focusing on three key engineering principles:

1. **Explainable AI (XAI):** No black-box decisions. Every probabilistic risk score is strictly logged with a deterministic explanation in an immutable audit trail.
2. **Circuit Breaking (800ms SLA):** Machine learning models can introduce latency. The risk engine enforces a strict 800ms SLA. If the AI times out, the system implements a "Fail-Open" graceful degradation, approving the transaction to save the checkout experience while silently flagging it for manual review.
3. **Stateful Flow Management:** Transactions are not just evaluated; their state is managed (`pending` -> `gated` -> `approved`), allowing asynchronous user verification to unlock trapped revenue.

### Architecture Flowchart

```mermaid
graph TD
    %% Styling
    classDef client fill:#F4F0E6,stroke:#333,stroke-width:2px,color:#0a0a0a,font-weight:bold;
    classDef api fill:#1e293b,stroke:#3b82f6,stroke-width:2px,color:#fff;
    classDef engine fill:#0f172a,stroke:#eab308,stroke-width:2px,color:#fff;
    classDef db fill:#050505,stroke:#22c55e,stroke-width:2px,color:#fff;
    classDef block fill:#450a0a,stroke:#ef4444,stroke-width:2px,color:#fff;

    %% Nodes
    A[Checkout Client / UI]:::client
    B{FastAPI Gateway}:::api
    C[Agentic Risk Engine]:::engine
    D((SQLite DB: Audit Log & State)):::db
    
    %% Flows
    A -->|1. POST /api/checkout| B
    B -->|2. Evaluate Risk payload| C
    
    C -->|3a. Score < 40| App[Approve Transaction]:::db
    C -->|3b. Score 40-75| Gate[Gate: Await Verification]:::engine
    C -->|3c. Score > 75| Rej[Hard Reject: Bounded Limit]:::block
    C -.->|SLA Timeout > 800ms| FailOpen[Fail Open: Flag & Approve]:::db
    
    App --> D
    Gate --> D
    Rej --> D
    FailOpen --> D
    
    %% Gated Verification Flow
    User[User Answers Prompt]:::client -.->|4. POST /api/verify-gated| B
    B -.->|5. Validate Answer| D
    D -.->|6. State Update: Gated -> Approved| App