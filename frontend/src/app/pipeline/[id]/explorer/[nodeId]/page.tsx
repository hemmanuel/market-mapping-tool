"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { ArrowLeft, BrainCircuit, Network, ExternalLink } from "lucide-react";
import ReactMarkdown from "react-markdown";

// Dynamically import ForceGraph2D to avoid SSR issues
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

export default function NodeExplorerPage() {
  const params = useParams();
  const router = useRouter();
  const pipelineId = params.id as string;
  const nodeId = params.nodeId as string;
  const { getToken } = useAuth();

  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [centralNode, setCentralNode] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [windowSize, setWindowSize] = useState({ width: 400, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Hover state
  const [hoverNode, setHoverNode] = useState<any>(null);

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

        // Transform data for react-force-graph
        const nodes = data.entities.map((e: any) => ({
          id: e.id,
          name: e.name,
          type: e.type,
          val: e.id === nodeId ? 4 : 2, // Central node is larger
          color: e.id === nodeId ? '#ef4444' : (e.type === 'Company' ? '#f97316' : '#a855f7'),
        }));

        const links = data.relationships.map((r: any) => ({
          source: r.source,
          target: r.target,
          name: r.type,
          weight: r.weight,
          quotes: r.quotes,
          source_urls: r.source_urls,
          color: 'rgba(203, 213, 225, 0.6)'
        }));

        setGraphData({ nodes, links } as any);
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

  return (
    <div className="flex flex-col h-screen w-full bg-slate-50 text-slate-900 overflow-hidden">
      <header className="flex items-center justify-between p-4 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push(`/pipeline/${pipelineId}/graph`)} className="mr-2 text-slate-500 hover:text-slate-700">
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Full Graph
          </Button>
          <Network className="w-6 h-6 text-indigo-600" />
          <h1 className="text-xl font-bold">Group Explorer: {centralNode?.name || "Loading..."}</h1>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Pane: Ego Graph */}
        <div className="w-1/2 relative bg-slate-950 border-r border-slate-800" ref={containerRef}>
          {isLoading ? (
            <div className="absolute inset-0 flex items-center justify-center text-slate-400">
              <BrainCircuit className="w-8 h-8 animate-pulse mr-3" /> Analyzing Group...
            </div>
          ) : graphData.nodes.length === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center text-slate-400">
              No connections found.
            </div>
          ) : (
            <ForceGraph2D
              width={windowSize.width}
              height={windowSize.height}
              graphData={graphData}
              nodeLabel="name"
              nodeColor="color"
              nodeVal="val"
              linkColor="color"
              linkLabel={(link: any) => `Relationship: ${link.name}`}
              linkDirectionalArrowLength={3.5}
              linkDirectionalArrowRelPos={1}
              onNodeHover={(node) => setHoverNode(node)}
              nodeCanvasObject={(node: any, ctx, globalScale) => {
                const label = node.name;
                const fontSize = 12/globalScale;
                ctx.font = `${fontSize}px Sans-Serif`;
                
                const isHovered = node === hoverNode;
                const isCentral = node.id === nodeId;

                // Draw node circle
                ctx.beginPath();
                ctx.arc(node.x, node.y, node.val * 2, 0, 2 * Math.PI, false);
                ctx.fillStyle = node.color;
                ctx.fill();

                // Always draw label for central node, otherwise on hover
                if (isCentral || isHovered) {
                  const textWidth = ctx.measureText(label).width;
                  const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2);

                  ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
                  ctx.fillRect(node.x - bckgDimensions[0] / 2, node.y + node.val * 2 + 2, bckgDimensions[0], bckgDimensions[1]);

                  ctx.textAlign = 'center';
                  ctx.textBaseline = 'middle';
                  ctx.fillStyle = 'white';
                  ctx.fillText(label, node.x, node.y + node.val * 2 + 2 + bckgDimensions[1] / 2);
                }
              }}
            />
          )}
        </div>

        {/* Right Pane: Insights and Quotes */}
        <div className="w-1/2 bg-white overflow-y-auto p-8">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
              <BrainCircuit className="w-12 h-12 animate-pulse mb-4 text-indigo-500" />
              <p className="text-lg font-medium">Generating VC/PE Investment Thesis...</p>
              <p className="text-sm mt-2">Gemini is analyzing the relationships in this group.</p>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto">
              <div className="mb-8">
                <h2 className="text-3xl font-bold text-slate-900 mb-2">{centralNode?.name}</h2>
                <span className="inline-block bg-slate-100 text-slate-600 px-3 py-1 rounded-full text-sm font-medium border border-slate-200">
                  {centralNode?.type}
                </span>
              </div>

              <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-6 mb-10 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <BrainCircuit className="w-5 h-5 text-indigo-600" />
                  <h3 className="text-lg font-bold text-indigo-900">Investor Insight</h3>
                </div>
                <div className="prose prose-indigo max-w-none text-slate-700">
                  <ReactMarkdown>
                    {centralNode?.investor_insight || "No insight available."}
                  </ReactMarkdown>
                </div>
              </div>

              <h3 className="text-xl font-bold text-slate-900 mb-6 border-b pb-2">Verified Relationships</h3>
              
              <div className="space-y-6">
                {graphData.links.map((link: any, idx: number) => {
                  const isOutgoing = link.source.id === nodeId || link.source === nodeId;
                  const otherNodeName = isOutgoing ? (link.target.name || link.target_name) : (link.source.name || link.source_name);
                  
                  return (
                    <div key={idx} className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm hover:shadow-md transition-shadow">
                      <div className="flex items-center gap-3 mb-3">
                        <span className="font-semibold text-slate-900">{centralNode?.name}</span>
                        <span className="text-xs font-mono bg-slate-100 text-slate-500 px-2 py-1 rounded">
                          {isOutgoing ? `-[${link.name}]->` : `<-[${link.name}]-`}
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
                                  <a 
                                    href={sourceUrl} 
                                    target="_blank" 
                                    rel="noopener noreferrer"
                                    className="text-xs text-indigo-500 hover:text-indigo-700 flex items-center gap-1 ml-3"
                                  >
                                    <ExternalLink className="w-3 h-3" />
                                    Source Document
                                  </a>
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
                
                {graphData.links.length === 0 && (
                  <p className="text-slate-500 italic">No relationships found for this entity.</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
