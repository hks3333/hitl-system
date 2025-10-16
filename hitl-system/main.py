# main.py
import uuid
import logging
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from langgraph.checkpoint.postgres import PostgresSaver

# Import broker configuration BEFORE importing workers
import event_broker

from agent import workflow as agent_workflow, GraphState
from config import settings
from workers import start_agent, resume_agent, rollback_workflow_async

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI(
    title="Guardian AI - Moderation Orchestrator",
    description="API for starting and resuming content moderation workflows."
)

origins = [
    "http://localhost:3000",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- Pydantic Models for API Data Validation ---
class StartWorkflowRequest(BaseModel):
    content_id: str
    content_text: str

class ResumeWorkflowRequest(BaseModel):
    human_decision: str # e.g., "approve_removal", "ignore"
    moderator_id: str
    comment: Optional[str] = None

# --- API Endpoints ---
@app.post("/workflows/start", status_code=202)
def start_workflow(payload: StartWorkflowRequest):
    """
    Starts a new content moderation workflow by enqueuing a task.
    """
    thread_id = f"moderation_case_{uuid.uuid4()}"
    logging.info(f"---API: Enqueuing task for new workflow with thread_id: {thread_id}---")

    # Send a message to the start_agent worker instead of using BackgroundTasks
    start_agent.send(thread_id, payload.dict())

    return {"thread_id": thread_id, "message": "Workflow task enqueued successfully."}


@app.post("/workflows/{thread_id}/resume", status_code=202)
def resume_workflow(thread_id: str, payload: ResumeWorkflowRequest):
    """
    Receives a human's decision and enqueues a task to resume the workflow.
    """
    logging.info(f"---API: Received human decision for thread_id: {thread_id}---")

    # Send a message to the resume_agent worker
    resume_agent.send(thread_id, payload.dict())

    return {"thread_id": thread_id, "message": "Decision received. Resume task enqueued."}


class RollbackRequest(BaseModel):
    reason: str  # e.g., "Mod changed mind"
    moderator_id: str  # Who is requesting the rollback

@app.post("/workflows/{thread_id}/rollback", status_code=202)
def rollback_workflow(thread_id: str, payload: RollbackRequest):
    """
    Initiates an asynchronous rollback of a completed workflow.
    Reverses executed actions and re-pauses for human review.
    """
    logging.info(f"---API: Rollback requested for {thread_id} by {payload.moderator_id}: {payload.reason}---")
    
    # Validate workflow exists and is in a rollback-eligible state
    try:
        with PostgresSaver.from_conn_string(settings.DATABASE_URL) as memory:
            agent_with_memory = agent_workflow.compile(checkpointer=memory)
            config = {"configurable": {"thread_id": thread_id}}
            state_snapshot = agent_with_memory.get_state(config)
            
            if not state_snapshot:
                raise HTTPException(status_code=404, detail="Workflow not found")
            
            state = state_snapshot.values
            current_status = state.get("status", "UNKNOWN")
            
            # Only allow rollback if workflow is completed
            if current_status not in ["COMPLETED", "ROLLBACK_COMPLETE"]:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Cannot rollback workflow in status: {current_status}. Only COMPLETED workflows can be rolled back."
                )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error validating rollback for {thread_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate rollback request")
    
    # Enqueue async rollback task
    rollback_workflow_async.send(thread_id, payload.dict())
    
    return {
        "thread_id": thread_id, 
        "message": "Rollback initiated asynchronously",
        "status": "processing"
    }


@app.get("/workflows/status/{thread_id}")
def get_workflow_status(thread_id: str):
    """
    Gets the latest saved state for a given workflow thread.
    This is used by the frontend to poll for updates.
    """
    try:
        with PostgresSaver.from_conn_string(settings.DATABASE_URL) as memory:
            # Compile the graph with the checkpointer (same as in background task)
            agent_with_memory = agent_workflow.compile(checkpointer=memory)
            
            config = {"configurable": {"thread_id": thread_id}}
            
            # Fetch the latest StateSnapshot for this thread
            latest_state_snapshot = agent_with_memory.get_state(config)
            
            if latest_state_snapshot is None:
                raise HTTPException(status_code=404, detail="Workflow not found or no checkpoint yet.")
            
            # Extract GraphState from snapshot.values
            state = latest_state_snapshot.values
            
            # For the frontend: Simple mapping from analysis_result (no 'none' default)
            ai_result = state.get("analysis_result")
            ai_suggestion = ai_result.get("violation_type") if ai_result else None
            severity = ai_result.get("severity") if ai_result else None
            suggested_action = ai_result.get("suggested_action") if ai_result else None
            
            # FIXED: Infer status from snapshot.next (no direct 'status' attr)
            if not latest_state_snapshot.next:
                inferred_status = "done"
            else:
                inferred_status = "interrupted"  # Paused/pending human review
            
            # ENHANCED: Expose more for dashboard
            analysis_summary = ai_result.get("message") if ai_result else None
            
            return {
                "thread_id": thread_id,
                "ai_suggestion": ai_suggestion,  # e.g., "confidential_info"
                "analysis_summary": analysis_summary,  # e.g., "The post contains a potential API key..."
                "severity": severity,
                "suggested_action": suggested_action,
                "analysis_result": ai_result,  # for richer frontends (optional)
                "human_decision": state.get("human_decision"),  # e.g., "remove_content_and_ban"
                "ui_schema": state.get("ui_schema"),  # Dynamic form schema
                "rollback_history": state.get("rollback_history", []),  # Detailed rollback audit
                "executed_actions": state.get("executed_actions", []),  # Actions that were executed
                "escalation_count": state.get("escalation_count", 0),  # For escalation display
                "status": state.get("status", inferred_status),  # Use explicit status if available
                "workflow_status": inferred_status,  # Graph execution status
                "next_node": latest_state_snapshot.next,  # e.g., tuple of upcoming nodes
                "history": state.get("history", []),  # Full event history
                "last_updated": state.get("last_updated")  # Last update timestamp
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching status for {thread_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch workflow status.")