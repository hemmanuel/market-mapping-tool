"use client";

import { useState, useEffect, useRef } from "react";
import { useParams } from "next/navigation";
import { useChat } from "ai/react";
import ReactMarkdown from "react-markdown";
import { useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Play, RefreshCw, Database, Activity, CheckCircle2, AlertCircle, Bot, Terminal } from "lucide-react";

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

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [queue, setQueue] = useState<any[]>([]);
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
      // We need to wait for Clerk to be ready, but getToken is async and safe to call
      startAcquisition();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

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
      const token = await getToken();
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

  useEffect(() => {
    const eventSource = new EventSource(`http://localhost:8000/api/v1/pipelines/${pipelineId}/logs`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'log') {
          setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${data.message}`]);
        } else if (data.type === 'queue') {
          setQueue(data.data);
        } else if (data.type === 'new_data') {
          if (data.entities && data.entities.length > 0) {
            setEntities(prev => [...prev, ...data.entities]);
          }
          if (data.relationships && data.relationships.length > 0) {
            setRelationships(prev => [...prev, ...data.relationships]);
          }
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
              <Button type="submit" disabled={!input.trim()}>Send</Button>
            </form>
          </div>
        </div>

        {/* Column 2: The Engine */}
        <div className="w-1/3 flex flex-col border-r border-slate-200 bg-white">
          {/* Top Half: URL Queue */}
          <div className="flex flex-col h-1/2 border-b border-slate-200">
            <div className="p-4 border-b border-slate-200 bg-slate-50 font-semibold text-sm text-slate-700 flex items-center gap-2">
              <Activity className="w-4 h-4" /> URL Queue
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <div className="space-y-3">
                {queue.map((item, idx) => (
                  <div key={idx} className="flex items-center justify-between p-3 border border-slate-100 rounded-lg bg-slate-50">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium truncate w-48" title={item.url}>{item.url}</span>
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
