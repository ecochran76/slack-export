import type { SearchResultCandidate, SelectedResultReportArtifact } from "../../contracts";
import { MetricStrip } from "../../components/MetricStrip";

const sampleCandidates: SearchResultCandidate[] = [
  {
    conversationLabel: "runtime-ops",
    score: { rank: 1, score: 0.94, source: "hybrid" },
    snippet: "Backfill queue has drained and live sync listener is active.",
    sourceLabel: "default",
    target: {
      id: "default:C123:1776806033.000100",
      kind: "message",
      messageId: "1776806033.000100",
      source: { platform: "slack", sourceId: "default", label: "Default workspace" },
      version: 1
    },
    timestamp: "2026-04-21T17:12:00Z",
    title: "Live sync status update"
  },
  {
    conversationLabel: "reports",
    score: { rank: 2, score: 0.88, source: "rerank" },
    snippet: "Selected-result report generated with context windows and linked artifacts.",
    sourceLabel: "default",
    target: {
      id: "default:file:F123:chunk:4",
      kind: "derived_text",
      source: { platform: "slack", sourceId: "default", label: "Default workspace" },
      version: 1
    },
    timestamp: "2026-04-21T17:18:00Z",
    title: "Report artifact context"
  }
];

const sampleArtifact: SelectedResultReportArtifact = {
  artifactId: "selected-report-preview",
  contextPolicy: {
    after: 2,
    before: 2,
    includeText: true,
    maxTextChars: 12000,
    threadPolicy: "provider_default"
  },
  generatedAt: "2026-04-21T17:20:00Z",
  itemCount: 2,
  items: [],
  kind: "selected-results",
  resolvedCount: 2,
  schemaVersion: 1,
  title: "Selected report preview",
  unresolvedCount: 0,
  url: "/exports/selected-report-preview"
};

export function SelectedResultWorkbench() {
  return (
    <section className="workbench" aria-labelledby="selected-results-heading">
      <div className="workbench__intro">
        <div>
          <p className="eyebrow">Contract-driven shell</p>
          <h2 id="selected-results-heading">Search candidates to report artifacts</h2>
          <p>
            This placeholder screen proves the frontend package, theme contract, shell layout, and
            selected-result data model before binding live Slack Mirror APIs.
          </p>
        </div>
        <a className="button button--primary" href={sampleArtifact.url}>
          Open artifact
        </a>
      </div>
      <MetricStrip
        metrics={[
          { label: "Candidates", value: String(sampleCandidates.length), tone: "info" },
          { label: "Resolved", value: String(sampleArtifact.resolvedCount), tone: "success" },
          { label: "Context", value: `${sampleArtifact.contextPolicy.before}+${sampleArtifact.contextPolicy.after}`, tone: "neutral" },
          { label: "Unresolved", value: String(sampleArtifact.unresolvedCount), tone: "warning" }
        ]}
      />
      <div className="result-list">
        {sampleCandidates.map((candidate) => (
          <article className="result-card" key={candidate.target.id}>
            <div>
              <p className="result-card__meta">
                {candidate.sourceLabel} / {candidate.conversationLabel} / rank {candidate.score?.rank}
              </p>
              <h3>{candidate.title}</h3>
              <p>{candidate.snippet}</p>
            </div>
            <span className="status-badge">{candidate.target.kind}</span>
          </article>
        ))}
      </div>
    </section>
  );
}
