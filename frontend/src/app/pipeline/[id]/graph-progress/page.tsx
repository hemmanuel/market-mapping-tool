"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Database, Terminal, ArrowLeft, CheckCircle2, AlertCircle, RefreshCw, Square } from "lucide-react";

export default function GraphProgressPage() {
  const params = useParams();
  const router = useRouter();
  const pipelineId = params.id as string;
  const { getToken } = useAuth();

  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);
  const [currentPhase, setCurrentPhase] = useState("Initializing...");
  const [status, setStatus] = useState<"running" | "complete" | "error" | "cancelled">("running");
  
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  useEffect(() => {
    const eventSource = new EventSource(`http://localhost:8000/api/v1/pipelines/${pipelineId}/logs`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'graph_progress') {
          setCurrentPhase(data.current_phase);
          
          if (data.total_chunks > 0) {
            setProgress(Math.round((data.processed_chunks / data.total_chunks) * 100));
          }

          if (data.current_phase === 'Complete') {
            setStatus("complete");
            setProgress(100);
          } else if (data.current_phase === 'Error') {
            setStatus("error");
          } else if (data.current_phase === 'Cancelled') {
            setStatus("cancelled");
          }

          setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${data.message}`]);
        }
      } catch (err) {
        console.error("Failed to parse SSE message", err);
      }
    };

    eventSource.onerror = (err) => {
      console.error("EventSource failed:", err);
    };

    return () => {
      eventSource.close();
    };
  }, [pipelineId]);

  const stopGeneration = async () => {
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(`http://localhost:8000/api/v1/pipelines/${pipelineId}/cancel-graph`, {
        method: 'POST',
        headers
      });
      if (!res.ok) throw new Error("Failed to stop graph generation");
    } catch (error) {
      console.error(error);
      alert("Failed to stop graph generation.");
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
          <h1 className="text-xl font-bold">Graph Generation</h1>
        </div>
        <div className="flex gap-3">
          {status === "running" && (
            <Button 
              onClick={stopGeneration} 
              variant="destructive"
            >
              <Square className="w-4 h-4 mr-2 fill-current" /> Stop Generation
            </Button>
          )}
          {status === "complete" && (
            <Button 
              onClick={() => router.push(`/pipeline/${pipelineId}/graph`)} 
              className="bg-purple-600 hover:bg-purple-700"
            >
              <Database className="w-4 h-4 mr-2" /> View Graph
            </Button>
          )}
        </div>
      </header>

      <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full p-8 gap-8">
        {/* Progress Section */}
        <div className="bg-white p-8 rounded-xl border border-slate-200 shadow-sm flex flex-col items-center justify-center text-center">
          {status === "running" && <RefreshCw className="w-12 h-12 text-purple-600 animate-spin mb-4" />}
          {status === "complete" && <CheckCircle2 className="w-12 h-12 text-emerald-500 mb-4" />}
          {status === "error" && <AlertCircle className="w-12 h-12 text-red-500 mb-4" />}
          {status === "cancelled" && <Square className="w-12 h-12 text-amber-500 mb-4" />}
          
          <h2 className="text-2xl font-bold mb-2">{currentPhase}</h2>
          
          <div className="w-full max-w-md bg-slate-100 rounded-full h-4 mt-6 overflow-hidden border border-slate-200">
            <div 
              className={`h-full transition-all duration-500 ${status === 'error' ? 'bg-red-500' : status === 'complete' ? 'bg-emerald-500' : status === 'cancelled' ? 'bg-amber-500' : 'bg-purple-600'}`}
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-sm text-slate-500 mt-3">{progress}% Complete</p>
        </div>

        {/* Logs Section */}
        <div className="flex-1 bg-slate-900 rounded-xl border border-slate-800 shadow-sm overflow-hidden flex flex-col">
          <div className="p-3 border-b border-slate-800 bg-slate-950 font-semibold text-sm text-slate-300 flex items-center gap-2">
            <Terminal className="w-4 h-4" /> Generation Logs
          </div>
          <div className="flex-1 overflow-y-auto p-4 font-mono text-xs text-emerald-400">
            {logs.map((log, idx) => (
              <div key={idx} className="mb-1">{log}</div>
            ))}
            {logs.length === 0 && (
              <div className="text-slate-500">Waiting for generation to start...</div>
            )}
            <div ref={logsEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}