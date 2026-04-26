"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { CompanyDossier } from "@/components/company-dossier";
import {
  buildDossierViewModelFromArtifact,
  buildDossierViewModelFromGraphNode,
  EnrichmentArtifact,
  EnrichmentArtifactsResponse,
  findMatchingArtifact,
} from "@/lib/enrichment";
import {
  DocumentViewData,
  ExplorerNodeResponse,
  getRelationshipEndpointId,
  PipelineEntity,
  PipelineRelationship,
} from "@/lib/pipeline-types";
import { ArrowLeft, BrainCircuit, ExternalLink, Building2, FileText, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";

export default function NodeExplorerPage() {
  const params = useParams();
  const router = useRouter();
  const pipelineId = params.id as string;
  const nodeId = params.nodeId as string;
  const { getToken } = useAuth();

  const [centralNode, setCentralNode] = useState<PipelineEntity | null>(null);
  const [relationships, setRelationships] = useState<PipelineRelationship[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [artifacts, setArtifacts] = useState<EnrichmentArtifact[]>([]);

  // Document Viewer state
  const [selectedDocument, setSelectedDocument] = useState<string | null>(null);
  const [documentData, setDocumentData] = useState<DocumentViewData | null>(null);
  const [isDocumentLoading, setIsDocumentLoading] = useState(false);

  useEffect(() => {
    const abortController = new AbortController();

    const fetchNodeData = async () => {
      setIsLoading(true);
      try {
        const token = await getToken();
        const headers: Record<string, string> = {};
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        const res = await fetch(`http://localhost:8000/api/v1/pipelines/${pipelineId}/nodes/${nodeId}/explore`, { 
          headers,
          signal: abortController.signal
        });
        if (!res.ok) throw new Error("Failed to fetch node data");
        
        const data = (await res.json()) as ExplorerNodeResponse;
        setCentralNode(data.central_node);
        setRelationships(data.relationships);
        setIsLoading(false);
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          console.log('Fetch aborted');
          return;
        }
        console.error(error);
        setIsLoading(false);
      }
    };

    fetchNodeData();

    return () => abortController.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId, nodeId]);

  useEffect(() => {
    const abortController = new AbortController();

    const fetchArtifacts = async () => {
      try {
        const token = await getToken();
        const headers: Record<string, string> = {};

        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        const res = await fetch(
          `http://localhost:8000/api/v1/pipelines/${pipelineId}/enrichment-artifacts`,
          {
            headers,
            signal: abortController.signal,
          }
        );

        if (!res.ok) {
          return;
        }

        const data = (await res.json()) as EnrichmentArtifactsResponse;
        setArtifacts(Array.isArray(data.items) ? data.items : []);
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }

        console.error(error);
      }
    };

    void fetchArtifacts();

    return () => abortController.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

  const fetchDocument = async (sourceUrl: string) => {
    setIsDocumentLoading(true);
    setSelectedDocument(sourceUrl);
    setDocumentData(null);
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const res = await fetch(`http://localhost:8000/api/v1/pipelines/${pipelineId}/documents/view?source_url=${encodeURIComponent(sourceUrl)}`, { headers });
      if (!res.ok) throw new Error("Failed to fetch document");
      
      const data = (await res.json()) as DocumentViewData;
      setDocumentData(data);
    } catch (error) {
      console.error(error);
    } finally {
      setIsDocumentLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col h-screen w-full bg-slate-50 items-center justify-center text-slate-500">
        <BrainCircuit className="w-12 h-12 animate-pulse mb-4 text-indigo-500" />
        <p className="text-lg font-medium">Loading Entity Data...</p>
      </div>
    );
  }

  if (!centralNode) {
    return (
      <div className="flex flex-col h-screen w-full bg-slate-50 items-center justify-center text-red-500">
        <p>Entity not found.</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push(`/pipeline/${pipelineId}/graph`)}>
          Back to Graph
        </Button>
      </div>
    );
  }

  const props = (centralNode.props || {}) as Record<string, unknown>;
  const isEnrichedCompany = props.business_model || props.stage_estimate;
  const communityName =
    (typeof props.community_name === "string" && props.community_name) ||
    (props.community_id ? `Community ${String(props.community_id)}` : null);
  const communitySummary =
    typeof props.community_summary === "string" ? props.community_summary : null;
  const matchedArtifact = findMatchingArtifact(artifacts, [
    typeof props.company_name === "string" ? props.company_name : null,
    centralNode.name,
  ]);
  const activeDossier = matchedArtifact
    ? buildDossierViewModelFromArtifact(matchedArtifact, {
        companyType: centralNode.type,
        fallbackName: centralNode.name,
        fallbackDescription: centralNode.description,
      })
    : isEnrichedCompany
      ? buildDossierViewModelFromGraphNode(centralNode)
      : null;
  const stageLabel = activeDossier?.stageEstimate || null;
  const websiteUrl = activeDossier?.websiteUrl || (typeof props.url === "string" ? props.url : null);
  const showCompanyDossier = Boolean(activeDossier);

  return (
    <div className="flex flex-col h-screen w-full bg-slate-50 text-slate-900 overflow-hidden">
      <header className="flex items-center justify-between p-4 bg-white border-b border-slate-200 shrink-0 shadow-sm z-10">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push(`/pipeline/${pipelineId}/graph`)} className="mr-2 text-slate-500 hover:text-slate-700">
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Graph
          </Button>
          <Building2 className="w-6 h-6 text-indigo-600" />
          <h1 className="text-xl font-bold truncate max-w-xl">{activeDossier?.companyName || centralNode.name}</h1>
          <span className="inline-block bg-indigo-100 text-indigo-800 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider border border-indigo-200">
            {centralNode.type}
          </span>
          {stageLabel && (
            <span className="inline-block bg-emerald-100 text-emerald-800 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider border border-emerald-200">
              {stageLabel}
            </span>
          )}
        </div>
        {websiteUrl && (
          <a href={websiteUrl} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1 font-medium">
            <ExternalLink className="w-4 h-4" /> Visit Website
          </a>
        )}
      </header>

      <div className="flex-1 overflow-y-auto p-8 relative">
        <div className="max-w-6xl mx-auto">
          
          {showCompanyDossier ? (
            <div className="space-y-6">
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="text-sm font-medium text-slate-900">
                      {matchedArtifact
                        ? "Artifact-backed dossier loaded from durable enrichment evidence."
                        : "Using graph-projected company properties while artifact detail catches up."}
                    </p>
                    <p className="mt-1 text-sm text-slate-500">
                      {matchedArtifact
                        ? `${matchedArtifact.document_count ?? 0} documents and ${matchedArtifact.source_urls?.length ?? 0} evidence URLs contributed to this dossier.`
                        : "This company detail remains usable even when a matching enrichment artifact is not available yet."}
                    </p>
                  </div>
                  {matchedArtifact?.run_status && (
                    <span className="inline-block rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-bold uppercase tracking-wider text-slate-700">
                      {matchedArtifact.run_status}
                    </span>
                  )}
                </div>
              </div>

              <CompanyDossier dossier={activeDossier!} onOpenSource={fetchDocument} />
            </div>
          ) : (
            // --- GENERIC NODE VIEW (Fallback for non-companies) ---
            <div className="max-w-3xl mx-auto">
              <div className="mb-8">
                <h2 className="text-3xl font-bold text-slate-900 mb-2">{centralNode?.name}</h2>
                <span className="inline-block bg-slate-100 text-slate-600 px-3 py-1 rounded-full text-sm font-medium border border-slate-200">
                  {centralNode?.type}
                </span>
              </div>

              {centralNode?.description && (
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-6 mb-6 shadow-sm">
                  <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-2">Original Context</h3>
                  <p className="text-slate-700 italic">&quot;{centralNode.description}&quot;</p>
                </div>
              )}

              {(communityName || communitySummary) && (
                <div className="bg-violet-50 border border-violet-100 rounded-xl p-6 mb-6 shadow-sm">
                  <h3 className="text-sm font-bold text-violet-700 uppercase tracking-wider mb-2">Community</h3>
                  {communityName && <p className="text-lg font-semibold text-violet-950">{communityName}</p>}
                  {communitySummary && <p className="text-sm text-violet-900 mt-2">{communitySummary}</p>}
                </div>
              )}

              <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-6 mb-10 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <BrainCircuit className="w-5 h-5 text-indigo-600" />
                  <h3 className="text-lg font-bold text-indigo-900">AI Insight</h3>
                </div>
                <div className="prose prose-indigo max-w-none text-slate-700">
                  <ReactMarkdown
                    components={{
                      a: ({ ...props }) => {
                        return (
                          <a 
                            {...props} 
                            onClick={(e) => {
                              e.preventDefault();
                              if (props.href) {
                                fetchDocument(props.href);
                              }
                            }}
                            className="text-indigo-600 hover:text-indigo-800 cursor-pointer underline"
                          />
                        );
                      }
                    }}
                  >
                    {centralNode?.investor_insight || "No insight available."}
                  </ReactMarkdown>
                </div>
              </div>

              <h3 className="text-xl font-bold text-slate-900 mb-6 border-b pb-2">Verified Relationships</h3>
              
              <div className="space-y-6">
                {relationships.map((link, idx) => {
                  const isOutgoing = getRelationshipEndpointId(link.source) === nodeId;
                  const otherNodeName = isOutgoing ? link.target_name : link.source_name;
                  
                  return (
                    <div key={idx} className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm hover:shadow-md transition-shadow">
                      <div className="flex items-center gap-3 mb-3">
                        <span className="font-semibold text-slate-900">{centralNode?.name}</span>
                        <span className="text-xs font-mono bg-slate-100 text-slate-500 px-2 py-1 rounded">
                          {isOutgoing ? `-[${link.type}]->` : `<-[${link.type}]-`}
                        </span>
                        <span className="font-semibold text-slate-900">{otherNodeName}</span>
                      </div>
                      
                      {link.quotes && link.quotes.length > 0 ? (
                        <div className="space-y-3 mt-4">
                          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Extracted Evidence</p>
                          {link.quotes.map((quote: string, qIdx: number) => {
                            const sourceUrl = link.source_urls && link.source_urls[qIdx] ? link.source_urls[qIdx] : null;
                            return (
                              <div key={qIdx} className="flex flex-col gap-1">
                                <blockquote className="text-sm text-slate-600 border-l-2 border-indigo-300 pl-3 italic bg-slate-50 py-2 pr-2 rounded-r">
                                  &quot;{quote}&quot;
                                </blockquote>
                                {sourceUrl && (
                                  <button 
                                    onClick={() => fetchDocument(sourceUrl)} 
                                    className="text-xs text-indigo-500 hover:text-indigo-700 flex items-center gap-1 ml-3 bg-transparent border-none p-0 cursor-pointer"
                                  >
                                    <ExternalLink className="w-3 h-3" />
                                    Source Document
                                  </button>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="text-sm text-slate-400 italic mt-2">No direct quotes available for this relationship.</p>
                      )}
                    </div>
                  );
                })}
                
                {relationships.length === 0 && (
                  <p className="text-slate-500 italic">No relationships found for this entity.</p>
                )}
              </div>
            </div>
          )}

        </div>
      </div>

      {/* Document Viewer Panel */}
      {selectedDocument && (
        <div className="absolute top-0 right-0 h-full w-[600px] bg-white shadow-2xl border-l border-slate-200 flex flex-col z-50 transform transition-transform duration-300">
          <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-slate-50">
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-blue-500" />
              <h2 className="text-lg font-bold truncate pr-4" title={documentData?.title || selectedDocument}>
                {documentData?.title || 'Loading Document...'}
              </h2>
            </div>
            <Button variant="ghost" size="icon" onClick={() => setSelectedDocument(null)}>
              <ArrowLeft className="w-4 h-4" />
            </Button>
          </div>
          
          <div className="flex-1 overflow-auto p-4 bg-slate-50">
            {isDocumentLoading ? (
              <div className="flex flex-col items-center justify-center h-full text-slate-400">
                <RefreshCw className="w-8 h-8 animate-spin mb-4" />
                <p>Loading document content...</p>
              </div>
            ) : documentData ? (
              <div className="h-full bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
                {documentData.viewer_url ? (
                  <iframe 
                    src={documentData.viewer_url} 
                    className="w-full h-full border-0"
                    title={documentData.title}
                  />
                ) : (
                  <div className="p-6 prose prose-slate max-w-none">
                    <div className="mb-4 pb-4 border-b border-slate-200">
                      <a href={documentData.source_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline text-sm flex items-center gap-1">
                        <ExternalLink className="w-4 h-4" /> View Original Source
                      </a>
                    </div>
                    <div className="whitespace-pre-wrap font-mono text-sm">
                      {documentData.content}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-red-500">
                Failed to load document content.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}