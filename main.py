import uuid
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from event_broker import rabbitmq_broker
import dramatiq
# Import our own modules
import models
from database import engine, get_db
from graph_builder import app as moderation_graph

app = FastAPI(
    title="Human in the Loop Orchestrator",
    description="API for managing and responding to approval workflows."
)

class WorkflowCreate(BaseModel):
    content_id: str
    content_text: str

@app.post("/workflows", status_code=202) # 202 Accepted means it's running in the background
def create_workflow(payload: WorkflowCreate):
    """
    Starts a new content moderation workflow.
    """
    # Define the initial state for our graph
    initial_state = {
        "content_id": payload.content_id,
        "content_text": payload.content_text,
        "escalation_count": 0
    }

    # For a truly async operation, you would use .ainvoke() in a background task
    # For this hackathon, a synchronous call is fine to show it works.
    # The result will contain the final state of the graph.
    final_state = moderation_graph.invoke(initial_state)

    # You would still save the final state to your PostgreSQL DB here
    # For now, we just return it
    return final_state

# We will rebuild the /callback endpoint later to inject responses into a *running* graph