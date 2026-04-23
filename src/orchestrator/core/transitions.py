# Central registry mapping the outcome of a task to the next task(s).
# This makes the workflow deterministic and auditable.

TRANSITION_TABLE = {
    "MARKET_SIZING": {
        "SUCCESS": "EXTRACT_COMPANIES",
        "FAILED": "HALT_PIPELINE"
    },
    "EXTRACT_COMPANIES": {
        # Fan-out to TWO parallel tracks for each discovered company
        "SUCCESS": ["ENRICH_COMPANY", "PLAN_COMPANY_SEARCH"],
        "FAILED": "HALT_PIPELINE"
    },
    "ENRICH_COMPANY": {
        "SUCCESS": "SAVE_TO_NEO4J",
        "FAILED": "LOG_AND_CONTINUE"
    },
    "PLAN_COMPANY_SEARCH": {
        "SUCCESS": "SCRAPE_URL",
        "FAILED": "LOG_AND_CONTINUE"
    },
    "SCRAPE_URL": {
        "SUCCESS": "BOUNCER_EVALUATION",
        "FAILED": "MARK_URL_FAILED"
    },
    "BOUNCER_EVALUATION": {
        "IS_RELEVANT": "VECTOR_STORAGE",
        "NOT_RELEVANT": "DISCARD"
    }
}
