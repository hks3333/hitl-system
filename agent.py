# agent.py
import json
import uuid
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver # <- IMPORT the official saver

# This line loads your .env file
load_dotenv()

# Import the state definition and your settings
from graph_state import GraphState
from config import settings

# The analyze_content_node function remains exactly the same.
def analyze_content_node(state: GraphState) -> GraphState:
    """
    Analyzes the content using our fast LLM to get a preliminary assessment.
    """
    print("---NODE: ANALYZING CONTENT---")
    prompt = ChatPromptTemplate.from_template(
        "You are an expert content moderator. Analyze the following text for policy violations like hate speech or violence. "
        "Respond ONLY with a valid JSON object containing two keys: a 'confidence_score' (from 0 to 100) and a 'suggested_action' "
        "which must be one of the following strings: 'IGNORE', 'WARN', or 'ESCALATE'.\n\n"
        "Content to analyze: {content}"
    )
    llm = ChatGroq(model_name="llama-3.3-70b-versatile", groq_api_key=settings.GROQ_API_KEY)
    chain = prompt | llm
    response = chain.invoke({"content": state["content_text"]})
    try:
        result = json.loads(response.content)
        print(f"---LLM Analysis Successful: {result}---")
    except json.JSONDecodeError:
        print("---LLM Response was not valid JSON, using fallback.---")
        result = {"confidence_score": 50, "suggested_action": "ESCALATE"}
    state["analysis_result"] = result
    return state


def request_human_review_node(state: GraphState) -> GraphState:
    """This node doesn't do any work. It's a state that represents a pause."""
    print("---NODE: PAUSING FOR HUMAN REVIEW---")
    # The graph will stop executing after this node until it's resumed.
    return state


def should_request_human_review(state: GraphState) -> str:
    """Based on the AI's analysis, decide where to go next."""
    print("---CONDITION: CHECKING AI ANALYSIS---")
    suggested_action = state["analysis_result"].get("suggested_action", "ESCALATE")

    if suggested_action == "ESCALATE":
        print("---DECISION: Human review is required. Routing to 'request_human_review' node.---")
        return "request_human_review"
    else:
        print("---DECISION: AI can handle this. Auto-resolving and ending workflow.---")
        return "end" # We'll map this string to the END node


def execute_final_action_node(state: GraphState) -> GraphState:
    """Executes the final action based on the human's decision."""
    print("---NODE: EXECUTING FINAL ACTION---")
    
    # The human_decision was injected by our resume_worker
    decision = state.get("human_decision") 
    print(f"---Human decision was: {decision}---")
    
    if decision == "remove_content_and_ban":
        print("---Action: Calling platform API to remove content and ban user.---")
        # In a real app, an API call would happen here.
    else:
        print(f"---Action: Logging decision '{decision}' and closing case.---")
        
    return state



workflow = StateGraph(GraphState)

workflow.add_node("analyze_content", analyze_content_node)
workflow.add_node("request_human_review", request_human_review_node)
workflow.add_node("execute_final_action", execute_final_action_node)

workflow.set_entry_point("analyze_content")
workflow.add_conditional_edges(
    "analyze_content", # The starting node for the decision
    should_request_human_review, # The function that makes the decision
    {
        "request_human_review": "request_human_review",
        "end": END
    }
)
workflow.add_edge("request_human_review", "execute_final_action")
workflow.add_edge("execute_final_action", END)


# with PostgresSaver.from_conn_string(settings.DATABASE_URL) as memory:
#     agent_app = workflow.compile(checkpointer=memory)

    # print("Testing agent run with PAUSE logic...")
    # thread_id = str(uuid.uuid4())
    # config = {"configurable": {"thread_id": thread_id}}
    # initial_case_file = {
    #     "content_id": "test_vid_004",
    #     "content_text": "This is content that our AI should probably escalate.",
    #     "escalation_count": 0
    # }

    # for event in agent_app.stream(initial_case_file, config):
    #     print(event)
    
    # print(f"\n✅ Run paused. Check your database for thread_id: {thread_id}")