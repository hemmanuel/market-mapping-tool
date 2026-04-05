"use client";

import { useChat } from "@ai-sdk/react";
import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Send, Bot, User, Settings } from "lucide-react";

export default function OnboardingWizard() {
  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: "/api/chat",
  });

  const [pipelineConfig, setPipelineConfig] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    if (lastMessage?.role === "assistant" && lastMessage.toolInvocations) {
      const toolCall = lastMessage.toolInvocations.find(
        (t) => t.toolName === "finalize_market_map"
      );
      if (toolCall && "args" in toolCall) {
        setPipelineConfig(toolCall.args);
      }
    }
  }, [messages]);

  return (
    <main className="flex h-screen w-full bg-slate-50 text-slate-900">
      <div className="flex flex-col w-1/2 border-r border-slate-200 bg-white">
        <div className="p-4 border-b border-slate-200 bg-slate-50 flex items-center gap-2">
          <Bot className="w-5 h-5 text-blue-600" />
          <h1 className="font-semibold text-lg">The Consultant</h1>
        </div>
        
        <ScrollArea className="flex-1 p-4">
          <div className="flex flex-col gap-4">
            {messages.length === 0 && (
              <div className="text-center text-slate-500 mt-10">
                <p>Hello! I am your Market Intelligence Consultant.</p>
                <p className="text-sm">What niche are we mapping today?</p>
              </div>
            )}
            
            {messages.map((m) => (
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
                  className={`max-w-[80%] rounded-lg p-3 ${
                    m.role === "user"
                      ? "bg-blue-600 text-white rounded-tr-none"
                      : "bg-slate-100 text-slate-800 rounded-tl-none"
                  }`}
                >
                  {m.content && <p className="whitespace-pre-wrap text-sm">{m.content}</p>}
                  
                  {m.toolInvocations?.map((toolInvocation) => {
                    if (toolInvocation.toolName === "finalize_market_map") {
                      return (
                        <div key={toolInvocation.toolCallId} className="mt-2 p-2 bg-slate-200 rounded border border-slate-300 text-xs text-slate-600 flex items-center gap-2">
                          <Settings className="w-3 h-3" />
                          <span>Generating pipeline configuration...</span>
                        </div>
                      );
                    }
                    return null;
                  })}
                </div>
                
                {m.role === "user" && (
                  <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center shrink-0">
                    <User className="w-4 h-4 text-slate-600" />
                  </div>
                )}
              </div>
            ))}
            {isLoading && (
              <div className="flex gap-3 justify-start">
                <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                  <Bot className="w-4 h-4 text-blue-600" />
                </div>
                <div className="bg-slate-100 text-slate-800 rounded-lg rounded-tl-none p-3 flex items-center gap-1">
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" />
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0.2s" }} />
                  <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0.4s" }} />
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        <div className="p-4 border-t border-slate-200 bg-white">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              value={input}
              onChange={handleInputChange}
              placeholder="Describe your market niche..."
              className="flex-1"
              disabled={isLoading}
            />
            <Button type="submit" disabled={isLoading || !input.trim()}>
              <Send className="w-4 h-4" />
            </Button>
          </form>
        </div>
      </div>

      <div className="flex flex-col w-1/2 bg-slate-900 text-slate-300 font-mono text-sm">
        <div className="p-4 border-b border-slate-800 bg-slate-950 flex items-center gap-2">
          <Settings className="w-5 h-5 text-emerald-500" />
          <h2 className="font-semibold text-lg text-slate-100">The Factory: Pipeline Config</h2>
        </div>
        
        <ScrollArea className="flex-1 p-6">
          {pipelineConfig ? (
            <pre className="text-emerald-400 whitespace-pre-wrap">
              {JSON.stringify(pipelineConfig, null, 2)}
            </pre>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-slate-600 mt-20">
              <Settings className="w-12 h-12 mb-4 opacity-20" />
              <p>Awaiting configuration from The Consultant...</p>
              <p className="text-xs mt-2 max-w-sm text-center">
                Once the AI understands your niche, it will generate the deterministic JSON payload here.
              </p>
            </div>
          )}
        </ScrollArea>
        
        {pipelineConfig && (
          <div className="p-4 border-t border-slate-800 bg-slate-950 flex justify-end">
            <Button className="bg-emerald-600 hover:bg-emerald-700 text-white">
              Deploy Pipeline
            </Button>
          </div>
        )}
      </div>
    </main>
  );
}
