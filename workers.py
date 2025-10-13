# workers.py
import dramatiq
import time
from event_broker import rabbitmq_broker

# This is the real implementation of our actor
@dramatiq.actor
def process_workflow_event(event: dict):
    """
    This worker listens for events and orchestrates the workflow.
    """
    print(f"WORKER: Received event! Details: {event}")

    workflow_id = event.get("workflow_id")
    event_type = event.get("event_type")

    if event_type == "WORKFLOW_CREATED":
        # In the future, this could trigger a notification service.
        print(f"WORKER: New workflow {workflow_id} created. Awaiting approval.")

    elif event_type == "APPROVAL_COMPLETED":
        decision = event.get("decision")
        if decision == "approved":
            print(f"WORKER: Approval received for {workflow_id}. Starting deployment...")
            # Simulate a long-running deployment task
            time.sleep(5)
            print(f"WORKER: ✅ Deployment for {workflow_id} complete!")
        else:
            print(f"WORKER: Rejection received for {workflow_id}. Starting rollback...")
            # Simulate a rollback task
            time.sleep(2)
            print(f"WORKER: ❌ Rollback for {workflow_id} complete.")