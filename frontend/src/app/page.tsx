"use client";

import { useChat } from "ai/react";
import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Send, Bot, User, Settings, Plus, Trash2 } from "lucide-react";
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

  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
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
            }
            break;
          case 'add_entity':
            if (!config.schema?.entities.includes(args.entity_name)) {
              setConfig(prev => ({
                ...prev,
                schema: {
                  ...prev.schema!,
                  entities: [...(prev.schema?.entities || []), args.entity_name]
                }
              }));
            }
            break;
          case 'remove_entity':
            setConfig(prev => ({
              ...prev,
              schema: {
                ...prev.schema!,
                entities: prev.schema?.entities.filter(e => e !== args.entity_name) || []
              }
            }));
            break;
          case 'finalize_entities':
            setCurrentStep('relationships');
            break;
          case 'add_relationship':
            setConfig(prev => {
              const exists = prev.schema?.relationships.some(
                r => r.source === args.source && r.type === args.type && r.target === args.target
              );
              if (exists) return prev;
              return {
                ...prev,
                schema: {
                  ...prev.schema!,
                  relationships: [...(prev.schema?.relationships || []), {
                    source: args.source,
                    type: args.type,
                    target: args.target
                  }]
                }
              };
            });
            break;
          case 'finalize_relationships':
            setCurrentStep('sources');
            break;
          case 'add_source':
            if (!config.sources.find(s => s.url === args.url)) {
              setConfig(prev => ({
                ...prev,
                sources: [...prev.sources, {
                  type: args.type,
                  url: args.url,
                  name: args.name
                }]
              }));
            }
            break;
          case 'remove_source':
            setConfig(prev => ({
              ...prev,
              sources: prev.sources.filter(s => s.url !== args.url)
            }));
            break;
          case 'finalize_sources':
            setCurrentStep('review');
            break;
        }
      });
    }
  }, [messages, config.niche, config.schema, config.sources]);

  // Update config.currentStep when currentStep changes
  useEffect(() => {
    setConfig(prev => ({ ...prev, currentStep }));
  }, [currentStep]);

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
              <h1 className="font-semibold text-lg">The Consultant</h1>
            </div>
            <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
              Phase: {currentStep.toUpperCase()}
            </Badge>
          </div>
          
          <ScrollArea className="flex-1 p-4">
            <div className="flex flex-col gap-4">
              {messages.length === 0 && (
                <div className="text-center text-slate-500 mt-10">
                  <p>Hello! I am your Market Intelligence Consultant.</p>
                  <p className="text-sm mt-2">Let&apos;s start by defining the specific market ecosystem you want to map.</p>
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
                      return (
                        <div key={toolInvocation.toolCallId} className="mt-2 p-2 bg-slate-200 rounded border border-slate-300 text-xs text-slate-600 flex items-center gap-2">
                          <Settings className="w-3 h-3" />
                          <span className="font-mono">{toolInvocation.toolName}</span>
                        </div>
                      );
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
                placeholder="Chat with the consultant..."
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
          <div className="flex flex-col w-1/2 bg-slate-50 border-l border-slate-200 animate-in slide-in-from-right-1/2 duration-500">
            <div className="p-4 border-b border-slate-200 bg-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Settings className="w-5 h-5 text-emerald-600" />
                <h2 className="font-semibold text-lg">The Factory</h2>
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
            
            <ScrollArea className="flex-1 p-6">
              <div className="space-y-6 max-w-2xl mx-auto">
                
                {/* Niche Card */}
                <Card className="opacity-70">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium text-slate-500 uppercase tracking-wider">1. Market Niche</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {config.niche ? (
                      <div className="text-xl font-semibold text-slate-900">{config.niche}</div>
                    ) : (
                      <div className="text-sm text-slate-400 italic">Chat with the consultant to define your niche...</div>
                    )}
                  </CardContent>
                </Card>

                {/* Entities Card */}
                {(currentStep === 'entities' || currentStep === 'relationships' || currentStep === 'sources' || currentStep === 'review') && (
                  <Card className={currentStep === 'entities' ? 'border-blue-400 shadow-sm' : 'opacity-70'}>
                    <CardHeader className="pb-3 flex flex-row items-center justify-between">
                      <CardTitle className="text-sm font-medium text-slate-500 uppercase tracking-wider">2. Entities</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div>
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
                    </CardContent>
                  </Card>
                )}

                {/* Relationships Card */}
                {(currentStep === 'relationships' || currentStep === 'sources' || currentStep === 'review') && (
                  <Card className={currentStep === 'relationships' ? 'border-blue-400 shadow-sm' : 'opacity-70'}>
                    <CardHeader className="pb-3 flex flex-row items-center justify-between">
                      <CardTitle className="text-sm font-medium text-slate-500 uppercase tracking-wider">3. Relationships</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div>
                        <div className="space-y-2 mb-3">
                          {config.schema?.relationships.map((rel, idx) => (
                            <div key={idx} className="flex items-center gap-2 text-sm bg-slate-100 p-2 rounded border border-slate-200">
                              <Badge variant="outline" className="bg-white">{rel.source}</Badge>
                              <span className="text-slate-400 font-mono text-xs">-[{rel.type}]-&gt;</span>
                              <Badge variant="outline" className="bg-white">{rel.target}</Badge>
                            </div>
                          ))}
                          {config.schema?.relationships.length === 0 && <span className="text-sm text-slate-400 italic">No relationships defined.</span>}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Sources Card */}
                {(currentStep === 'sources' || currentStep === 'review') && (
                  <Card className={currentStep === 'sources' ? 'border-blue-400 shadow-sm' : 'opacity-70'}>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-medium text-slate-500 uppercase tracking-wider">4. Data Sources</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2">
                        {config.sources.map((source, idx) => (
                          <div key={idx} className="flex items-center justify-between bg-slate-100 p-3 rounded border border-slate-200">
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
                        <form onSubmit={handleAddSource} className="flex flex-col gap-2 pt-2 border-t border-slate-100">
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
                    </CardContent>
                  </Card>
                )}
                
              </div>
            </ScrollArea>
          </div>
        )}
      </div>
    </main>
  );
}
