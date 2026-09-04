from app.models import TransactionStatus

class InvalidStateTransitionError(Exception):
    """Raised when an illegal transaction status change is attempted."""
    pass

class TransactionStateMachine:
    """
    Guarantees strict state transitions across the payment lifecycle:
      PENDING -> APPROVED (Low Risk / Fallback Approved)
      PENDING -> GATED    (Medium Risk -> Needs Challenge)
      PENDING -> REJECTED (High Risk / Rule Hard-Block)
      GATED   -> APPROVED (Challenge verified successfully)
      GATED   -> REJECTED (Max attempts exceeded or explicitly declined)
      GATED   -> GATED    (Failed attempt, attempts remain)
    """
    _VALID_TRANSITIONS = {
        TransactionStatus.PENDING: {
            TransactionStatus.APPROVED,
            TransactionStatus.GATED,
            TransactionStatus.REJECTED
        },
        TransactionStatus.GATED: {
            TransactionStatus.APPROVED,
            TransactionStatus.REJECTED,
            TransactionStatus.GATED
        },
        TransactionStatus.APPROVED: set(),  # Terminal state
        TransactionStatus.REJECTED: set(),  # Terminal state
    }

    @classmethod
    def validate_transition(cls, current_state: TransactionStatus, target_state: TransactionStatus) -> None:
        if target_state not in cls._VALID_TRANSITIONS.get(current_state, set()):
            raise InvalidStateTransitionError(
                f"Illegal state transition requested: {current_state.value} -> {target_state.value}. "
                f"Terminal or forbidden state boundary violated."
            )