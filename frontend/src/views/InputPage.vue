<template>
  <div class="page-shell review-page">
    <div class="content-width">
      <header class="review-heading motion-enter">
        <div>
          <span class="eyebrow">AI REVIEW WORKSPACE</span>
          <h1 class="page-title"><span class="gradient-number">AI</span> 资料审查</h1>
          <p class="page-subtitle">多 Agent 协同核验资料真实性、完整度与岗位相关性，并为每项能力结论建立可追溯证据。</p>
        </div>
      </header>

      <div v-if="jobError" class="error-state glass-surface">
        <b>岗位能力模型加载失败</b><span>请确认后端服务已启动后重试。</span><button type="button" @click="loadJobs">重新加载</button>
      </div>

      <div v-else class="workspace-grid motion-enter motion-delay-1">
        <section class="review-workspace glass-surface">
          <div class="workspace-top">
            <div class="workspace-status"><span class="pulse"></span><b>资料审查 Agent</b><span>实时工作区</span></div>
            <div ref="jobPickerRef" class="job-picker">
              <span class="job-picker-label">目标岗位</span>
              <button class="job-trigger" type="button" :disabled="jobLoading || submitting" :aria-expanded="jobPickerOpen" @click="jobPickerOpen = !jobPickerOpen"><span><Briefcase /><b>{{ selectedJob?.job_title || '请选择岗位' }}</b></span><ArrowDown :class="{ open: jobPickerOpen }" /></button>
              <div v-if="jobPickerOpen" class="job-menu" role="listbox">
                <button v-for="job in jobs" :key="job.id" type="button" :class="{ active: job.id === selectedJobId }" @click="selectJob(job.id)"><span class="job-menu-icon"><Briefcase /></span><span class="job-menu-copy"><b>{{ job.job_title }}</b><small>{{ job.description }}</small><em>{{ job.required_skills.slice(0, 3).join(' · ') }}</em></span><CircleCheck v-if="job.id === selectedJobId" /></button>
              </div>
            </div>
          </div>

          <div class="conversation" aria-live="polite">
            <div v-if="demoMode || !reviewMessages.length" class="message agent-message">
              <span class="message-avatar"><Cpu /></span>
              <div class="bubble"><p>你好，我是资料审查 Agent。请用一段文字说明你已经掌握的能力、完成过的实践，以及目前还不确定的部分。我会先完成两轮信息核验，再协调后续 Agent 建立能力证据图谱。</p><time>已就绪</time></div>
            </div>
            <template v-if="!demoMode">
              <div v-for="message in reviewMessages" :key="message.id" class="message" :class="message.role === 'user' ? 'user-message' : 'agent-message continuation'">
                <span v-if="message.role === 'assistant'" class="message-avatar"><Cpu /></span>
                <div class="bubble" :class="{ 'review-feedback': message.role === 'assistant' }"><b v-if="message.role === 'assistant'">{{ reviewSufficient ? '资料审查结论' : '资料审查 Agent 追问' }}</b><p>{{ message.content }}</p><small v-if="message.role === 'assistant' && reviewMissing.length && !reviewSufficient">建议补充：{{ reviewMissing.join('、') }}</small><time>第 {{ message.turn_index }} 轮</time></div>
              </div>
            </template>
            <template v-if="demoMode">
              <div class="message user-message"><div class="bubble"><p>{{ previewUserInput }}</p><time>第 1 轮 · 10:30</time></div></div>
              <div v-if="!demoReplySent" class="message agent-message continuation guided-followup">
                <span class="message-avatar"><Cpu /></span>
                <div class="bubble review-feedback">
                  <span class="turn-badge">第 2 轮 · Agent 定向追问</span>
                  <b>我已识别到项目经历，但还缺少可核验的个人贡献证据。</b>
                  <p>第一轮资料已确认你使用过 Vue、JavaScript 与接口联调；本轮不需要重复技术清单，只需补全一个关键事实。</p>
                  <div class="guided-question"><span>请直接回答</span><strong>{{ previewFollowupQuestion }}</strong></div>
                  <small>回答中写清“负责内容、具体做法、验证结果”即可，系统会与第一轮资料合并归档。</small>
                  <time>Agent 已根据第一轮材料生成问题</time>
                </div>
              </div>
              <template v-else>
                <div class="message user-message"><div class="bubble"><p>{{ previewReply }}</p><time>第 2 轮 · 已提交</time></div></div>
                <div class="message agent-message continuation"><span class="message-avatar"><Cpu /></span><div class="bubble review-feedback"><span class="turn-badge complete">第 2 轮 · 已归档</span><b>补充内容已纳入能力证据图谱</b><p>系统已将你的项目职责、技术做法与验证结果同第一轮资料关联，可进入能力诊断与个性化学习路径生成。</p><time>多轮资料审查完成</time></div></div>
              </template>
            </template>
            <div v-if="submitting" class="message agent-message continuation"><div class="bubble typing-bubble"><span>{{ liveProgress.label }}</span><i></i><i></i><i></i></div></div>

          </div>

          <div class="composer" :class="{ focused: composerFocused, 'followup-composer': followupPending || (demoMode && !demoReplySent) }">
            <div v-if="(followupPending && reviewHint) || (demoMode && !demoReplySent)" class="composer-question"><span>第 2 轮 · 请回答 Agent 问题</span><b>{{ demoMode ? previewFollowupQuestion : reviewHint }}</b></div>
            <textarea v-model="userInput" :disabled="submitting || reviewSufficient" :placeholder="reviewSufficient ? '资料审查已完成，正在进入能力诊断…' : demoMode ? '请直接说明：你负责的模块、具体做法和验证结果…' : followupPending ? '请围绕上方 Agent 问题补充细节…' : '例如：我掌握了哪些技术，完成了哪些项目，目前哪些能力仍需补强…'" @focus="composerFocused = true" @blur="composerFocused = false"></textarea>
            <div class="composer-tools">
              <span class="composer-hint">{{ reviewSufficient ? '多轮资料已归档，正在传递给正式诊断流程' : demoMode ? '请只回答本轮问题，无需重复第一轮描述' : `第 ${Math.min(reviewTurnCount + 1, minimumReviewTurns)} 轮资料将作为能力证据` }}</span>
              <div class="submit-group"><button v-if="canSkipFollowup && !reviewSufficient" class="skip-followup" type="button" :disabled="submitting" @click="skipFollowup">按当前资料继续</button><span>{{ userInput.length }} 字</span><button class="send-button primary-gradient-button" type="button" :disabled="submitting || reviewSufficient || !selectedJobId || userInput.trim().length < 10" @click="startReview()"><span>{{ submitting ? '审查中' : demoMode || followupPending ? '提交第 2 轮回答' : '发送并审查' }}</span><ArrowUp /></button></div>
            </div>
          </div>
        </section>

        <aside class="review-inspector glass-surface">
          <header class="inspector-head"><div><span class="eyebrow">REVIEW INSPECTOR</span><h2>审查控制台</h2></div><span class="inspector-state" :class="{ running: submitting || demoMode }"><i></i>{{ submitting || demoMode ? '审查中' : reviewSufficient ? '已就绪' : '待开始' }}</span></header>

          <section class="inspector-section target-section">
            <div class="target-section-heading">
              <div class="section-label"><Briefcase /> 目标岗位</div>
              <button class="target-refresh" type="button" :disabled="jobLoading || submitting" @click="loadJobs"><Refresh /> 刷新岗位</button>
            </div>
            <h3>{{ selectedJob?.job_title || '等待选择岗位' }}</h3>
            <p>{{ selectedJob?.description || '选择目标岗位后，系统会加载对应能力模型。' }}</p>
            <div v-if="selectedJob" class="skill-pills"><span v-for="skill in selectedJob.required_skills.slice(0, 4)" :key="skill">{{ skill }}</span></div>
          </section>

          <section class="inspector-section progress-section">
            <div class="section-label-line"><div class="section-label"><DataAnalysis /> 审查进度</div><button class="progress-expand" type="button" :aria-expanded="showPipeline" :title="showPipeline ? '收起完整协同进度' : '展开完整协同进度'" @click="showPipeline = !showPipeline"><ArrowDown :class="{ open: showPipeline }" /></button></div>
            <div class="progress-layout"><div class="progress-ring" :style="{ '--p': `${displayProgress * 3.6}deg` }"><b>{{ displayProgress }}%</b></div><div class="progress-copy"><span>整体进度</span><div class="track"><i :style="{ width: `${displayProgress}%` }"></i></div><small>{{ submitting || demoMode ? liveProgress.label : reviewSufficient ? '资料可进入能力诊断' : '提交资料后开始' }}</small></div></div>
            <div v-if="submitting" class="live-agent"><span class="live-agent-dot"></span><div><small>当前执行</small><b>{{ liveProgress.agent }}</b></div><em>{{ liveProgress.status === 'failed' ? '执行失败' : '实时同步' }}</em></div>
            <ol v-if="showPipeline && progressEvents.length" class="progress-events" aria-label="Agent 执行记录">
              <li v-for="event in progressEvents" :key="`${event.updated_at}-${event.percent}-${event.label}`" :class="event.status"><i></i><div><b>{{ event.agent }}</b><span>{{ event.label }}</span></div><strong>{{ event.percent }}%</strong></li>
            </ol>
          </section>

          <section class="inspector-section quality-section">
            <div class="section-label quality-title"><CircleCheck /> 证据质量</div>
            <div class="quality-row"><span>文字描述</span><b>{{ demoMode || userInput.trim().length >= 20 ? '已补充' : '待补充' }}</b></div>
            <div class="quality-row"><span>能力关键词</span><b>{{ evidenceKeywordCount }} 项</b></div>
            <div class="quality-row"><span>描述长度</span><b>{{ demoMode ? `${previewUserInput.length} 字` : `${userInput.trim().length} 字` }}</b></div>
            <div class="quality-row"><span>完整度</span><b>{{ evidenceLabel }}</b></div>
            <div class="evidence-meter"><i :style="{ width: `${evidencePercent}%` }"></i></div>
          </section>
        </aside>
      </div>

      <section v-if="showPipeline" class="pipeline glass-surface motion-enter motion-delay-2">
        <div class="pipeline-title"><div><span class="eyebrow">MULTI-AGENT PIPELINE</span><h2>多 Agent 协同工作中</h2></div><span class="pipeline-caption">输入摘要 → 证据抽取 → 能力对照 → 审核纠偏</span></div>
        <div class="pipeline-track">
          <template v-for="(agent, index) in pipeline" :key="agent.name">
            <div class="agent-node" :class="agent.status"><span class="agent-symbol"><component :is="agent.icon" /></span><div><b>{{ agent.name }}</b><small>{{ agent.detail }}</small><em>{{ agentStatusText(agent.status) }}</em></div></div>
            <span v-if="index < pipeline.length - 1" class="pipeline-link" :class="{ active: agent.status === 'running' || agent.status === 'completed' }"><i></i></span>
          </template>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Aim, ArrowDown, ArrowUp, Briefcase, CircleCheck, Cpu, DataAnalysis,
  DocumentCopy, Link, Refresh, Search,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getJobList, type JobInfo } from '@/api/jobs'
import { previewJobs } from '@/fixtures/previewJobs'
import { createAssessment, getAssessmentProgress, streamAssessmentProgress, submitAssessment, type AssessmentProgress } from '@/api/assessment'
import { createSession, getReviewSession, getSessionMessages, submitReviewTurn, type ReviewMessage } from '@/api/session'
import { useUserStore } from '@/stores/user'

const router = useRouter(); const route = useRoute(); const store = useUserStore()
const publicPreview = import.meta.env.DEV && import.meta.env.VITE_PUBLIC_PREVIEW === 'true'
const demoMode = computed(() => import.meta.env.DEV && route.query.demo === '1')
const jobs = ref<JobInfo[]>([]); const jobLoading = ref(true); const jobError = ref(false); const selectedJobId = ref('')
const userInput = ref(''); const reviewHint = ref(''); const reviewMissing = ref<string[]>([]); const reviewSufficient = ref(false)
const submitting = ref(false); const assessmentId = ref(''); const reviewSessionId = ref(''); const reviewMessages = ref<ReviewMessage[]>([])
const reviewTurnCount = ref(0); const minimumReviewTurns = ref(2); const followupPending = ref(false); const canSkipFollowup = ref(false)
const restoringReview = ref(false)
const liveProgress = ref<AssessmentProgress>({ stage: 'material', agent: '资料解析 Agent', label: '等待开始', percent: 0, status: 'waiting', updated_at: null, events: [] })
let progressTimer: number | null = null; let progressPolling = false; let progressStreamController: AbortController | null = null
const composerFocused = ref(false); const showPipeline = ref(false); const jobPickerOpen = ref(false); const jobPickerRef = ref<HTMLElement | null>(null)
const previewUserInput = '我做过一个电商平台前端项目，负责商品列表、购物车和订单页面，使用 Vue、JavaScript 和接口联调。熟悉 Git 协作，但对性能优化和工程化部署还不够熟悉。'
const previewFollowupQuestion = '在该电商项目中，你亲自负责了哪个模块？请说明你如何完成接口联调或性能优化，并给出一个可验证的结果。'
const previewReply = ref('我主要负责商品列表和购物车模块。我通过封装请求层完成商品、库存与购物车接口联调，并用路由懒加载和图片压缩减少首屏等待；联调后用浏览器 Network 面板核对接口状态和页面加载结果。')
const demoReplySent = ref(false)
const selectedJob = computed(() => jobs.value.find(job => job.id === selectedJobId.value) || null)
const accumulatedReviewText = computed(() => [...reviewMessages.value.filter(message => message.role === 'user').map(message => message.content), userInput.value].join(' '))
const evidenceKeywordCount = computed(() => demoMode.value ? 6 : [...new Set(['项目', '实践', '开发', '学习', '掌握', '接口', '数据库', '前端', '后端', '部署', '测试', '协作'].filter(word => accumulatedReviewText.value.includes(word)))].length)
const evidencePercent = computed(() => {
  if (demoMode.value) return 86
  if (!accumulatedReviewText.value.trim()) return 0
  return Math.min(100, Math.max(30, Math.round(accumulatedReviewText.value.trim().length * .42) + evidenceKeywordCount.value * 7))
})
const evidenceLabel = computed(() => evidencePercent.value >= 70 ? '较完整' : evidencePercent.value >= 40 ? '可用' : '待补充')
const displayProgress = computed(() => demoMode.value ? liveProgress.value.percent : submitting.value ? Math.max(4, liveProgress.value.percent) : reviewSufficient.value ? Math.max(62, evidencePercent.value) : reviewTurnCount.value ? Math.max(24, evidencePercent.value) : evidencePercent.value)
const progressEvents = computed(() => liveProgress.value.events.slice(-6).reverse())
const pipeline = computed(() => {
  if (demoMode.value) return [
    { icon: DocumentCopy, name: '资料解析 Agent', detail: '解析文字描述与能力线索', status: 'completed' },
    { icon: Search, name: '知识库检索 Agent', detail: '检索岗位知识与来源片段', status: 'completed' },
    { icon: DataAnalysis, name: '能力诊断 Agent', detail: '抽取证据并对照能力模型', status: 'running' },
    { icon: Aim, name: '真实结果校准 Agent', detail: '比对标准结果与评分误差', status: 'waiting' },
    { icon: Link, name: '路径规划 Agent', detail: '依据能力缺口规划路径', status: 'waiting' },
    { icon: Cpu, name: '资源生成 Agent', detail: '检索知识库并生成资源', status: 'waiting' },
    { icon: CircleCheck, name: '审核纠偏 Agent', detail: '校验来源与生成内容', status: 'waiting' },
  ]
  const p = liveProgress.value.percent
  const active = submitting.value
  const failedStage = liveProgress.value.status === 'failed' ? liveProgress.value.stage : ''
  const statusAt = (stage: string, start: number, done: number) => !active ? (reviewSufficient.value ? 'waiting' : 'idle') : failedStage === stage ? 'failed' : p >= done ? 'completed' : p >= start ? 'running' : 'waiting'
  return [
    { icon: DocumentCopy, name: '资料解析 Agent', detail: '解析文字描述与能力线索', status: statusAt('material', 5, 18) },
    { icon: Search, name: '知识库检索 Agent', detail: '检索岗位知识与来源片段', status: statusAt('retrieval', 18, 30) },
    { icon: DataAnalysis, name: '能力诊断 Agent', detail: '抽取证据并对照能力模型', status: statusAt('diagnosis', 30, 42) },
    { icon: Aim, name: '真实结果校准 Agent', detail: '比对标准结果与评分误差', status: statusAt('calibration', 42, 50) },
    { icon: Link, name: '路径规划 Agent', detail: '依据能力缺口规划路径', status: statusAt('path', 50, 55) },
    { icon: Cpu, name: '资源生成 Agent', detail: '检索知识库并生成资源', status: statusAt('resource', 55, 92) },
    { icon: CircleCheck, name: '审核纠偏 Agent', detail: '校验来源与生成内容', status: statusAt('review', 92, 100) },
  ]
})

async function loadJobs() {
  jobLoading.value = true
  jobError.value = false
  if (publicPreview || demoMode.value) {
    jobs.value = previewJobs
  } else {
    try { jobs.value = await getJobList() } catch { jobError.value = true }
  }
  const queryJob = typeof route.query.job === 'string' ? route.query.job : ''
  if (queryJob && jobs.value.some(job => job.id === queryJob)) selectedJobId.value = queryJob
  else if (!selectedJobId.value && jobs.value[0]) selectedJobId.value = jobs.value[0].id
  if (demoMode.value) {
    userInput.value = ''
    reviewTurnCount.value = 1
    minimumReviewTurns.value = 2
    followupPending.value = true
    canSkipFollowup.value = false
    reviewMissing.value = ['个人负责模块', '实现方式', '验证结果']
    reviewHint.value = previewFollowupQuestion
    reviewSufficient.value = false
    demoReplySent.value = false
    liveProgress.value = {
      stage: 'material', agent: '资料审查 Agent', label: '已完成第 1 轮，正在等待第 2 轮定向回答', percent: 42, status: 'running', updated_at: '2026-08-17T09:34:00Z',
      events: [
        { stage: 'material', agent: '资料解析 Agent', label: '已完成资料解析', percent: 22, status: 'completed', updated_at: '2026-08-17T09:31:00Z' },
        { stage: 'material', agent: '资料审查 Agent', label: '已生成第 2 轮定向问题', percent: 42, status: 'running', updated_at: '2026-08-17T09:34:00Z' },
      ],
    }
  }
  jobLoading.value = false
}
function resetReview() { reviewHint.value = ''; reviewMissing.value = []; reviewSufficient.value = false; followupPending.value = false; canSkipFollowup.value = false }
function resetConversation() {
  resetReview()
  reviewSessionId.value = ''
  reviewMessages.value = []
  reviewTurnCount.value = 0
  minimumReviewTurns.value = 2
  store.setCurrentSession(null)
}
function selectJob(jobId: string) { selectedJobId.value = jobId; jobPickerOpen.value = false }
function closeJobPicker(event: PointerEvent) { if (jobPickerRef.value && !jobPickerRef.value.contains(event.target as Node)) jobPickerOpen.value = false }
function agentStatusText(status: string) { return { idle: '待开始', waiting: '等待中', running: '运行中', completed: '已完成', failed: '失败', blocked: '已拦截' }[status] || '等待中' }
async function pollProgress() { if (!assessmentId.value || progressPolling) return; progressPolling = true; try { liveProgress.value = await getAssessmentProgress(assessmentId.value) } catch { /* keep the latest verified progress */ } finally { progressPolling = false } }
function startPolling() { stopPolling(); pollProgress(); progressTimer = window.setInterval(pollProgress, 900) }
function stopPolling() { if (progressTimer !== null) { window.clearInterval(progressTimer); progressTimer = null } }
function startProgressUpdates() {
  stopProgressUpdates()
  if (!assessmentId.value) return
  const controller = new AbortController()
  progressStreamController = controller
  void streamAssessmentProgress(assessmentId.value, snapshot => {
    liveProgress.value = snapshot
  }, controller.signal).catch(() => {
    if (!controller.signal.aborted) startPolling()
  })
}
function stopProgressUpdates() {
  progressStreamController?.abort()
  progressStreamController = null
  stopPolling()
}
async function waitForCompletion() {
  const deadline = Date.now() + 15 * 60 * 1000
  while (Date.now() < deadline) {
    if (liveProgress.value.status === 'failed') throw new Error(liveProgress.value.label || '诊断任务执行失败')
    if (liveProgress.value.percent >= 100 || liveProgress.value.status === 'completed') return
    await new Promise(resolve => window.setTimeout(resolve, 320))
  }
  throw new Error('诊断任务超过等待时间，请稍后进入能力诊断页查看状态')
}
async function ensureReviewSession() {
  if (reviewSessionId.value) return reviewSessionId.value
  const session = await createSession({ job_id: selectedJobId.value, minimum_turns: 2 })
  reviewSessionId.value = session.id
  store.setCurrentSession(session.id)
  return session.id
}
async function restoreReviewSession() {
  const sessionId = store.currentSessionId
  if (!sessionId || demoMode.value || !store.isLoggedIn) return
  try {
    const session = await getReviewSession(sessionId)
    if (session.status === 'completed' || session.assessment_id) {
      store.setCurrentSession(null)
      return
    }
    const messages = await getSessionMessages(sessionId)
    restoringReview.value = true
    reviewSessionId.value = session.id
    selectedJobId.value = session.job_id
    reviewMessages.value = messages
    reviewTurnCount.value = session.turn_count || 0
    minimumReviewTurns.value = Math.max(2, session.minimum_turns || 2)
    reviewSufficient.value = Boolean(session.ready_for_diagnosis)
    followupPending.value = !reviewSufficient.value && reviewTurnCount.value > 0
    canSkipFollowup.value = !reviewSufficient.value && reviewTurnCount.value >= 1
    reviewMissing.value = session.review_state?.missing || []
    reviewHint.value = session.review_state?.last_question || ''
    store.setCurrentSession(session.id)
  } catch {
    // A stale pointer can belong to a different signed-in user or a removed
    // session. Clear only the browser pointer; the server remains authoritative.
    store.setCurrentSession(null)
  } finally {
    restoringReview.value = false
  }
}
function recordDialogueTurn(content: string, result: Awaited<ReturnType<typeof submitReviewTurn>>) {
  const turnIndex = result.turn_count
  reviewMessages.value.push(
    { id: `user-${Date.now()}-${turnIndex}`, role: 'user', content, turn_index: turnIndex, created_at: new Date().toISOString() },
    { id: `assistant-${Date.now()}-${turnIndex}`, role: 'assistant', content: result.assistant_message, turn_index: turnIndex, created_at: new Date().toISOString() },
  )
  reviewTurnCount.value = result.turn_count
  minimumReviewTurns.value = result.minimum_turns
  reviewMissing.value = result.missing || []
  reviewHint.value = result.reason || ''
  reviewSufficient.value = result.ready_for_diagnosis
  followupPending.value = !result.ready_for_diagnosis
  canSkipFollowup.value = result.can_skip_followup
}
async function launchFormalDiagnosis() {
  liveProgress.value = { stage: 'material', agent: '资料解析 Agent', label: '多轮资料审查完成，正在创建正式诊断任务', percent: 8, status: 'running', updated_at: null, events: [] }
  const assessment = await createAssessment({ job_id: selectedJobId.value })
  assessmentId.value = assessment.id
  startProgressUpdates()
  await submitAssessment(assessment.id, {
    user_input: '多轮资料审查会话已提供能力证据。',
    session_id: reviewSessionId.value,
  })
  await waitForCompletion()
  liveProgress.value = { ...liveProgress.value, stage: 'complete', agent: '协同调度器', label: '审查完成', percent: 100, status: 'completed' }
  await store.fetchUserInfo().catch(() => undefined)
  // The just-completed assessment is always the immediate navigation target.
  // The diagnosis page then confirms the server-side active pointer on load.
  await router.push(`/diagnosis/${assessment.id}`)
}
async function startReview(forceFinish = false) {
  if (demoMode.value) {
    if (userInput.value.trim().length < 10 || demoReplySent.value) return
    previewReply.value = userInput.value.trim()
    userInput.value = ''
    demoReplySent.value = true
    reviewTurnCount.value = 2
    followupPending.value = false
    reviewSufficient.value = true
    reviewMissing.value = []
    liveProgress.value = {
      stage: 'complete', agent: '资料审查 Agent', label: '第 2 轮回答已归档，可进入能力诊断', percent: 100, status: 'completed', updated_at: new Date().toISOString(),
      events: [
        ...liveProgress.value.events,
        { stage: 'material', agent: '资料审查 Agent', label: '已归档第 2 轮定向回答', percent: 100, status: 'completed', updated_at: new Date().toISOString() },
      ],
    }
    return
  }
  if (!store.isLoggedIn) { router.push({ path: '/login', query: { next: '/input' } }); return }
  const content = forceFinish ? '暂不补充，按当前资料进入能力诊断。' : userInput.value.trim()
  if (!selectedJobId.value || content.length < 10 || reviewSufficient.value) return
  reviewHint.value = ''; reviewMissing.value = []
  try {
    submitting.value = true
    liveProgress.value = { stage: 'material', agent: '资料审查 Agent', label: reviewTurnCount.value ? '正在分析补充信息并决定是否进入诊断' : '正在提取首轮信息中的能力证据', percent: reviewTurnCount.value ? 46 : 18, status: 'running', updated_at: null, events: [] }
    const sessionId = await ensureReviewSession()
    const result = await submitReviewTurn(sessionId, { content, force_finish: forceFinish })
    recordDialogueTurn(content, result)
    userInput.value = ''
    if (result.ready_for_diagnosis) await launchFormalDiagnosis()
  } catch (error: any) { const message = error?.response?.data?.detail || error?.message || '审查任务启动失败，请稍后重试'; ElMessage.error(message); reviewHint.value = message } finally { submitting.value = false; stopProgressUpdates() }
}
function skipFollowup() { void startReview(true) }
watch(selectedJobId, (next, previous) => {
  if (!demoMode.value && !restoringReview.value && previous && next !== previous) resetConversation()
})
onMounted(() => {
  void loadJobs().then(restoreReviewSession)
  document.addEventListener('pointerdown', closeJobPicker)
})
onBeforeUnmount(() => {
  stopProgressUpdates()
  document.removeEventListener('pointerdown', closeJobPicker)
})
</script>

<style scoped>
.review-page { padding-top: 10px; background: radial-gradient(circle at 10% 8%, rgba(189,244,207,.2), transparent 32%), radial-gradient(circle at 88% 82%, rgba(222,250,222,.5), transparent 35%), linear-gradient(180deg,#fdfffe 0%,#f4fbf7 100%); }
.review-heading { margin-bottom: 14px; }
.workspace-grid { display: grid; grid-template-columns: minmax(0, 2.2fr) minmax(360px, 1fr); gap: 22px; align-items: stretch; }
.review-workspace {
  position: relative;
  min-height: 628px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  isolation: isolate;
  border: 1px solid rgba(255,255,255,.78);
  border-radius: var(--radius-xl);
  background: linear-gradient(144deg, rgba(255,255,255,.62), rgba(247,255,250,.35) 53%, rgba(189,244,207,.13)), rgba(250,255,252,.4);
  box-shadow: 0 32px 78px rgba(20,93,56,.09), inset 0 1px 1px rgba(255,255,255,.98), inset 0 -1px 1px rgba(34,181,107,.035);
  backdrop-filter: blur(34px) saturate(158%);
}
.workspace-top { position: relative; z-index: 40; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 4px 16px; border-bottom: 1px solid var(--line); }
.workspace-status { display: flex; align-items: center; gap: 7px; color: var(--ink-soft); font-size: 12px; }
.workspace-status b { color: var(--ink); font-size: 13px; }
.pulse { height: 8px; width: 8px; border-radius: 50%; background: var(--gradient-primary); box-shadow: 0 0 0 5px rgba(19,169,99,.11), 0 0 14px rgba(34,181,107,.25); animation: breathe 2s ease-in-out infinite; }
.job-picker { display: flex; align-items: center; gap: 7px; }
.job-picker label { font-size: 11px; color: var(--ink-soft); }
.job-picker select { max-width: 190px; border: 1px solid var(--line); border-radius: 10px; padding: 7px 25px 7px 10px; color: var(--ink); background: rgba(255,255,255,.69); outline: none; font-size: 12px; }
.conversation { z-index: 1; min-width: 0; min-height: 334px; flex: 1; position: relative; overflow-x: hidden; padding: 22px 9px 14px; display: flex; flex-direction: column; gap: 15px; }
.message { display: flex; gap: 10px; align-items: flex-start; max-width: 82%; }
.message.user-message { align-self: flex-end; justify-content: flex-end; }
.message.continuation { padding-left: 41px; }
.message-avatar { width: 32px; height: 32px; flex: 0 0 32px; display: grid; place-items: center; border-radius: 11px; background: var(--gradient-primary); color: #fff; box-shadow: 0 7px 15px rgba(9,132,72,.2); }
.message-avatar svg { width: 17px; }
.bubble { padding: 13px 15px; border: 1px solid rgba(255,255,255,.82); border-radius: 18px 18px 18px 6px; background: linear-gradient(138deg, rgba(246,255,249,.64), rgba(222,250,222,.31)), rgba(245,255,248,.37); box-shadow: inset 0 1px 1px rgba(255,255,255,.96), inset 0 -1px 1px rgba(57,178,105,.035), 0 10px 24px rgba(28,89,58,.06); backdrop-filter: blur(19px) saturate(145%); color: var(--ink-soft); font-size: 12px; line-height: 1.68; }
.bubble p { margin: 0; }
.bubble time { display: block; margin-top: 7px; color: var(--ink-faint); font-size: 9px; }
.user-message .bubble { border-radius: 18px 18px 6px 18px; background: linear-gradient(145deg, rgba(255,255,255,.72), rgba(234,255,242,.34)), rgba(255,255,255,.38); box-shadow: inset 0 1px 1px rgba(255,255,255,.98), 0 12px 28px rgba(19,110,60,.07); color: var(--ink); }
.review-feedback b { display: block; color: var(--green-deep); font-size: 12px; margin-bottom: 5px; }
.review-feedback small { display: block; margin-top: 6px; color: #9b6c13; }
.guided-followup { max-width: 88%; }
.guided-followup .bubble { border-color: rgba(36,184,100,.27); background: linear-gradient(145deg, rgba(250,255,252,.78), rgba(222,250,222,.42) 60%, rgba(187,244,207,.2)); box-shadow: inset 0 1px 1px rgba(255,255,255,.98), 0 15px 34px rgba(20,134,71,.1); }
.turn-badge { width: fit-content; display: inline-flex; align-items: center; margin-bottom: 8px; border: 1px solid rgba(30,168,89,.18); border-radius: 999px; padding: 4px 8px; background: rgba(255,255,255,.62); color: var(--green-deep); font-size: 9px; font-weight: 800; letter-spacing: .03em; }
.turn-badge.complete { border-color: rgba(27,161,83,.28); background: rgba(222,250,222,.72); }
.guided-question { margin-top: 11px; border: 1px solid rgba(35,168,91,.19); border-radius: 13px; padding: 10px 11px; background: linear-gradient(135deg, rgba(255,255,255,.68), rgba(219,249,226,.52)); box-shadow: inset 0 1px 1px rgba(255,255,255,.9); }
.guided-question span,.guided-question strong { display: block; }
.guided-question span { color: var(--green-deep); font-size: 9px; font-weight: 800; letter-spacing: .06em; }
.guided-question strong { margin-top: 4px; color: var(--ink); font-size: 12px; line-height: 1.58; }
.typing-bubble { display: flex; align-items: center; gap: 6px; min-width: 190px; }
.typing-bubble span { margin-right: 5px; }
.typing-bubble i { width: 5px; height: 5px; border-radius: 50%; background: var(--green); animation: breathe 1.2s infinite; }
.typing-bubble i:nth-of-type(2) { animation-delay: .18s; }
.typing-bubble i:nth-of-type(3) { animation-delay: .36s; }
.workspace-empty { position: absolute; inset: 103px 0 6px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; pointer-events: none; }
.empty-core { width: 116px; height: 86px; overflow: hidden; border-radius: 50%; mix-blend-mode: multiply; opacity: .87; }
.empty-core img { width: 168px; height: 95px; margin-left: -25px; object-fit: cover; object-position: 51% 47%; }
.workspace-empty h2 { margin: 10px 0 6px; font-size: 17px; }
.workspace-empty p { margin: 0; color: var(--ink-soft); font-size: 11px; }
.empty-actions { display: flex; gap: 8px; margin-top: 16px; pointer-events: auto; }
.empty-actions button { height: 35px; padding: 0 12px; display: inline-flex; align-items: center; gap: 6px; border: 1px solid rgba(14,94,52,.09); border-radius: 11px; background: rgba(255,255,255,.64); color: var(--ink-soft); font-size: 11px; cursor: pointer; }
.empty-actions button:hover:not(:disabled) { color: var(--green-deep); background: rgba(222,250,222,.65); }
.empty-actions svg { width: 14px; }
.composer { position: relative; z-index: 3; margin-top: auto; overflow: hidden; border-radius: 22px; padding: 14px 15px 12px; background: linear-gradient(145deg, rgba(255,255,255,.73), rgba(244,255,248,.4) 60%, rgba(189,244,207,.14)), rgba(255,255,255,.38); border: 1px solid rgba(255,255,255,.9); box-shadow: inset 0 1px 2px rgba(255,255,255,.98), inset 0 -2px 5px rgba(18,98,56,.022), 0 17px 38px rgba(27,85,56,.08); backdrop-filter: blur(27px) saturate(155%); transition: box-shadow .25s ease, border-color .25s ease; }
.composer::before { content: ''; position: absolute; inset: 0; pointer-events: none; background: linear-gradient(110deg, rgba(255,255,255,.34), transparent 25%, rgba(117,231,163,.07)); }
.composer > * { position: relative; z-index: 1; }
.composer.focused { border-color: rgba(134,231,177,.72); box-shadow: inset 0 1px 2px #fff, 0 0 0 4px rgba(222,250,222,.55), 0 17px 36px rgba(27,126,71,.11); }
.composer-question { margin: -2px 0 10px; display: grid; gap: 3px; border-left: 3px solid #1cb566; padding: 4px 0 4px 10px; }
.composer-question span { color: var(--green-deep); font-size: 10px; font-weight: 800; letter-spacing: .04em; }
.composer-question b { color: var(--ink-soft); font-size: 11px; line-height: 1.55; }
.followup-composer textarea { height: 58px; }
.composer.dragging { border-color: rgba(34,181,107,.55); }
.drop-overlay { position: absolute; inset: 0; z-index: 4; display: flex; align-items: center; justify-content: center; gap: 10px; border-radius: inherit; background: rgba(238,255,244,.94); color: var(--green-deep); backdrop-filter: blur(12px); }
.drop-overlay svg { width: 21px; }
.composer textarea { width: 100%; height: 72px; resize: none; border: 0; outline: none; background: transparent; color: var(--ink); line-height: 1.62; font-size: 13px; }
.composer textarea::placeholder { color: var(--ink-faint); }
.composer-tools { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.tool-group { display: flex; gap: 6px; flex-wrap: wrap; }
.tool-group button { height: 31px; padding: 0 9px; display: inline-flex; align-items: center; gap: 5px; border: 0; border-radius: 9px; background: rgba(243,251,246,.62); color: var(--ink-soft); font-size: 10px; cursor: pointer; }
.tool-group button:hover:not(:disabled) { color: var(--green-deep); background: rgba(222,250,222,.72); }
.tool-group svg { width: 13px; }
.submit-group { display: flex; align-items: center; gap: 10px; color: var(--ink-faint); font-size: 10px; }
.skip-followup { height: 34px; border: 1px solid rgba(20,131,72,.16); border-radius: 11px; padding: 0 10px; background: rgba(255,255,255,.56); color: var(--green-deep); font-size: 10px; font-weight: 700; cursor: pointer; transition: background .2s ease, border-color .2s ease; }
.skip-followup:hover:not(:disabled) { border-color: rgba(20,158,86,.38); background: rgba(222,250,222,.72); }
.skip-followup:disabled { opacity: .55; cursor: not-allowed; }
.send-button { min-width: 106px; height: 36px; padding: 0 12px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; border-radius: 12px; font-size: 11px; font-weight: 700; cursor: pointer; }
.send-button:disabled { opacity: .43; cursor: not-allowed; transform: none; }
.send-button svg { width: 14px; }
.inline-error { margin: 9px 2px 0; color: #b33434; font-size: 12px; }

.review-inspector { min-height: 628px; padding: 21px; overflow: hidden; isolation: isolate; border: 1px solid rgba(255,255,255,.76); border-radius: var(--radius-xl); background: linear-gradient(145deg, rgba(255,255,255,.61), rgba(247,255,250,.33) 56%, rgba(189,244,207,.13)), rgba(250,255,252,.4); box-shadow: 0 28px 68px rgba(20,91,55,.085), inset 0 1px 1px rgba(255,255,255,.98); backdrop-filter: blur(32px) saturate(154%); }
.inspector-head { display: flex; align-items: start; justify-content: space-between; gap: 12px; padding-bottom: 18px; }
.inspector-head h2 { margin: 6px 0 0; font-size: 17px; }
.inspector-state { display: inline-flex; align-items: center; gap: 6px; padding: 6px 9px; border-radius: 99px; background: rgba(243,251,246,.72); color: var(--ink-faint); font-size: 9px; }
.inspector-state i { width: 6px; height: 6px; border-radius: 50%; background: #aab7b0; }
.inspector-state.running { color: var(--green-deep); background: rgba(222,250,222,.72); }
.inspector-state.running i { background: var(--green); box-shadow: 0 0 9px rgba(34,181,107,.42); }
.inspector-section { padding: 18px 2px; border-top: 1px solid rgba(20,89,53,.075); }
.section-label, .section-label-line { display: flex; align-items: center; gap: 7px; color: var(--ink-soft); font-size: 10px; font-weight: 700; text-transform: uppercase; }
.section-label svg { width: 14px; color: var(--green-deep); }
.section-label-line { justify-content: space-between; }
.section-label-line button { width: 26px; height: 26px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; color: var(--ink-faint); cursor: pointer; }
.section-label-line button svg { width: 13px; }
.target-section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.target-refresh { min-height: 30px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; flex: 0 0 auto; border: 1px solid rgba(25,126,69,.14); border-radius: 10px; padding: 0 9px; background: linear-gradient(135deg, rgba(255,255,255,.68), rgba(222,250,222,.44)); color: var(--green-deep); box-shadow: inset 0 1px 1px rgba(255,255,255,.95); font-size: 10px; font-weight: 700; cursor: pointer; transition: border-color .2s ease, background .2s ease, transform .2s ease; }
.target-refresh:hover:not(:disabled) { border-color: rgba(25,164,87,.36); background: rgba(222,250,222,.78); transform: translateY(-1px); }
.target-refresh:disabled { opacity: .52; cursor: not-allowed; }
.target-refresh svg { width: 13px; }
.target-section h3 { margin: 11px 0 6px; font-size: 18px; }
.target-section p { margin: 0; color: var(--ink-soft); line-height: 1.55; font-size: 11px; }
.skill-pills { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 12px; }
.skill-pills span { padding: 4px 7px; border-radius: 8px; background: rgba(222,250,222,.66); color: var(--green-deep); font-size: 9px; }
.progress-layout { display: grid; grid-template-columns: 78px 1fr; gap: 15px; align-items: center; margin-top: 13px; }
.progress-ring { width: 74px; height: 74px; display: grid; place-items: center; position: relative; border-radius: 50%; background: conic-gradient(from 210deg, #079455 0deg, #45d986 var(--p), rgba(222,250,222,.72) var(--p)); }
.progress-ring::after { content: ''; position: absolute; inset: 8px; border-radius: 50%; background: rgba(255,255,255,.88); box-shadow: inset 0 1px 2px #fff; }
.progress-ring b { position: relative; z-index: 1; color: var(--green-deep); font-size: 16px; }
.progress-copy > span { color: var(--ink); font-size: 11px; font-weight: 700; }
.track, .evidence-meter { height: 6px; margin: 8px 0; overflow: hidden; border-radius: 99px; background: rgba(98,148,118,.12); }
.track i, .evidence-meter i { display: block; height: 100%; border-radius: inherit; background: var(--gradient-progress); transition: width .45s ease; }
.progress-copy small { color: var(--ink-faint); font-size: 9px; }
.live-agent { margin-top: 13px; padding: 9px 10px; display: flex; align-items: center; gap: 8px; border: 1px solid rgba(31,158,91,.13); border-radius: 11px; background: linear-gradient(120deg,rgba(222,250,222,.5),rgba(255,255,255,.42)); }
.live-agent-dot { width: 7px; height: 7px; flex: 0 0 auto; border-radius: 50%; background: #20b66a; box-shadow: 0 0 0 5px rgba(32,182,106,.1); animation: breathe 1.6s ease-in-out infinite; }
.live-agent div { min-width: 0; flex: 1; }
.live-agent small, .live-agent b { display: block; }
.live-agent small { color: var(--ink-faint); font-size: 8px; }
.live-agent b { margin-top: 2px; overflow: hidden; color: var(--green-deep); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.live-agent em { color: var(--green-deep); font-size: 8px; font-style: normal; }
.progress-events { margin: 10px 0 0; padding: 0; display: flex; flex-direction: column; gap: 7px; list-style: none; }
.progress-events li { display: grid; grid-template-columns: auto minmax(0,1fr) auto; gap: 7px; align-items: center; color: var(--ink-faint); }
.progress-events li > i { width: 6px; height: 6px; border-radius: 50%; background: rgba(30,118,70,.24); }
.progress-events li.running > i { background: #20b66a; box-shadow: 0 0 0 3px rgba(32,182,106,.1); }
.progress-events li.completed > i { background: #079455; }
.progress-events li.failed > i { background: #d94b4b; }
.progress-events li b, .progress-events li span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.progress-events li b { color: var(--ink-soft); font-size: 8px; }
.progress-events li span { margin-top: 1px; font-size: 8px; }
.progress-events li strong { color: var(--green-deep); font-size: 8px; }
.file-empty { padding: 19px 0 2px; display: flex; align-items: center; justify-content: center; gap: 6px; color: var(--ink-faint); font-size: 10px; }
.file-empty svg { width: 14px; }
.file-list { margin-top: 11px; display: flex; flex-direction: column; gap: 9px; }
.file-row { display: grid; grid-template-columns: auto minmax(0,1fr) auto auto; gap: 7px; align-items: center; font-size: 10px; }
.file-icon { width: 22px; height: 22px; display: grid; place-items: center; border-radius: 7px; background: rgba(222,250,222,.62); color: var(--green-deep); }
.file-icon svg { width: 12px; }
.file-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink-soft); }
.file-status { color: var(--ink-faint); font-size: 9px; }
.file-status.parsed { color: var(--green-deep); }
.file-status.failed { color: #c34c4c; }
.file-status.needs_ocr { color: #a36c18; }
.file-row button { width: 22px; height: 22px; display: grid; place-items: center; border: 0; background: transparent; color: var(--ink-faint); cursor: pointer; }
.file-row button svg { width: 12px; }
.quality-row { display: flex; justify-content: space-between; margin-top: 10px; color: var(--ink-soft); font-size: 10px; }
.quality-row b { color: var(--green-deep); }

.pipeline { margin-top: 22px; padding: 19px 23px 21px; overflow: hidden; isolation: isolate; border: 1px solid rgba(255,255,255,.76); border-radius: var(--radius-xl); background: linear-gradient(145deg, rgba(255,255,255,.58), rgba(243,255,248,.33) 52%, rgba(189,244,207,.14)), rgba(250,255,252,.38); box-shadow: 0 25px 62px rgba(20,91,55,.075), inset 0 1px 1px rgba(255,255,255,.96); backdrop-filter: blur(31px) saturate(154%); }
.pipeline-title { display: flex; align-items: end; justify-content: space-between; gap: 20px; }
.pipeline-title h2 { margin: 5px 0 0; font-size: 17px; }
.pipeline-caption { color: var(--ink-faint); font-size: 10px; }
.pipeline-track { display: flex; align-items: center; gap: 10px; margin-top: 20px; }
.agent-node { min-width: 0; flex: 1 1 0; display: grid; grid-template-columns: auto minmax(0,1fr); gap: 9px; align-items: center; }
.agent-symbol { width: 40px; height: 40px; display: grid; place-items: center; position: relative; border-radius: 50%; color: var(--ink-faint); background: rgba(255,255,255,.58); border: 1px solid rgba(15,112,62,.1); }
.agent-symbol svg { width: 17px; }
.agent-node.running .agent-symbol { color: var(--green-deep); background: linear-gradient(135deg, #f5fff7, #bdf4cf); box-shadow: 0 0 0 6px rgba(222,250,222,.44), 0 0 22px rgba(34,181,107,.18); animation: breathe 2s ease-in-out infinite; }
.agent-node.completed .agent-symbol { color: #fff; background: var(--gradient-primary); }
.agent-node.failed .agent-symbol { color: #fff; background: linear-gradient(135deg,#e96b6b,#c83e3e); box-shadow: 0 0 0 5px rgba(217,75,75,.1); }
.agent-node b, .agent-node small, .agent-node em { display: block; }
.agent-node b { font-size: 11px; }
.agent-node small { margin-top: 3px; color: var(--ink-soft); font-size: 9px; line-height: 1.4; }
.agent-node em { margin-top: 4px; color: var(--ink-faint); font-size: 8px; font-style: normal; }
.agent-node.running em, .agent-node.completed em { color: var(--green-deep); }
.pipeline-link { width: 45px; height: 1px; position: relative; background: rgba(30,118,70,.12); overflow: hidden; }
.pipeline-link::before, .pipeline-link::after { content: ''; position: absolute; }
.pipeline-link::after { right: 0; top: -2px; width: 5px; height: 5px; border-top: 1px solid rgba(30,118,70,.25); border-right: 1px solid rgba(30,118,70,.25); transform: rotate(45deg); }
.pipeline-link i { display: block; width: 42%; height: 100%; background: var(--gradient-progress); opacity: 0; }
.pipeline-link.active i { opacity: 1; animation: link-flow 2.2s ease-in-out infinite; }
@keyframes link-flow { from { transform: translateX(-110%); } to { transform: translateX(340%); } }
.error-state { padding: 30px; border-radius: var(--radius-md); display: flex; align-items: center; gap: 14px; }
.error-state span { color: var(--ink-soft); font-size: 13px; }
.error-state button { border: 0; border-radius: 10px; padding: 9px 12px; margin-left: auto; background: var(--gradient-primary); color: #fff; cursor: pointer; }
@media (max-width: 1060px) { .workspace-grid { grid-template-columns: 1fr; } .review-inspector { min-height: auto; display: grid; grid-template-columns: repeat(2,1fr); gap: 0 22px; } .inspector-head { grid-column: 1 / 3; } .inspector-section:nth-of-type(1), .inspector-section:nth-of-type(2) { border-top: 1px solid var(--line); } .pipeline-track { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; } .pipeline-link { display: none; } }
@media (max-width: 680px) { .workspace-top { align-items: flex-start; flex-direction: column; } .job-picker select { max-width: 230px; } .review-workspace { padding: 14px; min-height: 640px; } .conversation { min-height: 330px; } .workspace-empty { inset-top: 100px; } .empty-actions { flex-wrap: wrap; justify-content: center; } .composer-tools { align-items: flex-end; } .submit-group > span { display: none; } .tool-group button { padding-inline: 7px; } .review-inspector { display: block; padding: 18px; } .inspector-head { display: flex; } .pipeline { padding: 16px; } .pipeline-title { display: block; } .pipeline-caption { display: block; margin-top: 8px; } .pipeline-track { grid-template-columns: 1fr; } .message { max-width: 96%; } .error-state { display: block; } .error-state > * { display: block; margin: 8px 0; } .error-state button { margin-left: 0; } }

/* Final desktop composition pass: keep the workspace and the multi-agent strip in one viewport. */
@media (min-width: 1061px) {
  .review-heading .eyebrow { display: none; }
  .review-heading { margin-bottom: 24px; }
  .review-workspace { min-height: 480px; }
  .review-inspector {
    min-width: 0;
    min-height: 0;
    margin-top: 0;
    padding: 18px 21px 17px;
  }
  .review-inspector .inspector-head { display: none; }
  .review-inspector .inspector-section { padding-top: 9px; padding-bottom: 9px; }
  .review-inspector .progress-events { display: flex; max-height: 166px; overflow: auto; padding-right: 4px; }
  .conversation { min-height: 215px; }
  .composer textarea { height: 58px; }
  .pipeline { margin-top: 16px; }
}

/* Desktop legibility pass: enlarge the review workspace without changing its workflow. */
@media (min-width: 1061px) {
  .review-page { padding-top: 6px; }
  .review-page .review-heading { margin-bottom: 12px; }
  .review-page .workspace-grid { gap: 28px; }
  .review-page .review-workspace {
    min-height: 620px;
    padding: 28px;
  }
  .review-page .workspace-top { gap: 20px; padding: 0 6px 20px; }
  .review-page .workspace-status { gap: 10px; font-size: 14px; }
  .review-page .workspace-status b { font-size: 16px; }
  .review-page .pulse { width: 9px; height: 9px; }
  .review-page .job-picker { gap: 10px; }
  .review-page .job-picker label { font-size: 13px; }
  .review-page .job-picker select { max-width: 240px; min-height: 44px; padding: 10px 34px 10px 13px; border-radius: 12px; font-size: 14px; }
  .review-page .conversation { min-height: 300px; padding: 28px 14px 20px; gap: 20px; }
  .review-page .message { gap: 14px; }
  .review-page .message.continuation { padding-left: 54px; }
  .review-page .message-avatar { width: 40px; height: 40px; flex-basis: 40px; border-radius: 13px; }
  .review-page .message-avatar svg { width: 21px; }
  .review-page .bubble { padding: 17px 19px; border-radius: 21px 21px 21px 7px; font-size: 15px; line-height: 1.72; }
  .review-page .user-message .bubble { border-radius: 21px 21px 7px 21px; }
  .review-page .bubble time { margin-top: 9px; font-size: 11px; }
  .review-page .review-feedback b { font-size: 14px; }
  .review-page .review-feedback small { font-size: 12px; }
  .review-page .workspace-empty { inset: 118px 0 8px; }
  .review-page .empty-core { width: 138px; height: 100px; }
  .review-page .empty-core img { width: 198px; height: 112px; margin-left: -30px; }
  .review-page .workspace-empty h2 { margin-top: 14px; font-size: 21px; }
  .review-page .workspace-empty p { font-size: 13px; }
  .review-page .empty-actions { gap: 10px; margin-top: 20px; }
  .review-page .empty-actions button { height: 42px; padding: 0 15px; border-radius: 13px; font-size: 13px; }
  .review-page .empty-actions svg { width: 16px; }
  .review-page .composer { padding: 19px 20px 16px; border-radius: 25px; }
  .review-page .composer textarea { height: 90px; font-size: 16px; }
  .review-page .composer-tools { gap: 16px; }
  .review-page .tool-group { gap: 8px; }
  .review-page .tool-group button { height: 38px; padding: 0 12px; border-radius: 11px; gap: 7px; font-size: 12px; }
  .review-page .tool-group svg { width: 15px; }
  .review-page .submit-group { gap: 12px; font-size: 12px; }
  .review-page .skip-followup { height: 40px; border-radius: 13px; padding: 0 13px; font-size: 12px; }
  .review-page .send-button { min-width: 124px; height: 44px; border-radius: 14px; gap: 8px; font-size: 13px; }
  .review-page .send-button svg { width: 16px; }
  .review-page .review-inspector {
    min-width: 0;
    min-height: 0;
    margin-top: 0;
    padding: 28px;
    border-radius: 30px;
  }
  .review-page .review-inspector .inspector-section { padding: 18px 3px; }
  .review-page .section-label,
  .review-page .section-label-line { gap: 9px; font-size: 13px; }
  .review-page .section-label svg { width: 17px; }
  .review-page .section-label-line button { width: 32px; height: 32px; }
  .review-page .section-label-line button svg { width: 15px; }
  .review-page .target-refresh { min-height: 34px; padding: 0 11px; border-radius: 11px; font-size: 11px; }
  .review-page .target-refresh svg { width: 14px; }
  .review-page .target-section h3 { margin: 13px 0 8px; font-size: 24px; }
  .review-page .target-section p { font-size: 13px; line-height: 1.7; }
  .review-page .skill-pills { gap: 7px; margin-top: 15px; }
  .review-page .skill-pills span { padding: 6px 9px; border-radius: 9px; font-size: 11px; }
  .review-page .progress-layout { grid-template-columns: 98px 1fr; gap: 18px; margin-top: 16px; }
  .review-page .progress-ring { width: 92px; height: 92px; }
  .review-page .progress-ring::after { inset: 10px; }
  .review-page .progress-ring b { font-size: 20px; }
  .review-page .progress-copy > span { font-size: 14px; }
  .review-page .track,
  .review-page .evidence-meter { height: 7px; margin: 10px 0; }
  .review-page .progress-copy small { font-size: 11px; }
  .review-page .live-agent { margin-top: 16px; padding: 12px 13px; gap: 10px; border-radius: 13px; }
  .review-page .live-agent-dot { width: 8px; height: 8px; }
  .review-page .live-agent small { font-size: 10px; }
  .review-page .live-agent b { font-size: 12px; }
  .review-page .live-agent em { font-size: 10px; }
  .review-page .progress-events { margin-top: 14px; gap: 10px; max-height: 205px; }
  .review-page .progress-events li { gap: 9px; }
  .review-page .progress-events li > i { width: 8px; height: 8px; }
  .review-page .progress-events li b { font-size: 10px; }
  .review-page .progress-events li span { font-size: 11px; }
  .review-page .progress-events li strong { font-size: 10px; }
  .review-page .file-list { margin-top: 14px; gap: 12px; }
  .review-page .file-row { gap: 9px; font-size: 13px; }
  .review-page .file-icon { width: 30px; height: 30px; border-radius: 9px; }
  .review-page .file-icon svg { width: 16px; }
  .review-page .file-status { font-size: 11px; }
  .review-page .file-row button { width: 30px; height: 30px; }
  .review-page .file-row button svg { width: 15px; }
  .review-page .file-empty { padding-top: 24px; font-size: 12px; }
  .review-page .file-empty svg { width: 17px; }
  .review-page .quality-row { margin-top: 13px; font-size: 13px; }
  .review-page .evidence-meter { margin-top: 9px; }
  .review-page .pipeline { margin-top: 24px; padding: 24px 30px 26px; }
  .review-page .pipeline-title h2 { font-size: 21px; }
  .review-page .pipeline-caption { font-size: 12px; }
  .review-page .pipeline-track { gap: 14px; margin-top: 24px; }
  .review-page .agent-node { gap: 11px; }
  .review-page .agent-symbol { width: 48px; height: 48px; }
  .review-page .agent-symbol svg { width: 21px; }
  .review-page .agent-node b { font-size: 13px; }
  .review-page .agent-node small { font-size: 11px; }
  .review-page .agent-node em { font-size: 10px; }
  .review-page .pipeline-link { width: 56px; }
}

/* Text-first review flow: the job selector and progress disclosure share the glass system. */
.job-picker { position: relative; z-index: 60; display: flex; align-items: center; gap: 9px; }
.job-picker-label { color: var(--ink-soft); font-size: 11px; white-space: nowrap; }
.job-trigger { min-width: 208px; min-height: 38px; display: flex; align-items: center; justify-content: space-between; gap: 12px; border: 1px solid rgba(255,255,255,.86); border-radius: 12px; padding: 0 11px; background: linear-gradient(145deg, rgba(255,255,255,.75), rgba(231,252,239,.42)); box-shadow: inset 0 1px 1px rgba(255,255,255,.98), 0 9px 20px rgba(20,92,53,.055); color: var(--ink); cursor: pointer; transition: border-color .2s ease, transform .2s ease; }
.job-trigger:hover:not(:disabled) { border-color: rgba(31,179,96,.35); transform: translateY(-1px); }
.job-trigger:disabled { opacity: .58; cursor: not-allowed; }
.job-trigger > span { display: flex; min-width: 0; align-items: center; gap: 7px; }
.job-trigger > span svg { width: 15px; flex: 0 0 auto; color: var(--green-deep); }
.job-trigger b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.job-trigger > svg { width: 15px; color: var(--green-deep); transition: transform .2s ease; }
.job-trigger > svg.open { transform: rotate(180deg); }
.job-menu { position: absolute; z-index: 80; top: calc(100% + 8px); right: 0; width: min(360px, calc(100vw - 44px)); max-height: 330px; overflow: auto; padding: 7px; border: 1px solid rgba(255,255,255,.9); border-radius: 16px; background: linear-gradient(145deg, rgba(255,255,255,.91), rgba(238,255,245,.78)); box-shadow: 0 24px 54px rgba(18,73,43,.16), inset 0 1px 1px #fff; backdrop-filter: blur(28px) saturate(155%); }
.job-menu button { width: 100%; display: grid; grid-template-columns: 34px minmax(0,1fr) auto; gap: 9px; align-items: center; border: 0; border-radius: 11px; padding: 9px; background: transparent; color: var(--ink); text-align: left; cursor: pointer; }
.job-menu button:hover,.job-menu button.active { background: linear-gradient(135deg, rgba(222,250,222,.86), rgba(255,255,255,.48)); }
.job-menu > button > svg { width: 15px; color: var(--green-deep); }
.job-menu-icon { display: grid; width: 34px; height: 34px; place-items: center; border-radius: 10px; background: rgba(222,250,222,.78); color: var(--green-deep); }
.job-menu-icon svg { width: 16px; }
.job-menu-copy { min-width: 0; }
.job-menu-copy b,.job-menu-copy small,.job-menu-copy em { display: block; }
.job-menu-copy b { font-size: 12px; }
.job-menu-copy small { overflow: hidden; margin-top: 3px; color: var(--ink-soft); font-size: 9px; line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }
.job-menu-copy em { margin-top: 4px; color: var(--green-deep); font-size: 8px; font-style: normal; }
.composer-hint { color: var(--ink-faint); font-size: 10px; }
.progress-expand { width: 27px; height: 27px; display: grid; place-items: center; border: 1px solid rgba(25,126,69,.12); border-radius: 9px; background: rgba(255,255,255,.54); color: var(--green-deep); cursor: pointer; }
.progress-expand:hover { background: rgba(222,250,222,.78); }
.progress-expand svg { width: 14px; transition: transform .2s ease; }
.progress-expand svg.open { transform: rotate(180deg); }
.quality-title { margin-bottom: 16px; color: var(--ink); font-size: 16px; font-weight: 800; }
.quality-title svg { width: 19px; }
@media (min-width: 1061px) { .review-page .review-inspector { min-width: 0; min-height: 0; margin-top: 0; align-self: stretch; } .review-page .quality-title { margin-bottom: 20px; font-size: 18px; } .review-page .composer-hint { font-size: 12px; } .review-page .job-trigger { min-width: 258px; min-height: 44px; border-radius: 13px; } .review-page .job-trigger b { font-size: 14px; } }
@media (max-width: 680px) { .review-page { padding-top: 22px; } .job-picker { width: 100%; justify-content: space-between; } .job-trigger { flex: 1; min-width: 0; } .job-menu { left: 0; right: auto; } .composer-hint { display: none; } .target-refresh { min-height: 32px; padding-inline: 10px; } }
</style>
