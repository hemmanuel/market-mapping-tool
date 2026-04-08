"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Play, RefreshCw, Database, Activity, CheckCircle2, AlertCircle } from "lucide-react";

// Add global type for Clerk
declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    Clerk?: any;
  }
}

export default function DataCommandCenter() {
  const params = useParams();
  const pipelineId = params.id as string;

  const [isAcquiring, setIsAcquiring] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [entities, setEntities] = useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [relationships, setRelationships] = useState<any[]>([]);

  // Mock live feed data for now
  const [feed] = useState([
    { id: 1, url: "https://techcrunch.com/space", status: "extracting", type: "News" },
    { id: 2, url: "https://spacenews.com/latest", status: "queued", type: "News" },
    { id: 3, url: "https://example.com/startup-db", status: "completed", type: "Directory" },
  ]);

  const startAcquisition = async () => {
    setIsAcquiring(true);
    try {
      const token = await window.Clerk?.session?.getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(`http://localhost:8000/api/v1/pipelines/${pipelineId}/acquire`, {
        method: 'POST',
        headers
      });
      if (!res.ok) throw new Error("Failed to start acquisition");
      alert("Acquisition started in the background!");
    } catch (error) {
      console.error(error);
      alert("Failed to start acquisition.");
      setIsAcquiring(false);
    }
  };

  const fetchExplorerData = async () => {
    try {
      const token = await window.Clerk?.session?.getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(`http://localhost:8000/api/v1/pipelines/${pipelineId}/entities`, {
        headers
      });
      if (res.ok) {
        const data = await res.json();
        setEntities(data.entities || []);
        setRelationships(data.relationships || []);
      }
    } catch (error) {
      console.error("Failed to fetch explorer data", error);
    }
  };

  useEffect(() => {
    fetchExplorerData();
    // Poll every 5 seconds for updates
    const interval = setInterval(fetchExplorerData, 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

  return (
    <div className="flex flex-col h-screen w-full bg-slate-50 text-slate-900">
      {/* Header */}
      <header className="flex items-center justify-between p-4 bg-white border-b border-slate-200">
        <div className="flex items-center gap-3">
          <Database className="w-6 h-6 text-blue-600" />
          <h1 className="text-xl font-bold">Data Command Center</h1>
          <Badge variant="outline" className="ml-2 bg-slate-100 text-slate-600">Pipeline: {pipelineId.slice(0, 8)}...</Badge>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={fetchExplorerData}>
            <RefreshCw className="w-4 h-4 mr-2" /> Refresh
          </Button>
          <Button 
            onClick={startAcquisition} 
            disabled={isAcquiring}
            className={isAcquiring ? "bg-emerald-600 hover:bg-emerald-700" : "bg-blue-600 hover:bg-blue-700"}
          >
            {isAcquiring ? (
              <><Activity className="w-4 h-4 mr-2 animate-pulse" /> Acquiring Data...</>
            ) : (
              <><Play className="w-4 h-4 mr-2" /> Start Acquisition</>
            )}
          </Button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Pane: Strategy & Live Feed */}
        <div className="w-1/2 flex flex-col border-r border-slate-200 bg-white">
          <div className="p-4 border-b border-slate-200 bg-slate-50 font-semibold text-sm text-slate-700 flex items-center gap-2">
            <Activity className="w-4 h-4" /> Live Ingestion Feed
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <div className="space-y-3">
              {feed.map(item => (
                <div key={item.id} className="flex items-center justify-between p-3 border border-slate-100 rounded-lg bg-slate-50">
                  <div className="flex flex-col">
                    <span className="text-sm font-medium truncate w-64" title={item.url}>{item.url}</span>
                    <span className="text-xs text-slate-500 mt-1">{item.type}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {item.status === 'completed' && <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100 border-emerald-200"><CheckCircle2 className="w-3 h-3 mr-1" /> Done</Badge>}
                    {item.status === 'extracting' && <Badge className="bg-blue-100 text-blue-700 hover:bg-blue-100 border-blue-200"><RefreshCw className="w-3 h-3 mr-1 animate-spin" /> Extracting</Badge>}
                    {item.status === 'queued' && <Badge className="bg-slate-200 text-slate-700 hover:bg-slate-200 border-slate-300">Queued</Badge>}
                    {item.status === 'failed' && <Badge className="bg-red-100 text-red-700 hover:bg-red-100 border-red-200"><AlertCircle className="w-3 h-3 mr-1" /> Failed</Badge>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Pane: Data Explorer */}
        <div className="w-1/2 flex flex-col bg-slate-50">
          <div className="p-4 border-b border-slate-200 bg-white font-semibold text-sm text-slate-700 flex items-center gap-2">
            <Database className="w-4 h-4" /> Knowledge Graph Explorer
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            
            <div className="mb-8">
              <h3 className="text-lg font-semibold mb-4">Extracted Entities ({entities.length})</h3>
              {entities.length === 0 ? (
                <div className="text-center p-8 border border-dashed border-slate-300 rounded-lg text-slate-500">
                  No entities extracted yet. Start acquisition to populate the graph.
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-4">
                  {entities.map((ent, i) => (
                    <div key={i} className="p-3 bg-white border border-slate-200 rounded-lg shadow-sm">
                      <div className="font-medium text-sm">{ent.name}</div>
                      <Badge variant="outline" className="mt-2 text-xs">{ent.type}</Badge>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <h3 className="text-lg font-semibold mb-4">Extracted Relationships ({relationships.length})</h3>
              {relationships.length === 0 ? (
                <div className="text-center p-8 border border-dashed border-slate-300 rounded-lg text-slate-500">
                  No relationships extracted yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {relationships.map((rel, i) => (
                    <div key={i} className="flex items-center gap-3 p-3 bg-white border border-slate-200 rounded-lg shadow-sm text-sm">
                      <span className="font-medium text-blue-700">{rel.source}</span>
                      <span className="text-slate-400 font-mono text-xs bg-slate-100 px-2 py-1 rounded">-[{rel.type}]-&gt;</span>
                      <span className="font-medium text-emerald-700">{rel.target}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
