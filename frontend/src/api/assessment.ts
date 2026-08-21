import request, { getToken } from './request'

export interface DimensionItem {
  index: number
  name: string
  value: number
  weight: 'high' | 'mid' | 'low'
  category: string
}

export interface GapValidationItem {
  gap: string
  status: 'grounded' | 'partial' | 'ungrounded'
  reason: string
}

export interface AssessmentResponse {
  id: string
  user_id: string
  job_id: string
  user_input: string | null
  overall_mastery: number | null
  ability_vector: DimensionItem[]
  knowledge_gaps: string[]
  gap_validation: GapValidationItem[] | null
  confidence: number | null
  requirement_scores: RequirementScore[]
  calibration_status: CalibrationStatus
  calibration_summary: CalibrationSummary | null
  material_ids?: string[] | null
  created_at: string
}

export interface AgentTraceEvent {
  name: string
  status: 'waiting' | 'running' | 'completed' | 'failed' | 'blocked' | 'needs_review'
  input_summary?: string
  output_summary?: string
  confidence?: number
  review_result?: string
}

export interface RequirementScore {
  requirement_id: string
  requirement_name: string
  dimension: string
  score: number
  status: 'qualified' | 'partial' | 'gap' | 'unknown'
  evidence_ids: string[]
  prediction_source?: string
}

export type CalibrationStatus = 'passed' | 'needs_review' | 'rejected' | 'unvalidated'

export interface CalibrationSummary {
  status: CalibrationStatus
  version?: string
  evaluated_count: number
  prediction_count?: number
  label_coverage?: number
  accuracy: number | null
  score_accuracy?: number | null
  status_accuracy?: number | null
  mean_absolute_error: number | null
  pass_accuracy_target?: number
  pass_mae_target?: number
  correction_applied?: boolean
  needs_human_review?: boolean
  unvalidated_reason?: string | null
  mode?: 'automatic_evidence_review' | 'ground_truth' | string
  metric_label?: string
  is_ground_truth?: boolean
}

export interface AssessmentListItem {
  id: string
  user_id: string
  job_id: string
  overall_mastery: number | null
  knowledge_gaps: string[]
  created_at: string
}

export interface ReviewInputResponse {
  sufficient: boolean
  missing: string[]
  hint: string
}

/** 创建一次评估 */
export function createAssessment(data: { job_id: string }): Promise<{ id: string }> {
  return request.post('/assessment/create', data) as any
}

/** 输入完整性审查（提交前预检） */
export function reviewInput(data: { job_id: string; user_input: string }): Promise<ReviewInputResponse> {
  return request.post('/assessment/review-input', data) as any
}

/** 提交用户输入并排队执行诊断；耗时任务通过进度流读取，不阻塞提交请求。 */
export function submitAssessment(id: string, data: {
  user_input: string
  gold_labels?: Array<Record<string, unknown>>
  apply_corrections?: boolean
  material_ids?: string[]
  session_id?: string
}): Promise<AssessmentResponse> {
  return request.post(`/assessment/${id}/submit`, data, { timeout: 30_000 }) as any
}

/** 测试/评审阶段：提交客观题、实操或专家标注的真实结果进行校准 */
export function calibrateAssessment(id: string, data: {
  gold_labels: Array<Record<string, unknown>>
  apply_corrections?: boolean
}): Promise<{ assessment_id: string; calibration: CalibrationSummary; records: Array<Record<string, unknown>>; diagnosis_updated: boolean }> {
  return request.post(`/assessment/${id}/calibrate`, data) as any
}

export function autoCalibrateAssessment(id: string): Promise<{
  assessment_id: string
  calibration: Record<string, any>
  records: Record<string, any>[]
  diagnosis_updated: boolean
}> {
  return request.post(`/assessment/${id}/auto-calibrate`) as any
}

export function repairLearningPackage(id: string): Promise<{
  assessment_id: string
  status: 'queued' | 'already_running'
}> {
  return request.post(`/assessment/${id}/repair-learning-package`) as any
}

/** 查询逐能力项校准记录 */
export function getCalibration(id: string): Promise<{
  assessment_id: string
  status: CalibrationStatus
  summary: CalibrationSummary
  records: Array<Record<string, unknown>>
}> {
  return request.get(`/assessment/${id}/calibration`) as any
}

/** 查询单次评估详情 */
export function getAssessment(id: string): Promise<AssessmentResponse> {
  return request.get(`/assessment/${id}`) as any
}

export interface AssessmentProgressEvent {
  stage: 'material' | 'retrieval' | 'diagnosis' | 'calibration' | 'path' | 'resource' | 'review' | 'complete'
  agent: string
  label: string
  percent: number
  status: 'waiting' | 'running' | 'completed' | 'failed'
  updated_at: string | null
}

export interface AssessmentProgress extends AssessmentProgressEvent {
  events: AssessmentProgressEvent[]
}

/** 查询诊断进度及阶段事件（前端实时面板轮询用） */
export function getAssessmentProgress(id: string): Promise<AssessmentProgress> {
  return request.get(`/assessment/${id}/progress`) as any
}

/** 通过 SSE 订阅真实 Agent 进度，前端无法连接时再回退到轮询。 */
export async function streamAssessmentProgress(
  id: string,
  onProgress: (progress: AssessmentProgress) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken()
  const response = await fetch(`/api/assessment/${id}/progress/stream`, {
    method: 'GET',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal,
  })
  if (!response.ok) throw new Error(`进度连接失败（${response.status}）`)
  if (!response.body) throw new Error('当前浏览器不支持实时进度流')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const consume = (block: string) => {
    const dataLine = block.split('\n').find(line => line.startsWith('data:'))
    if (!dataLine) return
    try {
      onProgress(JSON.parse(dataLine.slice(5).trim()) as AssessmentProgress)
    } catch {
      // Ignore an incomplete event; the next polling cycle remains authoritative.
    }
  }
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    blocks.forEach(consume)
    if (done) break
  }
  if (buffer.trim()) consume(buffer)
}

export function getAssessmentAgents(id: string): Promise<{
  assessment_id: string
  progress: AssessmentProgress
  trace: { agents?: AgentTraceEvent[]; retrieval_sources?: Array<Record<string, unknown>> }
}> {
  return request.get(`/assessment/${id}/agents`) as any
}

/** 当前用户的评估历史 */
export function getAssessmentList(): Promise<AssessmentListItem[]> {
  return request.get('/assessment/list') as any
}

/** 删除评估记录 */
export function deleteAssessment(id: string): Promise<void> {
  return request.delete(`/assessment/${id}`) as any
}
