export type OnboardingStep = 'niche' | 'entities' | 'relationships' | 'sources' | 'review';

export interface Entity {
  name: string;
}

export interface Relationship {
  source: string;
  type: string;
  target: string;
}

export interface DataSource {
  type: 'rss' | 'api' | 'webhook' | 'custom';
  url: string;
  name: string;
}

export interface SchemaConfig {
  entities: string[];
  relationships: Relationship[];
}

export interface PipelineConfig {
  currentStep: OnboardingStep;
  niche: string | null;
  schema: SchemaConfig | null;
  sources: DataSource[];
}
