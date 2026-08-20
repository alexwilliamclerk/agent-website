import request from './request'

export interface ReviewMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  turn_index: number
  created_at: string
}

export interface ReviewTurnResponse {
  session_id: string
  turn_count: number
  minimum_turns: number
  decision: 'ask_followup' | 'ready_for_diagnosis'
  assistant_message: string
  question: string
  missing: string[]
  summary: Record<string, string[]>
  reason: string
  ready_for_diagnosis: boolean
  can_skip_followup: boolean
  context_trace_id: string
}

export interface ReviewSessionState {
  id: string
  job_id: string
  status: 'reviewing' | 'ready_for_diagnosis' | 'completed' | string
  turn_count: number
  minimum_turns: number
  ready_for_diagnosis: boolean
  review_state: {
    missing?: string[]
    summary?: Record<string, string[]>
    last_question?: string
    last_decision?: string
  } | null
  assessment_id: string | null
}

/** 创建学习会话 */
export function createSession(data: { job_id: string; minimum_turns?: number }): Promise<{ id: string }> {
  return request.post('/session/create', data) as any
}

/** 读取资料审查会话，刷新页面后仍可恢复最近对话。 */
export function getSessionMessages(sessionId: string): Promise<ReviewMessage[]> {
  return request.get(`/session/${sessionId}/messages`) as any
}

/** 读取服务端资料审查状态；恢复时不使用浏览器保存的聊天全文。 */
export function getReviewSession(sessionId: string): Promise<ReviewSessionState> {
  return request.get(`/session/${sessionId}`) as any
}

/** 提交一轮学习者描述，由资料审查 Agent 决定追问或放行正式诊断。 */
export function submitReviewTurn(sessionId: string, data: { content: string; force_finish?: boolean }): Promise<ReviewTurnResponse> {
  return request.post(`/session/${sessionId}/review-turn`, data) as any
}
