import json
from typing import Dict, Any

from src.agents.schemas.enrichment import CompanyEnrichment
from src.db.neo4j_session import driver


def _node_type_for_stage(stage_estimate: str) -> str:
    stage_lower = (stage_estimate or "").lower()
    node_type = "Startup"
    if "incumbent" in stage_lower or "public" in stage_lower or "mature" in stage_lower:
        node_type = "Incumbent"
    elif "utility" in stage_lower or "muni" in stage_lower:
        node_type = "Utility"
    elif "investor" in stage_lower or "vc" in stage_lower or "pe" in stage_lower:
        node_type = "Investor"
    return node_type


async def project_company_enrichment_to_neo4j(pipeline_id: str, company: Dict[str, Any]):
    stage_estimate = str(company.get("stage_estimate") or "")
    node_type = _node_type_for_stage(stage_estimate)
    founders = list(company.get("founders") or [])
    taxonomy = dict(company.get("taxonomy") or {})
    vc_dossier = dict(company.get("vc_dossier") or {})
    strategic_analysis = dict(company.get("strategic_analysis") or {})
    unit_economics = dict(strategic_analysis.get("unit_economics_inference") or {})
    metric_rationales = dict(company.get("metric_rationales") or {})

    props: Dict[str, Any] = {
        "pipeline_id": pipeline_id,
        "name": company.get("name") or company.get("company_name"),
        "company_name": company.get("company_name") or company.get("name"),
        "type": node_type,
        "url": company.get("url") or "",
        "description": company.get("full_description") or "",
        "full_description": company.get("full_description") or "",
        "pitch_summary": company.get("pitch_summary") or "",
        "primary_sector": company.get("primary_sector") or "",
        "business_model": company.get("business_model") or "",
        "tech_stack": list(company.get("tech_stack") or []),
        "tangibility_score": company.get("tangibility_score") or 0,
        "customer_type": company.get("customer_type") or "",
        "investment_thesis_one_liner": company.get("investment_thesis_one_liner") or "",
        "venture_scale_score": company.get("venture_scale_score") or 0.0,
        "stage_estimate": stage_estimate,
        "rationale": company.get("rationale") or "",
        "company_twitter_url": company.get("company_twitter_url") or "",
        "taxonomy_l1": taxonomy.get("l1") or "",
        "taxonomy_l2": taxonomy.get("l2") or "",
        "taxonomy_l3": taxonomy.get("l3") or "",
        "vc_dossier_hq_location": vc_dossier.get("hq_location") or "",
        "vc_dossier_year_founded": vc_dossier.get("year_founded") or "",
        "vc_dossier_headcount_estimate": vc_dossier.get("headcount_estimate") or "",
        "vc_dossier_corporate_status": vc_dossier.get("corporate_status") or "",
        "vc_dossier_plain_english_summary": vc_dossier.get("plain_english_summary") or "",
        "vc_dossier_macro_trend": vc_dossier.get("macro_trend") or "",
        "vc_dossier_analogy": vc_dossier.get("analogy") or "",
        "vc_dossier_moat_description": vc_dossier.get("moat_description") or "",
        "vc_dossier_total_raised": vc_dossier.get("total_raised") or "",
        "vc_dossier_latest_round": vc_dossier.get("latest_round") or "",
        "vc_dossier_key_investors": vc_dossier.get("key_investors") or "",
        "vc_dossier_key_customers": vc_dossier.get("key_customers") or "",
        "vc_dossier_source_urls": list(vc_dossier.get("source_urls") or company.get("source_urls") or []),
        "strategic_market_depth_score": strategic_analysis.get("market_depth_score") or 0,
        "strategic_market_narrative": strategic_analysis.get("market_narrative") or "",
        "strategic_competitive_noise_level": strategic_analysis.get("competitive_noise_level") or "",
        "strategic_ai_survival_score": strategic_analysis.get("ai_survival_score") or 0.0,
        "strategic_ai_force_multiplier_thesis": strategic_analysis.get("ai_force_multiplier_thesis") or "",
        "unit_econ_acv_proxy": unit_economics.get("acv_proxy") or "",
        "unit_econ_retention_quality": unit_economics.get("retention_quality") or "",
        "unit_econ_distribution_friction": unit_economics.get("distribution_friction") or "",
        "rationale_market_scale": metric_rationales.get("market_scale_rationale") or "",
        "rationale_competition": metric_rationales.get("competition_rationale") or "",
        "rationale_contract_size": metric_rationales.get("contract_size_rationale") or "",
        "rationale_stickiness": metric_rationales.get("stickiness_rationale") or "",
        "rationale_sales_difficulty": metric_rationales.get("sales_difficulty_rationale") or "",
        "rationale_ai_defensibility": metric_rationales.get("ai_defensibility_rationale") or "",
        "dimension_scores_json": json.dumps(company.get("dimension_scores") or {}),
        "founders_json": json.dumps(founders),
        "founder_count": len(founders),
        "source_document_ids_json": json.dumps(company.get("source_document_ids") or []),
        "enrichment_source": "postgres_projection",
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


async def save_enriched_company_to_neo4j(pipeline_id: str, company: CompanyEnrichment):
    await project_company_enrichment_to_neo4j(pipeline_id, company.model_dump())
