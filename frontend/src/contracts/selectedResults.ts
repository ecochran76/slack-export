export type SourcePlatform = "slack" | "sms" | "whatsapp" | "email" | "unknown";

export type ResultTargetKind = "message" | "derived_text" | "attachment" | "thread" | "source";

export type SelectionResolutionStatus = "resolved" | "unresolved" | "partial";

export type TextPresence = "included" | "omitted" | "unavailable";

export type NativeValue = string | number | boolean | null | NativeValue[] | { [key: string]: NativeValue };

export type NativeMetadata = Record<string, NativeValue | undefined>;

export interface SourceRef {
  platform: SourcePlatform;
  sourceId: string;
  label?: string;
  native?: NativeMetadata;
}

export interface ConversationRef {
  id: string;
  label?: string;
  kind?: "channel" | "direct" | "group" | "thread" | "mailbox" | "unknown";
  source?: SourceRef;
  native?: NativeMetadata;
}

export interface ThreadRef {
  id: string;
  label?: string;
  conversation?: ConversationRef;
  native?: NativeMetadata;
}

export interface ParticipantRef {
  id: string;
  label?: string;
  handle?: string;
  native?: NativeMetadata;
}

export interface AttachmentRef {
  id: string;
  label?: string;
  mediaType?: string;
  sourceKind?: "file" | "canvas" | "email_part" | "external" | "unknown";
  native?: NativeMetadata;
}

export interface SelectedResultTarget {
  version: number;
  kind: ResultTargetKind;
  id: string;
  source: SourceRef;
  conversation?: ConversationRef;
  thread?: ThreadRef;
  messageId?: string;
  participant?: ParticipantRef;
  attachment?: AttachmentRef;
  selectionLabel?: string;
  native?: NativeMetadata;
}

export interface SearchScoreExplain {
  source?: "lexical" | "semantic" | "hybrid" | "rerank" | "unknown";
  score?: number;
  rank?: number;
  details?: Record<string, unknown>;
}

export interface SearchResultCandidate {
  target: SelectedResultTarget;
  title: string;
  snippet?: string;
  sourceLabel?: string;
  conversationLabel?: string;
  timestamp?: string;
  score?: SearchScoreExplain;
  badges?: string[];
}

export interface SelectionState {
  targetsById: Record<string, SelectedResultTarget>;
  visibleTargetIds: string[];
}

export interface ContextPolicy {
  before: number;
  after: number;
  includeText: boolean;
  maxTextChars: number;
  threadPolicy?: "selected_only" | "include_thread" | "provider_default";
}

export interface MessageContextItem {
  id: string;
  relation: "before" | "hit" | "after" | "linked" | "context";
  selected: boolean;
  source: SourceRef;
  conversation?: ConversationRef;
  thread?: ThreadRef;
  participant?: ParticipantRef;
  timestamp?: string;
  textPresence: TextPresence;
  text?: string;
  native?: NativeMetadata;
}

export interface DerivedTextContextItem {
  id: string;
  relation: "before" | "hit" | "after" | "context";
  selected: boolean;
  attachment?: AttachmentRef;
  chunkIndex?: number;
  startOffset?: number;
  endOffset?: number;
  textPresence: TextPresence;
  text?: string;
  native?: NativeMetadata;
}

export interface SelectedResultReportItem {
  index: number;
  target: SelectedResultTarget;
  status: SelectionResolutionStatus;
  reason?: string;
  messageContext?: MessageContextItem[];
  derivedTextContext?: DerivedTextContextItem[];
  linkedMessages?: MessageContextItem[];
}

export interface ManagedArtifactRef {
  artifactId: string;
  kind: "selected-results" | "channel-day" | "runtime-report" | "unknown";
  title?: string;
  url?: string;
  jsonUrl?: string;
  generatedAt?: string;
}

export interface SelectedResultReportArtifact extends ManagedArtifactRef {
  kind: "selected-results";
  schemaVersion: number;
  contextPolicy: ContextPolicy;
  itemCount: number;
  resolvedCount: number;
  unresolvedCount: number;
  items: SelectedResultReportItem[];
}

export interface ReportViewAction {
  id: "copy_report_link" | "print" | "copy_target_json" | "copy_item_link" | "open_json";
  label: string;
  targetId?: string;
  href?: string;
}
