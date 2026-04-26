"use client";

import { Button } from "@/components/ui/button";
import { CompanyDossierViewModel, hasSparseEvidence } from "@/lib/enrichment";
import { cn } from "@/lib/utils";
import {
  BarChart3,
  BrainCircuit,
  Building2,
  Calendar,
  DollarSign,
  ExternalLink,
  FileText,
  Link as LinkIcon,
  MapPin,
  Target,
  Users,
  Zap,
} from "lucide-react";

interface CompanyDossierProps {
  dossier: CompanyDossierViewModel;
  className?: string;
  onOpenSource?: (sourceUrl: string) => void;
}

function renderScoreBar(label: string, score: number) {
  const percentage = Math.round((score || 0) * 100);
  let colorClass = "bg-indigo-500";

  if (percentage < 40) {
    colorClass = "bg-red-500";
  } else if (percentage < 70) {
    colorClass = "bg-yellow-500";
  } else if (percentage >= 90) {
    colorClass = "bg-emerald-500";
  }

  return (
    <div key={label} className="mb-3">
      <div className="mb-1 flex justify-between text-xs font-medium">
        <span className="text-slate-700">{label.replace(/_/g, " ")}</span>
        <span className="text-slate-900">{percentage}%</span>
      </div>
      <div className="h-2 w-full rounded-full bg-slate-200">
        <div className={`${colorClass} h-2 rounded-full`} style={{ width: `${percentage}%` }} />
      </div>
    </div>
  );
}

export function CompanyDossier({ dossier, className, onOpenSource }: CompanyDossierProps) {
  const sparseEvidence = hasSparseEvidence(dossier);

  return (
    <div className={cn("space-y-8", className)}>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-900">
            <Target className="h-5 w-5 text-indigo-500" /> Executive Summary
          </h2>
          {dossier.investmentThesis && (
            <div className="mb-4 rounded-r-lg border-l-4 border-indigo-500 bg-indigo-50 p-4">
              <p className="font-medium italic text-indigo-900">&quot;{dossier.investmentThesis}&quot;</p>
            </div>
          )}
          {dossier.communityName && (
            <div className="mb-4 rounded-lg border border-violet-100 bg-violet-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wider text-violet-700">Community</p>
              <p className="mt-1 text-sm font-semibold text-violet-950">{dossier.communityName}</p>
              {dossier.communitySummary && (
                <p className="mt-2 text-sm text-violet-900">{dossier.communitySummary}</p>
              )}
            </div>
          )}
          <div className="mb-4">
            <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-400">
              Pitch Summary
            </h3>
            <p className="text-slate-700">{dossier.pitchSummary || "N/A"}</p>
          </div>
          <div>
            <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-400">
              Full Description
            </h3>
            <p className="text-sm leading-relaxed text-slate-700">
              {dossier.fullDescription || "N/A"}
            </p>
          </div>
          {dossier.rationale && (
            <div className="mt-4 rounded-lg border border-sky-100 bg-sky-50 p-4">
              <p className="mb-1 text-xs font-bold uppercase tracking-wider text-sky-700">
                Investment Rationale
              </p>
              <p className="text-sm text-sky-950">{dossier.rationale}</p>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-900">
            <Zap className="h-5 w-5 text-amber-500" /> Fast Facts
          </h2>
          <ul className="space-y-4">
            <li className="flex items-start gap-3">
              <DollarSign className="mt-0.5 h-5 w-5 text-emerald-500" />
              <div>
                <p className="text-xs font-bold uppercase text-slate-400">Total Raised</p>
                <p className="font-medium text-slate-900">{dossier.totalRaised || "Undisclosed"}</p>
                {dossier.latestRound && (
                  <p className="text-xs text-slate-500">Latest: {dossier.latestRound}</p>
                )}
              </div>
            </li>
            <li className="flex items-start gap-3">
              <MapPin className="mt-0.5 h-5 w-5 text-blue-500" />
              <div>
                <p className="text-xs font-bold uppercase text-slate-400">HQ Location</p>
                <p className="font-medium text-slate-900">{dossier.hqLocation || "Unknown"}</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <Calendar className="mt-0.5 h-5 w-5 text-purple-500" />
              <div>
                <p className="text-xs font-bold uppercase text-slate-400">Founded</p>
                <p className="font-medium text-slate-900">{dossier.yearFounded || "Unknown"}</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <Users className="mt-0.5 h-5 w-5 text-teal-500" />
              <div>
                <p className="text-xs font-bold uppercase text-slate-400">Team / Evidence</p>
                <p className="font-medium text-slate-900">
                  {dossier.founderCount} founders, {dossier.documentCount ?? 0} docs
                </p>
                <p className="text-xs text-slate-500">{dossier.sourceUrls.length} source URLs</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <BarChart3 className="mt-0.5 h-5 w-5 text-indigo-500" />
              <div>
                <p className="text-xs font-bold uppercase text-slate-400">Venture Scale Score</p>
                <p className="font-medium text-slate-900">
                  {dossier.ventureScaleScore !== null
                    ? `${Math.round(dossier.ventureScaleScore * 100)}%`
                    : "N/A"}
                </p>
              </div>
            </li>
          </ul>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-900">
            <BrainCircuit className="h-5 w-5 text-pink-500" /> Strategic Analysis
          </h2>
          <div className="space-y-4">
            <div>
              <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-400">
                Market Narrative
              </h3>
              <p className="text-sm text-slate-700">{dossier.marketNarrative || "N/A"}</p>
            </div>
            <div>
              <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-400">
                Moat Description
              </h3>
              <p className="text-sm text-slate-700">{dossier.moatDescription || "N/A"}</p>
            </div>
            {dossier.aiForceMultiplierThesis && (
              <div className="rounded-lg border border-pink-100 bg-pink-50 p-3">
                <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-pink-600">
                  AI Force Multiplier
                </h3>
                <p className="text-sm text-pink-900">{dossier.aiForceMultiplierThesis}</p>
              </div>
            )}
            <div className="mt-4 grid grid-cols-2 gap-4">
              <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                <p className="text-xs font-bold uppercase text-slate-400">Competitive Noise</p>
                <p className="font-medium text-slate-900">
                  {dossier.competitiveNoiseLevel || "N/A"}
                </p>
              </div>
              <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                <p className="text-xs font-bold uppercase text-slate-400">AI Survival Score</p>
                <p className="font-medium text-slate-900">
                  {dossier.aiSurvivalScore !== null ? `${dossier.aiSurvivalScore}/1.0` : "N/A"}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-900">
            <BarChart3 className="h-5 w-5 text-sky-500" /> Dimension Scores
          </h2>
          <div className="mb-6">
            {Object.entries(dossier.dimensionScores).length > 0 ? (
              Object.entries(dossier.dimensionScores).map(([key, value]) =>
                renderScoreBar(key, value)
              )
            ) : (
              <p className="text-sm italic text-slate-500">No dimension scores available.</p>
            )}
          </div>

          <div className="border-t border-slate-100 pt-4">
            <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-400">
              Unit Economics Proxy
            </h3>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded border border-slate-100 bg-slate-50 p-2">
                <p className="text-[10px] font-bold uppercase text-slate-400">ACV Proxy</p>
                <p className="text-sm font-medium text-slate-800">{dossier.acvProxy || "N/A"}</p>
              </div>
              <div className="rounded border border-slate-100 bg-slate-50 p-2">
                <p className="text-[10px] font-bold uppercase text-slate-400">Retention</p>
                <p className="text-sm font-medium text-slate-800">
                  {dossier.retentionQuality || "N/A"}
                </p>
              </div>
              <div className="rounded border border-slate-100 bg-slate-50 p-2">
                <p className="text-[10px] font-bold uppercase text-slate-400">Friction</p>
                <p className="text-sm font-medium text-slate-800">
                  {dossier.distributionFriction || "N/A"}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-1">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-900">
            <Users className="h-5 w-5 text-teal-500" /> Founders & Team
          </h2>
          {dossier.founders.length > 0 ? (
            <div className="space-y-4">
              {dossier.founders.map((founder, index) => (
                <div
                  key={`${founder.name}-${index}`}
                  className="flex flex-col border-b border-slate-100 pb-3 last:border-0 last:pb-0"
                >
                  <span className="font-bold text-slate-800">{founder.name}</span>
                  <span className="text-sm text-slate-500">{founder.role || "Founder"}</span>
                  {founder.linkedinUrl && (
                    <a
                      href={founder.linkedinUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 flex items-center gap-1 text-xs text-blue-600 hover:underline"
                    >
                      <LinkIcon className="h-3 w-3" /> LinkedIn Profile
                    </a>
                  )}
                  {founder.bio && (
                    <p className="mt-2 text-xs italic text-slate-600">&quot;{founder.bio}&quot;</p>
                  )}
                  {founder.previousCompanies.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {founder.previousCompanies.map((company) => (
                        <span
                          key={company}
                          className="rounded border border-slate-200 bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600"
                        >
                          {company}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm italic text-slate-500">No founder information available.</p>
          )}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-900">
            <Building2 className="h-5 w-5 text-slate-500" /> Business Details
          </h2>
          <div className="mb-6 grid grid-cols-2 gap-4">
            <div>
              <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-400">
                Primary Sector
              </h3>
              <p className="font-medium text-slate-800">{dossier.primarySector || "N/A"}</p>
            </div>
            <div>
              <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-400">
                Business Model
              </h3>
              <p className="font-medium text-slate-800">{dossier.businessModel || "N/A"}</p>
            </div>
            <div>
              <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-400">
                Customer Type
              </h3>
              <p className="font-medium text-slate-800">{dossier.customerType || "N/A"}</p>
            </div>
            <div>
              <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-400">
                Web Presence
              </h3>
              <div className="mt-1 flex flex-wrap gap-2">
                {dossier.websiteUrl ? (
                  <a
                    href={dossier.websiteUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-sm text-blue-600 hover:underline"
                  >
                    <ExternalLink className="h-3.5 w-3.5" /> Website
                  </a>
                ) : (
                  <span className="text-sm text-slate-500">N/A</span>
                )}
                {dossier.twitterUrl && (
                  <a
                    href={dossier.twitterUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-sm text-sky-600 hover:underline"
                  >
                    <ExternalLink className="h-3.5 w-3.5" /> X / Twitter
                  </a>
                )}
              </div>
            </div>
            <div className="col-span-2">
              <h3 className="mb-1 text-xs font-bold uppercase tracking-wider text-slate-400">
                Tech Stack / Keywords
              </h3>
              <div className="mt-1 flex flex-wrap gap-1">
                {dossier.techStack.length > 0 ? (
                  dossier.techStack.map((tech) => (
                    <span
                      key={tech}
                      className="rounded border border-slate-200 bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600"
                    >
                      {tech}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-slate-500">N/A</span>
                )}
              </div>
            </div>
          </div>

          <div className="border-t border-slate-100 pt-4">
            <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-400">
              Key Stakeholders
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="mb-1 text-xs font-bold text-slate-500">Key Investors</p>
                <p className="text-sm text-slate-700">{dossier.keyInvestors || "None listed"}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-bold text-slate-500">Key Customers</p>
                <p className="text-sm text-slate-700">{dossier.keyCustomers || "None listed"}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-900">
          <FileText className="h-5 w-5 text-violet-500" /> Evidence Trail
        </h2>
        {sparseEvidence && (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-4">
            <p className="text-sm font-medium text-amber-900">
              Evidence is still sparse for this dossier. More documents may improve coverage and confidence.
            </p>
          </div>
        )}
        {dossier.sourceUrls.length > 0 ? (
          <div className="space-y-3">
            {dossier.sourceUrls.map((sourceUrl) => {
              const content = (
                <>
                  <span className="truncate">{sourceUrl}</span>
                  <ExternalLink className="h-4 w-4 shrink-0" />
                </>
              );

              if (onOpenSource) {
                return (
                  <Button
                    key={sourceUrl}
                    type="button"
                    variant="outline"
                    className="flex h-auto w-full items-center justify-between gap-3 py-3 text-left"
                    onClick={() => onOpenSource(sourceUrl)}
                  >
                    {content}
                  </Button>
                );
              }

              return (
                <a
                  key={sourceUrl}
                  href={sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-4 py-3 text-sm text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50"
                >
                  {content}
                </a>
              );
            })}
          </div>
        ) : (
          <p className="text-sm italic text-slate-500">
            No evidence URLs were preserved for this dossier yet.
          </p>
        )}
      </div>
    </div>
  );
}
