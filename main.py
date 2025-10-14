# main.py
import uuid
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
from langgraph.checkpoint.postgres import PostgresSaver

from agent import workflow as agent_workflow, GraphState
from config import settings

# This is our FastAPI application
app = FastAPI(
    title="Guardian AI - Moderation Orchestrator",
    description="API for starting and resuming content moderation workflows."
)

# --- Pydantic Models for API Data Validation ---
class StartWorkflowRequest(BaseModel):
    content_id: str
    content_text: str

class ResumeWorkflowRequest(BaseModel):
    human_decision: str # e.g., "approve_removal", "ignore"
    moderator_id: str
    comment: Optional[str] = None

# --- Background Task Function ---
def run_agent_in_background(thread_id: str, payload: StartWorkflowRequest):
    """A wrapper function to run the LangGraph agent in the background."""
    print(f"---Starting background agent run for thread_id: {thread_id}---")
    
    with PostgresSaver.from_conn_string(settings.DATABASE_URL) as memory:
        # Compile the agent with the checkpointer just before running
        agent_with_memory = agent_workflow.compile(checkpointer=memory)

        initial_state = GraphState(
            content_id=payload.content_id,
            content_text=payload.content_text,
            analysis_result=None,
            ui_schema=None,
            human_decision=None,
            escalation_count=0
        )
        
        config = {"configurable": {"thread_id": thread_id}}
        
        # Invoke the agent with memory
        agent_with_memory.invoke(initial_state, config)
    
    print(f"---Agent run PAUSED for thread_id: {thread_id}---")

# --- API Endpoints ---
@app.post("/workflows/start", status_code=202)
def start_workflow(payload: StartWorkflowRequest, background_tasks: BackgroundTasks):
    """
    Starts a new content moderation workflow in the background.
    """
    # Generate a unique ID for this moderation case
    thread_id = f"moderation_case_{uuid.uuid4()}"
    
    # Add the agent execution to run in the background after the response is sent
    background_tasks.add_task(run_agent_in_background, thread_id, payload)
    
    # Immediately return the ID so the client can track the case
    return {"thread_id": thread_id, "message": "Workflow started. Awaiting AI analysis."}

@app.post("/workflows/{thread_id}/resume", status_code=200)
def resume_workflow(thread_id: str, payload: ResumeWorkflowRequest):
    """
    Receives a human's decision and will (soon) resume the paused workflow.
    """
    print(f"---Received human decision for thread_id: {thread_id}---")
    print(f"---Decision: {payload.human_decision} by {payload.moderator_id}---")

    # In the NEXT step, this endpoint will publish a message to RabbitMQ.
    # For now, we'll just return a success message.
    
    return {"thread_id": thread_id, "message": "Decision received. Workflow will be resumed."}