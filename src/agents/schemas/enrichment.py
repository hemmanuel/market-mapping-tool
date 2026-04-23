from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class Taxonomy(BaseModel):
    l1: str = Field(description="Level 1 taxonomy (e.g., Grid Operations & Software)")
    l2: str = Field(description="Level 2 taxonomy (e.g., Asset Performance Management)")
    l3: str = Field(description="Level 3 taxonomy (e.g., Transformer Monitoring & Analytics)")

class VCDossier(BaseModel):
    hq_location: str = Field(description="Headquarters location")
    year_founded: str = Field(description="Year the company was founded")
    headcount_estimate: str = Field(description="Estimated number of employees")
    corporate_status: str = Field(description="Corporate status (e.g., Independent, Acquired, Public)")
    plain_english_summary: str = Field(description="A simple, easy-to-understand summary of what the company does")
    macro_trend: str = Field(description="The macro trend driving this company's market")
    analogy: str = Field(description="A simple analogy (e.g., 'The Fitbit for Grid Assets')")
    moat_description: str = Field(description="Description of the company's competitive moat")
    total_raised: str = Field(description="Total funding raised (e.g., '$3.8M - $5M (Est.)')")
    latest_round: str = Field(description="Latest funding round and year (e.g., 'Series A (2018)')")
    key_investors: str = Field(description="Comma-separated list of key investors")
    key_customers: str = Field(description="Comma-separated list of key customers or partners")
    source_urls: List[str] = Field(description="List of URLs used as sources for this dossier")

class Founder(BaseModel):
    name: str = Field(description="Founder's full name")
    role: str = Field(description="Founder's role (e.g., President & CEO)")
    bio: str = Field(description="Detailed biography of the founder")
    hometown: Optional[str] = Field(default=None, description="Founder's hometown or current location")
    linkedin_url: Optional[str] = Field(default=None, description="Founder's LinkedIn URL")
    twitter_url: Optional[str] = Field(default=None, description="Founder's Twitter URL")
    previous_companies: List[str] = Field(default_factory=list, description="List of previous companies the founder worked at")
    education: List[str] = Field(default_factory=list, description="List of educational degrees and institutions")
    is_technical: bool = Field(description="Whether the founder has a technical background")
    tags: List[str] = Field(default_factory=list, description="Tags describing the founder (e.g., 'Serial Founder', 'Technical')")

class UnitEconomics(BaseModel):
    acv_proxy: str = Field(description="Proxy for Average Contract Value (e.g., 'Low', 'Medium', 'High')")
    retention_quality: str = Field(description="Quality of customer retention (e.g., 'Low', 'Medium', 'High')")
    distribution_friction: str = Field(description="Level of friction in distribution/sales (e.g., 'Low', 'Medium', 'High')")

class StrategicAnalysis(BaseModel):
    market_depth_score: int = Field(description="Score from 1-10 indicating market depth")
    market_narrative: str = Field(description="Narrative describing the market focus")
    competitive_noise_level: str = Field(description="Level of competitive noise (e.g., 'Low', 'Medium', 'High')")
    unit_economics_inference: UnitEconomics = Field(description="Inferences about unit economics")
    ai_survival_score: float = Field(description="Score from 0.0 to 1.0 indicating survivability against AI disruption")
    ai_force_multiplier_thesis: str = Field(description="Thesis on why this company survives or thrives in an AI-driven world")

class MetricRationales(BaseModel):
    market_scale_rationale: str = Field(description="Rationale for the market scale assessment")
    competition_rationale: str = Field(description="Rationale for the competitive landscape assessment")
    contract_size_rationale: str = Field(description="Rationale for the contract size/ACV assessment")
    stickiness_rationale: str = Field(description="Rationale for the customer stickiness/retention assessment")
    sales_difficulty_rationale: str = Field(description="Rationale for the sales difficulty/friction assessment")
    ai_defensibility_rationale: str = Field(description="Rationale for the AI defensibility/survival score")

class CompanyEnrichment(BaseModel):
    name: str = Field(description="The name of the company")
    url: str = Field(description="The primary URL of the company")
    full_description: str = Field(description="A full, detailed description of the company")
    company_name: str = Field(description="The formal company name")
    pitch_summary: str = Field(description="A concise pitch summary of the company's value proposition")
    primary_sector: str = Field(description="The primary sector the company operates in")
    business_model: str = Field(description="The company's business model (e.g., 'SaaS', 'Hardware')")
    tech_stack: List[str] = Field(description="List of technologies in the company's tech stack")
    tangibility_score: int = Field(description="Score from 1-10 indicating how tangible/physical the product is")
    customer_type: str = Field(description="The primary type of customer (e.g., 'Electric Utilities')")
    investment_thesis_one_liner: str = Field(description="A one-sentence investment thesis")
    dimension_scores: Dict[str, Optional[float]] = Field(description="Dictionary of various dimension scores (0.0 to 1.0)")
    venture_scale_score: float = Field(description="Score from 0.0 to 1.0 indicating venture scale potential")
    stage_estimate: str = Field(description="Estimated funding stage (e.g., 'Series A', 'Seed')")
    rationale: str = Field(description="Overall rationale for the company's positioning and potential")
    taxonomy: Taxonomy = Field(description="Taxonomy classification")
    vc_dossier: VCDossier = Field(description="Detailed VC dossier")
    founders: List[Founder] = Field(description="List of founders and their details")
    company_twitter_url: Optional[str] = Field(default=None, description="Company's Twitter URL")
    strategic_analysis: StrategicAnalysis = Field(description="Strategic analysis of the company")
    metric_rationales: MetricRationales = Field(description="Rationales for the various metrics and scores")
