# Architecture Diagram


![[vid.mp4]]

## Core Features

* **Stateful Agent Core**: Built with **LangGraph**, the agent has persistent memory, allowing it to be paused and resumed without losing context.

* **Asynchronous & Non-Blocking**: The entire system is event-driven, using **RabbitMQ** and background workers. The API remains fast and responsive, capable of managing thousands of concurrent workflows.

* **Durable Persistence**: Agent state is automatically saved as checkpoints in Supabase **PostgreSQL** database, ensuring resilience against system crashes.

* **Complete Rollback & Appeal Lifecycle**: Rollback mechanism reverts actions and re-queues the case for a second review, creating a full appeal loop.

* **Full Observability**: Integrated with **LangSmith**, providing complete, step-by-step traces of the agent's reasoning process for debugging and auditing.

  

## The "Guardian" Architecture: A Deep Dive

The system is designed as a set of decoupled services communicating through an event bus. This mirrors a professional "Command Center" operation, ensuring scalability and resilience.

* **The Agent (`agent.py`) is the Specialist**: This is the expert analyst (our LangGraph brain). It performs a single task, like analyzing content, and has its own memory (the `GraphState`). It knows its own workflow, including when it needs to stop and ask for orders.

* **The API (`main.py`) is the Front Desk**: This is the public-facing entry point. It receives incoming requests (`/start`, `/resume`, `/rollback`) from the outside world (like a user or another service). It doesn't do any heavy thinking; it simply validates the request and enqueues a task for a background worker.

* **The Workers (`workers.py`) are the Dispatchers**: These are the background operators who do the actual work by listening for messages on the queue.

    * The `start_agent` worker takes a new case and hands it to the Specialist (the agent).
    * The `resume_agent` worker takes a decision from a human and delivers it to the correct paused Specialist.
    * The `rollback_workflow_async` worker handles the complex logic of reversing an agent's actions.

* **RabbitMQ (`event_broker.py`) is the Secure Comms Channel**: This is the message broker connecting the Front Desk to the Dispatchers. It guarantees that messages are delivered reliably and asynchronously, so the API is never blocked waiting for a worker to be free.

  

## The Full Workflow Lifecycle: From Creation to Appeal

The true power of the architecture is demonstrated by its ability to handle a complete, multi-stage workflow.

1.  **Start**: A user posts content. The API receives it and enqueues a `start_agent` task.

2.  **Analyze & Pause**: The agent runs, analyzes the content, and if a violation is detected, it pauses itself by interrupting before the `request_human_review` step. Its state is saved to PostgreSQL.

3.  **Human Decision**: A moderator reviews the case and submits a decision. The API receives this and enqueues a `resume_agent` task.

4.  **Execute**: The resume worker wakes the agent. The agent executes the final action (e.g., `remove_content_api`). The workflow is now `COMPLETED`.

5.  **Appeal & Rollback**: A user or supervisor submits an appeal via the `/rollback` endpoint. This enqueues a `rollback_workflow_async` task.

6.  **Reverse & Re-Pause**: The rollback worker wakes the agent. The agent runs its `rollback` node, which dynamically calls the correct reversal functions for the actions it previously took. It then loops back to the `request_human_review` node and pauses again, waiting for a second, escalated review.

  

## Getting Started
### 1. Prerequisites

* Python 3.10+
* An active virtual environment
* Access keys for Supabase, CloudAMQP, Groq, and LangSmith.

### 2. Setup
1.  **Clone the repository.**

2.  **Install dependencies**:

    ```bash

    pip install -r requirements.txt

    ```

3.  **Configure Environment**:

    * Create a `.env` file in the `hitl-system` directory.

    * Fill in the required API keys and URLs from your providers (Supabase, CloudAMQP, etc.). A `.env.example` is provided for reference.

### 3. Running the System
The system requires two separate terminal processes to run concurrently.

* **Terminal 1: Start the API Server**

    ```bash

    uvicorn main:app --reload

    ```

* **Terminal 2: Start the Background Workers**

    ```bash

    dramatiq workers -p 1

    ```


You can also interact with the system via the automatically generated API documentation at `http://127.0.0.1:8000/docs` and the included `demo.html` file.