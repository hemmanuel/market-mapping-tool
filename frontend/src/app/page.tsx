"use client";

import { useChat } from "ai/react";
import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Send, Bot, User, Settings, Plus, Trash2, Target, Database, Network, Link, CheckCircle2 } from "lucide-react";
import { OnboardingStep, PipelineConfig, DataSource } from "@/lib/types";
import { Timeline } from "@/components/Timeline";

export default function OnboardingWizard() {
  const [currentStep, setCurrentStep] = useState<OnboardingStep>('niche');
  const [config, setConfig] = useState<PipelineConfig>({
    currentStep: 'niche',
    niche: null,
    schema: { entities: [], relationships: [] },
    sources: []
  });

  const [isDeploying, setIsDeploying] = useState(false);
  const [deploySuccess, setDeploySuccess] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { messages, input, handleInputChange, handleSubmit, isLoading, setMessages, append } = useChat({
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
          case 'sync_entities_state':
            setConfig(prev => ({
              ...prev,
              schema: {
                ...prev.schema!,
                entities: args.entities
              }
            }));
            if (args.is_finished && currentStep !== 'relationships') {
              setCurrentStep('relationships');
              setTimeout(() => {
                append({
                  role: 'user',
                  content: `SYSTEM_AUTO_PROMPT: We are now in the Relationships step. Please briefly explain to me what relationships mean in this context (e.g., "Company -[RAISED]-> Funding Round"), deduce the basic logical relationships between our defined entities, add them to the schema using the tool, and ask me if I want to add more or remove any.`
                });
              }, 500);
            }
            break;
          case 'sync_relationships_state':
            setConfig(prev => ({
              ...prev,
              schema: {
                ...prev.schema!,
                relationships: args.relationships
              }
            }));
            if (args.is_finished && currentStep !== 'sources') {
              setCurrentStep('sources');
              setTimeout(() => {
                append({
                  role: 'user',
                  content: `SYSTEM_AUTO_PROMPT: We are now in the Data Sources step. Please briefly explain what data sources are (e.g., RSS feeds, APIs, websites), suggest some relevant sources for our niche, add them to the schema using the tool, and ask me if I want to add more or remove any.`
                });
              }, 500);
            }
            break;
          case 'sync_sources_state':
            setConfig(prev => ({
              ...prev,
              sources: args.sources
            }));
            if (args.is_finished && currentStep !== 'review') {
              setCurrentStep('review');
              setTimeout(() => {
                append({
                  role: 'user',
                  content: `SYSTEM_AUTO_PROMPT: We are now in the Review step. Please congratulate me on finishing the configuration, summarize the pipeline we just built, and tell me to click the Deploy Pipeline button in the right pane when I'm ready.`
                });
              }, 500);
            }
            break;
        }
      });
    }
  }, [messages, config.niche, config.schema, config.sources]);

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

  const handleAddSource = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const nameInput = form.elements.namedItem('sourceName') as HTMLInputElement;
    const urlInput = form.elements.namedItem('sourceUrl') as HTMLInputElement;
    const typeSelect = form.elements.namedItem('sourceType') as HTMLSelectElement;
    
    const name = nameInput.value.trim();
    const url = urlInput.value.trim();
    const type = typeSelect.value as DataSource['type'];
    
    if (name && url && !config.sources.find(s => s.url === url)) {
      setConfig(prev => ({
        ...prev,
        sources: [...prev.sources, { name, url, type }]
      }));
      nameInput.value = '';
      urlInput.value = '';
    }
  };

  const handleDeploy = async () => {
    setIsDeploying(true);
    try {
      const res = await fetch('http://localhost:8000/api/v1/pipelines', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config),
      });

      if (!res.ok) {
        throw new Error('Failed to deploy pipeline');
      }

      setDeploySuccess(true);
    } catch (error) {
      console.error(error);
      alert('Failed to deploy pipeline. Check console for details.');
    } finally {
      setIsDeploying(false);
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
                if (m.role === "assistant" && !m.content) return null;
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
                      {m.content && (
                        <div className={`prose prose-sm max-w-none ${m.role === "user" ? "text-white prose-p:text-white prose-strong:text-white" : "prose-slate"}`}>
                          <ReactMarkdown>
                            {m.content}
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
              <Button type="submit" disabled={isLoading || !input.trim()}>
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
              {currentStep === 'review' && (
                <Button 
                  size="sm" 
                  className={deploySuccess ? "bg-blue-600 hover:bg-blue-700 text-white" : "bg-emerald-600 hover:bg-emerald-700 text-white"}
                  onClick={handleDeploy}
                  disabled={isDeploying || deploySuccess}
                >
                  {isDeploying ? 'Deploying...' : deploySuccess ? 'Deployed Successfully!' : 'Deploy Pipeline'}
                </Button>
              )}
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

                {/* Step 4: Data Sources */}
                <div className={`relative flex items-start gap-4 ${(currentStep === 'sources' || currentStep === 'review') ? 'opacity-100' : 'opacity-50'}`}>
                  <div className={`z-10 flex items-center justify-center w-10 h-10 rounded-full border-2 bg-white ${currentStep === 'review' ? 'border-emerald-500 text-emerald-500' : currentStep === 'sources' ? 'border-blue-600 text-blue-600' : 'border-slate-300 text-slate-400'}`}>
                    {currentStep === 'review' ? <CheckCircle2 className="w-5 h-5" /> : <Link className="w-5 h-5" />}
                  </div>
                  <div className="flex-1 pt-1.5 pb-6">
                    <h3 className="text-base font-semibold text-slate-900">Data Sources</h3>
                    {(currentStep === 'sources' || currentStep === 'review') ? (
                      <div className="mt-2 p-4 bg-white border border-slate-200 rounded-md shadow-sm">
                        <div className="space-y-2">
                          {config.sources.map((source, idx) => (
                            <div key={idx} className="flex items-center justify-between bg-slate-50 p-3 rounded border border-slate-100">
                              <div>
                                <div className="font-medium text-sm flex items-center gap-2">
                                  {source.name} <Badge variant="outline" className="text-[10px] h-5">{source.type}</Badge>
                                </div>
                                <div className="text-xs text-slate-500 font-mono mt-1 truncate max-w-sm">{source.url}</div>
                              </div>
                              {currentStep === 'sources' && (
                                <Button size="icon" variant="ghost" className="h-8 w-8 text-slate-400 hover:text-red-500" onClick={() => setConfig(prev => ({...prev, sources: prev.sources.filter(s => s.url !== source.url)}))}>
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              )}
                            </div>
                          ))}
                          {config.sources.length === 0 && <div className="text-sm text-slate-400 italic p-4 text-center border border-dashed rounded">No data sources added yet.</div>}
                        </div>
                        
                        {currentStep === 'sources' && (
                          <form onSubmit={handleAddSource} className="flex flex-col gap-2 pt-4 mt-4 border-t border-slate-100">
                            <div className="flex gap-2">
                              <Input name="sourceName" placeholder="Source Name" className="text-sm flex-1" required />
                              <select name="sourceType" className="flex h-10 w-32 items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50">
                                <option value="rss">RSS</option>
                                <option value="api">API</option>
                                <option value="webhook">Webhook</option>
                                <option value="custom">Custom</option>
                              </select>
                            </div>
                            <div className="flex gap-2">
                              <Input name="sourceUrl" placeholder="URL (e.g., https://...)" className="text-sm flex-1" required />
                              <Button type="submit" size="sm" variant="secondary"><Plus className="w-4 h-4 mr-1" /> Add</Button>
                            </div>
                          </form>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-slate-500 mt-1">Connect external data feeds.</p>
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
