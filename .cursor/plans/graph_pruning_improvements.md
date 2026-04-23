# Graph Pruning Improvements Backlog

## The Problem
In the Documents graph view, we are seeing apparent connections between documents that are just generic words (e.g., "year"). These single-word bridges are surviving the Phase 4 pruning process because their entity-to-entity degree is less than 50 (the current threshold for LLM verification). However, they still act as bridges between 2-15 documents, which makes them visible in the Documents graph.

We cannot simply delete all single words because some of them are highly valuable semantic concepts (e.g., "supply", "SaaS", "merger").

## Proposed Solutions

### 1. Secondary "Bridge" Pruning Pass (Phase 4b)
*   **Description:** Add a new phase to the graph worker. *After* documents are attached to entities (Phase 5), find all entities acting as document bridges (mentioned by 2-15 docs).
*   **Action:** Run these specific bridge entities through the LLM with a targeted prompt: *"Is this a meaningful semantic concept/entity that connects documents (like 'supply', 'merger', 'SaaS'), or is it a generic stopword/temporal word (like 'year', 'however', 'page')?"*

### 2. Lower the Phase 4 Threshold
*   **Description:** The current threshold for identifying "supernodes" in Phase 4 is a degree of `> 50`.
*   **Action:** Lower this threshold to `> 5` or `> 10`. This forces the LLM to evaluate a much larger percentage of the graph for "slop" before documents are even attached.

### 3. NLP Stopword Filter (Pre-Database)
*   **Description:** Implement a lightweight NLP filter during the initial extraction phase (Phase 1).
*   **Action:** Use a library like `nltk` or `spaCy` to automatically drop common English stopwords and temporal words (year, month, day, page, section) before they are even inserted into the Neo4j database. This prevents the slop from ever being created.