import request from './request'

export interface JobInfo {
  id: string
  job_title: string
  description: string
  required_skills: string[]
}

/** 职业列表 */
export function getJobList(): Promise<JobInfo[]> {
  return request.get('/jobs/list') as any
}
