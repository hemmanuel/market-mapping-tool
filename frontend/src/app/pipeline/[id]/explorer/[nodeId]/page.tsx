"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { ArrowLeft, BrainCircuit, ExternalLink, Building2, MapPin, Calendar, Users, DollarSign, Target, ShieldAlert, Zap, BarChart3, Link as LinkIcon, FileText, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";

export default function NodeExplorerPage() {
  const params = useParams();
  const router = useRouter();
  const pipelineId = params.id as string;
  const nodeId = params.nodeId as string;
  const { getToken } = useAuth();

  const [centralNode, setCentralNode] = useState<any>(null);
  const [relationships, setRelationships] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Document Viewer state
  const [selectedDocument, setSelectedDocument] = useState<string | null>(null);
  const [documentData, setDocumentData] = useState<any>(null);
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
        
        const data = await res.json();
        setCentralNode(data.central_node);
        setRelationships(data.relationships);
        setIsLoading(false);
      } catch (error: any) {
        if (error.name === 'AbortError') {
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
      
      const data = await res.json();
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

  const props = centralNode.props || {};
  const isEnrichedCompany = props.business_model || props.stage_estimate;

  // Parse JSON strings safely
  let founders = [];
  let dimensionScores = {};
  try {
    if (props.founders_json) founders = JSON.parse(props.founders_json);
    if (props.dimension_scores_json) dimensionScores = JSON.parse(props.dimension_scores_json);
  } catch (e) {
    console.error("Failed to parse JSON props", e);
  }

  const renderScoreBar = (label: string, score: number) => {
    const percentage = Math.round((score || 0) * 100);
    let colorClass = "bg-indigo-500";
    if (percentage < 40) colorClass = "bg-red-500";
    else if (percentage < 70) colorClass = "bg-yellow-500";
    else if (percentage >= 90) colorClass = "bg-emerald-500";

    return (
      <div key={label} className="mb-3">
        <div className="flex justify-between text-xs font-medium mb-1">
          <span className="text-slate-700">{label.replace(/_/g, ' ')}</span>
          <span className="text-slate-900">{percentage}%</span>
        </div>
        <div className="w-full bg-slate-200 rounded-full h-2">
          <div className={`${colorClass} h-2 rounded-full`} style={{ width: `${percentage}%` }}></div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-screen w-full bg-slate-50 text-slate-900 overflow-hidden">
      <header className="flex items-center justify-between p-4 bg-white border-b border-slate-200 shrink-0 shadow-sm z-10">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push(`/pipeline/${pipelineId}/graph`)} className="mr-2 text-slate-500 hover:text-slate-700">
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Graph
          </Button>
          <Building2 className="w-6 h-6 text-indigo-600" />
          <h1 className="text-xl font-bold truncate max-w-xl">{centralNode.name}</h1>
          <span className="inline-block bg-indigo-100 text-indigo-800 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider border border-indigo-200">
            {centralNode.type}
          </span>
          {props.stage_estimate && (
            <span className="inline-block bg-emerald-100 text-emerald-800 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider border border-emerald-200">
              {props.stage_estimate}
            </span>
          )}
        </div>
        {props.url && (
          <a href={props.url} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1 font-medium">
            <ExternalLink className="w-4 h-4" /> Visit Website
          </a>
        )}
      </header>

      <div className="flex-1 overflow-y-auto p-8 relative">
        <div className="max-w-6xl mx-auto">
          
          {isEnrichedCompany ? (
            // --- ENRICHED VC DOSSIER VIEW ---
            <div className="space-y-8">
              
              {/* Top Row: Executive Summary & Fast Facts */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                {/* Executive Summary */}
                <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                  <h2 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                    <Target className="w-5 h-5 text-indigo-500" /> Executive Summary
                  </h2>
                  {props.investment_thesis_one_liner && (
                    <div className="bg-indigo-50 border-l-4 border-indigo-500 p-4 mb-4 rounded-r-lg">
                      <p className="text-indigo-900 font-medium italic">"{props.investment_thesis_one_liner}"</p>
                    </div>
                  )}
                  <div className="mb-4">
                    <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Pitch Summary</h3>
                    <p className="text-slate-700">{props.pitch_summary || "N/A"}</p>
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Full Description</h3>
                    <p className="text-slate-700 text-sm leading-relaxed">{props.full_description || centralNode.description || "N/A"}</p>
                  </div>
                </div>

                {/* Fast Facts */}
                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                  <h2 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                    <Zap className="w-5 h-5 text-amber-500" /> Fast Facts
                  </h2>
                  <ul className="space-y-4">
                    <li className="flex items-start gap-3">
                      <DollarSign className="w-5 h-5 text-emerald-500 mt-0.5" />
                      <div>
                        <p className="text-xs font-bold text-slate-400 uppercase">Total Raised</p>
                        <p className="text-slate-900 font-medium">{props.vc_dossier_total_raised || "Undisclosed"}</p>
                        {props.vc_dossier_latest_round && <p className="text-xs text-slate-500">Latest: {props.vc_dossier_latest_round}</p>}
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <MapPin className="w-5 h-5 text-blue-500 mt-0.5" />
                      <div>
                        <p className="text-xs font-bold text-slate-400 uppercase">HQ Location</p>
                        <p className="text-slate-900 font-medium">{props.vc_dossier_hq_location || "Unknown"}</p>
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <Calendar className="w-5 h-5 text-purple-500 mt-0.5" />
                      <div>
                        <p className="text-xs font-bold text-slate-400 uppercase">Founded</p>
                        <p className="text-slate-900 font-medium">{props.vc_dossier_year_founded || "Unknown"}</p>
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <Users className="w-5 h-5 text-orange-500 mt-0.5" />
                      <div>
                        <p className="text-xs font-bold text-slate-400 uppercase">Headcount Est.</p>
                        <p className="text-slate-900 font-medium">{props.vc_dossier_headcount_estimate || "Unknown"}</p>
                      </div>
                    </li>
                  </ul>
                </div>
              </div>

              {/* Middle Row: Strategic Analysis & Dimension Scores */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                
                {/* Strategic Analysis */}
                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                  <h2 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                    <BrainCircuit className="w-5 h-5 text-pink-500" /> Strategic Analysis
                  </h2>
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Market Narrative</h3>
                      <p className="text-slate-700 text-sm">{props.strategic_market_narrative || "N/A"}</p>
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Moat Description</h3>
                      <p className="text-slate-700 text-sm">{props.vc_dossier_moat_description || "N/A"}</p>
                    </div>
                    {props.strategic_ai_force_multiplier_thesis && (
                      <div className="bg-pink-50 border border-pink-100 p-3 rounded-lg">
                        <h3 className="text-xs font-bold text-pink-600 uppercase tracking-wider mb-1">AI Force Multiplier</h3>
                        <p className="text-pink-900 text-sm">{props.strategic_ai_force_multiplier_thesis}</p>
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-4 mt-4">
                      <div className="bg-slate-50 p-3 rounded-lg border border-slate-100">
                        <p className="text-xs font-bold text-slate-400 uppercase">Competitive Noise</p>
                        <p className="text-slate-900 font-medium">{props.strategic_competitive_noise_level || "N/A"}</p>
                      </div>
                      <div className="bg-slate-50 p-3 rounded-lg border border-slate-100">
                        <p className="text-xs font-bold text-slate-400 uppercase">AI Survival Score</p>
                        <p className="text-slate-900 font-medium">{props.strategic_ai_survival_score}/1.0</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Dimension Scores */}
                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                  <h2 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-sky-500" /> Dimension Scores
                  </h2>
                  <div className="mb-6">
                    {Object.entries(dimensionScores).length > 0 ? (
                      Object.entries(dimensionScores).map(([key, val]) => renderScoreBar(key, val as number))
                    ) : (
                      <p className="text-sm text-slate-500 italic">No dimension scores available.</p>
                    )}
                  </div>
                  
                  <div className="pt-4 border-t border-slate-100">
                    <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Unit Economics Proxy</h3>
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div className="bg-slate-50 p-2 rounded border border-slate-100">
                        <p className="text-[10px] font-bold text-slate-400 uppercase">ACV Proxy</p>
                        <p className="text-sm font-medium text-slate-800">{props.unit_econ_acv_proxy || "N/A"}</p>
                      </div>
                      <div className="bg-slate-50 p-2 rounded border border-slate-100">
                        <p className="text-[10px] font-bold text-slate-400 uppercase">Retention</p>
                        <p className="text-sm font-medium text-slate-800">{props.unit_econ_retention_quality || "N/A"}</p>
                      </div>
                      <div className="bg-slate-50 p-2 rounded border border-slate-100">
                        <p className="text-[10px] font-bold text-slate-400 uppercase">Friction</p>
                        <p className="text-sm font-medium text-slate-800">{props.unit_econ_distribution_friction || "N/A"}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Bottom Row: Founders & Business Details */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                {/* Founders */}
                <div className="lg:col-span-1 bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                  <h2 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                    <Users className="w-5 h-5 text-teal-500" /> Founders & Team
                  </h2>
                  {founders.length > 0 ? (
                    <div className="space-y-4">
                      {founders.map((f: any, idx: number) => (
                        <div key={idx} className="flex flex-col border-b border-slate-100 pb-3 last:border-0 last:pb-0">
                          <span className="font-bold text-slate-800">{f.name}</span>
                          <span className="text-sm text-slate-500">{f.title || "Founder"}</span>
                          {f.linkedin_url && (
                            <a href={f.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:underline mt-1 flex items-center gap-1">
                              <LinkIcon className="w-3 h-3" /> LinkedIn Profile
                            </a>
                          )}
                          {f.background_summary && (
                            <p className="text-xs text-slate-600 mt-2 italic">"{f.background_summary}"</p>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500 italic">No founder information available.</p>
                  )}
                </div>

                {/* Business Details & Metric Rationales */}
                <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                  <h2 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                    <Building2 className="w-5 h-5 text-slate-500" /> Business Details
                  </h2>
                  <div className="grid grid-cols-2 gap-4 mb-6">
                    <div>
                      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Primary Sector</h3>
                      <p className="text-slate-800 font-medium">{props.primary_sector || "N/A"}</p>
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Business Model</h3>
                      <p className="text-slate-800 font-medium">{props.business_model || "N/A"}</p>
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Customer Type</h3>
                      <p className="text-slate-800 font-medium">{props.customer_type || "N/A"}</p>
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Tech Stack / Keywords</h3>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {props.tech_stack && Array.isArray(props.tech_stack) ? props.tech_stack.map((t: string) => (
                          <span key={t} className="bg-slate-100 text-slate-600 text-[10px] px-2 py-0.5 rounded border border-slate-200">{t}</span>
                        )) : <span className="text-sm text-slate-500">N/A</span>}
                      </div>
                    </div>
                  </div>

                  <div className="border-t border-slate-100 pt-4">
                    <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Key Stakeholders</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs font-bold text-slate-500 mb-1">Key Investors</p>
                        <p className="text-sm text-slate-700">{props.vc_dossier_key_investors || "None listed"}</p>
                      </div>
                      <div>
                        <p className="text-xs font-bold text-slate-500 mb-1">Key Customers</p>
                        <p className="text-sm text-slate-700">{props.vc_dossier_key_customers || "None listed"}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

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
                  <p className="text-slate-700 italic">"{centralNode.description}"</p>
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
                      a: ({ node, ...props }) => {
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
                {relationships.map((link: any, idx: number) => {
                  const isOutgoing = link.source === nodeId;
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
                                  "{quote}"
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