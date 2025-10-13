# main.py
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

# This will create the tables in the database if they don't exist
# It's good practice for the first run
models.Base.metadata.create_all(bind=engine)


@dramatiq.actor
def process_workflow_event(event: dict):
    # This is a stub. The actual logic will be in workers.py
    print(f"Stub received event: {event}")


app = FastAPI(
    title="Human in the Loop Orchestrator",
    description="API for managing and responding to approval workflows."
)

# --- Pydantic Models ---
class CallbackPayload(BaseModel):
    decision: str
    user_id: str
    comment: Optional[str] = None

class WorkflowCreate(BaseModel):
    context_data: dict

# --- API Endpoints ---
@app.post("/workflows", status_code=201)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    """A temporary endpoint to create a workflow for testing."""
    # Start a transaction to ensure both writes succeed or fail together
    with db.begin():
        new_workflow = models.Workflow(
            current_state='PENDING_APPROVAL',
            context_data=payload.context_data
        )
        db.add(new_workflow)
        db.flush() # This ensures new_workflow.id is populated

        audit_entry = models.AuditLog(
            workflow_id=new_workflow.id,
            to_state='PENDING_APPROVAL',
            comment="Workflow created and awaiting approval."
        )
        db.add(audit_entry)

    db.commit()
    db.refresh(new_workflow)

    process_workflow_event.send({
    "event_type": "WORKFLOW_CREATED",
    "workflow_id": str(new_workflow.id)
    })
    return new_workflow


@app.post("/callback/{workflow_id}")
def handle_callback(workflow_id: uuid.UUID, payload: CallbackPayload, db: Session = Depends(get_db)):
    """
    Handles the asynchronous response from a human.
    This is the core of our state management.
    """
    # A transaction ensures that the workflow update and the audit log entry
    # are an "atomic" operation. They both succeed, or they both fail.
    with db.begin():
        # Step 1: Find the workflow and lock it to prevent race conditions
        workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).with_for_update().first()

        # Step 2: Validate the current state
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found.")
        if workflow.current_state != 'PENDING_APPROVAL':
            raise HTTPException(status_code=409, detail=f"Workflow is not pending approval. Current state: {workflow.current_state}")

        # Step 3: Determine the new state
        from_state = workflow.current_state
        to_state = 'APPROVED' if payload.decision.lower() == 'approved' else 'REJECTED'

        # Step 4: Update the workflow's state
        workflow.current_state = to_state
        workflow.updated_at = datetime.utcnow()

        # Step 5: Create an audit log entry for this action
        audit_entry = models.AuditLog(
            workflow_id=workflow_id,
            from_state=from_state,
            to_state=to_state,
            triggered_by=payload.user_id,
            comment=payload.comment
        )
        db.add(audit_entry)

    db.commit()
    process_workflow_event.send({
    "event_type": "APPROVAL_COMPLETED",
    "workflow_id": str(workflow_id),
    "decision": to_state.lower()
    })
    return {"message": f"Workflow {workflow_id} has been {to_state.lower()}."}