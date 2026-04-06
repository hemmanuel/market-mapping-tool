from playwright.async_api import async_playwright, Page
from tests.agentic.state import TesterState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import asyncio
import os

async def init_browser(state: TesterState) -> TesterState:
    config = state["config"]
    state["logs"].append(f"Initializing browser and navigating to {config.target_url}")
    
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True) # Headless for WSL compatibility
    context = await browser.new_context()
    page = await context.new_page()
    
    await page.goto(config.target_url)
    await page.wait_for_load_state("networkidle")
    
    state["browser"] = browser
    state["context"] = context
    state["page"] = page
    state["playwright"] = p # Store to stop later
    
    state["logs"].append("Browser initialized successfully.")
    return state

async def test_niche_phase(state: TesterState) -> TesterState:
    page: Page = state["page"]
    config = state["config"]
    
    try:
        state["logs"].append(f"Testing Niche Phase with LLM Simulated User")
        
        # Initialize the Testing Agent's LLM
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY")
        tester_llm = ChatGoogleGenerativeAI(
            model="gemini-3.1-pro-preview",
            api_key=api_key
        )
        conversation_history = [SystemMessage(content=config.user_persona)]
        
        # Find the chat input
        chat_input = page.locator('input[placeholder="Chat with the consultant..."]')
        
        # Kick off the conversation
        initial_msg = "I would like to map the space thech space broadly from an early-stage vc"
        await chat_input.fill(initial_msg)
        await page.keyboard.press("Enter")
        
        state["logs"].append(f"Simulated User: {initial_msg}")
        conversation_history.append(AIMessage(content=initial_msg))
        
        turn_count = 0
        while turn_count < config.max_conversation_turns:
            # 1. Wait for the Consultant AI to finish generating
            await page.locator('.animate-bounce').first.wait_for(state="hidden", timeout=30000)
            
            # 2. Check if the UI transitioned to Phase: SCHEMA
            is_schema_phase = await page.locator('text=Phase: SCHEMA').is_visible()
            if is_schema_phase:
                state["logs"].append(f"✅ Success! Consultant locked the niche after {turn_count + 1} turns.")
                return state
                
            # 3. Scrape the Consultant's latest reply from the DOM
            chat_bubbles = await page.locator('.whitespace-pre-wrap.text-sm').all_inner_texts()
            consultant_reply = chat_bubbles[-1] if chat_bubbles else "Unknown"
            state["logs"].append(f"Consultant: {consultant_reply}")
            
            # 4. Pass the reply to the Simulated User LLM to generate a response
            conversation_history.append(HumanMessage(content=consultant_reply))
            simulated_user_reply = await tester_llm.ainvoke(conversation_history)
            
            # 5. Type the Simulated User's response into the chat input and submit
            reply_text = simulated_user_reply.content
            if isinstance(reply_text, list):
                # Sometimes the model returns a list of content blocks
                reply_text = " ".join([block.get("text", "") for block in reply_text if isinstance(block, dict)])
            
            state["logs"].append(f"Simulated User: {reply_text}")
            await chat_input.fill(reply_text)
            await page.keyboard.press("Enter")
            
            conversation_history.append(AIMessage(content=reply_text))
            turn_count += 1
            
        # If the loop exhausts max_conversation_turns without a UI transition, abandon the test
        raise AssertionError(f"❌ Test Abandoned: Consultant failed to lock the niche after {config.max_conversation_turns} turns.")
        
    except Exception as e:
        state["logs"].append(f"Niche Phase failed: {str(e)}")
        state["status"] = "fail"
        return state

async def test_schema_phase(state: TesterState) -> TesterState:
    if state.get("status") == "fail":
        return state
        
    page: Page = state["page"]
    config = state["config"]
    
    try:
        state["logs"].append("Testing Schema Phase...")
        await page.wait_for_timeout(2000) # Polite delay
        
        # We need to prompt the AI to generate the schema
        chat_input = page.locator('input[placeholder="Chat with the consultant..."]')
        await chat_input.fill("Yes, go ahead and add the entities and relationships for this niche.")
        await page.keyboard.press("Enter")
        
        state["logs"].append("Requested schema generation. Waiting for entities to populate...")
        
        # Wait for at least one entity badge to appear
        await page.locator('.space-y-4 >> .flex.flex-wrap.gap-2 >> .group\\/badge').first.wait_for(state="visible", timeout=45000)
        
        # Wait a bit more for all tool calls to finish
        await page.wait_for_timeout(5000)
        
        # Simulate Human-in-the-loop: Add a manual entity
        state["logs"].append("Simulating manual entity addition: 'University'")
        entity_input = page.locator('input[name="entityName"]')
        await entity_input.fill("University")
        await page.locator('form').filter(has=entity_input).locator('button[type="submit"]').click()
        
        # Give it a moment to render
        await page.wait_for_timeout(1000)
        
        # Check if University is there
        entity_badges = await page.locator('.space-y-4 >> .flex.flex-wrap.gap-2 >> .group\\/badge').all_inner_texts()
        # Clean up texts (remove the trash icon text if any)
        clean_badges = [text.replace('\n', '').strip() for text in entity_badges]
        
        if not any("University" in badge for badge in clean_badges):
            raise AssertionError(f"Manually added entity 'University' not found in badges: {clean_badges}")
            
        state["logs"].append("Manual entity addition verified.")
        
        # Click Next Step
        state["logs"].append("Clicking 'Next Step' to transition to Sources Phase...")
        await page.locator('button:has-text("Next Step")').click()
        
        # Verify transition to Sources
        await page.locator('text=Phase: SOURCES').wait_for(state="visible", timeout=5000)
        
        state["logs"].append("Schema Phase passed successfully.")
        return state
        
    except Exception as e:
        state["logs"].append(f"Schema Phase failed: {str(e)}")
        state["status"] = "fail"
        return state

async def test_sources_phase(state: TesterState) -> TesterState:
    if state.get("status") == "fail":
        return state
        
    page: Page = state["page"]
    
    try:
        state["logs"].append("Testing Sources Phase...")
        await page.wait_for_timeout(2000) # Polite delay
        
        # Fill out the manual source form
        state["logs"].append("Adding a manual data source...")
        await page.locator('input[name="sourceName"]').fill("SpaceNews")
        await page.locator('input[name="sourceUrl"]').fill("https://spacenews.com")
        await page.locator('select[name="sourceType"]').select_option("rss")
        
        # Click Add (the second button with text "Add" or specific to the form)
        add_btn = page.locator('form').nth(1).locator('button[type="submit"]')
        await add_btn.scroll_into_view_if_needed()
        await add_btn.click(force=True)
        
        await page.wait_for_timeout(1000)
        
        # Verify source appears in the list
        sources_text = await page.locator('.space-y-2').nth(1).inner_text()
        if "SpaceNews" not in sources_text or "https://spacenews.com" not in sources_text:
            # Let's try grabbing the whole card content just in case the selector is slightly off
            sources_text = await page.locator('.space-y-4').nth(1).inner_text()
            if "SpaceNews" not in sources_text or "https://spacenews.com" not in sources_text:
                raise AssertionError(f"Manually added source not found in the list. Found text: {sources_text}")
            
        state["logs"].append("Manual source addition verified.")
        
        # Verify Review Pipeline button is active
        review_btn = page.locator('button:has-text("Review Pipeline")')
        if not await review_btn.is_visible():
            raise AssertionError("Review Pipeline button is not visible.")
            
        state["status"] = "pass"
        state["logs"].append("Sources Phase passed successfully. Test Complete.")
        return state
        
    except Exception as e:
        state["logs"].append(f"Sources Phase failed: {str(e)}")
        state["status"] = "fail"
        return state

async def teardown(state: TesterState) -> TesterState:
    state["logs"].append("Tearing down browser...")
    
    if "browser" in state and state["browser"]:
        await state["browser"].close()
        
    if "playwright" in state and state["playwright"]:
        await state["playwright"].stop()
        
    state["logs"].append(f"Final Status: {state.get('status', 'unknown').upper()}")
    return state
