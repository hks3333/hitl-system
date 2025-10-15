# graph_state.py
from typing import TypedDict, List, Optional

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
    """
    content_id: str
    content_text: str
    analysis_result: Optional[dict]
    ui_schema: Optional[dict]
    human_decision: Optional[str]
    escalation_count: int