"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { backendApiPath } from "@/lib/backend-api";
import {
  DocumentInsightData,
  DocumentViewData,
  getRelationshipEndpointId,
  getRelationshipEndpointNode,
  GraphData,
  PipelineEntitiesResponse,
  PipelineEntity,
  PipelineRelationship,
} from "@/lib/pipeline-types";
import { ArrowLeft, Building2, Database, RefreshCw, FileText, Users } from "lucide-react";
import ReactMarkdown from "react-markdown";

// Dynamically import ForceGraph2D to avoid SSR issues
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

const GRAPH_THEMES = ["full", "investors", "companies", "communities", "regulatory", "documents"] as const;

export default function GraphViewerPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const pipelineId = params.id as string;
  const { getToken } = useAuth();
  const requestedTheme = searchParams.get("theme");
  const initialTheme =
    requestedTheme && GRAPH_THEMES.includes(requestedTheme as (typeof GRAPH_THEMES)[number])
      ? requestedTheme
      : "full";

  const [theme, setTheme] = useState(initialTheme);
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [isLoading, setIsLoading] = useState(true);
  const [windowSize, setWindowSize] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Hover state
  const [hoverNode, setHoverNode] = useState<PipelineEntity | null>(null);
  const [highlightNodes, setHighlightNodes] = useState<Set<PipelineEntity>>(new Set());
  const [highlightLinks, setHighlightLinks] = useState<Set<PipelineRelationship>>(new Set());

  // Document Viewer state
  const [selectedDocument, setSelectedDocument] = useState<string | null>(null);
  const [documentData, setDocumentData] = useState<DocumentViewData | null>(null);
  const [isDocumentLoading, setIsDocumentLoading] = useState(false);

  // Document Insight state
  const [selectedDocumentNode, setSelectedDocumentNode] = useState<PipelineEntity | null>(null);
  const [documentInsightData, setDocumentInsightData] = useState<DocumentInsightData | null>(null);
  const [isInsightLoading, setIsInsightLoading] = useState(false);
  const [selectedCommunityNode, setSelectedCommunityNode] = useState<PipelineEntity | null>(null);

  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current) {
        setWindowSize({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };

    window.addEventListener("resize", handleResize);
    handleResize();

    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const fetchGraphData = async () => {
    setIsLoading(true);
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const res = await fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/entities?theme=${theme}`), { headers });
      if (!res.ok) throw new Error("Failed to fetch graph data");
      
      const data = (await res.json()) as PipelineEntitiesResponse;
      
      // Transform data for react-force-graph
      const nodes: PipelineEntity[] = data.entities.map((e) => {
        let color = '#a855f7'; // Purple for default entities
        if (e.type === 'Community') color = '#7c3aed'; // Violet
        else if (e.type === 'Startup' || e.type === 'Company') color = '#f97316'; // Orange
        else if (e.type === 'Incumbent') color = '#64748b'; // Slate
        else if (e.type === 'Utility') color = '#0ea5e9'; // Cyan
        else if (e.type === 'Investor') color = '#10b981'; // Emerald
        else if (e.type === 'ServiceProvider') color = '#ec4899'; // Pink
        else if (e.type === 'Asset') color = '#22c55e'; // Green
        else if (e.type === 'Person') color = '#f59e0b'; // Amber
        else if (e.type === 'RegulatoryBody') color = '#eab308'; // Yellow
        else if (e.type === 'Document') color = '#3b82f6'; // Blue
        else if (e.type && /(regul|law|gov|polic|act|bill)/i.test(e.type)) color = '#eab308'; // Yellow for regulatory (contrasting)

        let val = 2; // Default size
        if (theme === 'communities') {
          val = e.type === 'Community' ? 8 : 2.2;
        } else if (theme === 'investors') {
          val = e.type === 'Investor' ? 5 : 2.2;
        } else if (theme === 'documents') {
          val = e.type === 'Document' ? 5 : 1.5; // Documents are huge, bridges are small
        } else {
          val = e.type === 'Document' ? 1.5 : 2; // Default sizing for other themes
        }

        return {
          id: e.id,
          name: e.name,
          type: e.type,
          val,
          color,
          summary: e.summary,
          source_url: e.source_url,
          community_key: e.community_key,
          community_name: e.community_name,
          community_summary: e.community_summary,
          community_rank: e.community_rank,
          member_count: e.member_count,
          relationship_count: e.relationship_count,
        };
      });

      const links: PipelineRelationship[] = data.relationships.map((r) => ({
        source: r.source,
        target: r.target,
        type: r.type,
        name: r.type,
        weight: r.weight,
        source_urls: r.source_urls,
        color: 'rgba(203, 213, 225, 0.4)' // Slate 300 with opacity
      }));

      setGraphData({ nodes, links });
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchGraphData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId, theme]);

  useEffect(() => {
    const nextTheme = searchParams.get("theme");
    if (
      nextTheme &&
      GRAPH_THEMES.includes(nextTheme as (typeof GRAPH_THEMES)[number]) &&
      nextTheme !== theme
    ) {
      setTheme(nextTheme);
    }
  }, [searchParams, theme]);

  useEffect(() => {
    setSelectedCommunityNode(null);
  }, [pipelineId, theme]);

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

      const res = await fetch(
        backendApiPath(`/api/v1/pipelines/${pipelineId}/documents/view?source_url=${encodeURIComponent(sourceUrl)}`),
        { headers }
      );
      if (!res.ok) throw new Error("Failed to fetch document");
      
      const data = (await res.json()) as DocumentViewData;
      setDocumentData(data);
    } catch (error) {
      console.error(error);
    } finally {
      setIsDocumentLoading(false);
    }
  };

  const fetchDocumentInsight = async (nodeId: string) => {
    setIsInsightLoading(true);
    setDocumentInsightData(null);
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const res = await fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/documents/${nodeId}/explore`), { headers });
      if (!res.ok) throw new Error("Failed to fetch document insight");
      
      const data = (await res.json()) as DocumentInsightData;
      setDocumentInsightData(data);
    } catch (error) {
      console.error(error);
    } finally {
      setIsInsightLoading(false);
    }
  };

  const handleNodeHover = (node: PipelineEntity | null) => {
    setHighlightNodes(new Set());
    setHighlightLinks(new Set());

    if (node) {
      const newHighlightNodes = new Set<PipelineEntity>([node]);
      const newHighlightLinks = new Set<PipelineRelationship>();

      graphData.links.forEach((link) => {
        if (
          getRelationshipEndpointId(link.source) === node.id ||
          getRelationshipEndpointId(link.target) === node.id
        ) {
          newHighlightLinks.add(link);
          const sourceNode = getRelationshipEndpointNode(link.source);
          const targetNode = getRelationshipEndpointNode(link.target);
          if (sourceNode) {
            newHighlightNodes.add(sourceNode);
          }
          if (targetNode) {
            newHighlightNodes.add(targetNode);
          }
        }
      });

      setHighlightNodes(newHighlightNodes);
      setHighlightLinks(newHighlightLinks);
    }

    setHoverNode(node || null);
  };

  const handleLinkHover = (link: PipelineRelationship | null) => {
    setHighlightNodes(new Set());
    setHighlightLinks(new Set());

    if (link) {
      setHighlightLinks(new Set([link]));
      const highlightedNodes = new Set<PipelineEntity>();
      const sourceNode = getRelationshipEndpointNode(link.source);
      const targetNode = getRelationshipEndpointNode(link.target);
      if (sourceNode) {
        highlightedNodes.add(sourceNode);
      }
      if (targetNode) {
        highlightedNodes.add(targetNode);
      }
      setHighlightNodes(highlightedNodes);
    }
  };

  const buildNodeLabel = (node: Partial<PipelineEntity>) => {
    const lines = [node.name || "Untitled Node"];

    if (node.type === "Community") {
      if (node.member_count) {
        lines.push(`${node.member_count} members`);
      }
      if (node.relationship_count) {
        lines.push(`${node.relationship_count} internal relationships`);
      }
      if (node.summary) {
        lines.push("", node.summary);
      }
      return lines.join("\n");
    }

    if (node.community_name) {
      lines.push(`Community: ${node.community_name}`);
    }
    if (node.summary) {
      lines.push("", node.summary);
    }
    return lines.join("\n");
  };

  const selectedCommunityMembers = selectedCommunityNode
    ? [...graphData.nodes]
        .filter(
          (node) =>
            node.type !== "Community" &&
            node.community_key &&
            node.community_key === selectedCommunityNode.community_key
        )
        .sort((a, b) => {
          const rankA = Number(a.community_rank || 999999);
          const rankB = Number(b.community_rank || 999999);
          if (rankA !== rankB) return rankA - rankB;
          return String(a.name || "").localeCompare(String(b.name || ""));
        })
    : [];

  return (
    <div className="flex flex-col h-screen w-full bg-slate-50 text-slate-900">
      <header className="flex items-center justify-between p-4 bg-white border-b border-slate-200">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push(`/pipeline/${pipelineId}/data`)} className="mr-2 text-slate-500 hover:text-slate-700">
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Command Center
          </Button>
          <Database className="w-6 h-6 text-purple-600" />
          <h1 className="text-xl font-bold">Knowledge Graph</h1>
        </div>
        
        <div className="flex items-center bg-slate-100 p-1 rounded-lg">
          <button
            onClick={() => setTheme('full')}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${theme === 'full' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Full Map
          </button>
          <button
            onClick={() => setTheme('investors')}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${theme === 'investors' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Investors
          </button>
          <button
            onClick={() => setTheme('companies')}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${theme === 'companies' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Companies
          </button>
          <button
            onClick={() => setTheme('communities')}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${theme === 'communities' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Communities
          </button>
          <button
            onClick={() => setTheme('regulatory')}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${theme === 'regulatory' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Regulatory
          </button>
          <button
            onClick={() => setTheme('documents')}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${theme === 'documents' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Documents
          </button>
        </div>

        <div className="flex gap-3">
          <Button variant="outline" onClick={() => router.push(`/pipeline/${pipelineId}/enrichments`)}>
            <Building2 className="w-4 h-4 mr-2" /> Company Dossiers
          </Button>
          <Button variant="outline" onClick={() => router.push(`/pipeline/${pipelineId}/communities`)}>
            <Users className="w-4 h-4 mr-2" /> Community Explorer
          </Button>
          <Button variant="outline" onClick={fetchGraphData} disabled={isLoading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>
      </header>

      <div className="flex-1 w-full relative bg-slate-950" ref={containerRef}>
        {isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center text-slate-400">
            <RefreshCw className="w-8 h-8 animate-spin mr-3" /> Loading Graph...
          </div>
        ) : graphData.nodes.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center text-slate-400">
            No graph data found. Generate the graph first.
          </div>
        ) : (
          <ForceGraph2D
            width={windowSize.width}
            height={windowSize.height}
            graphData={graphData}
            nodeLabel={(node) => buildNodeLabel(node as Partial<PipelineEntity>)}
            nodeColor="color"
            nodeVal="val"
            linkColor={(link) => {
              const typedLink = link as PipelineRelationship;
              if (hoverNode) {
                return highlightLinks.has(typedLink) ? 'rgba(255, 255, 255, 0.8)' : 'rgba(150, 150, 150, 0.1)';
              }
              return typedLink.color || 'rgba(203, 213, 225, 0.4)';
            }}
            linkLabel={(link) => {
              const typedLink = link as PipelineRelationship;
              return `Relationship: ${typedLink.name || typedLink.type}`;
            }}
            linkDirectionalArrowLength={3.5}
            linkDirectionalArrowRelPos={1}
            onNodeClick={(node) => {
              const typedNode = node as PipelineEntity;
              if (typedNode.type === 'Community') {
                setSelectedDocument(null);
                setSelectedDocumentNode(null);
                setSelectedCommunityNode(typedNode);
              } else if (typedNode.type === 'Document') {
                setSelectedCommunityNode(null);
                setSelectedDocumentNode(typedNode);
                fetchDocumentInsight(typedNode.id);
              } else {
                router.push(`/pipeline/${pipelineId}/explorer/${typedNode.id}`);
              }
            }}
            onNodeHover={(node) => handleNodeHover((node as PipelineEntity | null) ?? null)}
            onLinkHover={(link) => handleLinkHover((link as PipelineRelationship | null) ?? null)}
            nodeCanvasObject={(node, ctx, globalScale) => {
              const typedNode = node as PipelineEntity;
              const label = typedNode.name;
              const fontSize = 12/globalScale;
              const nodeX = typedNode.x ?? 0;
              const nodeY = typedNode.y ?? 0;
              const nodeRadius = (typedNode.val ?? 1) * 2;
              ctx.font = `${fontSize}px Sans-Serif`;
              
              const isHovered = typedNode === hoverNode;
              const isHighlighted = highlightNodes.has(typedNode);
              const isDimmed = hoverNode && !isHighlighted;

              // Draw node circle
              ctx.beginPath();
              ctx.arc(nodeX, nodeY, nodeRadius, 0, 2 * Math.PI, false);
              ctx.fillStyle = isDimmed ? 'rgba(150, 150, 150, 0.1)' : (typedNode.color || '#a855f7');
              ctx.fill();

              // Draw label if hovered or highlighted
              if (isHighlighted || isHovered) {
                const textWidth = ctx.measureText(label).width;
                const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2);

                ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
                ctx.fillRect(nodeX - bckgDimensions[0] / 2, nodeY + nodeRadius + 2, bckgDimensions[0], bckgDimensions[1]);

                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillStyle = 'white';
                ctx.fillText(label, nodeX, nodeY + nodeRadius + 2 + bckgDimensions[1] / 2);
              }
            }}
            nodePointerAreaPaint={(node, color, ctx) => {
              const typedNode = node as PipelineEntity;
              const nodeX = typedNode.x ?? 0;
              const nodeY = typedNode.y ?? 0;
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(nodeX, nodeY, (typedNode.val ?? 1) * 3, 0, 2 * Math.PI, false);
              ctx.fill();
            }}
          />
        )}
        
        {/* Legend */}
        <div className="absolute bottom-6 right-6 bg-white/90 backdrop-blur p-4 rounded-lg shadow-lg border border-slate-200 text-sm">
          <h3 className="font-bold mb-2">Legend</h3>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-orange-500"></div>
            <span>Startup / Company</span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-slate-500"></div>
            <span>Incumbent</span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-sky-500"></div>
            <span>Utility</span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-emerald-500"></div>
            <span>Investor</span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-pink-500"></div>
            <span>Service Provider</span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-green-500"></div>
            <span>Asset / Basin</span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-amber-500"></div>
            <span>Person</span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-violet-600"></div>
            <span>Community</span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
            <span>Regulatory</span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-blue-500"></div>
            <span>Document</span>
          </div>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-3 h-3 rounded-full bg-purple-500"></div>
            <span>Other Entity</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-0.5 bg-slate-300"></div>
            <span>{theme === 'communities' ? 'BELONGS_TO Edge' : 'Edge'}</span>
          </div>
        </div>

        {selectedCommunityNode && (
          <div className="absolute top-0 right-0 h-full w-[440px] bg-white shadow-2xl border-l border-slate-200 flex flex-col z-40 transform transition-transform duration-300">
            <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-slate-50">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wider text-violet-600">Community</p>
                <h2 className="text-lg font-bold text-slate-900 truncate" title={selectedCommunityNode.name}>
                  {selectedCommunityNode.name}
                </h2>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setSelectedCommunityNode(null)}>
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </div>

            <div className="flex-1 overflow-auto p-6 space-y-6 bg-slate-50">
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-3">Summary</h3>
                <p className="text-sm text-slate-700 leading-relaxed">
                  {selectedCommunityNode.summary || "No community summary is available yet."}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                  <p className="text-xs font-bold text-slate-400 uppercase">Members</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">
                    {selectedCommunityNode.member_count || selectedCommunityMembers.length}
                  </p>
                </div>
                <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                  <p className="text-xs font-bold text-slate-400 uppercase">Internal Relationships</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">
                    {selectedCommunityNode.relationship_count || 0}
                  </p>
                </div>
              </div>

              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-3">Top Members</h3>
                {selectedCommunityMembers.length > 0 ? (
                  <div className="space-y-2">
                    {selectedCommunityMembers.slice(0, 20).map((member) => (
                      <button
                        key={member.id}
                        onClick={() => router.push(`/pipeline/${pipelineId}/explorer/${member.id}`)}
                        className="w-full text-left rounded-lg border border-slate-200 px-3 py-3 hover:bg-slate-50 transition-colors"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <p className="font-medium text-slate-900 truncate">{member.name}</p>
                            <p className="text-xs text-slate-500 mt-1">{member.type}</p>
                          </div>
                          {member.community_rank ? (
                            <span className="text-xs font-semibold text-violet-700 bg-violet-50 border border-violet-100 rounded-full px-2 py-1 shrink-0">
                              #{member.community_rank}
                            </span>
                          ) : null}
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-slate-500 italic">No members are available in the current graph view.</p>
                )}
              </div>
            </div>
          </div>
        )}
        
        {/* Document Viewer Panel */}
        {selectedDocument && (
          <div className="absolute top-0 right-0 h-full w-[600px] bg-white shadow-2xl border-l border-slate-200 flex flex-col z-50 transform transition-transform duration-300">
            <div className="flex items-center justify-between p-4 border-b border-slate-200">
              <h2 className="text-lg font-bold truncate pr-4" title={documentData?.title || selectedDocument}>
                {documentData?.title || 'Loading Document...'}
              </h2>
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
                    <iframe 
                      src={documentData.source_url} 
                      className="w-full h-full border-0"
                      title={documentData.title}
                      sandbox="allow-same-origin allow-scripts"
                    />
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

        {/* Document Insight Explorer Panel */}
        {selectedDocumentNode && (
          <div className="absolute top-0 right-0 h-full w-[500px] bg-white shadow-2xl border-l border-slate-200 flex flex-col z-40 transform transition-transform duration-300">
            <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-500" />
                <h2 className="text-lg font-bold truncate" title={selectedDocumentNode.name}>
                  {selectedDocumentNode.name}
                </h2>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setSelectedDocumentNode(null)}>
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </div>
            
            <div className="flex-1 overflow-auto p-6">
              {isInsightLoading ? (
                <div className="flex flex-col items-center justify-center h-full text-slate-400">
                  <RefreshCw className="w-8 h-8 animate-spin mb-4" />
                  <p>Generating RAG Insight...</p>
                  <p className="text-xs mt-2 text-center max-w-[250px]">Analyzing document chunks and semantic connections...</p>
                </div>
              ) : documentInsightData ? (
                <div className="space-y-6">
                  {/* Action Buttons */}
                  <div className="flex gap-3 pb-4 border-b border-slate-100">
                    <Button 
                      className="w-full bg-blue-600 hover:bg-blue-700" 
                      onClick={() => {
                        if (documentInsightData.central_node?.source_url) {
                          fetchDocument(documentInsightData.central_node.source_url);
                        }
                      }}
                    >
                      <FileText className="w-4 h-4 mr-2" /> View Original Document
                    </Button>
                  </div>

                  {/* RAG Insight */}
                  <div>
                    <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3">Document Context & Connections</h3>
                    {documentInsightData.central_node?.investor_insight ? (
                      <div className="prose prose-slate prose-sm max-w-none">
                        <ReactMarkdown
                          components={{
                            a: ({ ...props }) => {
                              return (
                                <a
                                  {...props}
                                  href="#"
                                  onClick={(e) => {
                                    e.preventDefault();
                                    if (props.href) {
                                      fetchDocument(props.href);
                                    }
                                  }}
                                  className="text-blue-600 hover:text-blue-800 underline decoration-blue-300 underline-offset-2 cursor-pointer"
                                >
                                  {props.children}
                                </a>
                              );
                            },
                          }}
                        >
                          {documentInsightData.central_node.investor_insight}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <p className="text-slate-500 italic">No insight available.</p>
                    )}
                  </div>
                  
                  {/* Network Stats */}
                  <div className="bg-slate-50 p-4 rounded-lg border border-slate-100">
                    <h3 className="text-sm font-bold text-slate-700 mb-2">Network Summary</h3>
                    <ul className="text-sm text-slate-600 space-y-1">
                      <li>• Connected to <span className="font-bold text-slate-900">{documentInsightData.relationships.filter((r) => r.type === 'SIMILAR_TO').length}</span> similar documents</li>
                      <li>• Mentions <span className="font-bold text-slate-900">{documentInsightData.relationships.filter((r) => r.type === 'MENTIONS').length}</span> key entities</li>
                    </ul>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center h-full text-red-500">
                  Failed to load document insight.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}