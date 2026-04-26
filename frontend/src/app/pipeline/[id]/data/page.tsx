"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useChat } from "ai/react";
import ReactMarkdown from "react-markdown";
import { useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { backendApiPath } from "@/lib/backend-api";
import {
  DocumentChunk,
  DocumentsResponse,
  PendingDocument,
  PipelineEntitiesResponse,
  PipelineEntity,
  QueueItem,
} from "@/lib/pipeline-types";
import { Play, RefreshCw, Database, Activity, CheckCircle2, AlertCircle, Bot, Terminal, Square, Search, ExternalLink, Download, Users, Building2 } from "lucide-react";

// Add global type for Clerk
declare global {
  interface Window {
    Clerk?: {
      session?: {
        getToken?: () => Promise<string | null>;
      };
    };
  }
}

export default function DataCommandCenter() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const pipelineId = params.id as string;

  const [isAcquiring, setIsAcquiring] = useState(false);
  const [isGeneratingGraph, setIsGeneratingGraph] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [entities, setEntities] = useState<PipelineEntity[]>([]);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [pendingDocs, setPendingDocs] = useState<PendingDocument[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  
  const hasStartedAcquisition = useRef(false);
  const hasGreeted = useRef(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const { getToken } = useAuth();

  const { messages, input, handleInputChange, handleSubmit, append } = useChat({
    api: '/api/strategist',
    body: { pipelineId }
  });

  useEffect(() => {
    if (!hasGreeted.current && messages.length === 0) {
      hasGreeted.current = true;
      append({ role: 'user', content: 'SYSTEM_AUTO_PROMPT: INTRODUCE_DATA_STRATEGY' });
    }
  }, [messages.length, append]);

  useEffect(() => {
    if (!hasStartedAcquisition.current) {
      hasStartedAcquisition.current = true;
      // Only auto-start if the query parameter is present (coming from the onboarding wizard)
      if (searchParams.get("autoStart") === "true") {
        startAcquisition();
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId, searchParams]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const startAcquisition = async () => {
    setIsAcquiring(true);
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/acquire`), {
        method: 'POST',
        headers
      });
      if (!res.ok) throw new Error("Failed to start acquisition");
    } catch (error) {
      console.error(error);
      alert("Failed to start acquisition.");
      setIsAcquiring(false);
    }
  };

  const stopAcquisition = async () => {
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/cancel`), {
        method: 'POST',
        headers
      });
      if (!res.ok) throw new Error("Failed to stop acquisition");
      setIsAcquiring(false);
    } catch (error) {
      console.error(error);
      alert("Failed to stop acquisition.");
    }
  };

  const generateGraph = async () => {
    setIsGeneratingGraph(true);
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/generate-graph`), {
        method: 'POST',
        headers
      });
      if (!res.ok) throw new Error("Failed to start graph generation");
      router.push(`/pipeline/${pipelineId}/graph-progress`);
    } catch (error) {
      console.error(error);
      alert("Failed to start graph generation.");
      setIsGeneratingGraph(false);
    }
  };

  const stopGraphGeneration = async () => {
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/cancel-graph`), {
        method: 'POST',
        headers
      });
      if (!res.ok) throw new Error("Failed to stop graph generation");
      setIsGeneratingGraph(false);
    } catch (error) {
      console.error(error);
      alert("Failed to stop graph generation.");
    }
  };

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/export`), { headers });
      if (!res.ok) throw new Error("Failed to export graph");

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `graph_export_${pipelineId}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error(error);
      alert("Failed to export graph.");
    } finally {
      setIsExporting(false);
    }
  };

  const fetchExplorerData = useCallback(async () => {
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const [resEntities, resDocs, resPending] = await Promise.all([
        fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/entities`), { headers }),
        fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/documents`), { headers }),
        fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/pending-documents`), { headers })
      ]);

      if (resEntities.ok) {
        const data = (await resEntities.json()) as PipelineEntitiesResponse;
        setEntities(data.entities || []);
      }
      
      if (resDocs.ok) {
        const data = (await resDocs.json()) as DocumentsResponse;
        setChunks(data.chunks || []);
        setTotalChunks(data.total_chunks || 0);
      }

      if (resPending.ok) {
        const data = (await resPending.json()) as PendingDocument[];
        setPendingDocs(data || []);
      }
    } catch (error) {
      console.error("Failed to fetch explorer data", error);
    }
  }, [getToken, pipelineId]);

  const handleProcessPending = async (docId: string, action: string, charLimit?: number) => {
    try {
      const token = await getToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json'
      };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(backendApiPath(`/api/v1/pipelines/${pipelineId}/pending-documents/${docId}/process`), {
        method: 'POST',
        headers,
        body: JSON.stringify({ action, char_limit: charLimit })
      });

      if (res.ok) {
        // Remove from UI immediately
        setPendingDocs(prev => prev.filter(d => d.id !== docId));
      } else {
        alert("Failed to process document");
      }
    } catch (error) {
      console.error("Failed to process document", error);
    }
  };

  useEffect(() => {
    void fetchExplorerData();
  }, [fetchExplorerData]);

  useEffect(() => {
    const eventSource = new EventSource(backendApiPath(`/api/v1/pipelines/${pipelineId}/logs`));

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'status') {
          setIsAcquiring(data.is_acquiring);
        } else if (data.type === 'log') {
          setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${data.message}`]);
          if (data.message === "Workflow completed successfully." || data.message === "Workflow aborted by user.") {
            setIsAcquiring(false);
          }
        } else if (data.type === 'queue') {
          setQueue(data.data);
        } else if (data.type === 'queue_update') {
          setQueue(prev => prev.map(item => 
            item.url === data.url ? { ...item, status: data.status } : item
          ));
        } else if (data.type === 'new_data') {
          if (data.entities && data.entities.length > 0) {
            setEntities(prev => [...prev, ...data.entities]);
          }
        } else if (data.type === 'new_chunk') {
          setChunks(prev => [data.data, ...prev]);
          setTotalChunks(prev => prev + 1);
        } else if (data.type === 'graph_progress') {
          setIsGeneratingGraph(
            data.current_phase !== 'Complete' &&
            data.current_phase !== 'Error' &&
            data.current_phase !== 'Cancelled'
          );
          setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] [Graph] ${data.message}`]);
        }
      } catch (err) {
        console.error("Failed to parse SSE message", err);
      }
    };

    eventSource.onerror = (err) => {
      console.error("EventSource failed:", err);
      // Optional: eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [pipelineId, fetchExplorerData]);

  return (
    <div className="flex flex-col h-screen w-full bg-slate-50 text-slate-900">
      {/* Header */}
      <header className="flex items-center justify-between p-4 bg-white border-b border-slate-200">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard")} className="mr-2 text-slate-500 hover:text-slate-700">
            &larr; Dashboard
          </Button>
          <Database className="w-6 h-6 text-blue-600" />
          <h1 className="text-xl font-bold">Data Command Center</h1>
          <Badge variant="outline" className="ml-2 bg-slate-100 text-slate-600">Pipeline: {pipelineId.slice(0, 8)}...</Badge>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={fetchExplorerData}>
            <RefreshCw className="w-4 h-4 mr-2" /> Refresh
          </Button>
          {isAcquiring ? (
            <Button 
              onClick={stopAcquisition} 
              variant="destructive"
            >
              <Square className="w-4 h-4 mr-2 fill-current" /> Stop Acquisition
            </Button>
          ) : (
            <Button 
              onClick={startAcquisition} 
              className="bg-blue-600 hover:bg-blue-700"
            >
              <Play className="w-4 h-4 mr-2" /> Start Acquisition
            </Button>
          )}
          {isGeneratingGraph ? (
            <Button 
              onClick={stopGraphGeneration} 
              variant="destructive"
            >
              <Square className="w-4 h-4 mr-2 fill-current" /> Stop Generation
            </Button>
          ) : (
            <Button 
              onClick={generateGraph} 
              disabled={isAcquiring || totalChunks === 0}
              className="bg-purple-600 hover:bg-purple-700"
            >
              <Database className="w-4 h-4 mr-2" /> Generate Graph
            </Button>
          )}
          <Button 
            onClick={handleExport} 
            disabled={isExporting || totalChunks === 0}
            variant="outline"
            className="border-slate-300 text-slate-700 hover:bg-slate-50"
          >
            {isExporting ? (
              <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Download className="w-4 h-4 mr-2" />
            )}
            {isExporting ? "Exporting..." : "Export Gephi CSV"}
          </Button>
        </div>
      </header>

      {isAcquiring && (
        <div className="bg-blue-50 border-b border-blue-100 p-3 flex items-center justify-center gap-3 text-blue-700 text-sm font-medium">
          <RefreshCw className="w-4 h-4 animate-spin" />
          Building the backbone of your Knowledge Graph...
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Column 1: Strategist Chat */}
        <div className="w-1/3 flex flex-col border-r border-slate-200 bg-white">
          <div className="p-4 border-b border-slate-200 bg-slate-50 font-semibold text-sm text-slate-700 flex items-center gap-2">
            <Bot className="w-4 h-4" /> Strategist
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((m) => {
              if (m.role === "user" && m.content.startsWith("SYSTEM_AUTO_PROMPT:")) return null;
              
              return (
                <div
                  key={m.id}
                  className={`flex gap-3 ${m.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  {m.role === "assistant" && (
                    <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                      <Bot className="w-4 h-4 text-blue-600" />
                    </div>
                  )}
                  
                  <div
                    className={`max-w-[85%] rounded-lg p-3 ${
                      m.role === "user"
                        ? "bg-blue-600 text-white rounded-tr-none"
                        : "bg-slate-100 text-slate-800 rounded-tl-none"
                    }`}
                  >
                    <div className={`prose prose-sm max-w-none ${m.role === "user" ? "text-white prose-p:text-white prose-strong:text-white" : "prose-slate"}`}>
                      <ReactMarkdown>{m.content}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="p-4 border-t border-slate-200 bg-white">
            <form onSubmit={handleSubmit} className="flex gap-2">
              <input
                className="flex-1 p-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                value={input}
                placeholder="Discuss data sources..."
                onChange={handleInputChange}
              />
              <Button type="submit" disabled={!input?.trim()}>Send</Button>
            </form>
          </div>
        </div>

        {/* Column 2: The Engine */}
        <div className="w-1/3 flex flex-col border-r border-slate-200 bg-white">
          {/* Top Half: URL Queue */}
          <div className="flex flex-col h-1/2 border-b border-slate-200">
            {pendingDocs.length > 0 && (
              <div className="p-4 border-b border-amber-200 bg-amber-50 shrink-0">
                <div className="font-semibold text-sm text-amber-800 flex items-center gap-2 mb-3">
                  <AlertCircle className="w-4 h-4" /> Requires Attention: Large Files
                </div>
                <div className="space-y-3 max-h-48 overflow-y-auto">
                  {pendingDocs.map(doc => (
                    <div key={doc.id} className="bg-white p-3 rounded border border-amber-200 shadow-sm">
                      <a href={doc.url} target="_blank" rel="noopener noreferrer" className="text-xs font-medium truncate mb-1 block hover:underline text-blue-600" title={doc.url}>
                        {doc.url}
                      </a>
                      <div className="text-xs text-slate-500 mb-3">Estimated size: {(doc.estimated_size / 1000).toFixed(1)}k chars</div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" onClick={() => handleProcessPending(doc.id, 'skip')} className="text-xs h-7">Skip</Button>
                        <Button size="sm" variant="outline" onClick={() => {
                          const limit = prompt("Enter character limit (e.g. 50000):", "50000");
                          if (limit && !isNaN(parseInt(limit))) {
                            handleProcessPending(doc.id, 'extract_partial', parseInt(limit));
                          }
                        }} className="text-xs h-7">Extract First X Chars</Button>
                        <Button size="sm" className="bg-amber-600 hover:bg-amber-700 text-white text-xs h-7" onClick={() => handleProcessPending(doc.id, 'extract_all')}>Extract All</Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="p-4 border-b border-slate-200 bg-slate-50 font-semibold text-sm text-slate-700 flex items-center gap-2 shrink-0">
              <Activity className="w-4 h-4" /> URL Queue
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <div className="space-y-3">
                {queue.map((item, idx) => (
                  <div key={idx} className="flex items-center justify-between p-3 border border-slate-100 rounded-lg bg-slate-50">
                    <div className="flex flex-col">
                      <a href={item.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium truncate w-48 hover:underline text-blue-600" title={item.url}>
                        {item.url}
                      </a>
                      <span className="text-xs text-slate-500 mt-1">{item.type}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {item.status === 'completed' && <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100 border-emerald-200"><CheckCircle2 className="w-3 h-3 mr-1" /> Done</Badge>}
                      {item.status === 'extracting' && <Badge className="bg-blue-100 text-blue-700 hover:bg-blue-100 border-blue-200"><RefreshCw className="w-3 h-3 mr-1 animate-spin" /> Extracting</Badge>}
                      {item.status === 'evaluating' && <Badge className="bg-amber-100 text-amber-700 hover:bg-amber-100 border-amber-200"><Search className="w-3 h-3 mr-1 animate-pulse" /> Evaluating</Badge>}
                      {item.status === 'queued' && <Badge className="bg-slate-200 text-slate-700 hover:bg-slate-200 border-slate-300">Queued</Badge>}
                      {item.status === 'failed' && <Badge className="bg-red-100 text-red-700 hover:bg-red-100 border-red-200"><AlertCircle className="w-3 h-3 mr-1" /> Failed/Rejected</Badge>}
                    </div>
                  </div>
                ))}
                {queue.length === 0 && (
                  <div className="text-center text-slate-500 text-sm mt-4">Queue is empty.</div>
                )}
              </div>
            </div>
          </div>
          
          {/* Bottom Half: Dev Assistant Logs */}
          <div className="flex flex-col h-1/2">
            <div className="p-4 border-b border-slate-200 bg-slate-50 font-semibold text-sm text-slate-700 flex items-center gap-2">
              <Terminal className="w-4 h-4" /> Dev Assistant Logs
            </div>
            <div className="flex-1 overflow-y-auto p-4 bg-slate-900 text-emerald-400 font-mono text-xs">
              {logs.map((log, idx) => (
                <div key={idx} className="mb-1">{log}</div>
              ))}
              {logs.length === 0 && (
                <div className="text-slate-500">Waiting for logs...</div>
              )}
              <div ref={logsEndRef} />
            </div>
          </div>
        </div>

        {/* Column 3: The Vault */}
        <div className="w-1/3 flex flex-col bg-slate-50">
          <div className="p-4 border-b border-slate-200 bg-white font-semibold text-sm text-slate-700 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4" /> Semantic Corpus Viewer
            </div>
            <div className="flex items-center gap-2">
              <Button 
                variant="outline" 
                size="sm" 
                className="h-7 text-xs"
                disabled={isAcquiring || totalChunks === 0}
                onClick={() => router.push(`/pipeline/${pipelineId}/explorer`)}
              >
                <ExternalLink className="w-3 h-3 mr-1" /> Data Explorer
              </Button>
              <Button 
                variant="outline" 
                size="sm" 
                className="h-7 text-xs border-violet-200 text-violet-700 hover:bg-violet-50"
                onClick={() => router.push(`/pipeline/${pipelineId}/enrichments`)}
              >
                <Building2 className="w-3 h-3 mr-1" /> Company Dossiers
              </Button>
              <Button 
                variant="outline" 
                size="sm" 
                className="h-7 text-xs border-purple-200 text-purple-700 hover:bg-purple-50"
                disabled={entities.length === 0}
                onClick={() => router.push(`/pipeline/${pipelineId}/graph`)}
              >
                <Database className="w-3 h-3 mr-1" /> View Graph
              </Button>
              <Button 
                variant="outline" 
                size="sm" 
                className="h-7 text-xs border-violet-200 text-violet-700 hover:bg-violet-50"
                disabled={entities.length === 0}
                onClick={() => router.push(`/pipeline/${pipelineId}/communities`)}
              >
                <Users className="w-3 h-3 mr-1" /> Communities
              </Button>
              <Badge variant="secondary" className="bg-blue-100 text-blue-700">
                {totalChunks} Chunks
              </Badge>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {chunks.length === 0 ? (
              <div className="text-center p-8 border border-dashed border-slate-300 rounded-lg text-slate-500">
                No data ingested yet. Start acquisition to populate the vector database.
              </div>
            ) : (
              <div className="space-y-4">
                {chunks.map((chunk, i) => (
                  <div key={i} className="p-4 bg-white border border-slate-200 rounded-lg shadow-sm">
                    <div className="text-xs text-slate-500 mb-2 font-mono truncate" title={chunk.source_url || chunk.source || undefined}>
                      {chunk.source_url ? (
                        <a href={chunk.source_url} target="_blank" rel="noopener noreferrer" className="hover:underline text-blue-600">
                          {chunk.source_url}
                        </a>
                      ) : (
                        chunk.source || "Unknown Source"
                      )}
                    </div>
                    <div className="text-sm text-slate-800 leading-relaxed">
                      {chunk.text_snippet}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
