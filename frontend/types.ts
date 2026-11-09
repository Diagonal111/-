export type Grade = 'correct' | 'partial' | 'incorrect' | 'unknown'
export type Page = 'today' | 'questions' | 'knowledge' | 'mistakes' | 'settings' | 'records'
export type Knowledge = {
  id: string; name: string; chapter: string; subject: string; mastery: number;
  status: string; evidence: number; due_count: number; question_count: number; attempts: number;
  last_practiced: string | null
}
export type Review = {
  due_date: string; interval: number; last_grade: Grade; had_error: boolean;
  mistake_status: string | null; attempt_count: number
}
export type Question = {
  id: string; revision: number; title: string; body: string; type: string; options: string[]; answer: string;
  explanation: string; knowledge_id: string; knowledge: string; subject: string;
  minutes: number; verified: boolean; source: string; attachments: string[]; is_demo: boolean;
  review?: Review | null; history?: { id: string; grade: Grade; status: string; created_at: string; hinted: boolean; version: number }[]
}
export type Task = {
  id: string; question_id: string; title: string; knowledge: string; knowledge_id: string; subject: string;
  type: string; minutes: number; category: string; priority: number; reasons: string[];
  factors: Record<string, number>; status: string
}
export type Plan = {
  id: string; budget: number; tasks: Task[]; study_minutes: number; buffer_minutes: number;
  break_minutes: number; total_minutes: number; backlog: number;
  summary?: { summary: string; tasks: { id: string; explanation: string }[] } | null
  stale?: boolean
}
export type State = {
  token: string; date: string; demo_mode: boolean; share_mode?: boolean; budget: number; knowledge: Knowledge[];
  questions: Question[]; plan: Plan | null;
  stats: { due: number; mistakes: number; done_today: number; question_count: number; practiced: number; knowledge_count: number; week: { date: string; count: number; correct: number }[] };
  ai: { configured: boolean; has_key: boolean; base_url: string; model: string; json_mode: boolean }
}
export type Grading = {
  mode?: string; transcription: string; grade: Grade; summary: string;
  steps?: { quote: string; verdict: string; reason: string }[]; uncertainties?: string[]; error_types?: string[]
  workflow?: { step: string; status: string }[]
}
export type RAGExplanation = {
  answer: string
  citations: { question_id: string; title: string; knowledge: string; reason: string }[]
  recommendations: { question_id: string; title: string; knowledge: string }[]
  uncertainties: string[]
  retrieved_count: number
}
export type QuestionDraft = {
  title: string; body: string; type: string; options: string[]; answer: string; explanation: string;
  knowledge_id: string; minutes: number; verified: boolean; attachments: string[]; source: string; warnings?: string[]
  revision?: number
}
export type ImportResult = { id: string; name: string; version: number; items: QuestionDraft[]; warnings: string[]; mode?: string }
export type AttemptSummary = {
  id: string; question_id: string; title: string; knowledge: string; subject: string;
  grade: Grade | null; status: 'pending' | 'confirmed' | 'voided' | 'outdated';
  created_at: string; confirmed_at: string | null; hinted: boolean; version: number; is_demo: boolean
}
export type AttemptDetail = AttemptSummary & {
  answer: string; photos: string[]; transcription_override: string; ai_result: Grading | null;
  question: Question; current_revision: number;
  revisions: {version: number; grade: Grade; confirmed_at: string; action: string}[]
}
