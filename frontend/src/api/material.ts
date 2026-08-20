import request from './request'

export type MaterialStatus = 'uploaded' | 'parsed' | 'needs_ocr' | 'failed' | 'processing'

export interface UserMaterial {
  id: string
  job_id: string | null
  assessment_id: string | null
  original_name: string
  content_type: string | null
  size_bytes: number
  status: MaterialStatus
  extracted_text: string | null
  source_url: string | null
  error_message: string | null
  created_at: string
}

export function getMaterialList(params?: { job_id?: string; assessment_id?: string }): Promise<UserMaterial[]> {
  return request.get('/material/list', { params }) as any
}

export function uploadMaterial(file: File, jobId?: string | null): Promise<UserMaterial> {
  const form = new FormData()
  form.append('file', file)
  if (jobId) form.append('job_id', jobId)
  return request.post('/material/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } }) as any
}

export function createTextMaterial(data: { content: string; title?: string; job_id?: string | null }): Promise<UserMaterial> {
  return request.post('/material/text', data) as any
}

export function deleteMaterial(id: string): Promise<void> {
  return request.delete(`/material/${id}`) as any
}
