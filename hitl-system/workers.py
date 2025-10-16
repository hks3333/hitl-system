# hitl-system/workers.py
import dramatiq
import logging
from datetime import datetime, timezone

# Import broker configuration BEFORE defining actors
import event_broker

from langgraph.checkpoint.postgres import PostgresSaver
from agent import workflow as agent_workflow
from config import settings
from graph_state import GraphState

# Configure structured logging with file output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('workflow.log'),  # Detailed logs to file
        logging.StreamHandler()  # Console output
    ]
)

# Reduce noise from external libraries
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('dramatiq').setLevel(logging.WARNING)


@dramatiq.actor(max_retries=5, min_backoff=1000)
def start_agent(thread_id: str, payload: dict):
    """
    Dramatiq actor to start a new LangGraph agent workflow.
    """
    logging.info(f"🚀 Starting workflow: {thread_id}")

    with PostgresSaver.from_conn_string(settings.DATABASE_URL) as memory:
        agent_with_memory = agent_workflow.compile(checkpointer=memory)

        now = datetime.now(timezone.utc).isoformat()
        initial_state = GraphState(
            content_id=payload["content_id"],
            content_text=payload["content_text"],
            analysis_result=None,
            ui_schema=None,
            human_decision=None,
            escalation_count=0,
            # Initialize the new fields
            status="PENDING_AI_ANALYSIS",
            history=[(now, "Workflow started.")],
            last_updated=now,
            # Initialize rollback fields
            rollback_history=[],
            executed_actions=[],
            rollback_reason=None,
            rollback_requested_by=None,
            rollback_requested_at=None
        )

        config = {"configurable": {"thread_id": thread_id}}

        for event in agent_with_memory.stream(initial_state, config):
            # Log only node names, not full state
            node_name = list(event.keys())[0] if event else "unknown"
            logging.debug(f"  → Node executed: {node_name}")  # Debug level for detailed flow
            
            if "request_human_review" in event:
                logging.info(f"⏸️  Paused for human review: {thread_id}")
                return

    logging.info(f"✅ Workflow completed: {thread_id}")


@dramatiq.actor(max_retries=5, min_backoff=1000)
def resume_agent(thread_id: str, human_decision: dict):
    """
    Dramatiq actor to resume a paused LangGraph agent.
    """
    decision = human_decision.get("human_decision", "unknown")
    logging.info(f"▶️  Resuming workflow: {thread_id} | Decision: {decision}")

    with PostgresSaver.from_conn_string(settings.DATABASE_URL) as memory:
        agent_with_memory = agent_workflow.compile(checkpointer=memory)
        config = {"configurable": {"thread_id": thread_id}}

        # Update the state with the human's decision
        agent_with_memory.update_state(
            config,
            {"human_decision": human_decision["human_decision"]}
        )

        # Continue execution from the checkpoint
        for event in agent_with_memory.stream(None, config):
            node_name = list(event.keys())[0] if event else "unknown"
            logging.debug(f"  → Node executed: {node_name}")

    logging.info(f"✅ Workflow completed: {thread_id}")


@dramatiq.actor(max_retries=3, min_backoff=2000)
def rollback_workflow_async(thread_id: str, rollback_data: dict):
    """
    Dramatiq actor to handle workflow rollback asynchronously.
    Reverses executed actions and re-pauses for human review.
    """
    reason = rollback_data.get('reason', 'No reason provided')
    moderator = rollback_data.get('moderator_id', 'unknown')
    logging.info(f"🔄 Rolling back: {thread_id} | By: {moderator} | Reason: {reason}")
    
    with PostgresSaver.from_conn_string(settings.DATABASE_URL) as memory:
        agent_with_memory = agent_workflow.compile(checkpointer=memory)
        config = {"configurable": {"thread_id": thread_id}}
        
        # Inject rollback metadata into state
        agent_with_memory.update_state(config, {
            "rollback_reason": rollback_data["reason"],
            "rollback_requested_by": rollback_data.get("moderator_id", "unknown"),
            "rollback_requested_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Stream to execute rollback node
        for event in agent_with_memory.stream(None, config):
            node_name = list(event.keys())[0] if event else "unknown"
            logging.debug(f"  → Node executed: {node_name}")
            
            if "request_human_review" in event:
                logging.info(f"⏸️  Rollback complete, re-paused for review: {thread_id}")
                break
    
    logging.info(f"✅ Rollback completed: {thread_id}")