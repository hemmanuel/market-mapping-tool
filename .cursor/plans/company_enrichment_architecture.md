# Company Enrichment Architecture & Plan

## Objective
Transform the platform from a simple OpenIE text-extractor into a rigorous Market Intelligence tool. We will build a dedicated LangChain workflow that takes the curated list of startups generated during the `market_sizing_node` and `company_extraction_node` phases, and enriches them into deep, VC-grade dossiers *before* general graph extraction begins.

## The Problem
Currently, the pipeline spends compute generating a highly curated list of VC-backed startups, but only uses this list to seed Google searches. The actual graph generation relies on an unconstrained local model (Hermes) that blindly extracts noisy entities (utilities, municipalities, generic incumbents) from the scraped text. The 140 companies currently in the graph are low-signal and lack the depth required for venture analysis.

## The Solution: "Seed-First" Exhaustive Enrichment
We will integrate a new **Company Enrichment Agent** into the primary workflow. 

### 1. Workflow Integration
1. **Sizing & Extraction:** `market_sizing_node` and `company_extraction_node` generate the exhaustive list of startups.
2. **Enrichment (NEW):** Every discovered startup is passed to the Enrichment Agent.
3. **Database Seeding (NEW):** The enriched dossiers are saved directly to Neo4j as `Startup` nodes.
4. **Constrained Extraction:** The downstream OpenIE graph worker is constrained to only map relationships *between* these known, enriched startups (or distinctly tag new entities as `Incumbent`/`Utility` to avoid polluting the startup view).

### 2. The Exhaustive Search Agent
To populate the rigorous schema, a single Google search is insufficient. The LangChain agent must employ a multi-step, fallback-driven search strategy to exhaust all avenues for missing data:

*   **Step 1: Primary Asset Search:** Search for the official company website. Scrape the homepage, "About Us", and "Product/Technology" pages.
*   **Step 2: Financial & Investor Search:** Search `site:crunchbase.com OR site:pitchbook.com "[Company Name]"` to find total raised, latest round, and key investors.
*   **Step 3: Founder Deep-Dive:** Search `site:linkedin.com/in "[Founder Name]" "[Company Name]"` to extract bios, previous companies, and technical background.
*   **Step 4: Fallback/Exhaustion Loop:** If critical fields (e.g., `total_raised`, `stage_estimate`) are still missing, the agent must dynamically generate fallback queries (e.g., `"[Company Name]" "seed round" OR "series A" OR "raised" "press release"`) and scrape news articles until the data is found or definitively proven unavailable.

### 3. Target JSON Schema
The agent will be forced to output the following Pydantic/JSON structure for every company:

```json
{
    "name": "Fischer Block",
    "url": "https://dt2026.mapyourshow.com/8_0/exhibitor/exhibitor-details.cfm?exhid=A-316D0",
    "full_description": "Feb. 3- 5 San Diego, CA Home Floor Plan Exhibitor Collateral Fischer Block Booths ADMIN ONLY — Sponsor Mark As Visited  DTECH 2026•©2026 All Rights Reserved  Sitemap |  XML Sitemap | Help | Privacy Policy",
    "company_name": "Fischer Block",
    "pitch_summary": "Fischer Block provides an end-to-end monitoring solution for the electrical grid, utilizing high-frequency sensors and advanced analytics to provide predictive maintenance insights for critical assets like transformers. Their technology converts raw electrical waveforms into actionable intelligence to prevent equipment failure and improve grid reliability.",
    "primary_sector": "Distribution",
    "business_model": "SaaS",
    "tech_stack": [
      "IoT",
      "Edge Computing",
      "Machine Learning",
      "High-frequency Waveform Analysis",
      "Predictive Analytics",
      "Cloud Computing"
    ],
    "tangibility_score": 8,
    "customer_type": "Electric Utilities",
    "investment_thesis_one_liner": "Fischer Block enables grid modernization through a cost-effective IoT platform that transforms legacy infrastructure into intelligent, self-monitoring assets.",
    "dimension_scores": {
      "Side of the Meter": 1,
      "Time Horizon": 0.9,
      "Voltage Magnitude": 0.6,
      "Asset Intensity": 0.6,
      "Hardware Dependency": 0.9,
      "Deployment Friction": 0.5,
      "Network Sovereignty": 0.5,
      "Capital Intensity": 0.1,
      "Environmental Hardening": 1,
      "Energy Flow": 0,
      "Cloud Reliance": 0.5,
      "Autonomy Level": 0.3,
      "Value Chain Position": 0.6,
      "Storage Physics": null,
      "Data Source": 1,
      "Regulatory Moat": 0.6,
      "Project vs Product": 0.9,
      "Asset Health Strategy": 1,
      "Brownfield vs Greenfield": 1,
      "Moat Strategy": 0.2,
      "Tech Leverage": 0.8,
      "Customer Model": 1,
      "Operational Domain": 0
    },
    "venture_scale_score": 0.7,
    "stage_estimate": "Series A",
    "rationale": "Fischer Block addresses the critical problem of aging grid infrastructure through high-fidelity waveform analysis and predictive maintenance, offering a sticky, high-value data moat. However, the reliance on hardware retrofits within a regulated utility sales cycle introduces significant deployment friction and adoption latency.",
    "taxonomy": {
      "l1": "Grid Operations & Software (SaaS)",
      "l2": "Asset Performance Management",
      "l3": "Transformer Monitoring & Analytics"
    },
    "vc_dossier": {
      "hq_location": "West Chester, PA, United States",
      "year_founded": "2013",
      "headcount_estimate": "1-10",
      "corporate_status": "Independent",
      "plain_english_summary": "Fischer Block builds specialized sensors (SMART Block) and AI software that connect to existing electrical grid equipment. Think of it as an 'EKG machine' for power lines—it captures high-speed electrical waveforms to predict outages and equipment failures before they happen, without needing to replace the expensive legacy infrastructure already in place.",
      "macro_trend": "Grid Modernization & AI Reliability",
      "analogy": "The 'Fitbit' for Grid Assets",
      "moat_description": "Patented 'Non-Intrusive' Hardware Retrofit",
      "total_raised": "$3.8M - $5M (Est.)",
      "latest_round": "Series A (2018)",
      "key_investors": "Ben Franklin Technology Partners, Blu Venture Investors, SRI Capital, Carbon6 Ventures",
      "key_customers": "Certrec (Strategic Partner), Unnamed Global Automotive Manufacturer, Unnamed Vaccine Research Facility",
      "source_urls": [
        "https://fischerblock.com/",
        "https://www.certrec.com/news/certrecs-alliance-with-fischer-block-utilizing-predictive-analytics/",
        "https://bluventureinvestors.com/portfolio/fischer-block/",
        "https://www.crunchbase.com/organization/fischer-block",
        "https://pitchbook.com/profiles/company/120668-38"
      ]
    },
    "founders": [
      {
        "name": "Gregory R. Wolfe",
        "role": "President & CEO",
        "bio": "Gregory R. Wolfe began his career in 1986 as a Senior Electrical Engineer at Texas Instruments, where he worked on Advanced Defense Weapons Systems. He later served as the Director of Operations for McDonald Technologies before joining Megger, a leader in electrical test equipment, as an Executive Vice President for 14 years. In 2014, he co-founded Fischer Block to leverage his extensive background in power engineering and predictive analytics to develop 'intelligence at the edge' solutions for the electrical grid. Wolfe is an active member of the IEEE, holds multiple patents in power system analytics, and is a certified Six Sigma Black Belt.",
        "hometown": null,
        "linkedin_url": null,
        "twitter_url": null,
        "previous_companies": [
          "Texas Instruments",
          "McDonald Technologies",
          "Megger"
        ],
        "education": [
          "Bachelor of Science in Electrical Engineering, Michigan State University"
        ],
        "is_technical": true,
        "tags": [
          "Technical",
          "Six Sigma Black Belt",
          "Patents"
        ]
      },
      {
        "name": "Margaret Paietta",
        "role": "Co-founder, Director of Strategic Accounts & CMO",
        "bio": "Margaret Paietta began her career in 1982 as the first female software engineer at Singer's Link/Avionics Division in Silicon Valley, specializing in flight simulation systems. She later transitioned into entrepreneurship, founding Casual American Sportswear LLC in 2002 and Utility Staffing Associates, an energy-focused executive recruiting firm, in 2009. In 2013, she co-founded Fischer Block, Inc., where she combines her technical background with executive leadership to drive marketing and strategic accounts for smart grid analytics.",
        "hometown": "California",
        "linkedin_url": null,
        "twitter_url": null,
        "previous_companies": [
          "Singer, Link/Avionics Division",
          "Casual American Sportswear LLC",
          "Utility Staffing Associates"
        ],
        "education": [
          "Bachelor of Science in Psychology and Computer Science, Santa Clara University"
        ],
        "is_technical": true,
        "tags": [
          "Woman-Led",
          "Serial Founder",
          "Technical Founder"
        ]
      }
    ],
    "company_twitter_url": null,
    "strategic_analysis": {
      "market_depth_score": 6,
      "market_narrative": "Addressing the Distribution market with a focus on Electric Utilities.",
      "competitive_noise_level": "Low",
      "unit_economics_inference": {
        "acv_proxy": "Medium",
        "retention_quality": "Medium",
        "distribution_friction": "Medium"
      },
      "ai_survival_score": 0.87,
      "ai_force_multiplier_thesis": "Fischer Block secures a high survivability score because its core value proposition is tethered to physical IoT deployment and edge computing on critical infrastructure, rather than generic data processing. An AI agent cannot virtually extract high-frequency waveform data from a physical transformer; it requires the proprietary sensors and 'atoms-based' installation that Fischer Block provides. Furthermore, the company operates within the heavily regulated utility sector, where the friction of hardware certification and physical installation creates a defensive barrier that prevents swift displacement by pure software competitors."
    },
    "metric_rationales": {
      "market_scale_rationale": "The company operates within the critical Grid Modernization sector, specifically targeting the aging electrical distribution infrastructure which requires massive capital injection to handle the complexity of distributed energy resources (DERs).\n\nWhile the total addressable market for smart grid analytics is in the multi-billions due to the sheer size of global utility assets, the attainable market is gated by slow utility regulatory cycles and CapEx budget approvals. The demand is driven by an urgent need to reduce O&M costs and prevent catastrophic failures (like wildfires), creating a deep, albeit slow-moving, revenue pool.",
      "competition_rationale": "Fischer Block competes against massive legacy incumbents like Siemens, GE Vernova, and Schweitzer Engineering Laboratories (SEL), who dominate the physical hardware of the grid but often lack agile, software-first analytics capabilities.\n\nThey also face competition from niche grid-edge sensor startups like Sentient Energy, yet Fischer Block distinguishes itself through 'High-frequency Waveform Analysis' rather than simple RMS data logging. The company leverages Gregory Wolfe’s specific background at Megger to position their solution as a high-fidelity diagnostic tool rather than just another generic IoT monitoring platform.",
      "contract_size_rationale": "Initial engagements likely begin as paid pilot programs in the $50k-$150k range, focused on instrumenting specific substations or problematic feeder lines to prove ROI.\n\nUpon successful validation, contract values can scale into the high six-figures or millions annually, depending on whether the revenue model includes hardware sales or is purely SaaS-based analytics on existing infrastructure. Given the critical nature of grid reliability, utilities are willing to pay a premium for predictive insights that prevent outages, supporting a healthy Average Contract Value (ACV) once the 'land and expand' phase is executed.",
      "stickiness_rationale": "Retention is exceptionally high due to the physical and data-centric lock-in inherent in grid edge computing; once sensors are installed and calibrated to a specific grid topology, the switching costs are operationally prohibitive.\n\nFurthermore, the value of the platform compounds over time as the Machine Learning models ingest more historical waveform data specific to that utility's infrastructure, making the predictive analytics increasingly accurate. Utilities tend to be extremely risk-averse, meaning once a vendor is integrated into their safety and maintenance workflows, they rarely churn.",
      "sales_difficulty_rationale": "The sales cycle is excruciatingly high-friction, likely lasting 18 to 24 months, as selling to regulated public utilities involves navigating complex procurement processes, safety validations, and rate-case justifications.\n\nDespite Founder Margaret Paietta’s experience in utility staffing and strategic accounts, the company must overcome the 'pilot purgatory' phenomenon common in this sector where technology is tested indefinitely before full rollout. Success requires convincing conservative engineering teams to trust algorithmic predictions over traditional scheduled maintenance, which is a significant cultural shift.",
      "ai_defensibility_rationale": "Fischer Block secures a high survivability score because its core value proposition is tethered to physical IoT deployment and edge computing on critical infrastructure, rather than generic data processing. An AI agent cannot virtually extract high-frequency waveform data from a physical transformer; it requires the proprietary sensors and 'atoms-based' installation that Fischer Block provides. Furthermore, the company operates within the heavily regulated utility sector, where the friction of hardware certification and physical installation creates a defensive barrier that prevents swift displacement by pure software competitors."
    }
}
```

## Implementation Steps
1. **Create Pydantic Models:** Translate the JSON schema above into strict Pydantic models in `src/agents/schemas/enrichment.py`.
2. **Build the Agent (`src/agents/enrichment_agent.py`):** Create a LangChain state graph specifically for company enrichment that loops through the search strategies until all fields are populated or exhausted.
3. **Wire into Pipeline:** Update `src/agents/nodes.py` to call the enrichment agent on the `discovered_companies` list before proceeding to the `planner_node`.
4. **Neo4j Ingestion:** Write the enriched JSON objects to Neo4j as `CanonicalEntity {type: 'Startup'}` nodes with all nested properties serialized.
5. **Update OpenIE:** Modify `src/agents/graph_worker.py` to recognize these pre-seeded startups and avoid duplicating them with generic extractions.