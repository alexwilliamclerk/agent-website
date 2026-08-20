<template>
  <div class="profile-page">
    <!-- 顶部渐变区 -->
    <section class="profile-hero">
      <h2 class="page-title">个人中心</h2>
      <p class="page-desc">管理你的账户信息与诊断历史</p>
    </section>

    <div class="page-content">
      <!-- 加载中 -->
      <div v-if="loading" class="loading-area">
        <div class="loading-spinner"></div>
        <p>加载中...</p>
      </div>

      <template v-else>
        <div class="profile-grid">
          <!-- 左栏：用户信息 + 修改密码 -->
          <div class="left-col">
            <!-- 用户信息卡片 -->
            <div class="info-card">
              <div class="nav-avatar-large"></div>
              <div class="info-name">{{ store.username }}</div>
              <div class="info-meta">注册时间：{{ formatTime(store.userInfo?.created_at || '') }}</div>
            </div>

            <!-- 修改密码 -->
            <div class="pwd-card">
              <h3 class="card-title">账户安全</h3>
              <button class="app-btn app-btn-outline" style="width:100%;justify-content:center" @click="showPwdDialog = true">
                🔒 修改密码
              </button>
            </div>
          </div>

          <!-- 右栏：诊断历史 -->
          <div class="right-col">
            <div class="history-card">
              <h3 class="card-title">诊断历史</h3>
              <p v-if="history.length === 0 && !historyLoading" class="empty-text">暂无诊断记录</p>

              <!-- 历史列表加载中 -->
              <div v-if="historyLoading" class="loading-area" style="padding:40px 0">
                <div class="loading-spinner"></div>
              </div>

              <!-- 加载失败 -->
              <el-alert
                v-else-if="historyError"
                title="加载诊断历史失败"
                type="error"
                show-icon
                :closable="false"
              >
                <template #default>
                  <el-button type="primary" size="small" @click="loadHistory">重试</el-button>
                </template>
              </el-alert>

              <!-- 历史列表 -->
              <div v-else-if="history.length > 0" class="history-list">
                <div
                  v-for="item in history"
                  :key="item.id"
                  class="history-item"
                  @click="$router.push(`/diagnosis/${item.id}`)"
                >
                  <div class="history-left">
                    <div class="history-job">{{ jobTitleMap[item.job_id] || item.job_id }}</div>
                    <div class="history-time">{{ formatTime(item.created_at) }}</div>
                  </div>
                  <div class="history-right">
                    <span v-if="item.overall_mastery !== null" class="history-score" :class="scoreClass(item.overall_mastery)">
                      {{ Math.round(item.overall_mastery * 100) }}分
                    </span>
                    <span v-else class="history-score pending">诊断中</span>
                    <button class="del-btn" title="删除" @click.stop="handleDelete(item)">🗑</button>
                    <span class="history-arrow">→</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 修改密码弹窗 -->
    <el-dialog
      v-model="showPwdDialog"
      title="修改密码"
      width="420px"
      :close-on-click-modal="false"
      @closed="resetPwdForm"
    >
      <form class="pwd-form" @submit.prevent="handleChangePwd">
        <div class="form-item">
          <label class="form-label">旧密码</label>
          <input
            v-model="pwdForm.oldPwd"
            class="form-input"
            type="password"
            placeholder="请输入旧密码"
            autocomplete="current-password"
            @input="pwdError = ''"
          />
        </div>
        <div class="form-item">
          <label class="form-label">新密码</label>
          <input
            v-model="pwdForm.newPwd"
            class="form-input"
            type="password"
            placeholder="请输入新密码（至少6位）"
            autocomplete="new-password"
            @input="pwdError = ''"
          />
        </div>
        <div class="form-item">
          <label class="form-label">确认新密码</label>
          <input
            v-model="pwdForm.confirmPwd"
            class="form-input"
            type="password"
            placeholder="请再次输入新密码"
            autocomplete="new-password"
            @input="pwdError = ''"
          />
        </div>
        <p v-if="pwdError" class="form-error">{{ pwdError }}</p>
        <p v-if="pwdSuccess" class="form-success">{{ pwdSuccess }}</p>
        <button
          class="app-btn-submit"
          type="submit"
          :disabled="pwdLoading || !canChangePwd"
          style="width:100%;justify-content:center;height:42px;margin-top:8px"
        >
          <span v-if="pwdLoading" class="app-spinner"></span>
          {{ pwdLoading ? '修改中...' : '确认修改' }}
        </button>
      </form>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { getAssessmentList, deleteAssessment, type AssessmentListItem } from '@/api/assessment'
import { getJobList, type JobInfo } from '@/api/jobs'

const store = useUserStore()

// ---- 页面加载 ----
const loading = ref(false)

onMounted(async () => {
  if (!store.userInfo && store.isLoggedIn) {
    loading.value = true
    try { await store.fetchUserInfo() } catch {}
    loading.value = false
  }
  loadHistory()
})

// ---- 时间格式化 ----
function formatTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ---- 分数等级 ----
function scoreClass(score: number): string {
  if (score >= 0.8) return 'high'
  if (score >= 0.6) return 'mid'
  return 'low'
}

// ---- 诊断历史 ----
const history = ref<AssessmentListItem[]>([])
const historyLoading = ref(false)
const historyError = ref(false)
const jobTitleMap = ref<Record<string, string>>({})

async function loadHistory() {
  historyLoading.value = true
  historyError.value = false
  try {
    const [list, jobs] = await Promise.all([
      getAssessmentList(),
      getJobList(),
    ])
    history.value = list
    // 构建 job_id → job_title 映射
    const map: Record<string, string> = {}
    jobs.forEach((j: JobInfo) => { map[j.id] = j.job_title })
    jobTitleMap.value = map
  } catch {
    historyError.value = true
  } finally {
    historyLoading.value = false
  }
}

async function handleDelete(item: AssessmentListItem) {
  try {
    await ElMessageBox.confirm(
      `确定要删除「${jobTitleMap.value[item.job_id] || item.job_id}」的诊断记录吗？`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await deleteAssessment(item.id)
    ElMessage.success('已删除')
    history.value = history.value.filter(h => h.id !== item.id)
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '删除失败')
  }
}

// ---- 修改密码 ----
const showPwdDialog = ref(false)
const pwdLoading = ref(false)
const pwdError = ref('')
const pwdSuccess = ref('')
const pwdForm = ref({ oldPwd: '', newPwd: '', confirmPwd: '' })

const canChangePwd = computed(() =>
  pwdForm.value.oldPwd !== '' &&
  pwdForm.value.newPwd.length >= 6 &&
  pwdForm.value.newPwd === pwdForm.value.confirmPwd,
)

function resetPwdForm() {
  pwdForm.value = { oldPwd: '', newPwd: '', confirmPwd: '' }
  pwdError.value = ''
  pwdSuccess.value = ''
}

async function handleChangePwd() {
  if (!canChangePwd.value) return
  pwdLoading.value = true
  pwdError.value = ''
  pwdSuccess.value = ''
  try {
    await store.changePassword(pwdForm.value.oldPwd, pwdForm.value.newPwd)
    pwdSuccess.value = '密码修改成功'
    setTimeout(() => { showPwdDialog.value = false }, 1500)
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    pwdError.value = typeof detail === 'string' ? detail : '修改失败，请检查旧密码是否正确'
  } finally {
    pwdLoading.value = false
  }
}
</script>

<style scoped>
.profile-page {
  height: calc(100vh - 64px);
  background: #f5f7fa;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ---- 顶部渐变 ---- */
.profile-hero {
  padding: 24px 80px 20px;
  background: var(--hero-gradient);
  text-align: center;
}

.page-title {
  font-size: 32px;
  font-weight: 800;
  color: #111827;
  margin-bottom: 6px;
}

.page-desc {
  font-size: 15px;
  color: #666;
}

/* ---- 内容区 ---- */
.page-content {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 80px 24px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ---- 加载 ---- */
.loading-area {
  margin-top: 40px;
  text-align: center;
  color: #666;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e5e7eb;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: app-spin 0.7s linear infinite;
  margin: 0 auto 16px;
}

/* ---- 双栏布局 ---- */
.profile-grid {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 24px;
  margin-top: 20px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

/* ---- 用户信息卡片 ---- */
.info-card {
  background: #fff;
  border-radius: 16px;
  padding: 40px 28px;
  text-align: center;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  margin-bottom: 24px;
}

.info-name {
  font-size: 22px;
  font-weight: 700;
  color: #111827;
  margin: 16px 0 8px;
}

.info-meta {
  font-size: 13px;
  color: #999;
}

/* ---- 密码卡片 ---- */
.pwd-card {
  background: #fff;
  border-radius: 16px;
  padding: 24px 28px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.card-title {
  font-size: 16px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 16px;
}

/* ---- 历史卡片 ---- */
.right-col {
  overflow: hidden;
  min-height: 0;
}

.history-card {
  background: #fff;
  border-radius: 16px;
  padding: 28px 32px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  height: 100%;
  overflow-y: auto;
}

.empty-text {
  color: #999;
  font-size: 14px;
  padding: 60px 0;
  text-align: center;
}

.history-list {
  display: flex;
  flex-direction: column;
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 0;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background 0.2s;
}

.history-item:last-child {
  border-bottom: none;
}

.history-item:hover {
  background: #f8fafc;
  margin: 0 -12px;
  padding: 16px 12px;
  border-radius: 8px;
}

.history-job {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 4px;
}

.history-time {
  font-size: 13px;
  color: #999;
}

.history-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.history-score {
  font-size: 16px;
  font-weight: 700;
  padding: 4px 12px;
  border-radius: 6px;
}

.history-score.high {
  background: #dcfce7;
  color: #16a34a;
}

.history-score.mid {
  background: #fef3c7;
  color: #d97706;
}

.history-score.low {
  background: #fee2e2;
  color: #dc2626;
}

.history-score.pending {
  background: #e5e7eb;
  color: #888;
  font-weight: 500;
}

.history-arrow {
  color: #ccc;
  font-size: 16px;
}

.del-btn {
  border: none;
  background: none;
  font-size: 16px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
  opacity: 0.4;
  transition: all 0.2s;
  font-family: inherit;
  line-height: 1;
}

.del-btn:hover {
  opacity: 1;
  background: #fee2e2;
}

/* ---- 弹窗表单 ---- */
.pwd-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-label {
  font-size: 14px;
  color: #555;
  font-weight: 500;
}

.form-input {
  height: 40px;
  padding: 0 12px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  font-size: 14px;
  color: #111827;
  outline: none;
  transition: border-color 0.3s;
  font-family: inherit;
}

.form-input:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.1);
}

.form-error {
  color: #f56c6c;
  font-size: 13px;
  margin: 0;
}

.form-success {
  color: #16a34a;
  font-size: 13px;
  margin: 0;
}
</style>
