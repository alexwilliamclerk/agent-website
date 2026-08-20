import request from './request'

export interface PathStep {
  step: number
  knowledge_point: string
  resource_type: string
  resource_id: string | null
  estimated_time: number
  prerequisite: string | null
  status: string
  record_id: string | null
  weight: string
}

export interface LearningPathInfo {
  id: string
  user_id: string
  job_id: string
  assessment_id: string | null
  steps: PathStep[]
  current_step: number
  status: string
  created_at: string
  updated_at: string
}

/** 查询用户的学习路径 */
export function getLearningPaths(userId: string): Promise<LearningPathInfo[]> {
  return request.get(`/path/${userId}`) as any
}
