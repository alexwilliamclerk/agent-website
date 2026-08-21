<template>
  <div class="page-shell diagnosis-page">
    <div class="content-width">
      <header class="diagnosis-heading motion-enter">
        <div><span class="eyebrow">DIAGNOSTIC CORE</span><h1 class="page-title">能力诊断 <MagicStick /></h1><p class="page-subtitle">基于岗位能力模型与可追溯证据，形成多维能力判断、真实结果校准和下一阶段学习建议。</p></div>
        <div class="heading-actions"><button type="button" class="top-action" :disabled="loading || running" @click="loadAssessment"><Refresh /> 重新读取</button><button type="button" class="top-action primary" :disabled="demoMode || !assessment || !requirementItems.length" @click="showCalibration = !showCalibration"><Aim /> {{ showCalibration ? '收起校准' : '校准准确率' }}</button></div>
      </header>

      <section v-if="loading || running" class="diagnosis-loading glass-surface">
        <img src="/assets/diagnostic-platform.png" alt="正在运行的诊断空间核心" />
        <div class="loading-copy"><span class="glass-pill"><Loading /> Agent 运行中</span><h2>{{ running ? progress.label : '正在读取诊断报告' }}</h2><p>{{ running ? `${progress.percent}% · ${progress.agent} · 系统会在真实 Agent 任务完成后自动刷新` : '正在加载本次诊断的真实数据' }}</p><div class="loading-track"><i :style="{ width: `${Math.max(8, progress.percent)}%` }"></i></div><ol v-if="running && progress.events.length" class="diagnosis-progress-events"><li v-for="event in progress.events.slice(-5).reverse()" :key="`${event.updated_at}-${event.percent}-${event.label}`"><i></i><span>{{ event.agent }}</span><b>{{ event.percent }}%</b><small>{{ event.label }}</small></li></ol></div>
      </section>

      <section v-else-if="loadError" class="diagnosis-error glass-surface"><WarningFilled /><div><h2>{{ loadError }}</h2><p>请检查本次诊断是否已完成，或返回资料审查重新启动任务。</p></div><button type="button" @click="router.push('/input')">前往资料审查</button></section>

      <section v-else-if="!assessment" class="empty-diagnostic glass-surface motion-enter motion-delay-1">
        <div class="empty-visual-grid">
          <aside class="empty-match-preview"><span class="empty-label">岗位匹配度</span><strong>--</strong><small>等待能力证据</small><div class="empty-glass-orb"><Briefcase /></div></aside>
          <div class="empty-core-stage"><img src="/assets/diagnostic-platform.png" alt="待激活的能力诊断空间核心" /><div class="empty-core-copy"><span class="glass-pill"><DataAnalysis /> Diagnostic Core</span><h2>完成资料审查，激活能力诊断核心</h2><p>系统将汇总资料证据、能力问答与岗位要求，生成评分、雷达图和优先学习路径。</p><button class="primary-gradient-button" type="button" @click="router.push('/input')">开始资料审查 <ArrowRight /></button></div></div>
          <aside class="empty-dimension-preview"><span class="empty-label">能力维度</span><div v-for="name in emptyDimensions" :key="name"><span>{{ name }}</span><i></i><em>待评估</em></div></aside>
        </div>
        <div class="empty-process"><div v-for="(step, index) in emptySteps" :key="step.title"><span><component :is="step.icon" /></span><b>{{ index + 1 }}. {{ step.title }}</b><small>{{ step.detail }}</small></div></div>
      </section>

      <template v-else>
        <section v-if="showCalibration" class="calibration-panel glass-surface motion-enter"><div><span class="glass-pill">真实结果校准</span><h2>录入客观题、实操或专家标注结果</h2><p>系统仅在收到可追溯的真实结果后计算准确率；未校准不等于准确率低。</p></div><div class="calibration-fields"><label v-for="item in requirementItems" :key="item.requirement_id"><span>{{ item.requirement_name }}</span><input v-model.number="goldScores[item.requirement_id]" type="number" min="0" max="100" placeholder="0–100" /></label></div><div class="calibration-actions"><label class="correction-check"><input v-model="applyCorrections" type="checkbox" /> 将可信结果用于校正本次诊断</label><button type="button" :disabled="calibrationSubmitting" @click="submitCalibration">{{ calibrationSubmitting ? '校准中…' : '提交真实结果' }}</button></div></section>

        <section class="core-grid motion-enter motion-delay-1">
          <article class="match-card glass-surface">
            <div class="card-heading"><span class="card-eyebrow">总体匹配度</span><Briefcase /></div>
            <p>与 {{ jobTitle }} 能力模型匹配度</p>
            <strong class="gradient-number">{{ overallPercent }}<small>%</small></strong>
            <span class="match-badge" :class="levelClass"><i></i>{{ levelText }}</span>
            <div class="match-insight"><span>诊断置信度</span><b>{{ confidencePercent }}%</b></div>
            <footer>基于 {{ traceSourceCount || '待加载' }} 条可追溯依据</footer>
          </article>

          <article class="diagnostic-core" @pointermove="moveSpotlight" @pointerleave="resetSpotlight">
            <img class="diagnostic-platform" src="/assets/diagnostic-platform.png" alt="绿色玻璃质感的能力诊断空间平台" />
            <div class="core-glass glass-surface">
              <div class="core-body">
                <section class="score-module">
                  <div class="core-module-heading"><span>综合得分</span><small>OVERALL SCORE</small></div>
                  <div class="score-gauge-shell">
                    <div ref="scoreRef" class="score-gauge"></div>
                    <div class="score-value"><b>{{ overallPercent }}</b><span>/100</span></div>
                  </div>
                  <div class="score-verdict"><i></i><span>{{ levelText }}</span></div>
                </section>
                <span class="core-separator" aria-hidden="true"></span>
                <section class="radar-module">
                  <div class="core-module-heading"><span>能力雷达图</span><small>{{ assessment.ability_vector?.length || 0 }} DIMENSIONS</small></div>
                  <div ref="radarRef" class="radar-chart"></div>
                </section>
              </div>
              <div class="core-meta"><span>评估于 {{ formattedDate }}</span><span>{{ traceLabel }}</span><span class="core-status"><i></i>诊断完成</span><span v-if="demoMode" class="demo-badge">DEV 示例</span></div>
            </div>
          </article>

          <article class="agent-summary diagnostic-agent-summary glass-surface"><span class="agent-face"><Cpu /></span><h2>Agent 综合结论</h2><p>{{ agentSummary }}</p><div class="review-metric"><span>真实结果<br />准确率</span><b :class="accuracyClass">{{ calibrationText }}</b></div><button type="button" @click="openLibrary">查看推荐学习资料 <ArrowRight /></button></article>
        </section>

        <section class="analysis-grid motion-enter motion-delay-2">
          <article class="evidence-insights glass-surface">
            <section class="strengths"><h2><StarFilled /> 优势亮点</h2><ul v-if="strengths.length"><li v-for="item in strengths" :key="item.index"><span><CircleCheck /></span><div><b>{{ item.name }}</b><small>{{ toPercent(item.value) }} 分 · 已具备较强能力证据</small></div></li></ul><p v-else>本次诊断暂未形成足够的优势能力结论。</p></section>
            <section class="gaps"><h2><WarningFilled /> 待提升项</h2><ul v-if="gaps.length"><li v-for="(gap, index) in gaps.slice(0, 3)" :key="gap"><b>{{ String(index + 1).padStart(2, '0') }}</b><span>{{ gap }}</span></li></ul><p v-else>当前未识别到需要优先补强的能力缺口。</p></section>
          </article>

          <article class="roadmap-card glass-surface"><div class="roadmap-heading"><h2><MapLocation /> 优先学习路径</h2><span>推荐</span></div><div v-if="pathLoading" class="path-empty">正在读取学习路径…</div><div v-else-if="currentPath?.steps?.length" class="roadmap"><div class="roadmap-line"></div><div v-for="(step, index) in currentPath.steps.slice(0, 3)" :key="step.step" class="roadmap-step" :class="{ current: index === 0 }"><span>{{ String(index + 1).padStart(2, '0') }}</span><div><b>{{ step.knowledge_point }}</b><small>{{ step.resource_type }} · {{ step.estimated_time }} 分钟</small></div></div></div><div v-else class="path-empty">本次诊断尚未生成可展示的学习路径。</div></article>
        </section>

        <section class="quality-strip glass-panel"><div><CircleCheck /><span>防幻觉审核</span><b>{{ resourceQualityText }}</b></div><div><Files /><span>证据链来源</span><b>{{ traceSourceCount }} 条检索依据</b></div><div><Aim /><span>校准状态</span><b>{{ calibrationStatusText }}</b></div><button type="button" @click="openLibrary">进入资料库 <ArrowRight /></button></section>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import {
  Aim, ArrowRight, Briefcase, CircleCheck, Cpu, DataAnalysis, DocumentChecked,
  Files, Guide, Loading, MagicStick, MapLocation, Refresh, Search, StarFilled,
  WarningFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { calibrateAssessment, getAssessment, getAssessmentAgents, getAssessmentProgress, streamAssessmentProgress, type AssessmentProgress, type AssessmentResponse, type RequirementScore } from '@/api/assessment'
import { getLearningPaths, type LearningPathInfo } from '@/api/path'
import { getResourceList, type ResourceInfo } from '@/api/resource'
import { getJobList } from '@/api/jobs'
import { useUserStore } from '@/stores/user'

const route = useRoute(); const router = useRouter(); const store = useUserStore()
// An explicit demo query is available only in Vite development builds.
// Production builds always keep authentication and real API data enabled.
const demoMode = computed(() => import.meta.env.DEV && route.query.demo === '1')
const assessment = ref<AssessmentResponse | null>(null); const loading = ref(false); const loadError = ref(''); const progress = ref<AssessmentProgress>({ stage: 'material', agent: '资料解析 Agent', label: '正在解析学习情况', percent: 0, status: 'waiting', updated_at: null, events: [] }); const running = ref(false)
const radarRef = ref<HTMLDivElement | null>(null); const scoreRef = ref<HTMLDivElement | null>(null); let chart: echarts.ECharts | null = null; let scoreChart: echarts.ECharts | null = null; let progressTimer: number | null = null; let progressStreamController: AbortController | null = null; let finishing = false
let assessmentLoadSequence = 0
const currentPath = ref<LearningPathInfo | null>(null); const pathLoading = ref(false); const resources = ref<ResourceInfo[]>([]); const traceSourceCount = ref(0)
const showCalibration = ref(false); const calibrationSubmitting = ref(false); const applyCorrections = ref(false); const goldScores = ref<Record<string, number | null>>({})
const jobTitle = ref('目标岗位能力模型')
const assessmentId = computed(() => typeof route.params.id === 'string' ? route.params.id : '')
const overallPercent = computed(() => Math.round((assessment.value?.overall_mastery || 0) * 100)); const confidencePercent = computed(() => Math.round((assessment.value?.confidence || 0) * 100)); const formattedDate = computed(() => assessment.value ? new Date(assessment.value.created_at).toLocaleDateString('zh-CN') : '—')
const strengths = computed(() => [...(assessment.value?.ability_vector || [])].sort((a,b) => b.value - a.value).slice(0, 3)); const gaps = computed(() => assessment.value?.knowledge_gaps || []); const requirementItems = computed<RequirementScore[]>(() => assessment.value?.requirement_scores || [])
const levelClass = computed(() => overallPercent.value >= 80 ? 'good' : overallPercent.value >= 60 ? 'partial' : 'needs'); const levelText = computed(() => overallPercent.value >= 80 ? '良好匹配' : overallPercent.value >= 60 ? '部分匹配' : '优先补强')
const calibration = computed(() => assessment.value?.calibration_summary); const calibrationText = computed(() => calibration.value?.accuracy === null || calibration.value?.accuracy === undefined ? '待校准' : `${Math.round(calibration.value.accuracy * 100)}%`); const accuracyClass = computed(() => calibration.value?.accuracy && calibration.value.accuracy >= .9 ? 'accurate' : 'pending')
const calibrationStatusText = computed(() => assessment.value?.calibration_status === 'passed' ? '已通过' : assessment.value?.calibration_status === 'needs_review' ? '需要复核' : '未校准')
const resourceQualityText = computed(() => !resources.value.length ? '暂无可展示资源' : `${resources.value.filter(item => item.review_status === 'passed').length}/${resources.value.length} 已通过来源校验`)
const traceLabel = computed(() => traceSourceCount.value ? `${traceSourceCount.value} 条依据` : '证据待加载')
const agentSummary = computed(() => { const high = strengths.value.slice(0,2).map(item => item.name).join('、'); const low = [...(assessment.value?.ability_vector || [])].sort((a,b) => a.value - b.value)[0]?.name; if (!high && !low) return '本次诊断尚未形成完整的能力结论。'; return `你已具备较稳定的岗位基础，当前优势集中在${high || '已提交证据覆盖的能力'}。影响下一阶段竞争力的主要因素不是学习资源数量，而是${low || '复杂任务经验'}仍需补强。建议围绕能力缺口完成一次可验证的项目实践，并在复测后更新路径。` })
const emptyDimensions = ['工程能力', '项目经验', '学习潜力', '基础能力', '软实力']
const emptySteps: Array<{ icon: Component; title: string; detail: string }> = [
  { icon: DocumentChecked, title: '资料审查', detail: '提取学习与项目证据' },
  { icon: Search, title: '能力映射', detail: '对照岗位要求和达标规则' },
  { icon: Aim, title: '交叉校验', detail: '复核结论与来源依据' },
  { icon: Guide, title: '路径生成', detail: '输出下一阶段学习行动' },
]

const demoAssessment: AssessmentResponse = {
  id: 'demo-assessment', user_id: 'demo-user', job_id: 'demo-backend', user_input: '本地视觉验收示例', overall_mastery: .82, confidence: .94,
  ability_vector: [
    { index: 0, name: '工程能力', value: .85, weight: 'high', category: 'engineering' },
    { index: 1, name: '项目经验', value: .78, weight: 'high', category: 'project' },
    { index: 2, name: '学习潜力', value: .88, weight: 'mid', category: 'learning' },
    { index: 3, name: '基础能力', value: .74, weight: 'mid', category: 'foundation' },
    { index: 4, name: '软实力', value: .80, weight: 'low', category: 'soft_skill' },
  ],
  knowledge_gaps: ['复杂项目经验不足，缺少大型系统实践', '系统设计与架构思维需要加强', '高并发与分布式技术广度有待拓展'],
  gap_validation: [],
  requirement_scores: [
    { requirement_id: 'demo-r1', requirement_name: '工程实践', dimension: '工程能力', score: .85, status: 'qualified', evidence_ids: ['demo-e1'] },
    { requirement_id: 'demo-r2', requirement_name: '系统设计', dimension: '项目经验', score: .72, status: 'partial', evidence_ids: ['demo-e2'] },
    { requirement_id: 'demo-r3', requirement_name: '学习迁移', dimension: '学习潜力', score: .88, status: 'qualified', evidence_ids: ['demo-e3'] },
  ],
  calibration_status: 'passed',
  calibration_summary: { status: 'passed', evaluated_count: 3, accuracy: .93, mean_absolute_error: .06 },
  material_ids: ['demo-m1', 'demo-m2'], created_at: '2026-08-16T10:20:00+08:00',
}
const demoPath: LearningPathInfo = {
  id: 'demo-path', user_id: 'demo-user', job_id: 'demo-backend', assessment_id: 'demo-assessment', current_step: 1, status: 'active', created_at: '2026-08-16T10:20:00+08:00', updated_at: '2026-08-16T10:20:00+08:00',
  steps: [
    { step: 1, knowledge_point: '夯实工程基础', resource_type: '讲义 + 实操', resource_id: null, estimated_time: 120, prerequisite: null, status: 'current', record_id: null, weight: 'high' },
    { step: 2, knowledge_point: '项目进阶', resource_type: '项目任务书', resource_id: null, estimated_time: 180, prerequisite: '夯实工程基础', status: 'pending', record_id: null, weight: 'high' },
    { step: 3, knowledge_point: '综合突破', resource_type: '阶段复测', resource_id: null, estimated_time: 90, prerequisite: '项目进阶', status: 'pending', record_id: null, weight: 'mid' },
  ],
}
const demoResources: ResourceInfo[] = [0,1,2].map(index => ({ id: `demo-resource-${index}`, assessment_id: 'demo-assessment', knowledge_point: ['系统设计基础','并发编程','项目复盘'][index], content_type: ['讲义','实操任务','错题解析'][index], title: ['系统设计核心概念','并发任务实战','项目问题复盘'][index], body: '仅用于本地视觉验收的示例资料。', difficulty: index + 2, source_chunk_id: `demo-source-${index}`, source_text: '本地视觉示例来源', review_status: 'passed', review_reason: '示例已通过', display_status: 'visible', generation_method: 'demo', created_at: '2026-08-16T10:20:00+08:00' }))

function toPercent(value: number) { return Math.round(value * 100) }
function moveSpotlight(event: PointerEvent) { const element = event.currentTarget as HTMLElement; const rect = element.getBoundingClientRect(); element.style.setProperty('--spot-x', `${event.clientX - rect.left}px`); element.style.setProperty('--spot-y', `${event.clientY - rect.top}px`); element.style.setProperty('--spot-opacity', '.62') }
function resetSpotlight(event: PointerEvent) { const element = event.currentTarget as HTMLElement; element.style.setProperty('--spot-x', '50%'); element.style.setProperty('--spot-y', '38%'); element.style.setProperty('--spot-opacity', '.34') }
function openLibrary() { router.push({ path: '/library', query: demoMode.value ? { demo: '1' } : assessment.value ? { assessment: assessment.value.id } : {} }) }
async function loadDemoFixture() { stopProgressUpdates(); loading.value = false; loadError.value = ''; running.value = false; assessment.value = demoAssessment; jobTitle.value = '后端开发工程师'; currentPath.value = demoPath; resources.value = demoResources; traceSourceCount.value = 12; await nextTick(); renderVisuals() }
async function loadAssessment() {
  if (demoMode.value) { await loadDemoFixture(); return }
  const sequence = ++assessmentLoadSequence
  loading.value = true; loadError.value = ''
  try {
    // Refreshing this page must re-read the server pointer. A newly completed
    // diagnosis therefore replaces an older result immediately, while a
    // history selection remains stable until the server pointer changes.
    await store.fetchUserInfo().catch(() => undefined)
    if (sequence !== assessmentLoadSequence) return
    const currentId = store.currentAssessmentId
    const requestedId = assessmentId.value
    let requestedAssessment: AssessmentResponse | null = null
    if (currentId && requestedId && requestedId !== currentId) {
      // Completed history must follow the persisted selection, but an
      // in-progress diagnosis remains directly accessible from history so the
      // learner can inspect its live Agent progress.
      requestedAssessment = await getAssessment(requestedId)
      if (sequence !== assessmentLoadSequence) return
      if (requestedAssessment.overall_mastery !== null) {
        await router.replace(`/diagnosis/${currentId}`)
        return
      }
    } else if (currentId && !requestedId) {
      await router.replace(`/diagnosis/${currentId}`)
      return
    }
    const targetId = requestedId || currentId
    if (!targetId) {
      assessment.value = null; currentPath.value = null; resources.value = []; traceSourceCount.value = 0
      return
    }
    const item = requestedAssessment || await getAssessment(targetId)
    if (sequence !== assessmentLoadSequence) return
    assessment.value = item
    jobTitle.value = '目标岗位能力模型'
    getJobList().then(jobs => { jobTitle.value = jobs.find(job => job.id === item.job_id)?.job_title || '目标岗位能力模型' }).catch(() => undefined)
    running.value = item.overall_mastery === null
    if (running.value) startProgressUpdates()
    else { stopProgressUpdates(); await Promise.all([loadPath(), loadResources(), loadTrace()]); nextTick(renderVisuals) }
  } catch (error: any) { loadError.value = error?.response?.data?.detail || '无法读取诊断结果' }
  finally { if (sequence === assessmentLoadSequence) loading.value = false }
}
async function startPolling() { stopPolling(); await pollProgress(); progressTimer = window.setInterval(pollProgress, 2500) }
async function pollProgress() { if (!assessmentId.value) return; try { progress.value = await getAssessmentProgress(assessmentId.value); if (progress.value.status === 'failed') { stopProgressUpdates(); running.value = false; loadError.value = progress.value.label; return }; if (progress.value.percent >= 100) await refreshCompletedAssessment() } catch { /* next verified polling cycle retries */ } }
function stopPolling() { if (progressTimer !== null) { window.clearInterval(progressTimer); progressTimer = null } }
function startProgressUpdates() {
  stopProgressUpdates()
  if (!assessmentId.value) return
  const controller = new AbortController()
  progressStreamController = controller
  void streamAssessmentProgress(assessmentId.value, snapshot => {
    progress.value = snapshot
    if (snapshot.status === 'failed') {
      stopProgressUpdates()
      running.value = false
      loadError.value = snapshot.label
    } else if (snapshot.percent >= 100 || snapshot.status === 'completed') {
      void refreshCompletedAssessment()
    }
  }, controller.signal).catch(() => {
    if (!controller.signal.aborted) startPolling()
  })
}
function stopProgressUpdates() {
  progressStreamController?.abort()
  progressStreamController = null
  stopPolling()
}
async function refreshCompletedAssessment() {
  if (finishing) return
  finishing = true
  stopProgressUpdates()
  try { await store.fetchUserInfo().catch(() => undefined); await loadAssessment() } finally { finishing = false }
}
async function loadPath() { if (!assessment.value) return; if (!store.userInfo) await store.fetchUserInfo().catch(() => undefined); if (!store.userInfo) return; pathLoading.value = true; try { const paths = await getLearningPaths(store.userInfo.id, assessment.value.id); currentPath.value = paths[0] || null } finally { pathLoading.value = false } }
async function loadResources() { if (!assessment.value) return; try { resources.value = await getResourceList({ assessment_id: assessment.value.id }) } catch { resources.value = [] } }
async function loadTrace() { if (!assessment.value) return; try { const response = await getAssessmentAgents(assessment.value.id); traceSourceCount.value = response.trace.retrieval_sources?.length || 0 } catch { traceSourceCount.value = 0 } }
function renderScore() {
  if (!scoreRef.value) return
  scoreChart?.dispose()
  scoreChart = echarts.init(scoreRef.value)
  const progressColor = new echarts.graphic.LinearGradient(0, 1, 1, 0, [
    { offset: 0, color: '#05834a' },
    { offset: .58, color: '#18b86b' },
    { offset: 1, color: '#7ee5a7' },
  ])
  const gaugeBase = {
    type: 'gauge' as const,
    startAngle: 90,
    endAngle: -270,
    min: 0,
    max: 100,
    pointer: { show: false },
    axisTick: { show: false },
    splitLine: { show: false },
    axisLabel: { show: false },
    title: { show: false },
    detail: { show: false },
    silent: true,
  }
  scoreChart.setOption({
    animationDuration: 1100,
    animationEasing: 'cubicOut',
    series: [
      { ...gaugeBase, radius: '96%', axisLine: { lineStyle: { width: 2, color: [[1, 'rgba(255,255,255,.72)']] } }, data: [{ value: overallPercent.value }] },
      { ...gaugeBase, radius: '84%', progress: { show: true, roundCap: true, width: 12, itemStyle: { color: progressColor, shadowBlur: 13, shadowColor: 'rgba(28,184,105,.24)' } }, axisLine: { lineStyle: { width: 12, color: [[1, 'rgba(25,132,73,.085)']] } }, data: [{ value: overallPercent.value }] },
      { ...gaugeBase, radius: '66%', axisLine: { lineStyle: { width: 1, color: [[1, 'rgba(24,155,83,.13)']] } }, data: [{ value: overallPercent.value }] },
    ],
  })
}
function renderRadar() {
  const dims = assessment.value?.ability_vector || []
  if (!radarRef.value || !dims.length) return
  chart?.dispose()
  chart = echarts.init(radarRef.value)
  chart.setOption({
    animationDuration: 900,
    animationEasing: 'cubicOut',
    tooltip: { trigger: 'item', formatter: (params: any) => `${params.name || '能力向量'}<br/>${params.value?.map((value: number, index: number) => `${dims[index]?.name} ${toPercent(value)}`).join('<br/>') || ''}` },
    radar: {
      center: ['50%', '54%'],
      radius: '73%',
      splitNumber: 5,
      axisName: { color: 'rgba(35,76,53,.78)', fontSize: 10, fontWeight: 600 },
      axisNameGap: 10,
      splitArea: { areaStyle: { color: ['rgba(255,255,255,.01)', 'rgba(237,252,243,.055)', 'rgba(255,255,255,.012)', 'rgba(222,250,230,.055)', 'rgba(255,255,255,.01)'] } },
      splitLine: { lineStyle: { color: ['rgba(5,118,66,.075)', 'rgba(5,118,66,.12)'], width: 1 } },
      axisLine: { lineStyle: { color: 'rgba(5,118,66,.14)' } },
      indicator: dims.map(item => ({ name: item.name, max: 1 })),
    },
    graphic: [{ type: 'circle', left: 'center', top: '53%', shape: { r: 4 }, style: { fill: 'rgba(255,255,255,.95)', shadowBlur: 12, shadowColor: 'rgba(21,182,101,.45)', stroke: 'rgba(21,155,86,.35)', lineWidth: 1 } }],
    series: [
      {
        type: 'radar', symbol: 'none', silent: true,
        lineStyle: { color: 'rgba(37,199,113,.12)', width: 8, shadowBlur: 18, shadowColor: 'rgba(35,190,108,.18)' },
        areaStyle: { color: 'rgba(72,213,133,.055)' },
        data: [{ value: dims.map(item => item.value), name: '能力得分光层' }],
      },
      {
        type: 'radar', symbol: 'circle', symbolSize: 5,
        lineStyle: { color: 'rgba(5,139,76,.92)', width: 2.2, shadowBlur: 7, shadowColor: 'rgba(34,181,107,.16)' },
        itemStyle: { color: '#12aa61', borderColor: 'rgba(255,255,255,.96)', borderWidth: 1.4, shadowBlur: 8, shadowColor: 'rgba(34,181,107,.2)' },
        areaStyle: { color: new echarts.graphic.RadialGradient(.5, .46, .72, [{ offset: 0, color: 'rgba(116,226,158,.3)' }, { offset: .58, color: 'rgba(49,190,112,.2)' }, { offset: 1, color: 'rgba(10,139,76,.09)' }]) },
        data: [{ value: dims.map(item => item.value), name: '能力得分' }],
      },
    ],
  })
}
function renderVisuals() { renderScore(); renderRadar() }
async function submitCalibration() { if (!assessment.value || demoMode.value) return; const labels = requirementItems.value.map(item => ({ requirement_id: item.requirement_id, gold_score: goldScores.value[item.requirement_id], source_type: 'expert', trusted: true })).filter(item => typeof item.gold_score === 'number' && Number.isFinite(item.gold_score)); if (!labels.length) { ElMessage.warning('至少录入一项真实结果分数'); return }; calibrationSubmitting.value = true; try { await calibrateAssessment(assessment.value.id, { gold_labels: labels, apply_corrections: applyCorrections.value }); ElMessage.success('真实结果校准完成'); await loadAssessment(); showCalibration.value = false } catch (error: any) { ElMessage.error(error?.response?.data?.detail || '校准失败') } finally { calibrationSubmitting.value = false } }
function handleResize() { chart?.resize(); scoreChart?.resize() }
watch(() => [assessmentId.value, demoMode.value], () => { chart?.dispose(); scoreChart?.dispose(); chart = null; scoreChart = null; loadAssessment() }, { immediate: true }); window.addEventListener('resize', handleResize); onBeforeUnmount(() => { stopProgressUpdates(); chart?.dispose(); scoreChart?.dispose(); window.removeEventListener('resize', handleResize) })
</script>

<style scoped>
.diagnosis-page { background: radial-gradient(circle at 50% 36%, rgba(222,250,222,.38), transparent 39%), radial-gradient(circle at 83% 13%, rgba(134,231,177,.08), transparent 27%), linear-gradient(180deg,#fdfffe 0%,#f5fbf7 100%); }
.diagnosis-heading { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 25px; }
.diagnosis-heading .page-title { display: flex; align-items: center; gap: 9px; }
.diagnosis-heading .page-title svg { width: 26px; color: var(--green-accent); }
.heading-actions { display: flex; gap: 10px; }
.top-action { height: 40px; padding: 0 13px; display: inline-flex; align-items: center; gap: 7px; border: 1px solid var(--line); border-radius: 12px; background: rgba(255,255,255,.66); color: var(--ink-soft); font-size: 12px; cursor: pointer; }
.top-action svg { width: 15px; }
.top-action.primary { border-color: rgba(14,155,79,.2); color: var(--green-deep); background: rgba(237,255,244,.67); }
.top-action:disabled { opacity: .5; cursor: not-allowed; }
.diagnosis-loading { min-height: 430px; position: relative; overflow: hidden; display: grid; place-items: center; border-radius: var(--radius-xl); text-align: center; }
.diagnosis-loading img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; mix-blend-mode: multiply; opacity: .72; }
.loading-copy { z-index: 2; padding: 25px; }
.loading-copy h2 { margin: 17px 0 8px; font-size: 21px; }
.loading-copy p { margin: 0; color: var(--ink-soft); font-size: 12px; }
.loading-copy .glass-pill svg { width: 14px; animation: spin 1.2s linear infinite; }
.loading-track { width: 340px; max-width: 80vw; height: 7px; margin: 21px auto 0; border-radius: 99px; overflow: hidden; background: rgba(19,133,72,.11); }
.loading-track i { display: block; height: 100%; border-radius: inherit; background: var(--gradient-progress); transition: width .4s; }
@keyframes spin { to { transform: rotate(360deg); } }
.diagnosis-error { padding: 28px; display: flex; align-items: center; gap: 15px; border-radius: var(--radius-lg); }
.diagnosis-error > svg { width: 28px; color: #c88821; }
.diagnosis-error h2 { margin: 0 0 5px; font-size: 17px; }
.diagnosis-error p { margin: 0; color: var(--ink-soft); font-size: 12px; }
.diagnosis-error button { margin-left: auto; border: 0; border-radius: 11px; padding: 10px 13px; background: var(--gradient-primary); color: #fff; cursor: pointer; }

.empty-diagnostic { min-height: 560px; padding: 24px; overflow: hidden; border-radius: var(--radius-xl); }
.empty-visual-grid { min-height: 430px; display: grid; grid-template-columns: .72fr 1.65fr .8fr; align-items: center; gap: 18px; }
.empty-match-preview, .empty-dimension-preview { min-height: 255px; padding: 22px; border-radius: 21px; border: 1px solid rgba(255,255,255,.84); background: rgba(255,255,255,.48); box-shadow: inset 0 1px 1px #fff; }
.empty-label { color: var(--ink-soft); font-size: 11px; font-weight: 700; }
.empty-match-preview strong { display: block; margin-top: 25px; color: var(--ink-faint); font-size: 54px; line-height: 1; }
.empty-match-preview small { color: var(--ink-faint); font-size: 10px; }
.empty-glass-orb { width: 78px; height: 78px; margin: 25px auto 0; display: grid; place-items: center; border-radius: 50%; color: var(--green-deep); background: radial-gradient(circle at 35% 30%, #fff, rgba(222,250,222,.74) 45%, rgba(134,231,177,.34)); box-shadow: inset 0 1px 2px #fff, 0 13px 30px rgba(27,139,76,.1); opacity: .72; }
.empty-glass-orb svg { width: 27px; }
.empty-core-stage { min-height: 390px; position: relative; display: grid; place-items: center; overflow: hidden; }
.empty-core-stage > img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; mix-blend-mode: multiply; opacity: .76; mask-image: radial-gradient(ellipse, #000 56%, transparent 91%); }
.empty-core-copy { z-index: 2; width: min(470px, 84%); padding: 25px; text-align: center; border: 1px solid rgba(255,255,255,.73); border-radius: 22px; background: rgba(255,255,255,.48); backdrop-filter: blur(13px); box-shadow: 0 20px 50px rgba(25,109,62,.08), inset 0 1px 1px #fff; }
.empty-core-copy h2 { margin: 15px 0 8px; font-size: 21px; line-height: 1.3; }
.empty-core-copy p { margin: 0; color: var(--ink-soft); font-size: 11px; line-height: 1.65; }
.empty-core-copy button { min-height: 42px; margin-top: 18px; padding: 0 15px; display: inline-flex; align-items: center; gap: 8px; border-radius: 13px; font-size: 12px; font-weight: 700; cursor: pointer; }
.empty-core-copy button svg { width: 15px; }
.empty-dimension-preview > div { display: grid; grid-template-columns: 66px 1fr auto; align-items: center; gap: 7px; margin-top: 17px; color: var(--ink-soft); font-size: 10px; }
.empty-dimension-preview i { height: 5px; border-radius: 99px; background: linear-gradient(90deg, rgba(189,244,207,.64), rgba(224,238,229,.5)); }
.empty-dimension-preview em { color: var(--ink-faint); font-size: 8px; font-style: normal; }
.empty-process { display: grid; grid-template-columns: repeat(4,1fr); border-top: 1px solid var(--line); padding-top: 20px; }
.empty-process > div { display: grid; grid-template-columns: auto 1fr; gap: 3px 9px; padding: 0 18px; border-right: 1px solid var(--line); }
.empty-process > div:last-child { border-right: 0; }
.empty-process > div > span { grid-row: 1/3; width: 34px; height: 34px; display: grid; place-items: center; border-radius: 11px; color: var(--green-deep); background: rgba(222,250,222,.67); }
.empty-process svg { width: 17px; }
.empty-process b { font-size: 11px; }
.empty-process small { color: var(--ink-faint); font-size: 9px; }

.calibration-panel { border-radius: var(--radius-lg); padding: 21px; margin-bottom: 18px; display: grid; grid-template-columns: .8fr 1.6fr; gap: 21px; align-items: start; }
.calibration-panel h2 { font-size: 18px; margin: 12px 0 7px; }
.calibration-panel p { margin: 0; color: var(--ink-soft); font-size: 12px; line-height: 1.65; }
.calibration-fields { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; }
.calibration-fields label { display: flex; flex-direction: column; gap: 5px; font-size: 11px; color: var(--ink-soft); }
.calibration-fields input { width: 100%; padding: 8px 9px; border: 1px solid var(--line); border-radius: 9px; background: rgba(255,255,255,.65); outline: none; color: var(--ink); }
.calibration-actions { grid-column: 2; display: flex; justify-content: space-between; align-items: center; }
.calibration-actions button { border: 0; border-radius: 10px; padding: 10px 13px; background: var(--gradient-primary); color: #fff; cursor: pointer; font-size: 12px; }
.calibration-actions button:disabled { opacity: .5; }
.correction-check { font-size: 11px; color: var(--ink-soft); }

.core-grid {
  display: grid;
  grid-template-columns: minmax(270px, 320px) minmax(600px, 720px) minmax(270px, 320px);
  gap: clamp(16px, 1.25vw, 22px);
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.core-grid > * { min-width: 0; max-width: 100%; }
.match-card, .dimension-card {
  min-height: 366px;
  padding: clamp(20px, 1.45vw, 25px);
  overflow: hidden;
  isolation: isolate;
  border: 1px solid rgba(255,255,255,.76);
  border-radius: var(--radius-xl);
  background: linear-gradient(145deg, rgba(255,255,255,.62), rgba(245,255,249,.38) 54%, rgba(189,244,207,.15)), rgba(250,255,252,.42);
  box-shadow: 0 27px 66px rgba(21,88,54,.09), inset 0 1px 1px rgba(255,255,255,.97), inset 0 -1px 1px rgba(36,164,91,.035);
  backdrop-filter: blur(31px) saturate(154%);
}
.card-heading { display: flex; align-items: center; justify-content: space-between; }
.card-heading > svg { width: 21px; color: var(--green-deep); }
.card-eyebrow { color: var(--ink); font-size: 14px; font-weight: 800; }
.match-card p { margin: 38px 0 0; color: var(--ink-soft); font-size: 12px; line-height: 1.55; }
.match-card > strong { display: block; margin-top: 10px; overflow: visible; font-size: 59px; line-height: 1.08; white-space: nowrap; }
.match-card > strong small { font-size: 22px; }
.match-badge { display: inline-flex; align-items: center; gap: 6px; width: max-content; margin-top: 15px; padding: 7px 10px; border-radius: 99px; background: rgba(236,255,243,.78); color: var(--green-deep); font-size: 11px; font-weight: 700; }
.match-badge i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.match-badge.needs { color: #a85c21; background: #fff3df; }
.match-insight { display: flex; align-items: center; justify-content: space-between; margin-top: 31px; padding: 13px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); color: var(--ink-soft); font-size: 10px; }
.match-insight b { color: var(--green-deep); font-size: 14px; }
.match-card footer { margin-top: 13px; color: var(--ink-faint); font-size: 10px; }
.diagnostic-core {
  --spot-x: 50%;
  --spot-y: 50%;
  width: 100%;
  min-width: 0;
  min-height: 426px;
  position: relative;
  display: grid;
  place-items: center;
  overflow: hidden;
  contain: layout paint;
  isolation: isolate;
  border: 1px solid rgba(255,255,255,.58);
  border-radius: 34px;
  background: linear-gradient(145deg, rgba(255,255,255,.22), rgba(222,250,222,.08));
  box-shadow: 0 30px 82px rgba(17,107,59,.095), inset 0 1px 1px rgba(255,255,255,.74);
  backdrop-filter: blur(12px) saturate(126%);
}
.diagnostic-core::before { content: ''; position: absolute; inset: 5% 4% 1%; z-index: 1; border-radius: 44%; pointer-events: none; background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(109,226,156,.13) 68%, rgba(255,255,255,.21)); filter: blur(25px); opacity: .76; }
.diagnostic-core::after { content: ''; position: absolute; inset: 0; z-index: 2; pointer-events: none; background: radial-gradient(min(240px, 30vw) circle at var(--spot-x) var(--spot-y), rgba(255,255,255,.35), transparent 68%); }
.diagnostic-platform { position: absolute; inset: 0; z-index: 1; width: 100%; height: 100%; max-width: 100%; object-fit: cover; object-position: center; mix-blend-mode: multiply; opacity: .78; mask-image: radial-gradient(ellipse, #000 62%, transparent 92%); filter: saturate(.96) contrast(1.02); }
.core-glass {
  z-index: 3;
  width: min(740px, calc(100% - 46px));
  max-width: 100%;
  min-width: 0;
  min-height: 338px;
  padding: 20px clamp(18px, 2vw, 26px) 17px;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.8);
  border-radius: 26px;
  background: linear-gradient(142deg, rgba(255,255,255,.67), rgba(248,255,251,.36) 47%, rgba(184,246,207,.17)), rgba(252,255,253,.4);
  box-shadow: 0 34px 78px rgba(13,111,58,.14), 0 0 42px rgba(104,228,153,.11), inset 0 1px 1px rgba(255,255,255,.99), inset 0 -1px 1px rgba(45,176,101,.045);
  backdrop-filter: blur(35px) saturate(165%);
  -webkit-backdrop-filter: blur(35px) saturate(165%);
}
.core-topline { display: grid; grid-template-columns: .72fr 1.2fr; text-align: center; color: var(--ink); font-size: 13px; font-weight: 800; }
.core-body { display: grid; grid-template-columns: .72fr 1.2fr; align-items: center; height: 252px; }
.score-dial { width: clamp(136px, 10vw, 155px); height: clamp(136px, 10vw, 155px); margin: auto; display: grid; place-items: center; position: relative; border-radius: 50%; background: conic-gradient(from 210deg, #079455 0deg, #45d986 var(--score), rgba(218,248,227,.78) var(--score)); box-shadow: 0 0 0 9px rgba(255,255,255,.39), 0 0 0 10px rgba(12,159,78,.08), 0 13px 28px rgba(13,124,69,.13); }
.score-dial::before { content: ''; position: absolute; inset: 7px; border-radius: 50%; border-top: 2px solid rgba(255,255,255,.88); transform: rotate(-28deg); }
.score-dial > div { width: 125px; height: 125px; display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: 50%; background: rgba(255,255,255,.88); box-shadow: inset 0 1px 2px #fff; }
.score-dial b { font-size: 46px; line-height: 1; }
.score-dial small { color: var(--ink-soft); font-size: 11px; }
.score-dial em { margin-top: 6px; color: var(--green-deep); font-size: 9px; font-style: normal; font-weight: 700; }
.radar-chart { width: 100%; max-width: 360px; height: 225px; margin: 0 auto; }
.core-meta { display: flex; justify-content: center; align-items: center; gap: 8px; color: var(--ink-faint); font-size: 10px; }
.demo-badge { padding: 3px 6px; border-radius: 99px; color: var(--green-deep); background: rgba(222,250,222,.72); }
.dimension-card { padding: 25px; }
.dimension-head { display: flex; justify-content: space-between; align-items: center; }
.dimension-count { color: var(--ink-faint); font-size: 10px; }
.dimension-list { margin-top: 25px; display: flex; flex-direction: column; gap: 16px; }
.dimension-row { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 7px; align-items: center; }
.dimension-row > div:first-child { display: flex; align-items: center; gap: 8px; min-width: 0; }
.dimension-row b { font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dimension-icon { width: 29px; height: 29px; display: grid; place-items: center; border-radius: 9px; background: rgba(222,250,222,.68); color: var(--green-deep); }
.dimension-icon svg { width: 15px; }
.dimension-row strong { font-size: 11px; color: var(--ink); }
.dimension-row strong small { color: var(--ink-faint); font-weight: 500; }
.dimension-bar { grid-column: 1/3; height: 6px; overflow: hidden; border-radius: 99px; background: rgba(44,126,80,.1); }
.dimension-bar i { display: block; height: 100%; border-radius: inherit; background: var(--gradient-progress); transition: width .9s ease; }

.analysis-grid { display: grid; grid-template-columns: 1.2fr .7fr 1.12fr; gap: 14px; margin-top: 20px; }
.evidence-insights, .agent-summary, .roadmap-card { min-height: 238px; border-radius: var(--radius-lg); padding: 20px; }
.evidence-insights { display: grid; grid-template-columns: 1fr 1fr; gap: 0; }
.evidence-insights > section { padding-right: 20px; }
.evidence-insights > section + section { padding: 0 0 0 20px; border-left: 1px solid var(--line); }
.evidence-insights h2, .agent-summary h2, .roadmap-card h2 { margin: 0; display: flex; align-items: center; gap: 7px; color: var(--ink); font-size: 15px; }
.evidence-insights h2 svg, .roadmap-card h2 svg { width: 17px; color: var(--green-deep); }
.gaps h2 svg { color: #d28c1e; }
.evidence-insights ul { padding: 0; margin: 18px 0 0; list-style: none; display: flex; flex-direction: column; gap: 12px; }
.strengths li { display: flex; gap: 8px; align-items: flex-start; }
.strengths li > span { width: 18px; height: 18px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 50%; color: var(--green-deep); background: rgba(222,250,222,.74); }
.strengths li svg { width: 10px; }
.strengths li b, .strengths li small { display: block; }
.strengths li b { font-size: 11px; }
.strengths li small { margin-top: 3px; color: var(--ink-soft); font-size: 9px; line-height: 1.4; }
.gaps li { display: grid; grid-template-columns: 22px 1fr; gap: 6px; align-items: start; }
.gaps li b { color: #c7831c; font-size: 9px; }
.gaps li span { color: var(--ink-soft); font-size: 10px; line-height: 1.45; }
.evidence-insights p { margin-top: 20px; color: var(--ink-soft); font-size: 11px; line-height: 1.6; }
.agent-summary { position: relative; }
.agent-face { display: inline-grid; place-items: center; width: 35px; height: 35px; margin-right: 7px; border-radius: 11px; background: var(--gradient-primary); color: #fff; vertical-align: middle; box-shadow: 0 7px 15px rgba(15,164,91,.19); }
.agent-face svg { width: 18px; }
.agent-summary h2 { display: inline-flex; }
.agent-summary p { margin: 13px 0 10px; color: var(--ink-soft); font-size: 11px; line-height: 1.68; }
.summary-evidence { display: flex; align-items: center; gap: 7px; padding: 8px 0; border-top: 1px solid var(--line); color: var(--ink-faint); font-size: 9px; }
.summary-evidence svg { width: 13px; color: var(--green-deep); }
.review-metric { padding: 8px 0; border-top: 1px solid var(--line); display: flex; justify-content: space-between; color: var(--ink-soft); font-size: 9px; }
.review-metric b { font-size: 10px; }
.review-metric .accurate { color: var(--green-deep); }
.review-metric .pending { color: #9a781d; }
.agent-summary button { width: 100%; min-height: 34px; margin-top: 8px; display: flex; align-items: center; justify-content: center; gap: 6px; border: 0; border-radius: 10px; background: rgba(222,250,222,.72); color: var(--green-deep); cursor: pointer; font-size: 10px; font-weight: 700; }
.agent-summary button svg { width: 13px; }
.roadmap-heading { display: flex; align-items: center; justify-content: space-between; }
.roadmap-heading > span { padding: 4px 7px; border-radius: 99px; background: rgba(222,250,222,.7); color: var(--green-deep); font-size: 8px; }
.roadmap { min-height: 152px; position: relative; display: grid; grid-template-columns: repeat(3,1fr); gap: 9px; align-items: start; margin-top: 24px; }
.roadmap-line { position: absolute; left: 14%; right: 14%; top: 17px; height: 1px; border-top: 1px dashed rgba(34,181,107,.32); }
.roadmap-step { z-index: 2; text-align: center; }
.roadmap-step > span { width: 34px; height: 34px; margin: auto; display: grid; place-items: center; border-radius: 50%; background: rgba(248,255,250,.9); border: 1px solid rgba(34,181,107,.2); color: var(--green-deep); box-shadow: 0 6px 14px rgba(23,107,62,.08); font-size: 9px; font-weight: 800; }
.roadmap-step.current > span { color: #fff; background: var(--gradient-primary); box-shadow: 0 0 0 5px rgba(222,250,222,.66), 0 9px 19px rgba(15,164,91,.2); }
.roadmap-step > div { min-height: 84px; margin-top: 12px; padding: 11px 7px; border-radius: 12px; background: rgba(255,255,255,.45); border: 1px solid rgba(255,255,255,.83); }
.roadmap-step b, .roadmap-step small { display: block; }
.roadmap-step b { font-size: 10px; }
.roadmap-step small { margin-top: 5px; color: var(--ink-soft); font-size: 8px; line-height: 1.4; }
.path-empty { margin-top: 28px; color: var(--ink-faint); font-size: 11px; }
.quality-strip { margin-top: 16px; padding: 14px 19px; border-radius: 15px; display: grid; grid-template-columns: 1fr 1fr 1fr auto; align-items: center; gap: 15px; }
.quality-strip > div { display: grid; grid-template-columns: auto 1fr; gap: 2px 8px; padding-right: 15px; border-right: 1px solid var(--line); }
.quality-strip > div svg { grid-row: 1/3; width: 17px; color: var(--green-deep); }
.quality-strip span, .quality-strip b { display: block; }
.quality-strip span { color: var(--ink-faint); font-size: 9px; }
.quality-strip b { color: var(--green-deep); font-size: 11px; }
.quality-strip button { display: flex; align-items: center; gap: 6px; border: 0; background: transparent; color: var(--green-deep); font-weight: 700; font-size: 11px; cursor: pointer; }
.quality-strip button svg { width: 13px; }
@media (max-width: 1500px) and (min-width: 721px) {
  .core-grid { grid-template-columns: minmax(240px, 280px) minmax(560px, 1fr) minmax(240px, 280px); }
}
@media (max-width: 1260px) { .core-grid { grid-template-columns: minmax(220px, .72fr) minmax(520px, 1.3fr); } .dimension-card { grid-column: 1/3; min-height: auto; } .dimension-list { display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; } .analysis-grid { grid-template-columns: 1fr 1fr; } .roadmap-card { grid-column: 1/3; } .empty-visual-grid { grid-template-columns: .7fr 1.4fr; } .empty-dimension-preview { grid-column: 1/3; min-height: auto; display: grid; grid-template-columns: repeat(5,1fr); gap: 12px; } .empty-dimension-preview > .empty-label { grid-column: 1/6; } .empty-dimension-preview > div { grid-template-columns: 1fr; } }
@media (max-width: 720px) { .diagnosis-heading { display: block; } .heading-actions { margin-top: 15px; } .diagnosis-error { display: block; } .diagnosis-error button { margin: 14px 0 0; } .empty-diagnostic { padding: 14px; } .empty-visual-grid { grid-template-columns: 1fr; } .empty-match-preview { display: none; } .empty-core-stage { min-height: 400px; } .empty-dimension-preview { grid-column: auto; display: block; } .empty-process { grid-template-columns: 1fr 1fr; gap: 15px 0; } .empty-process > div:nth-child(2) { border-right: 0; } .core-grid { grid-template-columns: 1fr; } .diagnostic-core { order: -1; min-height: 510px; } .dimension-card { grid-column: auto; } .core-glass { width: 94%; } .core-body { grid-template-columns: 1fr; height: auto; } .core-topline { display: none; } .score-dial { margin: 13px auto 0; } .radar-chart { height: 220px; } .core-meta { flex-wrap: wrap; } .dimension-list { grid-template-columns: 1fr; } .analysis-grid { grid-template-columns: 1fr; } .roadmap-card { grid-column: auto; } .evidence-insights { grid-template-columns: 1fr; } .evidence-insights > section { padding: 0; } .evidence-insights > section + section { margin-top: 20px; padding: 20px 0 0; border-left: 0; border-top: 1px solid var(--line); } .quality-strip { grid-template-columns: 1fr 1fr; } .quality-strip > div { border: 0; } .calibration-panel { grid-template-columns: 1fr; } .calibration-fields { grid-template-columns: 1fr 1fr; } .calibration-actions { grid-column: auto; display: block; } .calibration-actions button { margin-top: 12px; } .match-card { min-height: 290px; } }
/* Diagnostic Console V4: clean liquid glass with restrained environmental light. */
.diagnostic-core {
  --spot-opacity: .26;
  min-height: 438px;
  border: 1px solid rgba(255,255,255,.58);
  background:
    radial-gradient(ellipse at 50% 94%, rgba(161,230,189,.075), transparent 42%),
    linear-gradient(145deg, rgba(255,255,255,.17), rgba(249,255,252,.055) 58%, rgba(216,245,228,.035));
  box-shadow:
    0 32px 82px rgba(18,78,47,.07),
    inset 0 1px 1px rgba(255,255,255,.78),
    inset 0 -1px 1px rgba(42,174,98,.025);
  backdrop-filter: blur(15px) saturate(118%);
  -webkit-backdrop-filter: blur(15px) saturate(118%);
}
.diagnostic-core::before {
  inset: auto 18% 4%;
  height: 72px;
  border-radius: 50%;
  background: radial-gradient(ellipse, rgba(96,210,143,.18) 0%, rgba(206,246,221,.1) 48%, transparent 76%);
  filter: blur(15px);
  opacity: .3;
}
.diagnostic-core::after {
  background:
    radial-gradient(min(230px, 28vw) circle at var(--spot-x) var(--spot-y), rgba(255,255,255,var(--spot-opacity)), transparent 72%),
    linear-gradient(118deg, rgba(255,255,255,.1), transparent 28%, rgba(117,230,161,.018) 69%, rgba(255,255,255,.08));
  transition: background .22s ease;
}
.diagnostic-platform {
  inset: 8% -2% -16%;
  width: 104%;
  height: 108%;
  object-position: center 67%;
  mix-blend-mode: normal;
  opacity: .3;
  mask-image: radial-gradient(ellipse at 50% 68%, #000 42%, rgba(0,0,0,.68) 62%, transparent 88%);
  filter: saturate(.78) contrast(.96) brightness(1.12);
}
.core-glass {
  position: relative;
  z-index: 4;
  isolation: isolate;
  width: min(760px, calc(100% - 36px));
  min-height: 356px;
  margin-top: -18px;
  padding: 20px 23px 14px;
  overflow: hidden;
  border: 1px solid transparent;
  outline: 1px solid rgba(116,226,160,.07);
  outline-offset: -4px;
  border-radius: 29px;
  background:
    linear-gradient(138deg, rgba(255,255,255,.34) 0%, rgba(253,255,254,.15) 34%, rgba(244,252,247,.075) 68%, rgba(214,242,225,.055) 100%) padding-box,
    linear-gradient(132deg, rgba(255,255,255,.96), rgba(255,255,255,.28) 31%, rgba(151,232,183,.24) 73%, rgba(255,255,255,.72)) border-box;
  box-shadow:
    0 39px 88px rgba(12,73,42,.12),
    0 13px 29px rgba(58,178,106,.035),
    0 -8px 27px rgba(255,255,255,.26),
    inset 0 2px 1px rgba(255,255,255,.9),
    inset 1px 0 1px rgba(255,255,255,.42),
    inset -1px -3px 3px rgba(40,179,97,.045);
  backdrop-filter: blur(24px) saturate(122%) brightness(1.035);
  -webkit-backdrop-filter: blur(24px) saturate(122%) brightness(1.035);
  transform: translateY(-8px) perspective(900px) rotateX(.55deg);
  transform-origin: center bottom;
  transition: transform .32s cubic-bezier(.2,.8,.2,1), box-shadow .32s ease;
}
.core-glass:hover {
  transform: translateY(-10px) perspective(900px) rotateX(.25deg);
  box-shadow:
    0 43px 98px rgba(12,73,42,.135),
    0 17px 37px rgba(58,178,106,.045),
    0 -9px 30px rgba(255,255,255,.3),
    inset 0 2px 1px rgba(255,255,255,.9),
    inset -1px -2px 2px rgba(40,179,97,.06);
}
.core-glass::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: inherit;
  pointer-events: none;
  background:
    radial-gradient(210px circle at var(--spot-x) var(--spot-y), rgba(255,255,255,.25), transparent 73%),
    linear-gradient(111deg, rgba(255,255,255,.6) 0%, rgba(255,255,255,.12) 18%, transparent 35%),
    radial-gradient(ellipse at 72% 112%, rgba(188,241,208,.045), transparent 54%);
  mix-blend-mode: screen;
  opacity: .72;
}
.core-glass::after {
  content: '';
  position: absolute;
  inset: 1px;
  z-index: 3;
  border-radius: 28px;
  pointer-events: none;
  box-shadow:
    inset 0 2px 1px rgba(255,255,255,.8),
    inset 10px 0 25px rgba(255,255,255,.055),
    inset -1px -3px 2px rgba(49,185,105,.052);
  border-top: 1px solid rgba(255,255,255,.7);
  border-right: 1px solid rgba(116,226,160,.04);
}
.core-glass > * { position: relative; z-index: 2; }
.core-body {
  display: grid;
  grid-template-columns: minmax(188px, .78fr) 1px minmax(320px, 1.32fr);
  gap: 20px;
  align-items: stretch;
  height: 282px;
}
.score-module,
.radar-module { min-width: 0; display: flex; flex-direction: column; }
.core-module-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; color: rgba(14,45,28,.92); }
.core-module-heading span { font-size: 13px; font-weight: 800; }
.core-module-heading small { color: rgba(65,105,82,.5); font-size: 8px; font-weight: 700; letter-spacing: .08em; }
.score-gauge-shell {
  width: 182px;
  height: 182px;
  margin: 15px auto 0;
  position: relative;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255,255,255,.46);
  border-radius: 50%;
  background: radial-gradient(circle at 38% 30%, rgba(255,255,255,.5), rgba(248,255,251,.19) 59%, rgba(211,244,224,.08));
  box-shadow: inset 0 2px 2px rgba(255,255,255,.72), 0 16px 38px rgba(12,104,57,.065);
  backdrop-filter: blur(9px);
  overflow: visible;
}
.score-gauge { position: absolute; inset: 6px; }
.score-value { position: absolute; inset: 0; z-index: 2; display: flex; align-items: center; justify-content: center; padding-top: 2px; color: #086c40; white-space: nowrap; overflow: visible; }
.score-value b { font-size: 48px; line-height: 1; font-variant-numeric: tabular-nums; letter-spacing: 0; }
.score-value span { margin-left: 3px; color: rgba(42,78,57,.58); font-size: 10px; font-weight: 600; }
.score-verdict { width: max-content; margin: -7px auto 0; padding: 6px 10px; display: inline-flex; align-items: center; gap: 6px; border: 1px solid rgba(16,153,80,.12); border-radius: 99px; color: #087748; background: rgba(241,255,247,.38); font-size: 9px; font-weight: 700; backdrop-filter: blur(8px); }
.score-verdict i,
.core-status i { width: 5px; height: 5px; border-radius: 50%; background: #21b76b; box-shadow: 0 0 0 4px rgba(33,183,107,.08); }
.core-separator { width: 1px; height: 76%; margin: auto 0; background: linear-gradient(180deg, transparent, rgba(21,111,61,.1) 25%, rgba(255,255,255,.62) 52%, rgba(21,111,61,.08) 76%, transparent); }
.radar-chart {
  width: 100%;
  max-width: 410px;
  height: 264px;
  margin: 1px auto 0;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255,255,255,.11), rgba(178,241,202,.025) 50%, transparent 72%);
  filter: drop-shadow(0 12px 22px rgba(23,139,74,.055));
}
.core-meta {
  min-height: 31px;
  margin-top: 5px;
  padding: 9px 10px 0;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 13px;
  border-top: 1px solid rgba(28,102,60,.07);
  color: rgba(55,89,68,.54);
  font-size: 9px;
}
.core-meta > span + span { position: relative; }
.core-meta > span + span::before { content: ''; position: absolute; left: -7px; top: 50%; width: 2px; height: 2px; margin-top: -1px; border-radius: 50%; background: rgba(31,102,62,.24); }
.core-status { display: inline-flex; align-items: center; gap: 6px; color: rgba(8,119,72,.72); }
.core-status::before { display: none; }
.demo-badge { padding: 3px 7px; border: 1px solid rgba(20,156,82,.1); background: rgba(239,255,246,.38); }
.match-card,
.dimension-card {
  border-color: rgba(255,255,255,.66);
  background:
    linear-gradient(145deg, rgba(255,255,255,.45), rgba(249,255,251,.25) 60%, rgba(215,245,226,.08)),
    rgba(250,255,252,.2);
  box-shadow:
    0 27px 66px rgba(21,75,47,.065),
    inset 0 1px 1px rgba(255,255,255,.9),
    inset 0 -1px 1px rgba(36,164,91,.025);
  backdrop-filter: blur(28px) saturate(125%);
  -webkit-backdrop-filter: blur(28px) saturate(125%);
}
.evidence-insights,
.agent-summary,
.roadmap-card {
  border: 1px solid rgba(255,255,255,.61);
  background:
    linear-gradient(145deg, rgba(255,255,255,.49), rgba(247,255,250,.27) 61%, rgba(189,244,207,.085)),
    rgba(250,255,252,.22);
  box-shadow: 0 24px 59px rgba(22,82,51,.07), inset 0 1px 1px rgba(255,255,255,.87);
  backdrop-filter: blur(26px) saturate(154%);
  -webkit-backdrop-filter: blur(26px) saturate(154%);
}

@media (max-width: 720px) {
  .diagnostic-core { min-height: 690px; }
  .core-glass { width: 94%; min-height: 626px; margin-top: -2px; transform: none; }
  .core-glass:hover { transform: translateY(-2px); }
  .core-body { grid-template-columns: 1fr; gap: 12px; height: auto; }
  .core-separator { width: 76%; height: 1px; margin: 0 auto; background: linear-gradient(90deg, transparent, rgba(21,111,61,.12), rgba(255,255,255,.7), rgba(21,111,61,.1), transparent); }
  .score-gauge-shell { width: 160px; height: 160px; margin-top: 9px; }
  .score-value b { font-size: 43px; }
  .radar-chart { height: 235px; }
  .core-meta { flex-wrap: wrap; }
  .diagnostic-platform { inset: 22% -11% -9%; width: 122%; height: 90%; }
}

/* Final desktop composition pass: match the reference's compact title-to-core rhythm. */
@media (min-width: 1061px) {
  .diagnosis-page { padding-top: 26px; }
  .diagnosis-heading { margin-bottom: -6px; }
  .diagnosis-heading .eyebrow { display: none; }
  .diagnosis-heading .page-title { margin-top: 0; margin-bottom: 6px; font-size: clamp(40px, 2.4vw, 43px); }
  .diagnosis-heading .page-subtitle { font-size: 13px; line-height: 1.55; }
  .diagnostic-core { min-height: 425px; }
  .core-glass { margin-top: -35px; }
}

/* Keep generated scene assets inside a soft spatial stage instead of a hard image frame. */
.diagnosis-loading,
.empty-core-stage {
  isolation: isolate;
  background:
    radial-gradient(ellipse at 50% 58%, rgba(210,250,224,.34), transparent 46%),
    linear-gradient(145deg, rgba(255,255,255,.56), rgba(240,253,246,.22));
}
.diagnosis-loading img,
.empty-core-stage > img {
  object-fit: contain;
  object-position: center;
  padding: 4% 7%;
  mix-blend-mode: multiply;
  opacity: .48;
  mask-image: radial-gradient(ellipse at center, #000 34%, rgba(0,0,0,.72) 65%, transparent 96%);
  filter: saturate(.86) contrast(.98) brightness(1.08);
}
.empty-core-stage > img { opacity: .42; padding: 6% 8%; }
.diagnosis-progress-events {
  width: min(520px, 92vw);
  margin: 18px auto 0;
  padding: 10px 12px;
  display: grid;
  gap: 7px;
  list-style: none;
  text-align: left;
  border: 1px solid rgba(255,255,255,.65);
  border-radius: 15px;
  background: rgba(255,255,255,.32);
  backdrop-filter: blur(13px);
}
.diagnosis-progress-events li { display: grid; grid-template-columns: 7px auto 1fr auto; gap: 7px; align-items: center; color: var(--ink-soft); font-size: 10px; }
.diagnosis-progress-events li i { width: 6px; height: 6px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 3px rgba(28,181,101,.1); }
.diagnosis-progress-events li small { grid-column: 2 / 4; color: var(--ink-faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.diagnosis-progress-events li b { color: var(--green-deep); font-size: 10px; }
@media (min-width: 1061px) {
  .diagnosis-progress-events li { font-size: 11px; }
  .diagnosis-progress-events li b { font-size: 11px; }
  .diagnosis-progress-events li small { font-size: 10px; }
}

/* Desktop legibility pass: scale the diagnostic console and its evidence panels together. */
@media (min-width: 1261px) {
  .diagnosis-page { padding-top: 30px; }
  .diagnosis-page .diagnosis-heading { margin-bottom: 18px; }
  .diagnosis-page .diagnosis-heading .page-title { font-size: clamp(42px, 2.6vw, 50px); }
  .diagnosis-page .diagnosis-heading .page-subtitle { font-size: 15px; }
  .diagnosis-page .heading-actions { gap: 12px; }
  .diagnosis-page .heading-actions .top-action { min-height: 46px; padding: 0 18px; border-radius: 13px; font-size: 14px; }
  .diagnosis-page .heading-actions .top-action svg { width: 17px; }
  .diagnosis-page .core-grid {
    grid-template-columns: minmax(280px, 310px) minmax(600px, 1fr) minmax(280px, 310px);
    gap: 26px;
  }
  .diagnosis-page .match-card,
  .diagnosis-page .dimension-card { min-height: 410px; padding: 30px; border-radius: 30px; }
  .diagnosis-page .card-eyebrow { font-size: 16px; }
  .diagnosis-page .card-heading > svg { width: 24px; }
  .diagnosis-page .match-card p { margin-top: 42px; font-size: 14px; line-height: 1.68; }
  .diagnosis-page .match-card > strong { margin-top: 13px; font-size: 70px; }
  .diagnosis-page .match-card > strong small { font-size: 26px; }
  .diagnosis-page .match-badge { margin-top: 18px; padding: 8px 12px; font-size: 13px; }
  .diagnosis-page .match-insight { margin-top: 35px; padding: 15px 0; font-size: 12px; }
  .diagnosis-page .match-insight b { font-size: 16px; }
  .diagnosis-page .match-card footer { margin-top: 16px; font-size: 12px; }
  .diagnosis-page .diagnostic-core { min-height: 480px; border-radius: 38px; }
  .diagnosis-page .core-glass { width: min(820px, calc(100% - 44px)); min-height: 400px; margin-top: -24px; padding: 27px 30px 18px; border-radius: 32px; }
  .diagnosis-page .core-topline { font-size: 16px; }
  .diagnosis-page .core-body { height: 320px; grid-template-columns: minmax(210px, .78fr) 1px minmax(340px, 1.32fr); gap: 24px; }
  .diagnosis-page .core-module-heading span { font-size: 16px; }
  .diagnosis-page .core-module-heading small { font-size: 10px; }
  .diagnosis-page .score-gauge-shell { width: 204px; height: 204px; margin-top: 18px; }
  .diagnosis-page .score-value b { font-size: 56px; }
  .diagnosis-page .score-value span { font-size: 12px; }
  .diagnosis-page .score-verdict { margin-top: -5px; padding: 7px 12px; font-size: 11px; }
  .diagnosis-page .radar-chart { max-width: 450px; height: 292px; }
  .diagnosis-page .core-meta { min-height: 36px; margin-top: 8px; padding-top: 11px; gap: 16px; font-size: 11px; }
  .diagnosis-page .dimension-head h2 { font-size: 20px; }
  .diagnosis-page .dimension-count { font-size: 12px; }
  .diagnosis-page .dimension-list { margin-top: 28px; gap: 20px; }
  .diagnosis-page .dimension-row { gap: 9px; }
  .diagnosis-page .dimension-row > div:first-child { gap: 10px; }
  .diagnosis-page .dimension-row b,
  .diagnosis-page .dimension-row strong { font-size: 14px; }
  .diagnosis-page .dimension-icon { width: 34px; height: 34px; border-radius: 10px; }
  .diagnosis-page .dimension-icon svg { width: 18px; }
  .diagnosis-page .dimension-bar { height: 7px; }
  .diagnosis-page .analysis-grid { gap: 18px; margin-top: 24px; }
  .diagnosis-page .evidence-insights,
  .diagnosis-page .agent-summary,
  .diagnosis-page .roadmap-card { min-height: 270px; padding: 25px; border-radius: 25px; }
  .diagnosis-page .evidence-insights h2,
  .diagnosis-page .agent-summary h2,
  .diagnosis-page .roadmap-card h2 { gap: 9px; font-size: 17px; }
  .diagnosis-page .evidence-insights h2 svg,
  .diagnosis-page .roadmap-card h2 svg { width: 20px; }
  .diagnosis-page .evidence-insights ul { margin-top: 21px; gap: 15px; }
  .diagnosis-page .strengths li { gap: 10px; }
  .diagnosis-page .strengths li > span { width: 22px; height: 22px; }
  .diagnosis-page .strengths li b { font-size: 13px; }
  .diagnosis-page .strengths li small { font-size: 11px; }
  .diagnosis-page .gaps li b { font-size: 11px; }
  .diagnosis-page .gaps li span { font-size: 12px; }
  .diagnosis-page .evidence-insights p { margin-top: 23px; font-size: 12px; }
  .diagnosis-page .agent-face { width: 42px; height: 42px; border-radius: 13px; }
  .diagnosis-page .agent-face svg { width: 21px; }
  .diagnosis-page .agent-summary p { margin: 16px 0 13px; font-size: 13px; }
  .diagnosis-page .summary-evidence,
  .diagnosis-page .review-metric { padding: 10px 0; font-size: 11px; }
  .diagnosis-page .summary-evidence svg { width: 15px; }
  .diagnosis-page .review-metric b { font-size: 12px; }
  .diagnosis-page .agent-summary button { min-height: 40px; margin-top: 10px; border-radius: 12px; font-size: 12px; }
  .diagnosis-page .agent-summary button svg { width: 15px; }
  .diagnosis-page .roadmap { min-height: 176px; gap: 11px; margin-top: 28px; }
  .diagnosis-page .roadmap-line { top: 19px; }
  .diagnosis-page .roadmap-step > span { width: 39px; height: 39px; font-size: 11px; }
  .diagnosis-page .roadmap-step > div { min-height: 96px; margin-top: 14px; padding: 13px 9px; border-radius: 14px; }
  .diagnosis-page .roadmap-step b { font-size: 12px; }
  .diagnosis-page .roadmap-step small { font-size: 10px; }
  .diagnosis-page .quality-strip { margin-top: 20px; padding: 17px 23px; gap: 18px; }
  .diagnosis-page .quality-strip > div { gap: 3px 10px; padding-right: 18px; }
  .diagnosis-page .quality-strip > div svg { width: 20px; }
  .diagnosis-page .quality-strip span { font-size: 11px; }
  .diagnosis-page .quality-strip b,
  .diagnosis-page .quality-strip button { font-size: 13px; }
  .diagnosis-page .quality-strip button svg { width: 15px; }
}

/* The right-hand panel carries the decision, not a second score visualization. */
.diagnostic-agent-summary { min-height: 366px; padding: clamp(20px, 1.45vw, 25px); overflow: hidden; border: 1px solid rgba(255,255,255,.76); border-radius: var(--radius-xl); background: linear-gradient(145deg, rgba(255,255,255,.62), rgba(245,255,249,.38) 54%, rgba(189,244,207,.15)), rgba(250,255,252,.42); box-shadow: 0 27px 66px rgba(21,88,54,.09), inset 0 1px 1px rgba(255,255,255,.97); backdrop-filter: blur(31px) saturate(154%); display: flex; flex-direction: column; }
.diagnostic-agent-summary > button { margin-top: auto; }
.diagnostic-agent-summary > p { display: -webkit-box; margin: 13px 0 14px; -webkit-box-orient: vertical; -webkit-line-clamp: 4; overflow: hidden; }
.diagnostic-agent-summary .review-metric { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; min-height: 78px; margin-bottom: 12px; padding: 13px 15px; border: 0; border-radius: 16px; background: linear-gradient(135deg, rgba(222,250,222,.84), rgba(255,255,255,.5)); box-shadow: inset 0 1px 1px rgba(255,255,255,.95); }
.diagnostic-agent-summary .review-metric span { color: var(--ink-soft); font-size: 12px; font-weight: 700; line-height: 1.5; }
.diagnostic-agent-summary .review-metric b { font-size: clamp(36px, 2.8vw, 48px); line-height: .88; letter-spacing: 0; }
.analysis-grid { grid-template-columns: minmax(0,1.06fr) minmax(0,.94fr); }
@media (min-width: 1261px) { .diagnosis-page .match-card, .diagnosis-page .diagnostic-agent-summary { min-height: 410px; padding: 30px; border-radius: 30px; } .diagnosis-page .diagnostic-agent-summary { min-height: 410px; } }
@media (max-width: 1260px) and (min-width: 721px) { .diagnostic-agent-summary { grid-column: 1 / 3; min-height: auto; } .analysis-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 720px) { .diagnostic-agent-summary { min-height: 270px; } }
</style>
