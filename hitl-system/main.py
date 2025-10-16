# main.py
import uuid
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from langgraph.checkpoint.postgres import PostgresSaver

import event_broker

from agent import workflow as agent_workflow
from config import settings
from workers import start_agent, resume_agent, rollback_workflow_async

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# In-memory tracking for current session (for demo purposes)
active_workflows = {}  # {thread_id: {"status": "...", "created_at": "...", "content_preview": "..."}}

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

    # Track in session
    from datetime import datetime, timezone
    active_workflows[thread_id] = {
        "status": "PENDING_AI_ANALYSIS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "content_preview": payload.content_text[:100]  # First 100 chars
    }

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


@app.get("/workflows/pending")
def get_pending_workflows():
    """
    Returns all workflows from current session that are pending human review.
    """
    pending_cases = []
    
    for thread_id in list(active_workflows.keys()):
        try:
            with PostgresSaver.from_conn_string(settings.DATABASE_URL) as memory:
                agent_with_memory = agent_workflow.compile(checkpointer=memory)
                config = {"configurable": {"thread_id": thread_id}}
                state_snapshot = agent_with_memory.get_state(config)
                
                if state_snapshot:
                    state = state_snapshot.values
                    status = state.get("status", "UNKNOWN")
                    
                    # Update session tracking
                    active_workflows[thread_id]["status"] = status
                    
                    # Include if pending human review or rollback complete (needs re-review)
                    if status in ["PENDING_HUMAN_REVIEW", "ROLLBACK_COMPLETE"]:
                        pending_cases.append({
                            "thread_id": thread_id,
                            "content_preview": active_workflows[thread_id].get("content_preview", ""),
                            "created_at": active_workflows[thread_id].get("created_at"),
                            "status": status,
                            "escalation_count": state.get("escalation_count", 0),
                            "rollback_history": state.get("rollback_history", [])
                        })
        except Exception as e:
            logging.error(f"Error checking workflow {thread_id}: {e}")
            continue
    
    return {"pending_cases": pending_cases, "count": len(pending_cases)}


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
            
            return {
                "thread_id": thread_id,
                "analysis_result": state.get("analysis_result"),
                "human_decision": state.get("human_decision"),
                "rollback_history": state.get("rollback_history", []),
                "executed_actions": state.get("executed_actions", []),
                "escalation_count": state.get("escalation_count", 0),
                "status": state.get("status", "UNKNOWN"),
                "history": state.get("history", []),
                "last_updated": state.get("last_updated")
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching status for {thread_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch workflow status.")