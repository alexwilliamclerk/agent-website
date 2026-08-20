import request from './request'

export interface LoginParams {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
}

export interface UserInfo {
  id: string
  username: string
  latest_assessment_id: string | null
  created_at: string
}

/** 登录 */
export function login(data: LoginParams): Promise<LoginResponse> {
  return request.post('/auth/login', data) as any
}

/** 注册 */
export function register(data: LoginParams): Promise<any> {
  return request.post('/auth/register', data) as any
}

/** 获取当前用户信息 */
export function getMe(): Promise<UserInfo> {
  return request.get('/auth/me') as any
}

/** 修改密码 */
export function changePassword(data: {
  old_password: string
  new_password: string
}): Promise<any> {
  return request.put('/auth/password', data) as any
}
