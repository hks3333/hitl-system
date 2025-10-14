# graph_builder.py
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from graph_state import GraphState
from config import settings

# 1. Define our tools / nodes
def analyze_content_node(state: GraphState):
    """Analyzes the content using our fast LLM."""
    print("---ANALYZING CONTENT---")

    prompt = ChatPromptTemplate.from_template(
        "You are an AI content moderator. Analyze the following text for potential policy violations "
        "(hate speech, violence, etc.). Respond with a JSON object containing a 'confidence_score' (0-100) "
        "and a 'suggested_action' (e.g., 'IGNORE', 'WARN', 'ESCALATE').\n\n"
        "Content: {content}"
    )

    llm = ChatGroq(model_name="llama3-70b-8192", groq_api_key=settings.GROQ_API_KEY)

    chain = prompt | llm

    # This is a placeholder for a real analysis result
    # In a real app, you would parse the LLM's JSON response
    result = {"confidence_score": 75, "suggested_action": "ESCALATE"}

    state['analysis_result'] = result
    return state

# 2. Define the graph
workflow = StateGraph(GraphState)

# 3. Add the nodes
workflow.add_node("analyze_content", analyze_content_node)

# 4. Add the edges
workflow.set_entry_point("analyze_content")
workflow.add_edge("analyze_content", END) # For now, it's a simple linear graph

# 5. Compile the graph
app = workflow.compile()

# To test this file directly
if __name__ == "__main__":
    initial_state = {
        "content_id": "vid123",
        "content_text": "This is some really controversial content that needs review.",
        "escalation_count": 0
    }
    # The .stream() method lets us see the output of each step
    for event in app.stream(initial_state):
        print(event)
        print("---")