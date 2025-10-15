# resume_worker.py
import dramatiq
from event_broker import rabbitmq_broker

from langgraph.checkpoint.postgres import PostgresSaver
from agent import workflow as agent_workflow
from config import settings


@dramatiq.actor
def resume_agent(thread_id: str, human_decision: dict):
    """
    This actor resumes a paused LangGraph agent.
    """
    print(f"---WORKER: Received resume signal for thread_id: {thread_id}---")
    print(f"---WORKER: Human decision: {human_decision}---")

    # The 'with' statement ensures the database connection is managed correctly
    with PostgresSaver.from_conn_string(settings.DATABASE_URL) as memory:
        # Compile the agent with memory, just like in the API
        agent_with_memory = agent_workflow.compile(checkpointer=memory)
        # The config tells the agent which "save slot" to use
        config = {"configurable": {"thread_id": thread_id}}

        agent_with_memory.update_state(
            config,
            {"human_decision": human_decision["human_decision"]}
        )

        # agent_with_memory.invoke(None, config=config)

        # Continue execution from the persisted checkpoint. Use stream to observe steps.
        for event in agent_with_memory.stream(None, config):
            print(f"RESUME STREAM EVENT: {event}")
            # If you want to detect something specific you can do so here.
            # If the workflow ends, the for-loop will complete.

    
    print(f"---WORKER: Agent for thread_id {thread_id} has been resumed.---")