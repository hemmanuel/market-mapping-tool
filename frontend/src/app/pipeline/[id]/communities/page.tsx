"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Database, Download, ExternalLink, Network, RefreshCw, Search, Users } from "lucide-react";

interface CommunityMember {
  node_id: number;
  canonical_key?: string;
  name: string;
  type: string;
  community_rank?: number | null;
  summary?: string | null;
}

interface CommunitySummaryItem {
  community_key: string;
  name: string;
  summary?: string | null;
  member_count: number;
  relationship_count: number;
  algorithm?: string | null;
  algorithm_version?: string | null;
  top_members: CommunityMember[];
}

interface CommunityRelationship {
  source_id: number;
  source_name: string;
  target_id: number;
  target_name: string;
  relationship_type: string;
  weight: number;
}

interface RelatedCommunity {
  community_key: string;
  community_name: string;
  interaction_count: number;
  example_members: string[];
}

interface CommunityDetail {
  community_key: string;
  name: string;
  summary?: string | null;
  member_count: number;
  relationship_count: number;
  algorithm?: string | null;
  algorithm_version?: string | null;
  members: CommunityMember[];
  internal_relationships: CommunityRelationship[];
  related_communities: RelatedCommunity[];
}

export default function CommunityExplorerPage() {
  const params = useParams();
  const router = useRouter();
  const pipelineId = params.id as string;
  const { getToken } = useAuth();

  const [communities, setCommunities] = useState<CommunitySummaryItem[]>([]);
  const [selectedCommunityKey, setSelectedCommunityKey] = useState<string | null>(null);
  const [selectedCommunity, setSelectedCommunity] = useState<CommunityDetail | null>(null);
  const [isLoadingCommunities, setIsLoadingCommunities] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isExporting, setIsExporting] = useState<"all" | "selected" | null>(null);
  const [query, setQuery] = useState("");

  const buildHeaders = async () => {
    const token = await getToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  };

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    window.URL.revokeObjectURL(url);
  };

  const fetchCommunities = async () => {
    setIsLoadingCommunities(true);
    try {
      const headers = await buildHeaders();
      const res = await fetch(`http://localhost:8000/api/v1/pipelines/${pipelineId}/communities`, { headers });
      if (!res.ok) {
        throw new Error("Failed to fetch communities");
      }
      const data = await res.json();
      setCommunities(data || []);
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoadingCommunities(false);
    }
  };

  const fetchCommunityDetail = async (communityKey: string) => {
    setIsLoadingDetail(true);
    try {
      const headers = await buildHeaders();
      const res = await fetch(
        `http://localhost:8000/api/v1/pipelines/${pipelineId}/communities/${encodeURIComponent(communityKey)}`,
        { headers }
      );
      if (!res.ok) {
        throw new Error("Failed to fetch community detail");
      }
      const data = await res.json();
      setSelectedCommunity(data);
    } catch (error) {
      console.error(error);
      setSelectedCommunity(null);
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const exportCommunities = async (communityKey?: string) => {
    setIsExporting(communityKey ? "selected" : "all");
    try {
      const headers = await buildHeaders();
      const queryString = communityKey ? `?community_key=${encodeURIComponent(communityKey)}` : "";
      const res = await fetch(
        `http://localhost:8000/api/v1/pipelines/${pipelineId}/communities/export${queryString}`,
        { headers }
      );
      if (!res.ok) {
        throw new Error("Failed to export communities");
      }

      const blob = await res.blob();
      const filename = communityKey
        ? `community_export_${pipelineId}_${communityKey.slice(0, 8)}.zip`
        : `communities_export_${pipelineId}.zip`;
      downloadBlob(blob, filename);
    } catch (error) {
      console.error(error);
      alert("Failed to export community data.");
    } finally {
      setIsExporting(null);
    }
  };

  useEffect(() => {
    fetchCommunities();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

  useEffect(() => {
    if (communities.length === 0) {
      setSelectedCommunityKey(null);
      setSelectedCommunity(null);
      return;
    }

    if (!selectedCommunityKey || !communities.some((community) => community.community_key === selectedCommunityKey)) {
      setSelectedCommunityKey(communities[0].community_key);
    }
  }, [communities, selectedCommunityKey]);

  useEffect(() => {
    if (!selectedCommunityKey) {
      setSelectedCommunity(null);
      return;
    }
    fetchCommunityDetail(selectedCommunityKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCommunityKey]);

  const filteredCommunities = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return communities;
    }

    return communities.filter((community) => {
      const haystack = [
        community.name,
        community.summary || "",
        community.top_members.map((member) => member.name).join(" "),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [communities, query]);

  return (
    <div className="flex flex-col h-screen w-full bg-slate-50 text-slate-900">
      <header className="flex items-center justify-between p-4 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push(`/pipeline/${pipelineId}/graph`)}
            className="mr-2 text-slate-500 hover:text-slate-700"
          >
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Graph
          </Button>
          <Users className="w-6 h-6 text-violet-600" />
          <div className="min-w-0">
            <h1 className="text-xl font-bold truncate">Community Explorer</h1>
            <p className="text-sm text-slate-500 truncate">Explore detected graph communities and export curated community datasets.</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button variant="outline" onClick={fetchCommunities} disabled={isLoadingCommunities}>
            <RefreshCw className={`w-4 h-4 mr-2 ${isLoadingCommunities ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button
            variant="outline"
            onClick={() => exportCommunities()}
            disabled={isExporting !== null || communities.length === 0}
          >
            {isExporting === "all" ? (
              <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Download className="w-4 h-4 mr-2" />
            )}
            Export All Communities
          </Button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="w-[380px] border-r border-slate-200 bg-white flex flex-col">
          <div className="p-4 border-b border-slate-200 bg-slate-50 space-y-3">
            <div className="flex items-center justify-between">
              <div className="font-semibold text-sm text-slate-700">Communities</div>
              <Badge variant="outline" className="bg-white text-slate-600">
                {filteredCommunities.length}
              </Badge>
            </div>
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search communities or members..."
                className="w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {isLoadingCommunities ? (
              <div className="p-6 text-center text-slate-500 text-sm">Loading communities...</div>
            ) : filteredCommunities.length === 0 ? (
              <div className="p-6 text-center text-slate-500 text-sm">No communities found.</div>
            ) : (
              <div className="divide-y divide-slate-100">
                {filteredCommunities.map((community) => {
                  const isSelected = community.community_key === selectedCommunityKey;
                  return (
                    <button
                      key={community.community_key}
                      onClick={() => setSelectedCommunityKey(community.community_key)}
                      className={`w-full text-left p-4 transition-colors ${isSelected ? "bg-violet-50 border-l-4 border-violet-600" : "hover:bg-slate-50 border-l-4 border-transparent"}`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-semibold text-slate-900 truncate">{community.name}</div>
                          <div className="text-xs text-slate-500 mt-1">
                            {community.member_count} members • {community.relationship_count} internal relationships
                          </div>
                        </div>
                        <Badge variant="secondary" className="bg-violet-100 text-violet-700 hover:bg-violet-100 shrink-0">
                          {community.top_members.length} shown
                        </Badge>
                      </div>
                      <p className="text-sm text-slate-600 mt-3 line-clamp-3">
                        {community.summary || "No summary available yet."}
                      </p>
                      {community.top_members.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-3">
                          {community.top_members.slice(0, 4).map((member) => (
                            <span
                              key={`${community.community_key}-${member.node_id}`}
                              className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-600"
                            >
                              {member.name}
                            </span>
                          ))}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-8">
          {!selectedCommunityKey ? (
            <div className="h-full flex items-center justify-center text-slate-500">
              Select a community to inspect it.
            </div>
          ) : isLoadingDetail ? (
            <div className="h-full flex items-center justify-center text-slate-500">
              <RefreshCw className="w-5 h-5 mr-2 animate-spin" /> Loading community detail...
            </div>
          ) : !selectedCommunity ? (
            <div className="h-full flex items-center justify-center text-red-500">
              Failed to load community detail.
            </div>
          ) : (
            <div className="max-w-6xl mx-auto space-y-6">
              <div className="flex items-start justify-between gap-6">
                <div className="min-w-0">
                  <div className="flex items-center gap-3 flex-wrap">
                    <h2 className="text-3xl font-bold text-slate-900 truncate">{selectedCommunity.name}</h2>
                    <Badge className="bg-violet-100 text-violet-700 hover:bg-violet-100 border-violet-200">
                      {selectedCommunity.member_count} members
                    </Badge>
                    <Badge variant="outline" className="bg-white text-slate-600">
                      {selectedCommunity.relationship_count} internal relationships
                    </Badge>
                  </div>
                  <p className="text-slate-600 mt-3 max-w-3xl leading-relaxed">
                    {selectedCommunity.summary || "No community summary available yet."}
                  </p>
                  {(selectedCommunity.algorithm || selectedCommunity.algorithm_version) && (
                    <div className="text-xs text-slate-500 mt-3">
                      Detection: {selectedCommunity.algorithm || "unknown"} {selectedCommunity.algorithm_version || ""}
                    </div>
                  )}
                </div>

                <Button
                  variant="outline"
                  onClick={() => exportCommunities(selectedCommunity.community_key)}
                  disabled={isExporting !== null}
                >
                  {isExporting === "selected" ? (
                    <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4 mr-2" />
                  )}
                  Export This Community
                </Button>
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <div className="xl:col-span-2 space-y-6">
                  <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
                    <div className="p-5 border-b border-slate-100 flex items-center gap-2">
                      <Users className="w-5 h-5 text-violet-600" />
                      <h3 className="text-lg font-bold text-slate-900">Members</h3>
                    </div>
                    <div className="p-5 space-y-3">
                      {selectedCommunity.members.length > 0 ? (
                        selectedCommunity.members.map((member) => (
                          <button
                            key={`${selectedCommunity.community_key}-${member.node_id}`}
                            onClick={() => router.push(`/pipeline/${pipelineId}/explorer/${member.node_id}`)}
                            className="w-full text-left rounded-lg border border-slate-200 px-4 py-3 hover:bg-slate-50 transition-colors"
                          >
                            <div className="flex items-center justify-between gap-4">
                              <div className="min-w-0">
                                <div className="font-medium text-slate-900 truncate">{member.name}</div>
                                <div className="text-xs text-slate-500 mt-1">{member.type}</div>
                              </div>
                              {member.community_rank ? (
                                <Badge variant="outline" className="bg-violet-50 text-violet-700 border-violet-200 shrink-0">
                                  Rank #{member.community_rank}
                                </Badge>
                              ) : null}
                            </div>
                            {member.summary ? (
                              <p className="text-sm text-slate-600 mt-3 line-clamp-2">{member.summary}</p>
                            ) : null}
                          </button>
                        ))
                      ) : (
                        <p className="text-sm text-slate-500 italic">No members available.</p>
                      )}
                    </div>
                  </div>

                  <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
                    <div className="p-5 border-b border-slate-100 flex items-center gap-2">
                      <Network className="w-5 h-5 text-blue-600" />
                      <h3 className="text-lg font-bold text-slate-900">Internal Relationships</h3>
                    </div>
                    <div className="p-5 space-y-3">
                      {selectedCommunity.internal_relationships.length > 0 ? (
                        selectedCommunity.internal_relationships.map((relationship, index) => (
                          <div key={`${relationship.source_id}-${relationship.target_id}-${index}`} className="rounded-lg border border-slate-200 px-4 py-3">
                            <div className="text-sm text-slate-900 font-medium">
                              {relationship.source_name} <span className="text-slate-400 mx-2">-[{relationship.relationship_type}]-&gt;</span> {relationship.target_name}
                            </div>
                            <div className="text-xs text-slate-500 mt-2">Weight: {relationship.weight}</div>
                          </div>
                        ))
                      ) : (
                        <p className="text-sm text-slate-500 italic">No internal relationships available.</p>
                      )}
                    </div>
                  </div>
                </div>

                <div className="space-y-6">
                  <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
                    <div className="p-5 border-b border-slate-100">
                      <h3 className="text-lg font-bold text-slate-900">Connected Communities</h3>
                    </div>
                    <div className="p-5 space-y-3">
                      {selectedCommunity.related_communities.length > 0 ? (
                        selectedCommunity.related_communities.map((community) => (
                          <button
                            key={community.community_key}
                            onClick={() => setSelectedCommunityKey(community.community_key)}
                            className="w-full text-left rounded-lg border border-slate-200 px-4 py-3 hover:bg-slate-50 transition-colors"
                          >
                            <div className="font-medium text-slate-900">{community.community_name}</div>
                            <div className="text-xs text-slate-500 mt-1">
                              {community.interaction_count} cross-community interactions
                            </div>
                            {community.example_members.length > 0 ? (
                              <div className="text-xs text-slate-500 mt-2 truncate">
                                Example members: {community.example_members.join(", ")}
                              </div>
                            ) : null}
                          </button>
                        ))
                      ) : (
                        <p className="text-sm text-slate-500 italic">No related communities detected.</p>
                      )}
                    </div>
                  </div>

                  <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
                    <div className="p-5 border-b border-slate-100">
                      <h3 className="text-lg font-bold text-slate-900">Actions</h3>
                    </div>
                    <div className="p-5 space-y-3">
                      <Button
                        variant="outline"
                        className="w-full justify-start"
                        onClick={() => router.push(`/pipeline/${pipelineId}/graph`)}
                      >
                        <Database className="w-4 h-4 mr-2" /> Back to Graph Viewer
                      </Button>
                      <Button
                        variant="outline"
                        className="w-full justify-start"
                        onClick={() => router.push(`/pipeline/${pipelineId}/graph?theme=communities`)}
                      >
                        <ExternalLink className="w-4 h-4 mr-2" /> Inspect in Graph Map
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
