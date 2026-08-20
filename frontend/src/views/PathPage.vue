<template>
  <div class="path-page">
    <!-- 顶部渐变区 -->
    <section class="path-hero">
      <h2 class="page-title">个性化学习路径</h2>
      <p class="page-desc">根据你的能力诊断结果，AI 为你规划的专属提升路径</p>
    </section>

    <div class="page-content">
      <!-- 加载中 -->
      <div v-if="loading" class="loading-area">
        <div class="loading-spinner"></div>
        <p>加载学习路径...</p>
      </div>

      <!-- 加载失败 -->
      <el-alert
        v-else-if="loadError"
        :title="loadError"
        type="error"
        show-icon
        :closable="false"
      >
        <template #default>
          <el-button type="primary" size="small" @click="loadPaths">重试</el-button>
        </template>
      </el-alert>

      <!-- 空态 -->
      <div v-else-if="paths.length === 0" class="empty-card">
        <div class="empty-icon">🗺️</div>
        <h3 class="empty-title">暂无学习路径</h3>
        <p class="empty-desc">完成能力诊断后，AI 将自动为你生成个性化的学习路径。</p>
        <button class="app-btn app-btn-primary app-btn-large" @click="$router.push('/input')">
          🚀 开始诊断
        </button>
      </div>

      <!-- 路径列表 -->
      <div v-else class="paths-list">
        <div v-for="p in paths" :key="p.id" class="path-card">
          <!-- 路径头部 -->
          <div class="path-header">
            <div class="path-header-left">
              <h3 class="path-job">{{ jobTitleMap[p.job_id] || p.job_id }}</h3>
              <span class="path-status" :class="p.status">{{ statusLabel(p.status) }}</span>
            </div>
            <div class="path-header-right">
              <span class="path-date">创建于 {{ formatTime(p.created_at) }}</span>
            </div>
          </div>

          <!-- 步骤时间线 -->
          <div class="timeline">
            <div
              v-for="(step, i) in p.steps"
              :key="step.step"
              class="timeline-step"
              :class="{ last: i === p.steps.length - 1 }"
              @click="goToResource(step)"
            >
              <!-- 左侧节点 + 线 -->
              <div class="tl-left">
                <div class="tl-node" :class="step.status">
                  <span v-if="step.status === 'completed'">✓</span>
                  <span v-else>{{ step.step }}</span>
                </div>
                <div v-if="i < p.steps.length - 1" class="tl-line" :class="{ filled: step.status === 'completed' }"></div>
              </div>

              <!-- 右侧内容 -->
              <div class="tl-content">
                <div class="tl-title-row">
                  <span class="tl-type-icon">{{ typeIcon(step.resource_type) }}</span>
                  <span class="tl-point">{{ step.knowledge_point }}</span>
                  <span class="tl-type-tag">{{ step.resource_type }}</span>
                  <span v-if="step.weight === 'high'" class="tl-weight high">核心</span>
                  <span v-else-if="step.weight === 'mid'" class="tl-weight mid">支撑</span>
                </div>
                <div class="tl-meta">
                  <span class="tl-time">⏱ {{ step.estimated_time }} 分钟</span>
                  <span v-if="step.prerequisite" class="tl-pre">📎 前置：{{ step.prerequisite }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { getLearningPaths, type LearningPathInfo } from '@/api/path'
import { getJobList, type JobInfo } from '@/api/jobs'

const router = useRouter()
const store = useUserStore()

// ---- 加载数据 ----
const paths = ref<LearningPathInfo[]>([])
const loading = ref(true)
const loadError = ref('')
const jobTitleMap = ref<Record<string, string>>({})

onMounted(async () => {
  // 确保 userInfo 已加载
  if (!store.userInfo && store.isLoggedIn) {
    try { await store.fetchUserInfo() } catch {}
  }

  if (!store.userInfo) {
    loading.value = false
    loadError.value = '请先登录'
    return
  }

  await loadPaths()
})

async function loadPaths() {
  if (!store.userInfo) return
  loading.value = true
  loadError.value = ''
  try {
    const [list, jobs] = await Promise.all([
      getLearningPaths(store.userInfo.id),
      getJobList(),
    ])
    paths.value = list
    const map: Record<string, string> = {}
    jobs.forEach((j: JobInfo) => { map[j.id] = j.job_title })
    jobTitleMap.value = map
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    loadError.value = typeof detail === 'string' ? detail : '加载学习路径失败'
  } finally {
    loading.value = false
  }
}

// ---- 工具函数 ----
function formatTime(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function statusLabel(s: string): string {
  return { active: '进行中', completed: '已完成', abandoned: '已放弃' }[s] || s
}

function typeIcon(t: string): string {
  return { '讲义': '📖', '练习': '✏️', '案例': '📋', '视频脚本': '🎬' }[t] || '📄'
}

function goToResource(step: { resource_id: string | null; status: string }) {
  if (step.resource_id) {
    router.push(`/resource/${step.resource_id}`)
  } else {
    ElMessage.info(step.status === 'pending' ? '该步骤尚未生成资源，请先进入资料库查看' : '该步骤暂未绑定资源')
  }
}
</script>

<style scoped>
.path-page {
  min-height: calc(100vh - 64px);
  background: #f5f7fa;
}

/* ---- 顶部渐变 ---- */
.path-hero {
  padding: 36px 80px;
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
  max-width: 900px;
  margin: 0 auto;
  padding: 0 80px 60px;
}

/* ---- 加载 / 空态 ---- */
.loading-area {
  margin-top: 60px;
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

.empty-card {
  margin-top: 60px;
  text-align: center;
  background: #fff;
  border-radius: 16px;
  padding: 60px 40px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
}

.empty-icon { font-size: 56px; margin-bottom: 16px; }
.empty-title { font-size: 22px; font-weight: 700; color: #111827; margin-bottom: 12px; }
.empty-desc { font-size: 15px; color: #666; line-height: 1.7; max-width: 440px; margin: 0 auto 28px; }

/* ---- 路径列表 ---- */
.paths-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
  margin-top: 32px;
}

.path-card {
  background: #fff;
  border-radius: 16px;
  padding: 28px 32px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
}

/* ---- 路径头部 ---- */
.path-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 28px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}

.path-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.path-job {
  font-size: 18px;
  font-weight: 700;
  color: #111827;
}

.path-status {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 12px;
}

.path-status.active {
  background: #dbeafe;
  color: #2563eb;
}

.path-status.completed {
  background: #dcfce7;
  color: #16a34a;
}

.path-status.abandoned {
  background: #f3f4f6;
  color: #888;
}

.path-date {
  font-size: 13px;
  color: #999;
}

/* ---- 时间线 ---- */
.timeline {
  padding-left: 4px;
}

.timeline-step {
  display: flex;
  gap: 16px;
  cursor: default;
}

.timeline-step:not(.last) {
  padding-bottom: 4px;
}

/* 左侧：节点 + 线 */
.tl-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}

.tl-node {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
  background: #f0f0f0;
  color: #999;
  transition: all 0.3s;
}

.tl-node.completed {
  background: #16a34a;
  color: #fff;
}

.tl-node.in_progress {
  background: #2563eb;
  color: #fff;
}

.tl-line {
  width: 2px;
  flex: 1;
  min-height: 28px;
  background: #e5e7eb;
  transition: background 0.3s;
}

.tl-line.filled {
  background: #16a34a;
}

/* 右侧：内容 */
.tl-content {
  flex: 1;
  padding: 6px 0 16px;
}

.tl-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tl-type-icon {
  font-size: 16px;
}

.tl-point {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.tl-type-tag {
  font-size: 12px;
  padding: 2px 8px;
  background: #f3f4f6;
  color: #666;
  border-radius: 4px;
}

.tl-weight {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 600;
}

.tl-weight.high {
  background: #fee2e2;
  color: #dc2626;
}

.tl-weight.mid {
  background: #fef3c7;
  color: #d97706;
}

.tl-meta {
  display: flex;
  gap: 16px;
  margin-top: 6px;
  font-size: 13px;
  color: #999;
}
</style>
