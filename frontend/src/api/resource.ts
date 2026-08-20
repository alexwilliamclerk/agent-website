import request from './request'

export interface ResourceInfo {
  id: string
  assessment_id: string | null
  knowledge_point: string
  content_type: string
  title: string
  body: string
  difficulty: number | null
  source_chunk_id: string | null
  source_text: string | null
  review_status: string | null
  review_reason: string | null
  display_status: string
  generation_method: string | null
  created_at: string
}

export interface ResourceBookmarkInfo {
  resource_id: string
  created_at: string
}

/** 获取资源列表（支持按知识点和类型过滤） */
export function getResourceList(params?: {
  knowledge_point?: string
  type?: string
  assessment_id?: string
}): Promise<ResourceInfo[]> {
  return request.get('/resource/list', { params }) as any
}

/** 获取资源详情 */
export function getResource(id: string): Promise<ResourceInfo> {
  return request.get(`/resource/${id}`) as any
}

export function getResourceBookmarks(): Promise<ResourceBookmarkInfo[]> {
  return request.get('/resource/bookmarks') as any
}

export function bookmarkResource(id: string): Promise<ResourceBookmarkInfo> {
  return request.post(`/resource/${id}/bookmark`) as any
}

export function unbookmarkResource(id: string): Promise<{ message: string }> {
  return request.delete(`/resource/${id}/bookmark`) as any
}
