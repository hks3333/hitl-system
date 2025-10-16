# agent.py
import json
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver  # <- IMPORT the official saver
from langchain_core.output_parsers import JsonOutputParser  # <- IMPORT THE PARSER
from typing import List, Dict  # NEW: For rollback_history
from jsonschema import Draft7Validator, ValidationError

# This line loads your .env file
load_dotenv()

# Import the state definition and your settings
from graph_state import GraphState
from config import settings

# UPDATED: Add rollback_history to GraphState (we'll update graph_state.py too)
# But for now, assume we extend it: rollback_history: Optional[List[str]] = []

# ===== MOCK API FUNCTIONS FOR DEMO =====
def remove_content_api(content_id: str) -> dict:
    """Mock API: Remove content from platform."""
    print(f"🚫 [MOCK API] Removing content: {content_id}")
    return {"status": "removed", "content_id": content_id, "timestamp": datetime.now(timezone.utc).isoformat()}

def restore_content_api(content_id: str) -> dict:
    """Mock API: Restore previously removed content."""
    print(f"✅ [MOCK API] Restoring content: {content_id}")
    return {"status": "restored", "content_id": content_id, "timestamp": datetime.now(timezone.utc).isoformat()}

def ban_user_api(content_id: str) -> dict:
    """Mock API: Ban user who created the content."""
    print(f"🔨 [MOCK API] Banning user for content: {content_id}")
    return {"status": "banned", "content_id": content_id, "timestamp": datetime.now(timezone.utc).isoformat()}

def unban_user_api(content_id: str) -> dict:
    """Mock API: Unban user."""
    print(f"🔓 [MOCK API] Unbanning user for content: {content_id}")
    return {"status": "unbanned", "content_id": content_id, "timestamp": datetime.now(timezone.utc).isoformat()}

def warn_user_api(content_id: str) -> dict:
    """Mock API: Send warning to user."""
    print(f"⚠️ [MOCK API] Warning user for content: {content_id}")
    return {"status": "warned", "content_id": content_id, "timestamp": datetime.now(timezone.utc).isoformat()}
# ===== END MOCK API FUNCTIONS =====


def update_state_meta(state: GraphState, event_description: str) -> GraphState:
    """Helper function to update metadata fields consistently."""
    now = datetime.now(timezone.utc).isoformat()
    state["last_updated"] = now
    state["history"].append((now, event_description))
    return state


def analyze_content_node(state: GraphState) -> GraphState:
    """
    Analyzes content against specific developer forum rules using a JSON output parser.
    """
    print("🔍 Analyzing content...")

    # 1. Instantiate the output parser
    state = update_state_meta(state, "Starting content analysis.")

    prompt = ChatPromptTemplate.from_template(
        """You are an expert content moderator for a community platform. Analyze the following content for policy violations.

**Your task**: Provide a comprehensive analysis in JSON format with these exact keys:
- "confidence_score": number from 0-100 (how confident you are in your assessment)
- "suggested_action": one of ["IGNORE", "WARN", "ESCALATE"]
- "violation_type": string describing the type of violation (e.g., "hate_speech", "violence", "harassment", "spam", "none")
- "severity": one of ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
- "detailed_reasoning": 2-3 sentences explaining WHY this content is problematic or acceptable
- "key_phrases": list of specific words/phrases that triggered the flag (if any)
- "context_consideration": any mitigating factors (e.g., "could be satire", "lacks context")

**Policy Guidelines**:
- Hate speech, threats, violence → ESCALATE (CRITICAL/HIGH)
- Harassment, bullying → ESCALATE (MEDIUM/HIGH)
- Spam, off-topic → WARN (LOW)
- Borderline cases → ESCALATE for human review
- Normal discussion → IGNORE

**Content to analyze**:
{content}

Respond with ONLY valid JSON, no other text."""
    )
    llm = ChatGroq(model_name="llama-3.3-70b-versatile", groq_api_key=settings.GROQ_API_KEY)
    chain = prompt | llm
    response = chain.invoke({"content": state["content_text"]})
    try:
        result = json.loads(response.content)
        print(f"✓ AI Analysis: {result.get('suggested_action', 'UNKNOWN')} (confidence: {result.get('confidence_score', 0)})")
        state = update_state_meta(state, f"LLM analysis successful: {result['suggested_action']}")
    except json.JSONDecodeError:
        print("⚠️  AI response invalid, using fallback")
        result = {"confidence_score": 50, "suggested_action": "ESCALATE"}
        state = update_state_meta(state, "LLM analysis failed, using fallback.")
    
    state["analysis_result"] = result
    state["status"] = "AI_ANALYSIS_COMPLETE"
    return state


def request_human_review_node(state: GraphState) -> GraphState:
    """
    Pauses the graph for human review and updates the state.
    """
    print("⏸️  Pausing for human review")
    state = update_state_meta(state, "Escalated for human review.")
    state["status"] = "PENDING_HUMAN_REVIEW"
    state["escalation_count"] += 1
    return state


def should_request_human_review(state: GraphState) -> str:
    """Based on the AI's analysis, decide where to go next."""
    print("🤔 Checking AI decision...")
    suggested_action = state["analysis_result"].get("suggested_action", "ESCALATE")

    if suggested_action == "ESCALATE":
        print("→ Escalating to human review")
        return "request_human_review"
    else:
        print("→ Auto-resolving (no human review needed)")
        return "end" # We'll map this string to the END node


def execute_final_action_node(state: GraphState) -> GraphState:
    """
    Executes the final action based on human decision and tracks all actions for potential reversal.
    """
    decision = state.get("human_decision")
    print(f"⚡ Executing action: {decision}")
    state = update_state_meta(state, f"Executing final action based on human decision: {decision}.")
    
    executed_actions = []
    content_id = state.get("content_id")
    
    # Execute actions based on decision and track them
    if decision == "remove_content_and_ban":
        # Action 1: Remove content
        result = remove_content_api(content_id)
        executed_actions.append({
            "action": "remove_content",
            "timestamp": result["timestamp"],
            "reversible": True,
            "reversal_function": "restore_content_api",
            "params": {"content_id": content_id},
            "status": "success",
            "result": result
        })
        
        # Action 2: Ban user
        result = ban_user_api(content_id)
        executed_actions.append({
            "action": "ban_user",
            "timestamp": result["timestamp"],
            "reversible": True,
            "reversal_function": "unban_user_api",
            "params": {"content_id": content_id},
            "status": "success",
            "result": result
        })
        
    elif decision == "approve_removal":
        # Only remove content
        result = remove_content_api(content_id)
        executed_actions.append({
            "action": "remove_content",
            "timestamp": result["timestamp"],
            "reversible": True,
            "reversal_function": "restore_content_api",
            "params": {"content_id": content_id},
            "status": "success",
            "result": result
        })
        
    elif decision == "request_changes":
        # Send warning to user
        result = warn_user_api(content_id)
        executed_actions.append({
            "action": "warn_user",
            "timestamp": result["timestamp"],
            "reversible": False,  # Can't un-warn someone
            "status": "success",
            "result": result
        })
    
    else:
        print(f"📝 Logging decision: {decision} (no platform actions)")

    # Store executed actions for potential rollback
    state["executed_actions"] = executed_actions
    state["status"] = "COMPLETED"
    state = update_state_meta(state, f"Workflow completed. Executed {len(executed_actions)} action(s).")
        
    return state

# NEW: Rollback node - resets and re-pauses with action reversal
def rollback_node(state: GraphState) -> GraphState:
    """Handles rollback: Reverse executed actions, clear decision, log reason, re-pause."""
    print("🔄 Rolling back workflow...")
    
    rollback_reason = state.get("rollback_reason", "unspecified")
    rollback_requested_by = state.get("rollback_requested_by", "unknown")
    rollback_requested_at = state.get("rollback_requested_at", datetime.now(timezone.utc).isoformat())
    
    # Get executed actions to reverse
    executed_actions = state.get("executed_actions", [])
    reversal_results = []
    
    # Reverse actions in reverse order (LIFO)
    for action in reversed(executed_actions):
        if action.get("reversible") and action.get("status") == "success":
            reversal_func_name = action.get("reversal_function")
            params = action.get("params", {})
            
            try:
                # Call the reversal function dynamically
                reversal_func = globals()[reversal_func_name]
                result = reversal_func(**params)
                
                reversal_results.append({
                    "original_action": action["action"],
                    "reversal_status": "success",
                    "timestamp": result["timestamp"],
                    "result": result
                })
                print(f"  ✓ Reversed: {action['action']}")
                
            except Exception as e:
                reversal_results.append({
                    "original_action": action["action"],
                    "reversal_status": "failed",
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                print(f"  ✗ Failed to reverse: {action['action']}")
        else:
            print(f"  ⊘ Skipped (non-reversible): {action.get('action')}")
    
    # Create detailed rollback record
    rollback_record = {
        "rollback_id": str(uuid.uuid4()),
        "reason": rollback_reason,
        "requested_by": rollback_requested_by,
        "requested_at": rollback_requested_at,
        "previous_decision": state.get("human_decision"),
        "escalation_number": state.get("escalation_count", 0) + 1,
        "actions_reversed": reversal_results,
        "completed_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Update state
    rollback_history = state.get("rollback_history", [])
    rollback_history.append(rollback_record)
    
    state["rollback_history"] = rollback_history
    state["human_decision"] = None
    state["executed_actions"] = []  # Clear executed actions
    state["rollback_reason"] = None  # Clear trigger
    state["rollback_requested_by"] = None
    state["rollback_requested_at"] = None
    state["escalation_count"] = rollback_record["escalation_number"]
    state["status"] = "ROLLBACK_COMPLETE"
    
    state = update_state_meta(state, f"Rollback #{rollback_record['escalation_number']} completed. Reversed {len(reversal_results)} action(s).")
    
    print(f"✓ Rollback complete (escalation #{rollback_record['escalation_number']})")
    return state

# UPDATED: New conditional after action to check for rollback signal
def should_end_or_rollback(state: GraphState) -> str:
    """Check if rollback was requested post-action."""
    rollback_reason = state.get("rollback_reason")
    if rollback_reason:
        return "rollback"
    return END

# Build the workflow
workflow = StateGraph(GraphState)

workflow.add_node("analyze_content", analyze_content_node)
workflow.add_node("request_human_review", request_human_review_node)
workflow.add_node("execute_final_action", execute_final_action_node)
workflow.add_node("rollback", rollback_node)  # NEW

workflow.set_entry_point("analyze_content")
workflow.add_conditional_edges(
    "analyze_content", 
    should_request_human_review, 
    {
        "request_human_review": "request_human_review",
        "end": END
    }
)
workflow.add_edge("request_human_review", "execute_final_action")

# NEW: Conditional after action
workflow.add_conditional_edges(
    "execute_final_action",
    should_end_or_rollback,
    {
        "rollback": "rollback",
        END: END  # Default to end if no rollback
    }
)
# NEW: After rollback, loop back to pause
workflow.add_edge("rollback", "request_human_review")

# Compile outside (as before)
# with PostgresSaver.from_conn_string(settings.DATABASE_URL) as memory:
#     agent_app = workflow.compile(checkpointer=memory)
