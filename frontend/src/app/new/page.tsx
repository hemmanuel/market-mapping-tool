"use client";

import { useChat } from "ai/react";
import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Send, Bot, User, Settings, Plus, Trash2, Target, Database, Network, CheckCircle2 } from "lucide-react";
import { OnboardingStep, PipelineConfig } from "@/lib/types";
import { Timeline } from "@/components/Timeline";
import { useRouter } from "next/navigation";

// Add global type for Clerk
declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    Clerk?: any;
  }
}

export default function OnboardingWizard() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState<OnboardingStep>('niche');
  const [config, setConfig] = useState<PipelineConfig>({
    currentStep: 'niche',
    niche: null,
    schema: { entities: [], relationships: [] },
    sources: []
  });

  const [, setIsDeploying] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { messages, input, handleInputChange, handleSubmit, isLoading, append } = useChat({
    api: "/api/chat",
    body: {
      currentStep,
      currentConfig: config
    }
  });

  // Handle tool calls to update state
  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    if (lastMessage?.role === "assistant" && lastMessage.toolInvocations) {
      lastMessage.toolInvocations.forEach((toolCall) => {
        if (!('args' in toolCall)) return;
        
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const args = toolCall.args as any;
        
        switch (toolCall.toolName) {
          case 'lock_in_niche':
            if (config.niche !== args.niche_name) {
              setConfig(prev => ({ ...prev, niche: args.niche_name }));
              setCurrentStep('entities');
              setTimeout(() => {
                append({
                  role: 'user',
                  content: `SYSTEM_AUTO_PROMPT: We are now in the Entities step. Please explain what entities are in this context, deduce the core entities we should track for the "${args.niche_name}" market, add them to the schema using the tool, and ask me if I want to add more or remove any.`
                });
              }, 500);
            }
            break;
          case 'sync_entities':
            if (JSON.stringify(config.schema?.entities) !== JSON.stringify(args.entities)) {
              setConfig(prev => ({
                ...prev,
                schema: {
                  ...prev.schema!,
                  entities: args.entities
                }
              }));
            }
            break;
          case 'finalize_entities':
            if (currentStep !== 'relationships') {
              setCurrentStep('relationships');
              setTimeout(() => {
                append({
                  role: 'user',
                  content: `SYSTEM_AUTO_PROMPT: We are now in the Relationships step. Please briefly explain to me what relationships mean in this context (e.g., "Company -[RAISED]-> Funding Round"), deduce the basic logical relationships between our defined entities, add them to the schema using the tool, and ask me if I want to add more or remove any.`
                });
              }, 500);
            }
            break;
          case 'sync_relationships':
            const newRelationships = JSON.stringify(args.relationships);
            const oldRelationships = JSON.stringify(config.schema?.relationships);
            const newEntities = JSON.stringify(args.entities || config.schema?.entities);
            const oldEntities = JSON.stringify(config.schema?.entities);
            
            if (newRelationships !== oldRelationships || newEntities !== oldEntities) {
              setConfig(prev => ({
                ...prev,
                schema: {
                  ...prev.schema!,
                  relationships: args.relationships,
                  entities: args.entities || prev.schema!.entities
                }
              }));
            }
            break;
          case 'finalize_relationships':
            if (currentStep !== 'sources') {
              setCurrentStep('sources'); // Advance step to prevent re-triggering
              setIsDeploying(true);
              
              const finalConfig = {
                ...config,
                schema: {
                  entities: config.schema?.entities || [],
                  relationships: config.schema?.relationships || []
                }
              };
              
              // Add a small delay to let the UI update before redirecting
              setTimeout(async () => {
                try {
                  // We need to get the Clerk token to authenticate the request
                  // Fetching it directly from window.Clerk avoids adding hooks to the dependency array
                  const token = await window.Clerk?.session?.getToken();
                  
                  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
                  if (token) {
                    headers['Authorization'] = `Bearer ${token}`;
                  }

                  const res = await fetch('http://localhost:8000/api/v1/pipelines', {
                    method: 'POST',
                    headers,
                    body: JSON.stringify(finalConfig),
                  });

                  if (!res.ok) {
                    throw new Error(`Server returned ${res.status}`);
                  }

                  const data = await res.json();
                  
                  if (data.site_id) {
                    window.location.href = `/pipeline/${data.site_id}/data?autoStart=true`;
                  } else {
                    console.error("No site_id in response:", data);
                    setIsDeploying(false);
                    alert('Failed to save pipeline: Invalid response from server');
                  }
                } catch (err) {
                  console.error(err);
                  setIsDeploying(false);
                  alert('Failed to save pipeline. Check console for details.');
                }
              }, 1000);
            }
            break;
        }
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, config.niche, config.schema, config.sources, append, currentStep]);

  // Update config.currentStep when currentStep changes
  useEffect(() => {
    setConfig(prev => ({ ...prev, currentStep }));
  }, [currentStep]);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Handlers for manual form edits
  const handleAddEntity = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const input = form.elements.namedItem('entityName') as HTMLInputElement;
    const val = input.value.trim();
    if (val && !config.schema?.entities.includes(val)) {
      setConfig(prev => ({
        ...prev,
        schema: {
          ...prev.schema!,
          entities: [...(prev.schema?.entities || []), val]
        }
      }));
      input.value = '';
    }
  };



  const isPaneVisible = currentStep !== 'niche';

  return (
    <main className="flex flex-col h-screen w-full bg-slate-50 text-slate-900">
      <Timeline currentStep={currentStep} />
      
      <div className="flex flex-1 overflow-hidden">
        {/* Left Pane: The Consultant (Chat) */}
        <div className={`flex flex-col min-h-0 transition-all duration-500 ${isPaneVisible ? 'w-1/2 border-r border-slate-200' : 'w-full max-w-3xl mx-auto'} bg-white`}>
          <div className="p-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard")} className="mr-2 text-slate-500 hover:text-slate-700">
                &larr; Dashboard
              </Button>
              <Bot className="w-5 h-5 text-blue-600" />
              <h1 className="font-semibold text-lg">Market Map Creator</h1>
            </div>
            <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
              Phase: {currentStep.toUpperCase()}
            </Badge>
          </div>
          
          <div className="flex-1 overflow-y-auto p-4">
            <div className="flex flex-col gap-4">
              {messages.length === 0 && (
                <div className="text-center text-slate-500 mt-10">
                  <p>Hello! I am your Market Map Creator.</p>
                  <p className="text-sm mt-2">Let&apos;s start by defining the specific market ecosystem you want to map.</p>
                </div>
              )}
              
              {messages.map((m) => {
                // Extract the message from the tool call if it exists
                const toolCall = m.toolInvocations?.[0];
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const toolMessage = toolCall && 'args' in toolCall ? (toolCall.args as any).message_to_user : null;
                const contentToRender = m.content || toolMessage;

                if (m.role === "assistant" && !contentToRender) return null;
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
                      className={`max-w-[80%] rounded-lg p-3 ${
                        m.role === "user"
                          ? "bg-blue-600 text-white rounded-tr-none"
                          : "bg-slate-100 text-slate-800 rounded-tl-none"
                      }`}
                    >
                      {contentToRender && (
                        <div className={`prose prose-sm max-w-none ${m.role === "user" ? "text-white prose-p:text-white prose-strong:text-white" : "prose-slate"}`}>
                          <ReactMarkdown>
                            {contentToRender}
                          </ReactMarkdown>
                        </div>
                      )}
                    </div>
                    
                    {m.role === "user" && (
                      <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center shrink-0">
                        <User className="w-4 h-4 text-slate-600" />
                      </div>
                    )}
                  </div>
                );
              })}
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
              <div ref={messagesEndRef} />
            </div>
          </div>

          <div className="p-4 border-t border-slate-200 bg-white">
            <form onSubmit={handleSubmit} className="flex gap-2">
              <Input
                value={input}
                onChange={handleInputChange}
                placeholder="Chat with the creator..."
                className="flex-1"
                disabled={isLoading}
              />
              <Button type="submit" disabled={isLoading || !input?.trim()}>
                <Send className="w-4 h-4" />
              </Button>
            </form>
          </div>
        </div>

        {/* Right Pane: The Factory (Interactive Forms) */}
        {isPaneVisible && (
          <div className="flex flex-col w-1/2 min-h-0 bg-slate-50 border-l border-slate-200 animate-in slide-in-from-right-1/2 duration-500">
            <div className="p-4 border-b border-slate-200 bg-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Settings className="w-5 h-5 text-emerald-600" />
                <h2 className="font-semibold text-lg">Define Market</h2>
              </div>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6">
              <div className="space-y-6 max-w-2xl mx-auto relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-200 before:to-transparent">
                
                {/* Step 1: Niche */}
                <div className="relative flex items-start gap-4 opacity-100">
                  <div className={`z-10 flex items-center justify-center w-10 h-10 rounded-full border-2 bg-white ${config.niche ? 'border-emerald-500 text-emerald-500' : 'border-blue-600 text-blue-600'}`}>
                    {config.niche ? <CheckCircle2 className="w-5 h-5" /> : <Target className="w-5 h-5" />}
                  </div>
                  <div className="flex-1 pt-1.5 pb-6">
                    <h3 className="text-base font-semibold text-slate-900">Market Niche</h3>
                    {config.niche ? (
                      <div className="mt-2 p-3 bg-emerald-50 border border-emerald-100 rounded-md text-emerald-800 font-medium">
                        {config.niche}
                      </div>
                    ) : (
                      <p className="text-sm text-slate-500 mt-1">Chat with the creator to define your focus area.</p>
                    )}
                  </div>
                </div>

                {/* Step 2: Entities */}
                <div className={`relative flex items-start gap-4 ${(currentStep === 'entities' || currentStep === 'relationships' || currentStep === 'sources' || currentStep === 'review') ? 'opacity-100' : 'opacity-50'}`}>
                  <div className={`z-10 flex items-center justify-center w-10 h-10 rounded-full border-2 bg-white ${(currentStep === 'relationships' || currentStep === 'sources' || currentStep === 'review') ? 'border-emerald-500 text-emerald-500' : currentStep === 'entities' ? 'border-blue-600 text-blue-600' : 'border-slate-300 text-slate-400'}`}>
                    {(currentStep === 'relationships' || currentStep === 'sources' || currentStep === 'review') ? <CheckCircle2 className="w-5 h-5" /> : <Database className="w-5 h-5" />}
                  </div>
                  <div className="flex-1 pt-1.5 pb-6">
                    <h3 className="text-base font-semibold text-slate-900">Entities</h3>
                    {(currentStep === 'entities' || currentStep === 'relationships' || currentStep === 'sources' || currentStep === 'review') ? (
                      <div className="mt-2 p-4 bg-white border border-slate-200 rounded-md shadow-sm">
                        <div className="flex flex-wrap gap-2 mb-3">
                          {config.schema?.entities.map(entity => (
                            <Badge key={entity} variant="secondary" className="px-2 py-1 flex items-center gap-1">
                              {entity}
                              {currentStep === 'entities' && (
                                <button onClick={() => setConfig(prev => ({...prev, schema: {...prev.schema!, entities: prev.schema!.entities.filter(e => e !== entity)}}))} className="ml-1 hover:text-red-500">
                                  <Trash2 className="w-3 h-3" />
                                </button>
                              )}
                            </Badge>
                          ))}
                          {config.schema?.entities.length === 0 && <span className="text-sm text-slate-400 italic">No entities defined.</span>}
                        </div>
                        {currentStep === 'entities' && (
                          <form onSubmit={handleAddEntity} className="flex gap-2">
                            <Input name="entityName" placeholder="Add entity (e.g., Company)" className="h-8 text-sm" />
                            <Button type="submit" size="sm" variant="secondary" className="h-8"><Plus className="w-4 h-4" /></Button>
                          </form>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-slate-500 mt-1">Define the key entities to track.</p>
                    )}
                  </div>
                </div>

                {/* Step 3: Relationships */}
                <div className={`relative flex items-start gap-4 ${(currentStep === 'relationships' || currentStep === 'sources' || currentStep === 'review') ? 'opacity-100' : 'opacity-50'}`}>
                  <div className={`z-10 flex items-center justify-center w-10 h-10 rounded-full border-2 bg-white ${(currentStep === 'sources' || currentStep === 'review') ? 'border-emerald-500 text-emerald-500' : currentStep === 'relationships' ? 'border-blue-600 text-blue-600' : 'border-slate-300 text-slate-400'}`}>
                    {(currentStep === 'sources' || currentStep === 'review') ? <CheckCircle2 className="w-5 h-5" /> : <Network className="w-5 h-5" />}
                  </div>
                  <div className="flex-1 pt-1.5 pb-6">
                    <h3 className="text-base font-semibold text-slate-900">Relationships</h3>
                    {(currentStep === 'relationships' || currentStep === 'sources' || currentStep === 'review') ? (
                      <div className="mt-2 p-4 bg-white border border-slate-200 rounded-md shadow-sm">
                        <div className="space-y-2">
                          {config.schema?.relationships.map((rel, idx) => (
                            <div key={idx} className="flex items-center gap-2 text-sm bg-slate-50 p-2 rounded border border-slate-100">
                              <Badge variant="outline" className="bg-white">{rel.source}</Badge>
                              <span className="text-slate-400 font-mono text-xs">-[{rel.type}]-&gt;</span>
                              <Badge variant="outline" className="bg-white">{rel.target}</Badge>
                            </div>
                          ))}
                          {config.schema?.relationships.length === 0 && <span className="text-sm text-slate-400 italic">No relationships defined.</span>}
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-slate-500 mt-1">Map how entities connect to each other.</p>
                    )}
                  </div>
                </div>

              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
