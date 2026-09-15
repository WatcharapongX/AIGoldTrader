// Canonical AI Advisory Domain Types matching backend app/services/ai/domain.py
// Output is strictly ADVISORY ONLY with no execution authority.

export type DirectionalBias = 'LONG' | 'SHORT' | 'NEUTRAL' | 'NO_BIAS';
export type EvidenceStrength = 'STRONG' | 'MODERATE' | 'WEAK' | 'INSUFFICIENT';
export type AgentAgreement = 'HIGH' | 'MEDIUM' | 'LOW' | 'CONFLICTING' | 'UNAVAILABLE';
export type AgentStatus =
  | 'READY'
  | 'PARTIAL'
  | 'DEGRADED'
  | 'UNAVAILABLE'
  | 'BLOCKED_BY_UPSTREAM'
  | 'STALE_INPUT';

export type MetaStatus =
  | 'READY'
  | 'PARTIAL'
  | 'DEGRADED'
  | 'UNAVAILABLE'
  | 'STALE'
  | 'BLOCKED_BY_KILL_SWITCH'
  | 'BLOCKED_BY_RISK'
  | 'BLOCKED_BY_UPSTREAM';

export interface AIProviderExecutionProvenance {
  provider_id: string;
  provider_type: 'fixture' | 'openai_compatible';
  model_alias: string;
  model_used: string;
  mode: 'fixture' | 'external';
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface AgentAnalysisResult {
  agent_id: string;
  agent_version: string;
  status: AgentStatus;
  directional_bias: DirectionalBias;
  evidence_strength: EvidenceStrength;
  summary_th: string;
  evidence_refs: string[];
  supporting_factors_th: string[];
  conflicting_factors_th: string[];
  warnings_th: string[];
  missing_context_th: string[];
  provider_provenance: string;
  execution_provenance?: AIProviderExecutionProvenance | null;
  prompt_version: string;
  generated_at: string;
  as_of: string;
  token_usage?: TokenUsage | null;
}

export interface AIAnalysisResult {
  analysis_id: string;
  symbol: string;
  as_of: string;
  status: MetaStatus;
  directional_bias: DirectionalBias;
  evidence_strength: EvidenceStrength;
  agent_agreement: AgentAgreement;
  summary_th: string;
  key_evidence_th: string[];
  conflicts_th: string[];
  risk_notes_th: string[];
  warnings_th: string[];
  agent_results: Record<string, AgentAnalysisResult>;
  strategy_id: string;
  strategy_version: string;
  risk_decision_id: string;
  risk_decision_status: string;
  kill_switch_state: string;
  provider_provenance: string;
  execution_provenance?: AIProviderExecutionProvenance | null;
  prompt_versions: Record<string, string>;
  generated_at: string;
  input_fingerprint: string;
  analysis_fingerprint: string;
  execution_disclaimer: 'ADVISORY_ONLY_NO_EXECUTION_AUTHORITY';
}

export interface AIEvaluationRequest {
  candidate_id: string;
  account_id: string;
  profile_id?: string | null;
}

export type CanonicalAgentId =
  | 'market_context'
  | 'smc_ict'
  | 'macro_news'
  | 'strategy_critic'
  | 'risk_interpreter'
  | 'trade_thesis';

export const CANONICAL_AGENT_IDS: readonly CanonicalAgentId[] = [
  'market_context',
  'smc_ict',
  'macro_news',
  'strategy_critic',
  'risk_interpreter',
  'trade_thesis',
] as const;

export interface AgentMeta {
  id: CanonicalAgentId;
  nameTh: string;
  descriptionTh: string;
  icon: string;
}

export const CANONICAL_AGENT_METADATA: Record<CanonicalAgentId, AgentMeta> = {
  market_context: {
    id: 'market_context',
    nameTh: 'บริบทตลาด',
    descriptionTh: 'วิเคราะห์โครงสร้างตลาดหลักและแนวโน้มภาพรวม',
    icon: '📊',
  },
  smc_ict: {
    id: 'smc_ict',
    nameTh: 'วิเคราะห์ SMC / ICT',
    descriptionTh: 'ประเมินสภาพคล่อง Swings, BOS, CHoCH, OB และ FVG',
    icon: '📐',
  },
  macro_news: {
    id: 'macro_news',
    nameTh: 'ข่าวและมหภาค',
    descriptionTh: 'ประเมินผลกระทบจากปฏิทินเศรษฐกิจและข่าวสำคัญ',
    icon: '📰',
  },
  strategy_critic: {
    id: 'strategy_critic',
    nameTh: 'ตรวจสอบกลยุทธ์',
    descriptionTh: 'วิเคราะห์ความสอดคล้องของ Candidate ตามกฎของกลยุทธ์',
    icon: '🔍',
  },
  risk_interpreter: {
    id: 'risk_interpreter',
    nameTh: 'วิเคราะห์ความเสี่ยง',
    descriptionTh: 'แปลผลการประเมิน Risk และข้อจำกัดพอร์ตโฟลิโอ',
    icon: '🛡️',
  },
  trade_thesis: {
    id: 'trade_thesis',
    nameTh: 'สรุป Thesis การเทรด',
    descriptionTh: 'สังเคราะห์ข้อสนับสนุนและข้อโต้แย้งเป็นสมมติฐานการเทรด',
    icon: '💡',
  },
};
