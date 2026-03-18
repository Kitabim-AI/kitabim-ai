export const PIPELINE_STEP = {
  OCR: 'ocr',
  CHUNKING: 'chunking',
  EMBEDDING: 'embedding',
  SUMMARY: 'summary',
  SPELL_CHECK: 'spell_check',
  READY: 'ready',
  ERROR: 'error',
} as const;

export type PipelineStep = typeof PIPELINE_STEP[keyof typeof PIPELINE_STEP];

export const PAGE_LEVEL_MILESTONE_STEPS = [
  PIPELINE_STEP.OCR,
  PIPELINE_STEP.CHUNKING,
  PIPELINE_STEP.EMBEDDING,
  PIPELINE_STEP.SPELL_CHECK,
] as const;

export const MILESTONE_FIELD_BY_STEP = {
  [PIPELINE_STEP.OCR]: 'ocrMilestone',
  [PIPELINE_STEP.CHUNKING]: 'chunkingMilestone',
  [PIPELINE_STEP.EMBEDDING]: 'embeddingMilestone',
  [PIPELINE_STEP.SPELL_CHECK]: 'spellCheckMilestone',
  [PIPELINE_STEP.SUMMARY]: 'hasSummary',
} as const;

export const ADMIN_PIPELINE_STEPS = [
  { key: PIPELINE_STEP.OCR, label: 'admin.pipeline.ocr' },
  { key: PIPELINE_STEP.CHUNKING, label: 'admin.pipeline.chunking' },
  { key: PIPELINE_STEP.EMBEDDING, label: 'admin.pipeline.embedding' },
  { key: PIPELINE_STEP.SUMMARY, label: 'admin.pipeline.summary' },
  { key: PIPELINE_STEP.SPELL_CHECK, label: 'admin.pipeline.spellCheck' },
] as const;

export const REPROCESS_STEP = {
  OCR: 'ocr',
  CHUNKING: 'chunking',
  EMBEDDING: 'embedding',
  WORD_INDEX: 'word-index',
  SPELL_CHECK: 'spell-check',
} as const;

export type ReprocessStep = typeof REPROCESS_STEP[keyof typeof REPROCESS_STEP];
