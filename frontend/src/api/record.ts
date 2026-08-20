import request from './request'

export interface LearningRecordInfo {
  id: string
  user_id: string
  session_id: string
  resource_id: string
  status: 'not_started' | 'in_progress' | 'completed'
  score: number | null
  time_spent: number
  started_at: string | null
  completed_at: string | null
}

export function getLearningRecords(assessmentId?: string): Promise<LearningRecordInfo[]> {
  return request.get('/record/list', { params: assessmentId ? { assessment_id: assessmentId } : undefined }) as any
}

export function getResourceRecord(resourceId: string): Promise<LearningRecordInfo | null> {
  return request.get(`/record/resource/${resourceId}`) as any
}

export function startResource(resourceId: string): Promise<LearningRecordInfo> {
  return request.post(`/record/resource/${resourceId}/start`) as any
}

export function completeRecord(recordId: string, data: { score?: number; time_spent?: number } = {}): Promise<LearningRecordInfo> {
  return request.put(`/record/${recordId}/complete`, data) as any
}
