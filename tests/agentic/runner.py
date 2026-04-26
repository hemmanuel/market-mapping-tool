import asyncio
import os
import datetime
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from tests.agentic.state import TesterState, TestConfig
from tests.agentic.nodes import init_browser, test_niche_phase, test_schema_phase, test_sources_phase, teardown

# Load environment variables from frontend/.env.local
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../frontend/.env.local'))

def create_tester_graph():
    workflow = StateGraph(TesterState)
    
    # Add nodes
    workflow.add_node("init_browser", init_browser)
    workflow.add_node("test_niche", test_niche_phase)
    workflow.add_node("test_schema", test_schema_phase)
    workflow.add_node("test_sources", test_sources_phase)
    workflow.add_node("teardown", teardown)
    
    # Define edges (linear flow)
    workflow.set_entry_point("init_browser")
    workflow.add_edge("init_browser", "test_niche")
    workflow.add_edge("test_niche", "test_schema")
    workflow.add_edge("test_schema", "test_sources")
    workflow.add_edge("test_sources", "teardown")
    workflow.add_edge("teardown", END)
    
    return workflow.compile()

# Expose the compiled graph globally for LangGraph Studio
app = create_tester_graph()

async def main():
    print("Starting Agentic Test against Vercel Deployment...")
    
    # Initialize the configuration
    config = TestConfig(
        target_url="https://market-mapping-tool.vercel.app/",
        target_niche="Spacetech"
    )
    
    # Initialize the state
    initial_state = TesterState(
        config=config,
        browser=None,
        context=None,
        page=None,
        logs=[],
        status="pending"
    )
    
    # Run the state machine
    print(f"Target URL: {config.target_url}")
    print(f"Target Niche: {config.target_niche}")
    print("-" * 40)
    
    final_state = await app.ainvoke(initial_state)
    
    print("\n--- Test Execution Logs ---")
    
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # Generate timestamped filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(logs_dir, f"test_run_{timestamp}.log")
    
    with open(log_filename, "w", encoding="utf-8") as log_file:
        log_file.write(f"Target URL: {config.target_url}\n")
        log_file.write(f"Target Niche: {config.target_niche}\n")
        log_file.write("-" * 40 + "\n\n")
        
        for log in final_state["logs"]:
            print(f"[*] {log}")
            log_file.write(f"[*] {log}\n")
            
        print("-" * 40)
        log_file.write("\n" + "-" * 40 + "\n")
        
        if final_state.get("status") == "pass":
            print("✅ ALL TESTS PASSED")
            log_file.write("✅ ALL TESTS PASSED\n")
        else:
            print("❌ TESTS FAILED")
            log_file.write("❌ TESTS FAILED\n")
            
    print(f"\nLogs saved to: {log_filename}")

if __name__ == "__main__":
    asyncio.run(main())
