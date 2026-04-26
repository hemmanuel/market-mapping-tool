"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { backendApiPath } from "@/lib/backend-api";
import { Database, FileText, File, FileSpreadsheet, Globe, ExternalLink, ArrowLeft } from "lucide-react";

interface Source {
  url: string;
  type: string;
  viewer_url: string | null;
}

interface Chunk {
  id: string;
  title: string;
  text_snippet: string;
  source_url: string;
  created_at: string;
}

export default function DataExplorer() {
  const params = useParams();
  const router = useRouter();
  const pipelineId = params.id as string;
  const { getToken } = useAuth();

  const [sources, setSources] = useState<Source[]>([]);
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [viewMode, setViewMode] = useState<"document" | "chunks">("document");
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<string>("all");

  const availableTypes = ["all", ...Array.from(new Set(sources.map(s => s.type)))];
  const filteredSources = typeFilter === "all" ? sources : sources.filter(s => s.type === typeFilter);

  useEffect(() => {
    fetchSources();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

  useEffect(() => {
    if (selectedSource) {
      fetchChunksForSource(selectedSource.url);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSource]);

  const fetchSources = async () => {
    setLoading(true);
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/sources`), { headers });
      if (res.ok) {
        const data = await res.json();
        setSources(data);
        if (data.length > 0) {
          setSelectedSource(data[0]);
        }
      }
    } catch (error) {
      console.error("Failed to fetch sources", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchChunksForSource = async (url: string) => {
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      // We'll fetch all chunks for this specific source
      const res = await fetch(
        backendApiPath(`/api/v1/pipelines/${pipelineId}/documents?source_url=${encodeURIComponent(url)}`),
        { headers }
      );
      if (res.ok) {
        const data = await res.json();
        setChunks(data.chunks || []);
      }
    } catch (error) {
      console.error("Failed to fetch chunks", error);
    }
  };

  const getSourceIcon = (type: string) => {
    switch (type) {
      case 'pdf': return <FileText className="w-4 h-4 text-red-500" />;
      case 'docx': return <File className="w-4 h-4 text-blue-500" />;
      case 'pptx': return <File className="w-4 h-4 text-orange-500" />;
      case 'spreadsheet': return <FileSpreadsheet className="w-4 h-4 text-green-500" />;
      default: return <Globe className="w-4 h-4 text-slate-500" />;
    }
  };

  return (
    <div className="flex flex-col h-screen w-full bg-slate-50 text-slate-900">
      {/* Header */}
      <header className="flex items-center justify-between p-4 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push(`/pipeline/${pipelineId}/data`)} className="mr-2 text-slate-500 hover:text-slate-700">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back to Command Center
          </Button>
          <Database className="w-6 h-6 text-blue-600" />
          <h1 className="text-xl font-bold">Data Explorer</h1>
          <Badge variant="outline" className="ml-2 bg-slate-100 text-slate-600">Pipeline: {pipelineId.slice(0, 8)}...</Badge>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar: Sources List */}
        <div className="w-1/4 flex flex-col border-r border-slate-200 bg-white">
          <div className="p-4 border-b border-slate-200 bg-slate-50 flex flex-col gap-3">
            <div className="font-semibold text-sm text-slate-700 flex items-center justify-between">
              <span>Sources ({filteredSources.length})</span>
            </div>
            <select 
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="w-full p-2 text-sm border border-slate-300 rounded-md bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {availableTypes.map(type => (
                <option key={type} value={type}>
                  {type === "all" ? "All Types" : type.toUpperCase()}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="p-4 text-center text-slate-500 text-sm">Loading sources...</div>
            ) : filteredSources.length === 0 ? (
              <div className="p-4 text-center text-slate-500 text-sm">No sources found.</div>
            ) : (
              <div className="divide-y divide-slate-100">
                {filteredSources.map((source, idx) => (
                  <button
                    key={idx}
                    onClick={() => setSelectedSource(source)}
                    className={`w-full text-left p-4 hover:bg-slate-50 transition-colors flex items-start gap-3 ${selectedSource?.url === source.url ? 'bg-blue-50 border-l-4 border-blue-600' : 'border-l-4 border-transparent'}`}
                  >
                    <div className="mt-0.5">{getSourceIcon(source.type)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-slate-900 truncate" title={source.url}>
                        {new URL(source.url).hostname}
                      </div>
                      <div className="text-xs text-slate-500 truncate mt-1">
                        {new URL(source.url).pathname}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col bg-slate-50">
          {selectedSource ? (
            <>
              {/* Toolbar */}
              <div className="p-4 border-b border-slate-200 bg-white flex items-center justify-between">
                <div className="flex items-center gap-2 overflow-hidden">
                  <Badge variant="secondary" className="uppercase text-[10px]">{selectedSource.type}</Badge>
                  <a href={selectedSource.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-blue-600 hover:underline truncate flex items-center gap-1">
                    {selectedSource.url} <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
                <div className="flex bg-slate-100 p-1 rounded-lg">
                  <button
                    onClick={() => setViewMode("document")}
                    className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${viewMode === "document" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
                  >
                    Original Document
                  </button>
                  <button
                    onClick={() => setViewMode("chunks")}
                    className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${viewMode === "chunks" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
                  >
                    Extracted Chunks ({chunks.length})
                  </button>
                </div>
              </div>

              {/* Viewer Area */}
              <div className="flex-1 overflow-hidden relative">
                {viewMode === "document" ? (
                  selectedSource.viewer_url ? (
                    <iframe
                      src={selectedSource.viewer_url}
                      className="w-full h-full border-0 bg-white"
                      title="Document Viewer"
                    />
                  ) : (
                    <div className="flex items-center justify-center h-full text-slate-500">
                      No viewer available for this document. It may not have been saved to MinIO.
                    </div>
                  )
                ) : (
                  <div className="h-full overflow-y-auto p-6">
                    <div className="max-w-3xl mx-auto space-y-4">
                      {chunks.length === 0 ? (
                        <div className="text-center p-8 border border-dashed border-slate-300 rounded-lg text-slate-500 bg-white">
                          No chunks found for this source.
                        </div>
                      ) : (
                        chunks.map((chunk, i) => (
                          <div key={i} className="p-5 bg-white border border-slate-200 rounded-lg shadow-sm">
                            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                              Chunk {i + 1}
                            </div>
                            <div className="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
                              {chunk.text_snippet}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-slate-500">
              Select a source from the sidebar to view it.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
