# Company Enrichment Implementation Plan

This document outlines the 4-round implementation plan for building the Company Enrichment feature. It is a temporary working document and can be deleted once this phase of the project is complete.

### Round 1: The Standalone Enrichment Agent (Schema & Search Loop)
**Goal:** Build the core engine that can take a single company name (e.g., "Fischer Block") and output the perfect JSON.
*   Create `src/agents/schemas/enrichment.py` with the exhaustive Pydantic models.
*   Create `src/agents/enrichment_agent.py`. This will be a mini LangGraph workflow that executes the multi-step search strategy (Primary Website -> Crunchbase/Pitchbook -> LinkedIn -> Fallback News Search).
*   *Testing:* We run this standalone script on 1-2 known companies to ensure the LLM successfully navigates the searches, handles paywalls/blocks, and outputs the exact JSON structure without crashing.

### Round 2: Neo4j Serialization & Storage
**Goal:** Figure out how to cleanly save this massive, nested JSON object into Neo4j.
*   Neo4j node properties do not natively support nested dictionaries or lists of dictionaries (e.g., the `founders` array or `dimension_scores`).
*   We need to write a utility function that serializes these nested objects (either by flattening them into dot-notation properties like `dimension_scores.Side_of_the_Meter`, or storing them as stringified JSON blocks on the node).
*   *Testing:* Push the output from Round 1 into your local Neo4j database and verify it looks correct in the Neo4j browser.

### Round 3: Main Pipeline Integration
**Goal:** Wire the new agent into your data acquisition phase.
*   Update `src/agents/nodes.py`. Right after the `company_extraction_node` generates the `discovered_companies` list, we pass that list to our new Enrichment Agent.
*   Because enriching hundreds of companies takes time and API calls, we will need to implement concurrent processing (using `asyncio.gather` with a semaphore to avoid rate limits).
*   Write the enriched companies to Neo4j *before* the planner node generates the broader Google searches.

### Round 4: OpenIE / Graph Worker Overhaul
**Goal:** Stop the Hermes model from polluting the graph with noise.
*   Update `src/agents/graph_worker.py`. 
*   Change the Hermes system prompt from *"extract every distinct entity"* to *"You are analyzing text for a specific set of known startups. Only extract relationships between these known entities. If you find a new company, classify it strictly as 'Incumbent', 'Utility', or 'Noise'."*
*   Ensure the graph generation phase correctly links the newly extracted relationships to the rich `Startup` nodes we seeded in Round 3.