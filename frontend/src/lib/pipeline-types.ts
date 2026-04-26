export interface PipelineEntity {
  id: string;
  name: string;
  type: string;
  summary?: string | null;
  source_url?: string | null;
  community_key?: string | null;
  community_name?: string | null;
  community_summary?: string | null;
  community_rank?: number | string | null;
  member_count?: number | null;
  relationship_count?: number | null;
  description?: string | null;
  investor_insight?: string | null;
  props?: Record<string, unknown> | null;
  val?: number;
  color?: string;
  x?: number;
  y?: number;
}

export type PipelineRelationshipEndpoint = string | PipelineEntity;

export interface PipelineRelationship {
  source: PipelineRelationshipEndpoint;
  target: PipelineRelationshipEndpoint;
  type: string;
  name?: string;
  weight?: number;
  color?: string;
  source_name?: string;
  target_name?: string;
  quotes?: string[];
  source_urls?: string[];
}

export interface GraphData {
  nodes: PipelineEntity[];
  links: PipelineRelationship[];
}

export interface PipelineEntitiesResponse {
  entities: PipelineEntity[];
  relationships: PipelineRelationship[];
}

export interface DocumentChunk {
  source_url?: string | null;
  source?: string | null;
  text_snippet?: string | null;
}

export interface DocumentsResponse {
  chunks: DocumentChunk[];
  total_chunks: number;
}

export interface QueueItem {
  url: string;
  type: string;
  status: string;
}

export interface PendingDocument {
  id: string;
  url: string;
  estimated_size: number;
}

export interface ExplorerNodeResponse {
  central_node: PipelineEntity;
  relationships: PipelineRelationship[];
}

export interface DocumentViewData {
  title: string;
  source_url: string;
  viewer_url?: string | null;
  content?: string | null;
}

export interface DocumentInsightData {
  central_node?: PipelineEntity | null;
  relationships: PipelineRelationship[];
}

export function getRelationshipEndpointId(endpoint: PipelineRelationshipEndpoint): string {
  return typeof endpoint === "string" ? endpoint : endpoint.id;
}

export function getRelationshipEndpointNode(
  endpoint: PipelineRelationshipEndpoint
): PipelineEntity | null {
  return typeof endpoint === "string" ? null : endpoint;
}
