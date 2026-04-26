"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { CompanyDossier } from "@/components/company-dossier";
import {
  buildDossierViewModelFromArtifact,
  EnrichmentArtifact,
  EnrichmentArtifactsResponse,
  hasSparseEvidence,
  NormalizedEnrichmentsResponse,
  normalizeCompanyName,
} from "@/lib/enrichment";
import { PipelineEntitiesResponse, PipelineEntity } from "@/lib/pipeline-types";
import {
  ArrowLeft,
  Building2,
  Database,
  ExternalLink,
  FileText,
  RefreshCw,
  Search,
} from "lucide-react";

interface DocumentViewResponse {
  title: string;
  source_url: string;
  viewer_url?: string | null;
  content?: string | null;
}

export default function PipelineEnrichmentsPage() {
  const params = useParams();
  const router = useRouter();
  const pipelineId = params.id as string;
  const { getToken } = useAuth();

  const [artifacts, setArtifacts] = useState<EnrichmentArtifact[]>([]);
  const [normalizedAvailable, setNormalizedAvailable] = useState(false);
  const [companyNodes, setCompanyNodes] = useState<PipelineEntity[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [stageFilter, setStageFilter] = useState("all");
  const [selectedCompanyKey, setSelectedCompanyKey] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedDocument, setSelectedDocument] = useState<string | null>(null);
  const [documentData, setDocumentData] = useState<DocumentViewResponse | null>(null);
  const [isDocumentLoading, setIsDocumentLoading] = useState(false);

  const loadData = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const token = await getToken();
      const headers: Record<string, string> = {};

      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const [artifactsResponse, normalizedResponse, entitiesResponse] = await Promise.all([
        fetch(`http://localhost:8000/api/v1/pipelines/${pipelineId}/enrichment-artifacts`, {
          headers,
        }),
        fetch(`http://localhost:8000/api/v1/pipelines/${pipelineId}/enrichments`, { headers }),
        fetch(`http://localhost:8000/api/v1/pipelines/${pipelineId}/entities?theme=companies`, {
          headers,
        }),
      ]);

      if (!artifactsResponse.ok) {
        throw new Error("Failed to load company dossiers.");
      }

      const artifactPayload = (await artifactsResponse.json()) as EnrichmentArtifactsResponse;
      setArtifacts(artifactPayload.items || []);

      if (normalizedResponse.ok) {
        const normalizedPayload =
          (await normalizedResponse.json()) as NormalizedEnrichmentsResponse;
        setNormalizedAvailable(Boolean(normalizedPayload.normalized_available));
      } else {
        setNormalizedAvailable(false);
      }

      if (entitiesResponse.ok) {
        const entityPayload = (await entitiesResponse.json()) as PipelineEntitiesResponse;
        setCompanyNodes(Array.isArray(entityPayload.entities) ? entityPayload.entities : []);
      } else {
        setCompanyNodes([]);
      }
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "Failed to load enrichments.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

  const artifactEntries = useMemo(
    () =>
      artifacts.map((artifact) => ({
        artifact,
        dossier: buildDossierViewModelFromArtifact(artifact),
      })),
    [artifacts]
  );

  const availableStages = useMemo(() => {
    const stages = artifactEntries
      .map((entry) => entry.dossier.stageEstimate)
      .filter((stage): stage is string => Boolean(stage));

    return ["all", ...Array.from(new Set(stages))];
  }, [artifactEntries]);

  const filteredEntries = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();

    return artifactEntries.filter((entry) => {
      const matchesQuery =
        !normalizedQuery ||
        [
          entry.dossier.companyName,
          entry.dossier.primarySector,
          entry.dossier.stageEstimate,
          entry.dossier.businessModel,
        ]
          .filter(Boolean)
          .some((value) => value!.toLowerCase().includes(normalizedQuery));

      const matchesStage =
        stageFilter === "all" || entry.dossier.stageEstimate === stageFilter;

      return matchesQuery && matchesStage;
    });
  }, [artifactEntries, searchQuery, stageFilter]);

  useEffect(() => {
    if (filteredEntries.length === 0) {
      setSelectedCompanyKey(null);
      return;
    }

    const hasSelectedEntry = filteredEntries.some(
      (entry) => normalizeCompanyName(entry.dossier.companyName) === selectedCompanyKey
    );

    if (!hasSelectedEntry) {
      setSelectedCompanyKey(normalizeCompanyName(filteredEntries[0].dossier.companyName));
    }
  }, [filteredEntries, selectedCompanyKey]);

  const selectedEntry =
    filteredEntries.find(
      (entry) => normalizeCompanyName(entry.dossier.companyName) === selectedCompanyKey
    ) ?? null;

  const graphNodeLookup = useMemo(() => {
    const lookup = new Map<string, PipelineEntity>();

    for (const node of companyNodes) {
      lookup.set(normalizeCompanyName(node.name), node);
    }

    return lookup;
  }, [companyNodes]);

  const selectedGraphNode =
    selectedEntry && graphNodeLookup.get(normalizeCompanyName(selectedEntry.dossier.companyName));

  const fetchDocument = async (sourceUrl: string) => {
    setIsDocumentLoading(true);
    setSelectedDocument(sourceUrl);
    setDocumentData(null);

    try {
      const token = await getToken();
      const headers: Record<string, string> = {};

      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(
        `http://localhost:8000/api/v1/pipelines/${pipelineId}/documents/view?source_url=${encodeURIComponent(sourceUrl)}`,
        { headers }
      );

      if (!response.ok) {
        throw new Error("Failed to fetch document");
      }

      const payload = (await response.json()) as DocumentViewResponse;
      setDocumentData(payload);
    } catch (err) {
      console.error(err);
    } finally {
      setIsDocumentLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-slate-50 text-slate-900">
      <header className="shrink-0 border-b border-slate-200 bg-white px-6 py-4 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push(`/pipeline/${pipelineId}/data`)}
              className="text-slate-500 hover:text-slate-700"
            >
              <ArrowLeft className="mr-2 h-4 w-4" /> Back to Command Center
            </Button>
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-violet-100 p-2 text-violet-700">
                <Building2 className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-xl font-bold">Company Dossiers</h1>
                <p className="text-sm text-slate-500">
                  Artifact-backed enrichment is live now; normalized data can layer in later.
                </p>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="bg-violet-100 text-violet-700">
              {artifacts.length} dossiers
            </Badge>
            <Badge
              variant="secondary"
              className={
                normalizedAvailable
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-slate-100 text-slate-600"
              }
            >
              {normalizedAvailable ? "Normalized ready" : "Artifact-backed view"}
            </Badge>
            <Button
              variant="outline"
              onClick={() => router.push(`/pipeline/${pipelineId}/graph?theme=companies`)}
            >
              <Database className="mr-2 h-4 w-4" /> Company Graph
            </Button>
            <Button variant="outline" onClick={() => void loadData()} disabled={isLoading}>
              <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-full shrink-0 flex-col border-r border-slate-200 bg-white lg:w-[360px]">
          <div className="border-b border-slate-200 p-4">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search company, sector, stage..."
                className="pl-9"
              />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {availableStages.map((stage) => (
                <Button
                  key={stage}
                  type="button"
                  variant={stageFilter === stage ? "default" : "outline"}
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => setStageFilter(stage)}
                >
                  {stage === "all" ? "All stages" : stage}
                </Button>
              ))}
            </div>
          </div>

          <ScrollArea className="min-h-0 flex-1">
            <div className="space-y-3 p-4">
              {isLoading && artifacts.length === 0 && (
                <Card className="border-dashed border-slate-300 bg-slate-50">
                  <CardContent className="py-8 text-center text-sm text-slate-500">
                    Loading company dossiers...
                  </CardContent>
                </Card>
              )}

              {error && (
                <Card className="border-red-200 bg-red-50">
                  <CardContent className="py-4 text-sm text-red-700">{error}</CardContent>
                </Card>
              )}

              {!isLoading && !error && filteredEntries.length === 0 && artifacts.length === 0 && (
                <Card className="border-dashed border-slate-300 bg-slate-50">
                  <CardContent className="py-8 text-center text-sm text-slate-500">
                    No enrichment dossiers are available yet. If the pipeline is still running, new dossiers
                    will appear here after evidence is processed.
                  </CardContent>
                </Card>
              )}

              {!isLoading && !error && filteredEntries.length === 0 && artifacts.length > 0 && (
                <Card className="border-dashed border-slate-300 bg-slate-50">
                  <CardContent className="py-8 text-center text-sm text-slate-500">
                    No dossiers match the current search or stage filter.
                  </CardContent>
                </Card>
              )}

              {filteredEntries.map((entry) => {
                const isSelected =
                  normalizeCompanyName(entry.dossier.companyName) === selectedCompanyKey;
                const sparseEvidence = hasSparseEvidence(entry.dossier);

                return (
                  <button
                    key={entry.artifact.company_name}
                    type="button"
                    onClick={() => setSelectedCompanyKey(normalizeCompanyName(entry.dossier.companyName))}
                    className={`w-full rounded-xl border p-4 text-left shadow-sm transition-colors ${
                      isSelected
                        ? "border-violet-300 bg-violet-50"
                        : "border-slate-200 bg-white hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold text-slate-900">{entry.dossier.companyName}</p>
                        <p className="mt-1 text-sm text-slate-500">
                          {entry.dossier.primarySector || "Sector pending"}
                        </p>
                      </div>
                      {entry.dossier.stageEstimate && (
                        <Badge variant="secondary" className="bg-emerald-100 text-emerald-700">
                          {entry.dossier.stageEstimate}
                        </Badge>
                      )}
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
                      <div className="rounded-lg bg-slate-50 px-3 py-2">
                        <p className="uppercase text-slate-400">Venture Scale</p>
                        <p className="mt-1 font-medium text-slate-800">
                          {entry.dossier.ventureScaleScore !== null
                            ? `${Math.round(entry.dossier.ventureScaleScore * 100)}%`
                            : "N/A"}
                        </p>
                      </div>
                      <div className="rounded-lg bg-slate-50 px-3 py-2">
                        <p className="uppercase text-slate-400">Founders</p>
                        <p className="mt-1 font-medium text-slate-800">{entry.dossier.founderCount}</p>
                      </div>
                      <div className="rounded-lg bg-slate-50 px-3 py-2">
                        <p className="uppercase text-slate-400">Documents</p>
                        <p className="mt-1 font-medium text-slate-800">
                          {entry.dossier.documentCount ?? 0}
                        </p>
                      </div>
                      <div className="rounded-lg bg-slate-50 px-3 py-2">
                        <p className="uppercase text-slate-400">Evidence URLs</p>
                        <p className="mt-1 font-medium text-slate-800">{entry.dossier.sourceUrls.length}</p>
                      </div>
                    </div>
                    {sparseEvidence && (
                      <p className="mt-3 text-xs font-medium text-amber-700">
                        Evidence is still sparse for this company.
                      </p>
                    )}
                  </button>
                );
              })}
            </div>
          </ScrollArea>
        </aside>

        <main className="min-h-0 flex-1 overflow-y-auto bg-slate-50 p-6">
          {selectedEntry ? (
            <div className="mx-auto max-w-6xl space-y-6">
              <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">{selectedEntry.dossier.companyName}</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    This view is currently powered by durable enrichment artifacts.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {selectedEntry.artifact.run_status && (
                    <Badge variant="secondary" className="bg-slate-100 text-slate-700">
                      {selectedEntry.artifact.run_status}
                    </Badge>
                  )}
                  {selectedGraphNode && (
                    <Button
                      variant="outline"
                      onClick={() => router.push(`/pipeline/${pipelineId}/explorer/${selectedGraphNode.id}`)}
                    >
                      <ExternalLink className="mr-2 h-4 w-4" /> Open graph entity
                    </Button>
                  )}
                </div>
              </div>

              <CompanyDossier dossier={selectedEntry.dossier} onOpenSource={fetchDocument} />
            </div>
          ) : (
            <div className="mx-auto max-w-3xl">
              <Card className="border-dashed border-slate-300 bg-white">
                <CardHeader>
                  <CardTitle>Select a company dossier</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-slate-500">
                  Choose a company from the left to inspect its executive summary, VC dossier, founder
                  details, and evidence trail.
                </CardContent>
              </Card>
            </div>
          )}
        </main>
      </div>

      {selectedDocument && (
        <div className="absolute right-0 top-0 z-50 flex h-full w-[600px] flex-col border-l border-slate-200 bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-blue-500" />
              <h2 className="truncate pr-4 text-lg font-bold" title={documentData?.title || selectedDocument}>
                {documentData?.title || "Loading Document..."}
              </h2>
            </div>
            <Button variant="ghost" size="icon" onClick={() => setSelectedDocument(null)}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex-1 overflow-auto bg-slate-50 p-4">
            {isDocumentLoading ? (
              <div className="flex h-full flex-col items-center justify-center text-slate-400">
                <RefreshCw className="mb-4 h-8 w-8 animate-spin" />
                <p>Loading document content...</p>
              </div>
            ) : documentData ? (
              <div className="h-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
                {documentData.viewer_url ? (
                  <iframe
                    src={documentData.viewer_url}
                    className="h-full w-full border-0"
                    title={documentData.title}
                  />
                ) : (
                  <div className="prose prose-slate max-w-none p-6">
                    <div className="mb-4 border-b border-slate-200 pb-4">
                      <a
                        href={documentData.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-sm text-blue-600 hover:underline"
                      >
                        <ExternalLink className="h-4 w-4" /> View Original Source
                      </a>
                    </div>
                    <div className="whitespace-pre-wrap font-mono text-sm">{documentData.content}</div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-red-500">
                Failed to load document content.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
