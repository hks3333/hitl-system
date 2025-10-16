# graph_state.py
from typing import TypedDict, List, Optional, Tuple
from datetime import datetime

class GraphState(TypedDict):
    """
    Represents the state of our moderation workflow.

    Attributes:
        content_id: The ID of the content being moderated.
        content_text: The actual text content to analyze.
        analysis_result: A dictionary containing the AI's analysis.
        ui_schema: The JSON schema for the dynamic UI.
        human_decision: The decision made by a human moderator.
        escalation_count: How many times this has been escalated.
        status: The current status of the workflow (e.g., "PENDING_AI", "PENDING_HUMAN").
        history: A log of events that have occurred in the workflow.
        last_updated: The timestamp of the last update.
        rollback_history: List of rollback events with details.
        executed_actions: List of actions that were executed (for reversal).
        rollback_reason: Reason for rollback (injected by API).
        rollback_requested_by: Moderator ID who requested rollback.
        rollback_requested_at: Timestamp when rollback was requested.
    """
    content_id: str
    content_text: str
    analysis_result: Optional[dict]
    ui_schema: Optional[dict]
    human_decision: Optional[str]
    escalation_count: int
    # --- New Fields for Enhanced State Tracking ---
    status: str
    history: List[Tuple[str, str]]
    last_updated: str
    # --- Rollback Fields ---
    rollback_history: List[dict]
    executed_actions: List[dict]
    rollback_reason: Optional[str]
    rollback_requested_by: Optional[str]
    rollback_requested_at: Optional[str]