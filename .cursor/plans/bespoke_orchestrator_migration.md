# Migration Plan: Bespoke Orchestration Kernel

## Phase 1: Define the Core Orchestration Primitives
Before touching the existing logic, we will build the foundational classes of the new kernel. This ensures strict, narrow lanes for data flow.

*   **1.1 Define the Task Frame Schema:**
    Create a strict Pydantic model representing a unit of work. Instead of passing a global state, the orchestrator will pass Task Frames to workers.
*   **1.2 Define Worker State Contracts (I/O):**
    For every existing node (Planner, Scraper, Bouncer, etc.), define a strict Input model and Output model. 
*   **1.3 Build the Declarative Transition Table:**
    Create a central registry (a dictionary or YAML) that maps the outcome of a task to the next task. This makes the entire workflow deterministic and auditable at a glance.

## Phase 2: Build the Bespoke LLM Client
Strip out `langchain-google-genai` and build a lightweight, transparent wrapper around the official Google/Ollama APIs.

*   **2.1 The Base LLM Client:**
    Create a Python class using `httpx` (or the official `google-genai` SDK) that handles raw API calls.
*   **2.2 Native Structured Output:**
    Implement a method that takes a Pydantic model, generates the corresponding JSON Schema, and passes it to the LLM API's native `response_schema` or `tools` parameter.
*   **2.3 Deterministic Retry Logic:**
    Move the exponential backoff logic (handling 429s, 500s, and JSON parsing errors) directly into this client so it is universally applied and highly visible, rather than hidden inside LangChain's retry middleware.

## Phase 3: Refactor Nodes into Isolated Workers
Convert the functions in `src/agents/nodes.py` from LangGraph nodes into isolated, stateless Python functions (or classes).

*   **3.1 Remove `AgentState` Mutations:**
    Rewrite each worker so it no longer reads from or writes to a global dictionary.
*   **3.2 Implement the Workers:**
    *   `MarketSizingWorker`
    *   `CompanyExtractionWorker`
    *   `PlannerWorker`
    *   `ScraperWorker`
    *   `BouncerWorker`
    *   `VectorStorageWorker`

## Phase 4: Build the Engine (The Orchestrator)
Write the actual kernel that reads the Transition Table, manages the Task Frames, and executes the Workers.

*   **4.1 The Event Loop / Queue Manager:**
    Create an `asyncio.Queue` (or a Postgres-backed queue for true persistence). The Orchestrator pulls a `TaskFrame` from the queue, checks its `task_type`, and routes the payload to the correct Worker.
*   **4.2 State Resolution:**
    When a Worker returns its Output contract, the Orchestrator looks up the `(task_type, outcome)` in the Transition Table. It then generates the *next* `TaskFrame(s)` and pushes them into the queue.
*   **4.3 Concurrency Control:**
    Implement `asyncio.Semaphore` at the Orchestrator level to strictly control how many tasks of a specific type (e.g., LLM calls vs. Web Scrapes) can run simultaneously.

## Phase 5: Wire the Endpoints and Cleanup
Connect the FastAPI backend to the new kernel and remove the old dependencies.

*   **5.1 Update `src/api/routes.py`:**
    Replace the `build_acquisition_graph().astream()` call with `Orchestrator.start_pipeline(pipeline_id)`.
*   **5.2 Event Publishing:**
    Ensure the Orchestrator emits the same SSE events (`event_manager.publish`) so the frontend UI continues to update in real-time without needing frontend rewrites.
*   **5.3 Dependency Pruning:**
    Remove `langchain`, `langchain-core`, `langchain-google-genai`, and `langgraph` from `requirements.txt`.