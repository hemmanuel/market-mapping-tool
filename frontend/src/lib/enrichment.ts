type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function asString(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return null;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function dedupeStrings(values: Array<string | null | undefined>): string[] {
  return Array.from(
    new Set(
      values
        .map((value) => (typeof value === "string" ? value.trim() : ""))
        .filter((value) => value.length > 0)
    )
  );
}

function asStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return dedupeStrings(value.map((entry) => asString(entry)));
  }

  if (typeof value === "string" && value.trim()) {
    return [value.trim()];
  }

  return [];
}

function parseMaybeJson<T>(value: unknown): T | null {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }

  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

function normalizeNumberRecord(value: unknown): Record<string, number> {
  const record = asRecord(value);
  const entries = Object.entries(record)
    .map(([key, entry]) => [key, asNumber(entry)] as const)
    .filter((entry): entry is readonly [string, number] => entry[1] !== null);

  return Object.fromEntries(entries);
}

function firstNonEmpty(...values: Array<unknown>): string | null {
  for (const value of values) {
    const normalized = asString(value);
    if (normalized) {
      return normalized;
    }
  }

  return null;
}

export interface CompanyEnrichmentFounder {
  name?: string | null;
  role?: string | null;
  title?: string | null;
  bio?: string | null;
  background_summary?: string | null;
  hometown?: string | null;
  linkedin_url?: string | null;
  twitter_url?: string | null;
  previous_companies?: string[];
  education?: string[];
  is_technical?: boolean | null;
  tags?: string[];
}

export interface CompanyEnrichmentVCDossier {
  total_raised?: string | null;
  latest_round?: string | null;
  key_investors?: string | null;
  key_customers?: string | null;
  moat_description?: string | null;
  hq_location?: string | null;
  year_founded?: string | null;
  headcount_estimate?: string | null;
  source_urls?: string[];
}

export interface CompanyEnrichmentUnitEconomics {
  acv_proxy?: string | null;
  retention_quality?: string | null;
  distribution_friction?: string | null;
}

export interface CompanyEnrichmentStrategicAnalysis {
  market_narrative?: string | null;
  competitive_noise_level?: string | null;
  ai_survival_score?: number | null;
  ai_force_multiplier_thesis?: string | null;
  unit_economics_inference?: CompanyEnrichmentUnitEconomics | null;
}

export interface CompanyEnrichmentProfile {
  company_name?: string | null;
  name?: string | null;
  url?: string | null;
  company_twitter_url?: string | null;
  pitch_summary?: string | null;
  full_description?: string | null;
  primary_sector?: string | null;
  business_model?: string | null;
  customer_type?: string | null;
  tech_stack?: string[];
  investment_thesis_one_liner?: string | null;
  stage_estimate?: string | null;
  venture_scale_score?: number | null;
  rationale?: string | null;
  dimension_scores?: Record<string, number>;
  founders?: CompanyEnrichmentFounder[];
  vc_dossier?: CompanyEnrichmentVCDossier | null;
  strategic_analysis?: CompanyEnrichmentStrategicAnalysis | null;
}

export interface EnrichmentArtifact {
  company_name: string;
  stage_estimate?: string | null;
  venture_scale_score?: number | null;
  primary_sector?: string | null;
  founder_count?: number | null;
  document_count?: number | null;
  source_document_ids?: string[];
  source_urls?: string[];
  run_id?: string | null;
  run_status?: string | null;
  created_at?: string | null;
  company_profile: CompanyEnrichmentProfile;
}

export interface EnrichmentArtifactsResponse {
  items: EnrichmentArtifact[];
}

export interface NormalizedEnrichmentFounder {
  name?: string | null;
  role?: string | null;
  bio?: string | null;
  linkedin_url?: string | null;
  twitter_url?: string | null;
  previous_companies?: string[];
}

export interface NormalizedEnrichment {
  id: string;
  company_name: string;
  stage_estimate?: string | null;
  venture_scale_score?: number | null;
  primary_sector?: string | null;
  business_model?: string | null;
  customer_type?: string | null;
  founder_count?: number | null;
  document_count?: number | null;
  source_urls?: string[];
  source_document_ids?: string[];
  run_id?: string | null;
  founders?: NormalizedEnrichmentFounder[];
}

export interface NormalizedEnrichmentsResponse {
  normalized_available: boolean;
  items: NormalizedEnrichment[];
}

export interface CompanyDossierFounderView {
  name: string;
  role: string | null;
  bio: string | null;
  hometown: string | null;
  linkedinUrl: string | null;
  twitterUrl: string | null;
  previousCompanies: string[];
  education: string[];
  isTechnical: boolean;
  tags: string[];
}

export interface CompanyDossierViewModel {
  companyName: string;
  companyType: string;
  websiteUrl: string | null;
  twitterUrl: string | null;
  stageEstimate: string | null;
  investmentThesis: string | null;
  pitchSummary: string | null;
  fullDescription: string | null;
  totalRaised: string | null;
  latestRound: string | null;
  hqLocation: string | null;
  yearFounded: string | null;
  headcountEstimate: string | null;
  marketNarrative: string | null;
  moatDescription: string | null;
  aiForceMultiplierThesis: string | null;
  competitiveNoiseLevel: string | null;
  aiSurvivalScore: number | null;
  acvProxy: string | null;
  retentionQuality: string | null;
  distributionFriction: string | null;
  primarySector: string | null;
  businessModel: string | null;
  customerType: string | null;
  techStack: string[];
  keyInvestors: string | null;
  keyCustomers: string | null;
  ventureScaleScore: number | null;
  rationale: string | null;
  dimensionScores: Record<string, number>;
  founders: CompanyDossierFounderView[];
  communityName: string | null;
  communitySummary: string | null;
  sourceUrls: string[];
  sourceDocumentIds: string[];
  documentCount: number | null;
  founderCount: number;
}

interface DossierOptions {
  companyType?: string | null;
  fallbackName?: string | null;
  fallbackDescription?: string | null;
  communityName?: string | null;
  communitySummary?: string | null;
  sourceUrls?: string[];
  sourceDocumentIds?: string[];
  documentCount?: number | null;
  founderCount?: number | null;
}

function normalizeFounder(founder: CompanyEnrichmentFounder | NormalizedEnrichmentFounder | JsonRecord): CompanyDossierFounderView | null {
  const record = asRecord(founder);
  const name = firstNonEmpty(record.name);

  if (!name) {
    return null;
  }

  return {
    name,
    role: firstNonEmpty(record.role, record.title),
    bio: firstNonEmpty(record.bio, record.background_summary),
    hometown: firstNonEmpty(record.hometown),
    linkedinUrl: firstNonEmpty(record.linkedin_url),
    twitterUrl: firstNonEmpty(record.twitter_url),
    previousCompanies: asStringArray(record.previous_companies),
    education: asStringArray(record.education),
    isTechnical: Boolean(record.is_technical),
    tags: asStringArray(record.tags),
  };
}

function normalizeFounders(value: unknown): CompanyDossierFounderView[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((founder) => normalizeFounder(asRecord(founder)))
    .filter((founder): founder is CompanyDossierFounderView => founder !== null);
}

export function normalizeCompanyName(value: string | null | undefined): string {
  return (value ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function inferCompanyTypeFromStage(stageEstimate: string | null | undefined): string {
  const normalized = normalizeCompanyName(stageEstimate);

  if (normalized.includes("incumbent")) {
    return "Incumbent";
  }

  if (normalized.includes("public")) {
    return "Public Company";
  }

  if (normalized.includes("startup") || normalized.includes("seed") || normalized.includes("series")) {
    return "Startup";
  }

  return "Company";
}

function buildDossierViewModel(
  profile: CompanyEnrichmentProfile | JsonRecord,
  options: DossierOptions = {}
): CompanyDossierViewModel {
  const normalizedProfile = asRecord(profile);
  const vcDossier = asRecord(normalizedProfile.vc_dossier);
  const strategicAnalysis = asRecord(normalizedProfile.strategic_analysis);
  const unitEconomics = asRecord(strategicAnalysis.unit_economics_inference);
  const founders = normalizeFounders(normalizedProfile.founders);
  const dimensionScores = normalizeNumberRecord(normalizedProfile.dimension_scores);

  return {
    companyName:
      firstNonEmpty(normalizedProfile.company_name, normalizedProfile.name, options.fallbackName) ?? "Unknown Company",
    companyType:
      firstNonEmpty(options.companyType) ??
      inferCompanyTypeFromStage(firstNonEmpty(normalizedProfile.stage_estimate)) ??
      "Company",
    websiteUrl: firstNonEmpty(normalizedProfile.url),
    twitterUrl: firstNonEmpty(normalizedProfile.company_twitter_url),
    stageEstimate: firstNonEmpty(normalizedProfile.stage_estimate),
    investmentThesis: firstNonEmpty(normalizedProfile.investment_thesis_one_liner),
    pitchSummary: firstNonEmpty(normalizedProfile.pitch_summary),
    fullDescription: firstNonEmpty(normalizedProfile.full_description, options.fallbackDescription),
    totalRaised: firstNonEmpty(vcDossier.total_raised),
    latestRound: firstNonEmpty(vcDossier.latest_round),
    hqLocation: firstNonEmpty(vcDossier.hq_location),
    yearFounded: firstNonEmpty(vcDossier.year_founded),
    headcountEstimate: firstNonEmpty(vcDossier.headcount_estimate),
    marketNarrative: firstNonEmpty(strategicAnalysis.market_narrative),
    moatDescription: firstNonEmpty(vcDossier.moat_description),
    aiForceMultiplierThesis: firstNonEmpty(strategicAnalysis.ai_force_multiplier_thesis),
    competitiveNoiseLevel: firstNonEmpty(strategicAnalysis.competitive_noise_level),
    aiSurvivalScore: asNumber(strategicAnalysis.ai_survival_score),
    acvProxy: firstNonEmpty(unitEconomics.acv_proxy),
    retentionQuality: firstNonEmpty(unitEconomics.retention_quality),
    distributionFriction: firstNonEmpty(unitEconomics.distribution_friction),
    primarySector: firstNonEmpty(normalizedProfile.primary_sector),
    businessModel: firstNonEmpty(normalizedProfile.business_model),
    customerType: firstNonEmpty(normalizedProfile.customer_type),
    techStack: asStringArray(normalizedProfile.tech_stack),
    keyInvestors: firstNonEmpty(vcDossier.key_investors),
    keyCustomers: firstNonEmpty(vcDossier.key_customers),
    ventureScaleScore: asNumber(normalizedProfile.venture_scale_score),
    rationale: firstNonEmpty(normalizedProfile.rationale),
    dimensionScores,
    founders,
    communityName: firstNonEmpty(options.communityName),
    communitySummary: firstNonEmpty(options.communitySummary),
    sourceUrls: dedupeStrings([
      ...asStringArray(options.sourceUrls),
      ...asStringArray(vcDossier.source_urls),
    ]),
    sourceDocumentIds: dedupeStrings(asStringArray(options.sourceDocumentIds)),
    documentCount: options.documentCount ?? null,
    founderCount: options.founderCount ?? founders.length,
  };
}

export function buildDossierViewModelFromArtifact(
  artifact: EnrichmentArtifact,
  options: DossierOptions = {}
): CompanyDossierViewModel {
  return buildDossierViewModel(artifact.company_profile, {
    ...options,
    fallbackName: options.fallbackName ?? artifact.company_name,
    companyType: options.companyType ?? inferCompanyTypeFromStage(artifact.stage_estimate),
    sourceUrls: artifact.source_urls ?? options.sourceUrls,
    sourceDocumentIds: artifact.source_document_ids ?? options.sourceDocumentIds,
    documentCount: artifact.document_count ?? options.documentCount ?? null,
    founderCount: artifact.founder_count ?? options.founderCount ?? null,
  });
}

export function buildDossierViewModelFromGraphNode(node: {
  name?: string | null;
  type?: string | null;
  description?: string | null;
  props?: Record<string, unknown> | null;
}): CompanyDossierViewModel {
  const props = asRecord(node.props);
  const parsedFounders = parseMaybeJson<unknown[]>(props.founders_json) ?? props.founders;
  const parsedDimensionScores =
    parseMaybeJson<JsonRecord>(props.dimension_scores_json) ?? props.dimension_scores;
  const parsedSourceUrls = parseMaybeJson<unknown[]>(props.source_urls_json) ?? props.source_urls;
  const parsedSourceDocumentIds =
    parseMaybeJson<unknown[]>(props.source_document_ids_json) ?? props.source_document_ids;
  const graphProfile = {
    ...props,
    founders: parsedFounders,
    dimension_scores: parsedDimensionScores,
  };

  return buildDossierViewModel(graphProfile, {
    fallbackName: node.name,
    fallbackDescription: node.description,
    companyType: firstNonEmpty(node.type, inferCompanyTypeFromStage(firstNonEmpty(props.stage_estimate))),
    communityName:
      firstNonEmpty(props.community_name) ??
      (props.community_id ? `Community ${String(props.community_id)}` : null),
    communitySummary: firstNonEmpty(props.community_summary),
    sourceUrls: asStringArray(parsedSourceUrls),
    sourceDocumentIds: asStringArray(parsedSourceDocumentIds),
    documentCount: asNumber(props.document_count),
    founderCount: asNumber(props.founder_count),
  });
}

export function findMatchingArtifact(
  artifacts: EnrichmentArtifact[],
  candidateNames: Array<string | null | undefined>
): EnrichmentArtifact | null {
  const normalizedCandidates = candidateNames
    .map((value) => normalizeCompanyName(value))
    .filter((value) => value.length > 0);

  if (normalizedCandidates.length === 0) {
    return null;
  }

  for (const artifact of artifacts) {
    const artifactNames = [
      artifact.company_name,
      artifact.company_profile.company_name,
      artifact.company_profile.name,
    ]
      .map((value) => normalizeCompanyName(value))
      .filter((value) => value.length > 0);

    if (artifactNames.some((value) => normalizedCandidates.includes(value))) {
      return artifact;
    }
  }

  return null;
}

export function isCompanyLikeNode(type: string | null | undefined): boolean {
  const normalized = normalizeCompanyName(type);
  return ["company", "startup", "incumbent", "public company", "utility", "investor"].includes(
    normalized
  );
}

export function hasSparseEvidence(dossier: Pick<CompanyDossierViewModel, "documentCount" | "sourceUrls">): boolean {
  const documentCount = dossier.documentCount ?? 0;
  return documentCount < 2 || dossier.sourceUrls.length < 2;
}
