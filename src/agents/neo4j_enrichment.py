import json
from typing import Dict, Any
from src.agents.schemas.enrichment import CompanyEnrichment
from src.db.neo4j_session import driver

async def save_enriched_company_to_neo4j(pipeline_id: str, company: CompanyEnrichment):
    """
    Serializes a CompanyEnrichment Pydantic model and saves it to Neo4j.
    Neo4j doesn't support nested dictionaries, so we flatten 1-to-1 relationships
    and JSON-stringify 1-to-many or dynamic dictionaries.
    """
    
    # Determine the node type based on the stage estimate
    stage_lower = company.stage_estimate.lower()
    node_type = "Startup"
    if "incumbent" in stage_lower or "public" in stage_lower or "mature" in stage_lower:
        node_type = "Incumbent"
    elif "utility" in stage_lower or "muni" in stage_lower:
        node_type = "Utility"
    elif "investor" in stage_lower or "vc" in stage_lower or "pe" in stage_lower:
        node_type = "Investor"

    props: Dict[str, Any] = {
        "pipeline_id": pipeline_id,
        "name": company.name,
        "company_name": company.company_name,
        "type": node_type,
        "url": company.url or "",
        "description": company.full_description or "",  # Map to standard description field
        "full_description": company.full_description or "",
        "pitch_summary": company.pitch_summary or "",
        "primary_sector": company.primary_sector or "",
        "business_model": company.business_model or "",
        "tech_stack": company.tech_stack or [], # Neo4j supports lists of strings
        "tangibility_score": company.tangibility_score,
        "customer_type": company.customer_type or "",
        "investment_thesis_one_liner": company.investment_thesis_one_liner or "",
        "venture_scale_score": company.venture_scale_score,
        "stage_estimate": company.stage_estimate or "",
        "rationale": company.rationale or "",
        "company_twitter_url": company.company_twitter_url or "",
        
        # Flatten Taxonomy
        "taxonomy_l1": company.taxonomy.l1 if company.taxonomy else "",
        "taxonomy_l2": company.taxonomy.l2 if company.taxonomy else "",
        "taxonomy_l3": company.taxonomy.l3 if company.taxonomy else "",
        
        # Flatten VC Dossier
        "vc_dossier_hq_location": company.vc_dossier.hq_location if company.vc_dossier else "",
        "vc_dossier_year_founded": company.vc_dossier.year_founded if company.vc_dossier else "",
        "vc_dossier_headcount_estimate": company.vc_dossier.headcount_estimate if company.vc_dossier else "",
        "vc_dossier_corporate_status": company.vc_dossier.corporate_status if company.vc_dossier else "",
        "vc_dossier_plain_english_summary": company.vc_dossier.plain_english_summary if company.vc_dossier else "",
        "vc_dossier_macro_trend": company.vc_dossier.macro_trend if company.vc_dossier else "",
        "vc_dossier_analogy": company.vc_dossier.analogy if company.vc_dossier else "",
        "vc_dossier_moat_description": company.vc_dossier.moat_description if company.vc_dossier else "",
        "vc_dossier_total_raised": company.vc_dossier.total_raised if company.vc_dossier else "",
        "vc_dossier_latest_round": company.vc_dossier.latest_round if company.vc_dossier else "",
        "vc_dossier_key_investors": company.vc_dossier.key_investors if company.vc_dossier else "",
        "vc_dossier_key_customers": company.vc_dossier.key_customers if company.vc_dossier else "",
        "vc_dossier_source_urls": company.vc_dossier.source_urls if company.vc_dossier else [],
        
        # Flatten Strategic Analysis
        "strategic_market_depth_score": company.strategic_analysis.market_depth_score if company.strategic_analysis else 0,
        "strategic_market_narrative": company.strategic_analysis.market_narrative if company.strategic_analysis else "",
        "strategic_competitive_noise_level": company.strategic_analysis.competitive_noise_level if company.strategic_analysis else "",
        "strategic_ai_survival_score": company.strategic_analysis.ai_survival_score if company.strategic_analysis else 0.0,
        "strategic_ai_force_multiplier_thesis": company.strategic_analysis.ai_force_multiplier_thesis if company.strategic_analysis else "",
        
        # Flatten Unit Economics
        "unit_econ_acv_proxy": company.strategic_analysis.unit_economics_inference.acv_proxy if company.strategic_analysis and company.strategic_analysis.unit_economics_inference else "",
        "unit_econ_retention_quality": company.strategic_analysis.unit_economics_inference.retention_quality if company.strategic_analysis and company.strategic_analysis.unit_economics_inference else "",
        "unit_econ_distribution_friction": company.strategic_analysis.unit_economics_inference.distribution_friction if company.strategic_analysis and company.strategic_analysis.unit_economics_inference else "",
        
        # Flatten Metric Rationales
        "rationale_market_scale": company.metric_rationales.market_scale_rationale if company.metric_rationales else "",
        "rationale_competition": company.metric_rationales.competition_rationale if company.metric_rationales else "",
        "rationale_contract_size": company.metric_rationales.contract_size_rationale if company.metric_rationales else "",
        "rationale_stickiness": company.metric_rationales.stickiness_rationale if company.metric_rationales else "",
        "rationale_sales_difficulty": company.metric_rationales.sales_difficulty_rationale if company.metric_rationales else "",
        "rationale_ai_defensibility": company.metric_rationales.ai_defensibility_rationale if company.metric_rationales else "",
        
        # JSON Stringify complex/dynamic structures
        "dimension_scores_json": json.dumps(company.dimension_scores) if company.dimension_scores else "{}",
        "founders_json": json.dumps([f.model_dump() for f in company.founders]) if company.founders else "[]"
    }

    query = """
    // Try to find an existing company node with this name
    OPTIONAL MATCH (existing:CanonicalEntity {name: $props.name, pipeline_id: $props.pipeline_id})
    WHERE existing.type IN ['Company', 'Startup', 'Incumbent', 'Utility', 'Investor']
    
    // If it exists, update it
    FOREACH (_ IN CASE WHEN existing IS NOT NULL THEN [1] ELSE [] END |
        SET existing += $props
    )
    
    // If it doesn't exist, create a new one
    FOREACH (_ IN CASE WHEN existing IS NULL THEN [1] ELSE [] END |
        CREATE (new_c:CanonicalEntity)
        SET new_c += $props
    )
    """
    
    try:
        async with driver.session() as session:
            await session.run(query, props=props)
            print(f"[Neo4j] Successfully saved {props['name']} as type '{props['type']}'")
    except Exception as e:
        print(f"[Neo4j] Failed to save {props['name']}: {e}")
