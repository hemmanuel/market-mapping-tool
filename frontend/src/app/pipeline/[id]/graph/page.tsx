"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Database, RefreshCw } from "lucide-react";

// Dynamically import ForceGraph2D to avoid SSR issues
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

export default function GraphViewerPage() {
  const params = useParams();
  const router = useRouter();
  const pipelineId = params.id as string;
  const { getToken } = useAuth();

  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [isLoading, setIsLoading] = useState(true);
  const [windowSize, setWindowSize] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Hover state
  const [hoverNode, setHoverNode] = useState<any>(null);
  const [highlightNodes, setHighlightNodes] = useState(new Set());
  const [highlightLinks, setHighlightLinks] = useState(new Set());

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

      const res = await fetch(`http://localhost:8000/api/v1/pipelines/${pipelineId}/entities`, { headers });
      if (!res.ok) throw new Error("Failed to fetch graph data");
      
      const data = await res.json();
      
      // Transform data for react-force-graph
      const nodes = data.entities.map((e: any) => ({
        id: e.id,
        name: e.name,
        type: e.type,
        val: 2,
        color: e.type === 'Company' ? '#f97316' : '#a855f7', // Orange for Company, Purple for others
        summary: e.summary
      }));

      const links = data.relationships.map((r: any) => ({
        source: r.source,
        target: r.target,
        name: r.type,
        weight: r.weight,
        color: 'rgba(203, 213, 225, 0.4)' // Slate 300 with opacity
      }));

      setGraphData({ nodes, links } as any);
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchGraphData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

  const handleNodeHover = (node: any) => {
    setHighlightNodes(new Set());
    setHighlightLinks(new Set());

    if (node) {
      const newHighlightNodes = new Set([node]);
      const newHighlightLinks = new Set();

      graphData.links.forEach((link: any) => {
        if (link.source.id === node.id || link.target.id === node.id) {
          newHighlightLinks.add(link);
          newHighlightNodes.add(link.source);
          newHighlightNodes.add(link.target);
        }
      });

      setHighlightNodes(newHighlightNodes);
      setHighlightLinks(newHighlightLinks);
    }

    setHoverNode(node || null);
  };

  const handleLinkHover = (link: any) => {
    setHighlightNodes(new Set());
    setHighlightLinks(new Set());

    if (link) {
      setHighlightLinks(new Set([link]));
      setHighlightNodes(new Set([link.source, link.target]));
    }
  };

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
        <div className="flex gap-3">
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
            nodeLabel={(node: any) => node.summary ? `${node.name}\n\n${node.summary}` : node.name}
            nodeColor="color"
            nodeVal="val"
            linkColor={(link: any) => {
              if (hoverNode) {
                return highlightLinks.has(link) ? 'rgba(255, 255, 255, 0.8)' : 'rgba(150, 150, 150, 0.1)';
              }
              return link.color;
            }}
            linkLabel={(link: any) => `Relationship: ${link.name}`}
            linkDirectionalArrowLength={3.5}
            linkDirectionalArrowRelPos={1}
            onNodeClick={(node: any) => {
              router.push(`/pipeline/${pipelineId}/explorer/${node.id}`);
            }}
            onNodeHover={handleNodeHover}
            onLinkHover={handleLinkHover}
            nodeCanvasObject={(node: any, ctx, globalScale) => {
              const label = node.name;
              const fontSize = 12/globalScale;
              ctx.font = `${fontSize}px Sans-Serif`;
              
              const isHovered = node === hoverNode;
              const isHighlighted = highlightNodes.has(node);
              const isDimmed = hoverNode && !isHighlighted;

              // Draw node circle
              ctx.beginPath();
              ctx.arc(node.x, node.y, node.val * 2, 0, 2 * Math.PI, false);
              ctx.fillStyle = isDimmed ? 'rgba(150, 150, 150, 0.1)' : node.color;
              ctx.fill();

              // Draw label if hovered or highlighted
              if (isHighlighted || isHovered) {
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
            nodePointerAreaPaint={(node: any, color, ctx) => {
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(node.x, node.y, node.val * 3, 0, 2 * Math.PI, false);
              ctx.fill();
            }}
          />
        )}
        
        {/* Legend */}
        <div className="absolute bottom-6 right-6 bg-white/90 backdrop-blur p-4 rounded-lg shadow-lg border border-slate-200 text-sm">
          <h3 className="font-bold mb-2">Legend</h3>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-orange-500"></div>
            <span>Company</span>
          </div>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-3 h-3 rounded-full bg-purple-500"></div>
            <span>Other Entity</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-0.5 bg-slate-300"></div>
            <span>INTERACTS_WITH</span>
          </div>
        </div>
      </div>
    </div>
  );
}