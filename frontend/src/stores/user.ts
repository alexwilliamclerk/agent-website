import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import router from '@/router'
import * as authApi from '@/api/auth'
import { setToken, getToken } from '@/api/request'
import type { UserInfo } from '@/api/auth'

export const useUserStore = defineStore('user', () => {
  // ---- state ----
  const token = ref<string | null>(getToken())
  const userInfo = ref<UserInfo | null>(null)
  // The dialogue itself remains authoritative on the server.  This browser
  // pointer only lets the review page restore that server-side conversation
  // after a refresh instead of asking the learner to repeat a turn.
  const currentSessionId = ref<string | null>(sessionStorage.getItem('career_review_session_id'))

  // ---- getters ----
  const isLoggedIn = computed(() => !!token.value)
  const username = computed(() => userInfo.value?.username || '')
  const hasAssessment = computed(() => !!userInfo.value?.latest_assessment_id)

  // ---- actions ----

  /** 登录 */
  async function login(username: string, password: string) {
    const res = await authApi.login({ username, password })
    token.value = res.access_token
    setToken(res.access_token)
    await fetchUserInfo()
  }

  /** 注册 */
  async function register(username: string, password: string) {
    await authApi.register({ username, password })
  }

  /** 退出登录 */
  function logout() {
    token.value = null
    userInfo.value = null
    currentSessionId.value = null
    sessionStorage.removeItem('career_review_session_id')
    setToken(null)
    router.push('/login')
  }

  /** 获取当前用户信息 */
  async function fetchUserInfo() {
    const info = await authApi.getMe()
    userInfo.value = info
  }

  /** 修改密码 */
  async function changePassword(oldPwd: string, newPwd: string) {
    await authApi.changePassword({ old_password: oldPwd, new_password: newPwd })
  }

  /** 存储当前学习会话 ID */
  function setCurrentSession(sessionId: string | null) {
    currentSessionId.value = sessionId || null
    if (sessionId) sessionStorage.setItem('career_review_session_id', sessionId)
    else sessionStorage.removeItem('career_review_session_id')
  }

  return {
    // state
    token,
    userInfo,
    currentSessionId,
    // getters
    isLoggedIn,
    username,
    hasAssessment,
    // actions
    login,
    register,
    logout,
    fetchUserInfo,
    changePassword,
    setCurrentSession,
  }
})
