"""Public contracts for the browser-only paper-trading simulation."""

from .bridge import (
    LiveKitPaperTradingBridge,
    PaperTradingBridge,
    PaperTradingUIUnavailableError,
)
from .call import CallPaperTradingBridge
from .models import (
    MAX_RPC_PAYLOAD_BYTES,
    PAPER_DRAFT_LIFETIME,
    PaperDashboardAck,
    PaperDraftAck,
    PaperOrderDraft,
    PaperOrderResult,
    PaperPortfolioSummary,
    PaperSide,
)

__all__ = [
    "MAX_RPC_PAYLOAD_BYTES",
    "PAPER_DRAFT_LIFETIME",
    "CallPaperTradingBridge",
    "LiveKitPaperTradingBridge",
    "PaperDashboardAck",
    "PaperDraftAck",
    "PaperOrderDraft",
    "PaperOrderResult",
    "PaperPortfolioSummary",
    "PaperSide",
    "PaperTradingBridge",
    "PaperTradingUIUnavailableError",
]
