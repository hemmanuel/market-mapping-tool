# True RAG Architecture & Document Graph Master Plan

## Current Status
- [x] Phase 1: Core RAG Engine (Backend)
- [x] Phase 2: Wire RAG to Main Graph Explorer
- [x] Phase 3: Fix Document Graph Visuals
- [x] Phase 4: Wire RAG to Document Explorer

---

## 1. The Goal
Implement a true Retrieval-Augmented Generation (RAG) system that uses chunk-level embeddings to provide context-rich, cited insights. Fix the Document Graph to prominently display all documents (including islands) connected by specific bridging entities and deep chunk-level semantic similarities.

## 2. The Architecture
- **PostgreSQL (`pgvector`)**: Stores raw document text and chunk-level vector embeddings.
- **Neo4j (Knowledge Graph)**: Stores explicit LLM-extracted entities (`CanonicalEntity`) and chunk-level `SIMILAR_TO` edges between documents.
- **RAG Engine**: 
  1. Fetches the graph neighborhood (Neo4j).
  2. Retrieves the exact raw text chunks associated with those nodes/edges (PostgreSQL).
  3. Packages the graph structure and raw text chunks into a strict prompt.
  4. Returns a cited, context-rich LLM response.

## 3. The Phases

### Phase 1: The Core RAG Engine (Backend Only)
- **Goal:** Build the isolated Python service (`src/services/rag_service.py`) that can fetch a graph neighborhood, retrieve the exact raw text chunks from PostgreSQL, and generate a cited LLM response.
- **Acceptance Criteria:** A standalone service that successfully returns accurate, cited text based on a given Entity ID or Document ID pair, without touching the UI.

### Phase 2: Wire RAG to the Main Graph Explorer (Full Stack)
- **Goal:** Replace the current hallucination-prone LLM call in the Main Graph Explorer with the new RAG engine.
- **Acceptance Criteria:** Clicking a Company or Regulation in the main graph returns a holistic explanation with specific citations (e.g., "According to [Document A], Company X...").

### Phase 3: Fix the Document Graph Visuals (Frontend & Cypher)
- **Goal:** Fix the `?theme=documents` view so it actually looks like a map of documents.
- **Acceptance Criteria:** A clean visual map where large Document nodes are connected by small, specific entity bridges. Island documents must be visible. Clicking a document must open the on-page viewer.

### Phase 4: Wire RAG to the Document Explorer (Full Stack)
- **Goal:** Apply the RAG engine to the Document clusters.
- **Acceptance Criteria:** Clicking a cluster of documents uses the RAG engine to explain exactly why those specific documents are connected, citing the overlapping sections.

## 4. Anti-Patterns (What NOT to do)
- **DO NOT truncate documents** to generate embeddings. Always use chunk-level embeddings.
- **DO NOT write Cypher queries that hide island nodes.** Always use `OPTIONAL MATCH` to ensure 100% document visibility.
- **DO NOT use generic "super-connector" entities as bridges** in the Document view. Filter out entities mentioned by every document.
- **DO NOT write hallucination-prone LLM calls** that guess instead of citing specific document chunks.
- **DO NOT build the entire architecture in one go.** Stick to the phases to prevent context overload and regressions.