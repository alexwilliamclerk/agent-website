<template>
  <div class="page-shell library-page">
    <div class="content-width">
      <header class="library-heading motion-enter">
        <div class="heading-copy">
          <span class="eyebrow">PERSONALIZED LEARNING INTELLIGENCE</span>
          <h1 class="page-title">个性化资料库</h1>
          <p class="page-subtitle">把能力缺口转化为可执行的讲义、实操、项目与复测资源，每一项正式内容均保留知识库来源与审核结果。</p>
        </div>
        <div class="heading-actions">
          <label class="search-box glass-panel">
            <Search />
            <input ref="searchInput" v-model.trim="keyword" type="search" placeholder="搜索资料、技术、关键词…" />
            <kbd>⌘ K</kbd>
          </label>
          <div class="view-switch glass-panel" aria-label="资源视图">
            <button type="button" :class="{ active: viewMode === 'grid' }" title="网格视图" @click="viewMode = 'grid'"><Grid /></button>
            <button type="button" :class="{ active: viewMode === 'list' }" title="列表视图" @click="viewMode = 'list'"><Menu /></button>
          </div>
        </div>
      </header>

      <section v-if="libraryLoading" class="state-stage glass-surface motion-enter">
        <div class="state-core loading-core"><Loading /></div>
        <span class="eyebrow">KNOWLEDGE ORCHESTRATION</span>
        <h2>正在编排个性化学习资料</h2>
        <p>系统正在读取诊断缺口、检索知识片段并核验资源来源。</p>
        <div class="state-progress"><i></i></div>
      </section>

      <section v-else-if="libraryError" class="state-stage glass-surface motion-enter">
        <div class="state-core error-core"><Warning /></div>
        <span class="eyebrow">LIBRARY TEMPORARILY UNAVAILABLE</span>
        <h2>{{ libraryError }}</h2>
        <p>已保留当前筛选条件。重新加载后，仅展示通过来源链审核的资源。</p>
        <button class="primary-gradient-button state-button" type="button" @click="assessmentId ? retryPackageRepair() : loadLibrary()"><Refresh />{{ assessmentId ? '重新生成学习包' : '重新加载' }}</button>
      </section>

      <div v-else class="library-layout motion-enter motion-delay-1">
        <aside class="filter-panel glass-surface">
          <div class="filter-title">
            <div><span>FILTERS</span><h2>筛选条件</h2></div>
            <button type="button" @click="resetFilters"><RefreshLeft />重置</button>
          </div>
          <section class="filter-group">
            <h3><Collection />资源类型</h3>
            <label v-for="type in visibleResourceTypes" :key="type" :class="{ disabled: !hasResources }">
              <input v-model="selectedTypes" type="checkbox" :value="type" :disabled="!hasResources" />
              <span>{{ type }}</span>
              <small>{{ hasResources ? typeCount(type) : '待生成' }}</small>
            </label>
          </section>
          <section class="filter-group">
            <h3><DataAnalysis />知识主题</h3>
            <template v-if="hasResources">
              <label v-for="point in knowledgePoints.slice(0, 7)" :key="point">
                <input v-model="selectedPoints" type="checkbox" :value="point" />
                <span>{{ point }}</span>
                <small>{{ pointCount(point) }}</small>
              </label>
            </template>
            <div v-else class="topic-preview"><span>岗位能力缺口</span><span>项目实践</span><span>阶段复测</span></div>
          </section>
          <section class="filter-group verification-group">
            <h3><CircleCheck />来源门禁</h3>
            <div class="audit-note"><i></i><span>只有绑定 source_chunk_id 且通过审核的资源才能进入正式资料库。</span></div>
          </section>
        </aside>

        <main class="library-content">
          <div class="library-tools">
            <span class="library-result-count">{{ hasResources ? `${filteredResources.length} 项可用资源` : packageRepairing ? `正在自动重建学习包 · ${repairProgress.percent}%` : '等待本次诊断结果' }}</span>
          </div>

          <article class="learning-package glass-surface" :class="{ 'is-empty': !featuredResource }" :style="packSpotlight" @pointermove="updateSpotlight" @pointerleave="clearSpotlight">
            <div class="package-copy">
              <span class="glass-pill"><MagicStick />AI 推荐学习包</span>
              <template v-if="featuredResource">
                <h2>{{ featuredResource.knowledge_point }} 进阶学习包</h2>
                <p>{{ featuredResource.title }}。依据本次能力诊断与审核通过的知识片段，为你组织下一阶段的学习顺序。</p>
                <div class="package-tags"><span>{{ featuredResource.content_type }}</span><span v-if="featuredResource.difficulty">难度 {{ featuredResource.difficulty }}/5</span><span><CircleCheckFilled />来源已审核</span></div>
                <div class="package-progress"><div><span>学习包完整度</span><b>{{ packageProgress }}%</b></div><div class="progress-track"><i :style="{ width: `${packageProgress}%` }"></i></div></div>
                <div class="package-actions"><button class="primary-gradient-button" type="button" @click="continueLearning">继续学习 <ArrowRight /></button><span>已编排 {{ filteredResources.length }} 项训练资源</span></div>
              </template>
              <template v-else>
                <h2>{{ assessmentId ? packageRepairing ? '正在自动修复并生成个性化学习包' : '本次学习包需要重新生成' : '完成诊断，生成你的 AI 学习包' }}</h2>
                <p>{{ assessmentId ? packageRepairing ? `${repairProgress.agent}：${repairProgress.label}。完成后本页会自动显示可学习正文与路径。` : '系统检测到这条历史诊断缺少可展示资源，将自动重新检索知识库、生成正文并完成来源审核。' : '诊断完成后，系统会围绕未达标项和证据不足项，生成讲义、实操任务、项目任务书与阶段复测。' }}</p>
                <div class="package-tags preview-tags"><span>个性化讲义</span><span>实操任务</span><span>阶段复测</span></div>
                <div class="package-actions"><button class="primary-gradient-button" type="button" :disabled="packageRepairing" @click="assessmentId ? retryPackageRepair() : router.push('/input')"><component :is="assessmentId ? packageRepairing ? Loading : Refresh : ArrowRight" />{{ assessmentId ? packageRepairing ? '自动生成中' : '自动重新生成' : '开始资料审查' }}</button><span>{{ assessmentId ? packageRepairing ? `${repairProgress.percent}% · 无需手动刷新` : '自动绑定本次诊断与知识库来源' : '约 3 个步骤完成能力诊断' }}</span></div>
              </template>
            </div>
            <div class="spatial-resource-object" aria-hidden="true">
              <div class="pack-halo"></div>
              <img src="/assets/learning-resource-cube-stage.png" alt="" />
              <div class="orbit orbit-one"></div><div class="orbit orbit-two"></div>
              <span class="floating-chip chip-one"><Document />讲义</span>
              <span class="floating-chip chip-two"><Monitor />实操</span>
              <span class="floating-chip chip-three"><EditPen />复测</span>
            </div>
          </article>

          <section v-if="currentPath?.steps?.length" class="library-path glass-panel">
            <div class="library-path-heading"><div><span>LEARNING PATH</span><h2>本次优先学习路径</h2></div><em>第 {{ currentPath.current_step || 1 }} / {{ currentPath.steps.length }} 阶段</em></div>
            <ol>
              <li v-for="(step, index) in currentPath.steps.slice(0, 3)" :key="step.step" :class="{ current: step.status === 'current' || (!currentPath.current_step && index === 0), completed: step.status === 'completed' }">
                <span>{{ String(index + 1).padStart(2, '0') }}</span>
                <div><b>{{ safePathLabel(step.knowledge_point, index) }}</b><small>{{ step.resource_type }} · 约 {{ step.estimated_time }} 分钟</small></div>
              </li>
            </ol>
          </section>

          <section class="resource-section">
            <div class="resource-heading"><div><span>CURATED FOR YOU</span><h2>精选资源</h2></div><em>{{ selectedLabel }}</em></div>
            <div v-if="hasResources && filteredResources.length" class="resource-grid" :class="{ 'list-view': viewMode === 'list' }">
              <article v-for="(resource, index) in filteredResources" :key="resource.id" class="resource-card glass-surface" :style="{ '--card-delay': `${Math.min(index, 8) * 35}ms` }">
                <div class="resource-card-top"><span class="resource-icon" :class="resourceTone(resource.content_type)"><component :is="resourceIcon(resource.content_type)" /></span><span class="resource-type">{{ resource.content_type }}</span><button type="button" class="bookmark" :class="{ active: bookmarkedIds.has(resource.id) }" :title="bookmarkedIds.has(resource.id) ? '取消收藏' : '收藏资源'" :aria-pressed="bookmarkedIds.has(resource.id)" @click.stop="toggleBookmark(resource)"><Star /></button></div>
                <div class="resource-card-copy"><h3>{{ resource.title }}</h3><p>{{ preview(resource.body) }}</p></div>
                <div class="resource-meta"><span>{{ resource.knowledge_point }}</span><span><CircleCheck />审核{{ reviewText(resource.review_status) }}</span></div>
                <div class="resource-footer"><div class="mini-progress"><i :style="{ width: `${resourceProgress(resource, index)}%` }"></i></div><button type="button" @click="openResource(resource)">查看资料 <ArrowRight /></button></div>
              </article>
            </div>
            <div v-else-if="hasResources" class="resource-empty glass-panel"><Search /><b>没有符合当前筛选条件的资源</b><p>可重置筛选，或返回资料审查补充能力证据。</p><button type="button" @click="resetFilters"><RefreshLeft />重置筛选</button></div>
            <div v-else class="resource-preview-grid" aria-label="待生成资源预览">
              <article v-for="item in emptyResourcePreview" :key="item.title" class="resource-preview-card glass-panel"><span class="resource-icon muted"><component :is="item.icon" /></span><div><small>{{ item.type }}</small><h3>{{ item.title }}</h3><p>{{ item.description }}</p></div><Lock class="preview-lock" /></article>
            </div>
          </section>
        </main>

        <aside class="overview-column">
          <section class="overview-card glass-surface">
            <div class="overview-title"><div><span>OVERVIEW</span><h2>我的学习概览</h2></div><em>{{ demoMode ? '演示数据' : '本次诊断' }}</em></div>
            <template v-if="hasResources">
              <div class="overview-score"><strong class="gradient-number">{{ resources.length }}</strong><span>项正式资源</span></div>
              <div class="overview-line"><span>来源审核通过</span><b>{{ passedCount }}</b><i :style="{ width: `${passedRate}%` }"></i></div>
              <div class="overview-line"><span>部分匹配待复核</span><b>{{ partialCount }}</b><i class="partial" :style="{ width: `${partialRate}%` }"></i></div>
              <div class="overview-line"><span>知识主题覆盖</span><b>{{ knowledgePoints.length }}</b><i :style="{ width: `${Math.min(100, knowledgePoints.length * 18)}%` }"></i></div>
              <button type="button" @click="openDiagnosis"><TrendCharts />查看诊断报告<ArrowRight /></button>
            </template>
            <template v-else><div class="overview-placeholder"><DataLine /><strong>学习概览将在诊断后生成</strong><p>资源数量、审核状态、主题覆盖与阶段进度都会在这里持续更新。</p></div></template>
          </section>
          <section class="collection-card glass-surface">
            <div class="overview-title"><div><span>PIPELINE</span><h2>资源生成状态</h2></div><em>{{ hasResources ? '已完成' : packageRepairing ? `${repairProgress.percent}%` : '待启动' }}</em></div>
            <ol class="pipeline-list"><li v-for="(step, index) in pipelineSteps" :key="step.title" :class="stepState(index)"><span><CircleCheckFilled v-if="stepState(index) === 'done'" /><Loading v-else-if="stepState(index) === 'running'" /><Clock v-else /></span><div><b>{{ step.title }}</b><small>{{ step.description }}</small></div></li></ol>
          </section>
        </aside>
      </div>
    </div>

    <el-dialog v-model="previewVisible" width="min(680px, calc(100vw - 32px))" class="resource-preview-dialog" :show-close="true">
      <template #header><div class="dialog-heading"><span class="resource-icon"><component :is="selectedPreview ? resourceIcon(selectedPreview.content_type) : Document" /></span><div><small>{{ selectedPreview?.content_type }}</small><h2>{{ selectedPreview?.title }}</h2></div></div></template>
      <div v-if="selectedPreview" class="resource-document">
        <section class="document-section document-summary"><span>学习内容</span><h3>资料讲解</h3><p v-for="(paragraph, index) in previewParagraphs" :key="index">{{ paragraph }}</p></section>
        <section class="document-section"><span>学习行动</span><h3>按此顺序完成练习</h3><ol><li v-for="action in previewActions" :key="action">{{ action }}</li></ol></section>
        <section class="document-section document-checkpoint"><span>阶段验收</span><h3>提交可验证的学习结果</h3><p>完成后回到能力诊断进行复测；系统将根据本资料绑定的知识来源与学习记录更新后续学习路径。</p></section>
      </div>
      <div class="dialog-source"><CircleCheckFilled /><div><b>来源已核验</b><span>{{ selectedPreview?.source_chunk_id }} · {{ selectedPreview?.review_reason }}</span></div></div>
      <div class="dialog-actions"><button class="primary-gradient-button" type="button" @click="beginPreviewLearning">{{ activeResourceId === selectedPreview?.id ? '学习进行中' : '开始学习' }} <ArrowRight /></button><button type="button" @click="previewVisible = false">返回资料库</button></div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, CircleCheck, CircleCheckFilled, Clock, Collection, DataAnalysis, DataLine, Document, EditPen, Files, Grid, Guide, Loading, Lock, MagicStick, Menu, Monitor, Refresh, RefreshLeft, Search, Star, TrendCharts, Warning } from '@element-plus/icons-vue'
import { bookmarkResource, getResourceBookmarks, getResourceList, unbookmarkResource, type ResourceInfo } from '@/api/resource'
import { getLearningRecords, type LearningRecordInfo } from '@/api/record'
import { getLearningPaths, type LearningPathInfo } from '@/api/path'
import { getAssessmentProgress, repairLearningPackage, type AssessmentProgress } from '@/api/assessment'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const store = useUserStore()
// Keep the local visual fixture consistent with the review and diagnosis pages.
// import.meta.env.DEV is compiled to false for production, so this cannot
// disable production authentication.
const demoMode = computed(() => import.meta.env.DEV && route.query.demo === '1')
const resources = ref<ResourceInfo[]>([])
const libraryLoading = ref(false)
const libraryError = ref('')
const assessmentId = ref('')
const keyword = ref('')
const selectedTypes = ref<string[]>([])
const selectedPoints = ref<string[]>([])
const viewMode = ref<'grid' | 'list'>('grid')
const searchInput = ref<HTMLInputElement | null>(null)
const selectedPreview = ref<ResourceInfo | null>(null)
const previewVisible = ref(false)
const spotlight = ref({ x: 74, y: 42, active: false })
const bookmarkedIds = ref<Set<string>>(new Set())
const learningRecords = ref<Record<string, LearningRecordInfo>>({})
const currentPath = ref<LearningPathInfo | null>(null)
const activeResourceId = ref('')
let libraryLoadSequence = 0
const packageRepairing = ref(false)
const repairProgress = ref<AssessmentProgress>({ stage: 'material', agent: '协同调度器', label: '等待自动修复', percent: 0, status: 'waiting', updated_at: null, events: [] })
const repairRequestedFor = new Set<string>()
let repairTimer: number | null = null
let repairPollCount = 0

const demoResources: ResourceInfo[] = [
  { id: 'demo-java-core', assessment_id: 'demo-assessment', knowledge_point: 'Java 并发', content_type: '个性化讲义', title: 'Java 并发核心原理精讲', body: '从线程模型、锁语义与线程池参数入手，结合订单处理场景理解并发安全边界，并完成一组可验证的代码实验。', difficulty: 3, source_chunk_id: 'java_backend_0182', source_text: 'Java 并发与线程池领域知识片段', review_status: 'passed', review_reason: '知识点与来源片段一致，代码范围明确。', display_status: 'published', generation_method: 'rag_agent', created_at: '2026-08-16T10:00:00' },
  { id: 'demo-spring-task', assessment_id: 'demo-assessment', knowledge_point: 'Spring Boot', content_type: '实操任务', title: '订单接口限流与缓存实战', body: '在现有 Spring Boot 服务中实现接口幂等、Redis 缓存与限流策略，并使用压测报告说明优化前后的吞吐变化。', difficulty: 4, source_chunk_id: 'java_backend_0241', source_text: 'Spring Boot 接口治理实操片段', review_status: 'passed', review_reason: '任务步骤与岗位能力要求一致。', display_status: 'published', generation_method: 'rag_agent', created_at: '2026-08-16T10:03:00' },
  { id: 'demo-db-review', assessment_id: 'demo-assessment', knowledge_point: 'MySQL', content_type: '错题解析', title: '高频 SQL 性能误区解析', body: '围绕联合索引、回表、覆盖索引与执行计划，解释本次测评中的典型错误，并给出可复现的对照实验。', difficulty: 3, source_chunk_id: 'java_backend_0318', source_text: 'MySQL 索引优化知识片段', review_status: 'passed', review_reason: '解析结论可由来源片段追溯。', display_status: 'published', generation_method: 'rag_agent', created_at: '2026-08-16T10:05:00' },
  { id: 'demo-microservice-guide', assessment_id: 'demo-assessment', knowledge_point: '微服务', content_type: '实操指南', title: '微服务故障排查操作手册', body: '按日志、链路追踪、指标监控与依赖关系四个层次建立排查清单，完成一次超时故障定位演练。', difficulty: 4, source_chunk_id: 'java_backend_0456', source_text: '微服务可观测性与故障排查片段', review_status: 'passed', review_reason: '操作步骤完整且无超出来源的技术断言。', display_status: 'published', generation_method: 'rag_agent', created_at: '2026-08-16T10:08:00' },
  { id: 'demo-rbac-project', assessment_id: 'demo-assessment', knowledge_point: '权限认证', content_type: '项目任务书', title: '企业级 RBAC 权限系统任务书', body: '完成角色、权限、资源与审计日志的数据建模、接口设计和验收测试，提交架构说明与核心代码证据。', difficulty: 4, source_chunk_id: 'java_backend_0520', source_text: 'RBAC 项目能力要求与验收规范', review_status: 'partial', review_reason: '主体任务已核验，部署部分建议人工复核。', display_status: 'published', generation_method: 'rag_agent', created_at: '2026-08-16T10:12:00' },
  { id: 'demo-roadmap', assessment_id: 'demo-assessment', knowledge_point: '系统设计', content_type: '阶段学习路径', title: '后端工程师三阶段成长路径', body: '先补齐数据库与工程基础，再通过综合项目强化架构能力，最后以复测和项目证据验证岗位达标情况。', difficulty: 3, source_chunk_id: 'java_backend_0614', source_text: '后端工程师阶段能力模型与训练顺序', review_status: 'passed', review_reason: '路径顺序与能力缺口及知识库要求一致。', display_status: 'published', generation_method: 'rag_agent', created_at: '2026-08-16T10:15:00' },
]

const defaultTypes = ['个性化讲义', '实操任务', '错题解析', '项目任务书', '阶段学习路径']
const resourceTypes = computed(() => [...new Set(resources.value.map(item => item.content_type))])
const visibleResourceTypes = computed(() => hasResources.value ? resourceTypes.value : defaultTypes)
const knowledgePoints = computed(() => [...new Set(resources.value.map(item => item.knowledge_point))])
const passedCount = computed(() => resources.value.filter(item => item.review_status === 'passed').length)
const partialCount = computed(() => resources.value.filter(item => item.review_status === 'partial').length)
const hasResources = computed(() => resources.value.length > 0)
const passedRate = computed(() => resources.value.length ? Math.round(passedCount.value / resources.value.length * 100) : 0)
const partialRate = computed(() => resources.value.length ? Math.round(partialCount.value / resources.value.length * 100) : 0)
const packageProgress = computed(() => Math.min(96, 58 + passedCount.value * 6))
const filteredResources = computed(() => { const search = keyword.value.toLowerCase(); return resources.value.filter(item => { const matchesSearch = !search || [item.title, item.knowledge_point,item.body].join(' ').toLowerCase().includes(search); const matchesType = !selectedTypes.value.length || selectedTypes.value.includes(item.content_type); const matchesPoint = !selectedPoints.value.length || selectedPoints.value.includes(item.knowledge_point); return matchesSearch && matchesType && matchesPoint }) })
const featuredResource = computed(() => filteredResources.value[0] || null)
const selectedLabel = computed(() => selectedTypes.value.length || selectedPoints.value.length ? '已应用筛选条件' : '基于本次能力缺口')
const previewParagraphs = computed(() => (selectedPreview.value?.body || '').split(/\n{2,}/).map(item => item.trim()).filter(Boolean))
const previewActions = computed(() => {
  const resource = selectedPreview.value
  if (!resource) return []
  return [
    `阅读资料并标记与“${resource.knowledge_point}”相关的关键概念和要求。`,
    `围绕“${resource.title}”完成一次可验证的练习或产出。`,
    '记录结果并完成阶段复测，让后续学习路径根据真实表现更新。',
  ]
})
const packSpotlight = computed(() => ({ '--spot-x': `${spotlight.value.x}%`, '--spot-y': `${spotlight.value.y}%`, '--spot-opacity': spotlight.value.active ? '.82' : '.48' }))
const emptyResourcePreview = [
  { type: '讲义', title: '个性化知识讲义', description: '围绕未达标知识点生成', icon: Document },
  { type: '实操', title: '岗位实操指南', description: '把知识点转化为任务步骤', icon: Monitor },
  { type: '项目', title: '项目任务书', description: '以验收标准验证能力证据', icon: Files },
  { type: '复测', title: '分阶测试与解析', description: '学习后重新校准能力状态', icon: EditPen },
]
const pipelineSteps = [
  { title: '识别能力缺口', description: '读取诊断与证据链' },
  { title: '检索知识片段', description: '匹配职业知识库来源' },
  { title: '生成训练资源', description: '组织讲义、任务与复测' },
  { title: '审核纠偏', description: '通过后进入正式资料库' },
]

function typeCount(type: string) { return resources.value.filter(item => item.content_type === type).length }
function pointCount(point: string) { return resources.value.filter(item => item.knowledge_point === point).length }
function preview(body: string) { return body.replace(/[#*`>]/g, '').replace(/\s+/g, ' ').trim().slice(0, 92) || '已生成学习资料，打开后可查看完整内容。' }
function resourceIcon(type: string) { if (type.includes('讲义')) return Document; if (type.includes('实操') || type.includes('指南')) return Monitor; if (type.includes('错题') || type.includes('测试')) return EditPen; if (type.includes('项目')) return Files; if (type.includes('路径')) return Guide; return Collection }
function resourceTone(type: string) { if (type.includes('错题') || type.includes('测试')) return 'violet'; if (type.includes('项目')) return 'blue'; if (type.includes('实操') || type.includes('指南')) return 'green'; if (type.includes('路径')) return 'mint'; return 'sky' }
function reviewText(status: string | null) { return status === 'passed' ? '通过' : status === 'partial' ? '部分匹配' : '复核中' }
function resourceProgress(resource: ResourceInfo, index: number) {
  if (demoMode.value) return activeResourceId.value === resource.id ? 50 : [78, 61, 42, 34, 83, 56][index % 6]
  const record = learningRecords.value[resource.id]
  if (!record) return 0
  return record.status === 'completed' ? 100 : record.status === 'in_progress' ? 50 : 0
}
function stepState(index: number) {
  if (hasResources.value) return 'done'
  if (!packageRepairing.value) return 'waiting'
  const thresholds = [50, 72, 92, 100]
  if (repairProgress.value.percent >= thresholds[index]) return 'done'
  const active = thresholds.findIndex(value => repairProgress.value.percent < value)
  return active === index ? 'running' : 'waiting'
}
function safePathLabel(value: string, index: number) {
  const cleaned = String(value || '').replace(/^[\s#>*\-\d.、()（）]+/, '').replace(/\s+/g, ' ').trim()
  if (!cleaned || /构建失败|网络问题|后端问题|异常|error|failed/i.test(cleaned)) return ['岗位核心能力', '项目实战', '阶段复测'][index] || `能力补强 ${index + 1}`
  return cleaned.slice(0, 32)
}
function openResource(resource: ResourceInfo, start = false) {
  if (resource.id.startsWith('demo-')) {
    selectedPreview.value = resource
    previewVisible.value = true
    if (start) activeResourceId.value = resource.id
    return
  }
  router.push({ path: `/resource/${resource.id}`, query: start ? { start: '1' } : undefined })
}
function continueLearning() {
  const current = currentPath.value?.steps.find(step => step.status === 'in_progress')
    || currentPath.value?.steps.find(step => step.status === 'current')
    || currentPath.value?.steps.find(step => step.status === 'not_started' && step.resource_id)
  const target = current?.resource_id ? resources.value.find(item => item.id === current.resource_id) : featuredResource.value
  if (!target) { ElMessage.warning('当前学习路径还没有可打开的资料'); return }
  openResource(target, true)
}
function beginPreviewLearning() {
  if (!selectedPreview.value) return
  if (!demoMode.value) { router.push({ path: `/resource/${selectedPreview.value.id}`, query: { start: '1' } }); return }
  activeResourceId.value = selectedPreview.value.id
  ElMessage.success('已开始学习，进度会同步到资料库和学习路径')
}
async function toggleBookmark(resource: ResourceInfo) {
  const next = new Set(bookmarkedIds.value)
  const active = next.has(resource.id)
  if (demoMode.value) {
    active ? next.delete(resource.id) : next.add(resource.id)
    bookmarkedIds.value = next
    return
  }
  try {
    if (active) { await unbookmarkResource(resource.id); next.delete(resource.id); ElMessage.success('已取消收藏') }
    else { await bookmarkResource(resource.id); next.add(resource.id); ElMessage.success('已收藏') }
    bookmarkedIds.value = next
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '收藏状态更新失败')
  }
}
function openDiagnosis() { if (demoMode.value) router.push('/diagnosis?demo=1'); else if (assessmentId.value) router.push(`/diagnosis/${assessmentId.value}`); else router.push('/diagnosis') }
function resetFilters() { keyword.value = ''; selectedTypes.value = []; selectedPoints.value = [] }
function updateSpotlight(event: PointerEvent) { const target = event.currentTarget as HTMLElement; const rect = target.getBoundingClientRect(); spotlight.value = { x: (event.clientX - rect.left) / rect.width * 100, y: (event.clientY - rect.top) / rect.height * 100, active: true } }
function clearSpotlight() { spotlight.value.active = false }
function handleShortcut(event: KeyboardEvent) { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); nextTick(() => searchInput.value?.focus()) } }
function stopRepairPolling() { if (repairTimer !== null) { window.clearInterval(repairTimer); repairTimer = null } }
async function pollPackageRepair() {
  if (!assessmentId.value || !packageRepairing.value) return
  repairPollCount += 1
  try {
    const snapshot = await getAssessmentProgress(assessmentId.value)
    repairProgress.value = snapshot
    if (snapshot.status === 'failed') {
      stopRepairPolling(); packageRepairing.value = false
      libraryError.value = snapshot.label || '学习包自动修复失败'
      return
    }
    if (snapshot.status === 'completed' || snapshot.percent >= 100) {
      stopRepairPolling(); packageRepairing.value = false
      await loadLibrary(false)
      if (!resources.value.length) {
        libraryError.value = '重建任务已结束，但没有产生通过来源审核的学习资料。请重试；若仍失败，请检查知识库检索与审核日志。'
      }
      return
    }
  } catch { /* a later polling cycle retries */ }
  if (repairPollCount >= 120) {
    stopRepairPolling(); packageRepairing.value = false
    libraryError.value = '学习包生成超时，请检查后端 Agent 与大模型配置'
  }
}
async function startPackageRepair(force = false) {
  const id = assessmentId.value
  if (!id || packageRepairing.value) return
  if (!force && repairRequestedFor.has(id)) return
  repairRequestedFor.add(id); libraryError.value = ''; packageRepairing.value = true; repairPollCount = 0
  repairProgress.value = { stage: 'material', agent: '协同调度器', label: '正在启动学习包自动修复', percent: 2, status: 'waiting', updated_at: null, events: [] }
  try {
    await repairLearningPackage(id)
    stopRepairPolling()
    await pollPackageRepair()
    if (packageRepairing.value) repairTimer = window.setInterval(pollPackageRepair, 2500)
  } catch (error: any) {
    packageRepairing.value = false
    libraryError.value = error?.response?.data?.detail || '无法启动学习包自动修复'
  }
}
async function retryPackageRepair() {
  if (!assessmentId.value) return
  repairRequestedFor.delete(assessmentId.value)
  await startPackageRepair(true)
}
async function loadLibrary(autoRepair = true) {
  const sequence = ++libraryLoadSequence
  libraryLoading.value = true; libraryError.value = ''; resources.value = []; currentPath.value = null; resetFilters()
  try {
    if (demoMode.value) {
      assessmentId.value = 'demo-assessment'; resources.value = demoResources; learningRecords.value = {}
      currentPath.value = { id: 'demo-path', user_id: 'demo-user', job_id: 'demo-backend', assessment_id: 'demo-assessment', current_step: 1, status: 'active', created_at: '2026-08-16T10:20:00+08:00', updated_at: '2026-08-16T10:20:00+08:00', steps: [
        { step: 1, knowledge_point: 'Java 并发', resource_type: '个性化讲义 + 实操', resource_id: 'demo-java-core', estimated_time: 120, prerequisite: null, status: 'current', record_id: null, weight: 'high' },
        { step: 2, knowledge_point: 'Spring Boot', resource_type: '项目任务书', resource_id: 'demo-spring-task', estimated_time: 180, prerequisite: 'Java 并发', status: 'pending', record_id: null, weight: 'high' },
        { step: 3, knowledge_point: '系统设计', resource_type: '阶段复测', resource_id: 'demo-roadmap', estimated_time: 90, prerequisite: 'Spring Boot', status: 'pending', record_id: null, weight: 'mid' },
      ] }
      return
    }
    // The active diagnosis is server-authoritative. Refreshing the library
    // picks up a newly completed diagnosis; an explicit history selection is
    // already persisted by the profile page and therefore remains selected.
    await store.fetchUserInfo()
    const byQuery = typeof route.query.assessment === 'string' ? route.query.assessment : ''
    const byParam = typeof route.params.assessmentId === 'string' ? route.params.assessmentId : ''
    const requestedId = byQuery || byParam
    const currentId = store.currentAssessmentId
    if (currentId && requestedId !== currentId) {
      await router.replace({ path: '/library', query: { assessment: currentId } })
      return
    }
    assessmentId.value = currentId
    if (!assessmentId.value) return
    const [resourceItems, bookmarks, records, paths] = await Promise.all([
      getResourceList({ assessment_id: assessmentId.value }),
      getResourceBookmarks(),
      getLearningRecords(assessmentId.value),
      store.userInfo ? getLearningPaths(store.userInfo.id, assessmentId.value) : Promise.resolve([]),
    ])
    if (sequence !== libraryLoadSequence) return
    resources.value = resourceItems
    bookmarkedIds.value = new Set(bookmarks.map(item => item.resource_id))
    learningRecords.value = Object.fromEntries(records.map(item => [item.resource_id, item]))
    currentPath.value = paths.find(path => path.assessment_id === assessmentId.value) || null
    if (!resources.value.length && autoRepair) void startPackageRepair()
  } catch (error: any) {
    if (sequence === libraryLoadSequence) {
      libraryError.value = error?.response?.data?.detail || '资料库加载失败'
      resources.value = []
    }
  }
  finally { if (sequence === libraryLoadSequence) libraryLoading.value = false }
}
watch(() => [route.query.assessment, route.query.demo, route.params.assessmentId], () => void loadLibrary(true), { immediate: true })
onMounted(() => { window.addEventListener('keydown', handleShortcut) })
onBeforeUnmount(() => { stopRepairPolling(); window.removeEventListener('keydown', handleShortcut) })
</script>

<style scoped>
.library-page{--pack-hero:linear-gradient(120deg,rgba(222,250,222,.88),rgba(248,255,250,.94) 49%,rgba(148,238,184,.26));padding-top:38px}.library-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:32px;margin-bottom:25px}.heading-copy{max-width:760px}.heading-actions{display:flex;align-items:center;gap:11px}.search-box{width:410px;height:52px;display:flex;align-items:center;gap:11px;padding:0 14px;border-radius:16px;color:var(--ink-faint)}.search-box>svg{width:18px}.search-box input{min-width:0;flex:1;border:0;outline:0;background:transparent;color:var(--ink);font-size:13px}.search-box input::placeholder{color:var(--ink-faint)}.search-box kbd{border:1px solid rgba(20,78,48,.08);border-radius:7px;padding:4px 7px;background:rgba(255,255,255,.7);box-shadow:inset 0 1px 0 white;color:var(--ink-faint);font-family:inherit;font-size:10px}.view-switch{display:flex;gap:4px;padding:5px;border-radius:14px}.view-switch button{width:38px;height:38px;border:0;border-radius:10px;display:grid;place-items:center;background:transparent;color:var(--ink-faint);cursor:pointer}.view-switch button svg{width:17px}.view-switch button.active{background:rgba(222,250,222,.9);color:var(--green-deep);box-shadow:0 5px 13px rgba(13,131,72,.09)}.library-layout{display:grid;grid-template-columns:244px minmax(0,1fr) 248px;gap:18px;align-items:start}.filter-panel,.overview-card,.collection-card{border-radius:var(--radius-lg);padding:19px}.filter-panel{position:sticky;top:92px}.filter-title,.overview-title{display:flex;align-items:center;justify-content:space-between;gap:10px}.filter-title>div>span,.overview-title>div>span,.resource-heading>div>span{display:block;margin-bottom:4px;color:var(--green-deep);font-size:9px;font-weight:800}.filter-title h2,.overview-title h2,.resource-heading h2{margin:0;font-size:16px}.filter-title button{display:flex;align-items:center;gap:4px;border:1px solid var(--line);border-radius:10px;padding:6px 8px;background:rgba(255,255,255,.57);color:var(--ink-soft);font-size:10px;cursor:pointer}.filter-title button svg{width:12px}.filter-group{padding-top:21px}.filter-group+.filter-group{margin-top:16px;border-top:1px solid var(--line)}.filter-group h3{display:flex;align-items:center;gap:7px;margin:0 0 13px;color:var(--ink);font-size:13px}.filter-group h3 svg{width:15px;color:var(--green-deep)}.filter-group label{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:8px;margin:11px 0;color:var(--ink-soft);font-size:11px;cursor:pointer}.filter-group label.disabled{cursor:not-allowed;opacity:.62}.filter-group input{accent-color:var(--green-accent)}.filter-group small{color:var(--ink-faint);font-size:9px}.topic-preview{display:flex;flex-wrap:wrap;gap:6px}.topic-preview span{padding:6px 7px;border-radius:8px;background:rgba(238,252,243,.72);color:var(--ink-soft);font-size:9px}.audit-note{display:flex;gap:8px;padding:11px;border-radius:12px;background:linear-gradient(135deg,rgba(222,250,222,.72),rgba(255,255,255,.62));color:var(--green-ink);font-size:10px;line-height:1.62}.audit-note i{flex:0 0 auto;width:7px;height:7px;margin-top:4px;border-radius:50%;background:var(--gradient-primary);box-shadow:0 0 10px rgba(34,181,107,.38)}.library-content{min-width:0}.library-tools{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:3px 0 15px}.library-tools>span{color:var(--ink-faint);font-size:11px}.type-tabs{display:flex;gap:7px;flex-wrap:wrap}.type-tabs button{border:1px solid rgba(14,94,52,.09);border-radius:999px;padding:7px 14px;background:rgba(255,255,255,.44);color:var(--ink-soft);font-size:11px;cursor:pointer;transition:.2s ease}.type-tabs button:disabled{cursor:not-allowed;opacity:.48}.type-tabs button.active{border-color:rgba(34,181,107,.24);background:var(--gradient-primary);color:white;box-shadow:0 7px 16px rgba(15,164,91,.17)}.learning-package{--spot-x:74%;--spot-y:42%;--spot-opacity:.48;position:relative;display:grid;grid-template-columns:1.08fr .92fr;min-height:300px;padding:29px;overflow:hidden;border-radius:var(--radius-lg);border-color:rgba(179,241,202,.76);background:var(--pack-hero);box-shadow:0 23px 55px rgba(33,124,73,.1),inset 0 1px 1px white}.learning-package::after{content:'';position:absolute;inset:0;z-index:0;background:radial-gradient(circle at var(--spot-x) var(--spot-y),rgba(255,255,255,var(--spot-opacity)),transparent 31%);pointer-events:none;transition:opacity .3s ease}.learning-package::before{opacity:.78}.package-copy{align-self:center;z-index:2}.package-copy .glass-pill svg{width:14px}.package-copy h2{max-width:560px;margin:17px 0 9px;font-size:clamp(24px,1.8vw,31px);line-height:1.25}.package-copy p{max-width:610px;margin:0;color:var(--ink-soft);font-size:12px;line-height:1.72}.package-tags{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}.package-tags span{display:inline-flex;align-items:center;gap:4px;padding:5px 8px;border-radius:8px;background:rgba(255,255,255,.62);border:1px solid rgba(255,255,255,.74);color:var(--green-deep);font-size:9px}.package-tags svg{width:11px}.package-progress{max-width:330px;margin-top:18px}.package-progress>div:first-child{display:flex;justify-content:space-between;color:var(--ink-soft);font-size:10px}.package-progress b{color:var(--green-deep)}.progress-track,.mini-progress{height:5px;overflow:hidden;border-radius:999px;background:rgba(17,105,61,.08)}.progress-track{margin-top:7px}.progress-track i,.mini-progress i{display:block;height:100%;border-radius:inherit;background:var(--gradient-progress)}.package-actions{display:flex;align-items:center;gap:14px;margin-top:20px}.package-actions button{display:inline-flex;align-items:center;gap:8px;border-radius:13px;padding:11px 16px;font-size:12px;font-weight:700;cursor:pointer}.package-actions button svg{width:15px}.package-actions>span{color:var(--ink-soft);font-size:10px}.spatial-resource-object{position:relative;z-index:2;min-height:235px;align-self:center}.spatial-resource-object img{position:absolute;z-index:2;left:50%;top:51%;width:min(360px,96%);height:224px;object-fit:cover;object-position:center;transform:translate(-50%,-50%);mix-blend-mode:multiply;filter:saturate(.91) contrast(1.03);animation:pack-float 7s ease-in-out infinite}.pack-halo{position:absolute;left:50%;top:52%;width:290px;height:150px;transform:translate(-50%,-50%);border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.94) 0%,rgba(134,231,177,.3) 38%,transparent 70%);filter:blur(10px)}.orbit{position:absolute;z-index:1;left:50%;top:55%;border:1px solid rgba(34,181,107,.21);border-radius:50%;transform:translate(-50%,-50%) rotateX(68deg)}.orbit-one{width:360px;height:140px}.orbit-two{width:265px;height:94px;transform:translate(-50%,-50%) rotateX(68deg) rotate(47deg)}.floating-chip{position:absolute;z-index:3;display:flex;align-items:center;gap:5px;padding:6px 9px;border:1px solid rgba(255,255,255,.88);border-radius:999px;background:rgba(255,255,255,.72);box-shadow:0 8px 19px rgba(19,102,58,.08);color:var(--green-ink);font-size:9px;backdrop-filter:blur(14px)}.floating-chip svg{width:12px}.chip-one{left:4%;top:27%;animation:chip-drift 5.8s ease-in-out infinite}.chip-two{right:2%;top:38%;animation:chip-drift 6.4s ease-in-out -.8s infinite}.chip-three{right:14%;bottom:14%;animation:chip-drift 5.5s ease-in-out -1.8s infinite}.resource-section{margin-top:20px}.resource-heading{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:11px}.resource-heading em{color:var(--ink-faint);font-size:10px;font-style:normal}.resource-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:11px}.resource-card{min-height:205px;padding:15px;border-radius:var(--radius-md);display:flex;flex-direction:column;animation:card-enter .45s cubic-bezier(.2,.8,.2,1) var(--card-delay) both;transition:transform .23s ease,box-shadow .23s ease}.resource-card:hover{transform:translateY(-4px);box-shadow:0 21px 38px rgba(25,90,56,.12),inset 0 1px 1px white}.resource-card-top{display:flex;align-items:center;gap:7px}.resource-icon{flex:0 0 auto;width:38px;height:38px;display:grid;place-items:center;border-radius:12px;background:linear-gradient(135deg,#a9d9ff,#4e8ff0);box-shadow:0 7px 15px rgba(44,105,211,.14);color:white}.resource-icon svg{width:18px}.resource-icon.green{background:linear-gradient(135deg,#a1efbf,#22aa68)}.resource-icon.violet{background:linear-gradient(135deg,#d4b6ff,#895de7)}.resource-icon.blue{background:linear-gradient(135deg,#9fd1ff,#397de6)}.resource-icon.mint{background:linear-gradient(135deg,#d9ffdf,#28b970)}.resource-icon.muted{background:linear-gradient(135deg,rgba(222,250,222,.9),rgba(177,235,199,.7));box-shadow:none;color:var(--green-deep)}.resource-type{color:var(--green-deep);font-size:9px;font-weight:700}.bookmark{margin-left:auto;width:28px;height:28px;border:0;display:grid;place-items:center;background:transparent;color:var(--ink-faint);cursor:pointer}.bookmark svg{width:14px}.resource-card-copy h3{margin:14px 0 6px;font-size:13px;line-height:1.42}.resource-card-copy p{margin:0;color:var(--ink-soft);font-size:10px;line-height:1.58}.resource-meta{display:flex;gap:5px;flex-wrap:wrap;margin-top:auto;padding-top:11px}.resource-meta span{display:flex;align-items:center;gap:3px;padding:4px 6px;border-radius:7px;background:rgba(235,251,241,.72);color:var(--green-deep);font-size:8px}.resource-meta svg{width:9px}.resource-footer{display:flex;align-items:center;gap:10px;margin-top:10px}.mini-progress{flex:1;height:4px}.resource-footer button{display:flex;align-items:center;gap:4px;border:0;padding:0;background:transparent;color:var(--green-deep);font-size:9px;font-weight:700;cursor:pointer}.resource-footer button svg{width:11px}.resource-grid.list-view{grid-template-columns:1fr}.resource-grid.list-view .resource-card{min-height:128px;display:grid;grid-template-columns:120px minmax(0,1fr) 260px;column-gap:14px;align-items:center}.resource-grid.list-view .resource-meta{margin:0;padding:0}.resource-grid.list-view .resource-footer{margin:0}.resource-preview-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.resource-preview-card{position:relative;min-height:112px;display:flex;align-items:center;gap:13px;padding:15px;border-radius:var(--radius-md);opacity:.72}.resource-preview-card small{color:var(--green-deep);font-size:8px}.resource-preview-card h3{margin:4px 0;font-size:12px}.resource-preview-card p{margin:0;color:var(--ink-soft);font-size:9px}.preview-lock{position:absolute;right:14px;top:14px;width:13px;color:var(--ink-faint)}.overview-column{display:flex;flex-direction:column;gap:14px}.overview-column>section{border-radius:var(--radius-lg)}.overview-title em{padding:5px 7px;border-radius:999px;background:rgba(235,251,241,.7);color:var(--green-deep);font-size:8px;font-style:normal}.overview-score{display:flex;align-items:end;gap:7px;padding:21px 0 13px;border-bottom:1px solid var(--line)}.overview-score strong{font-size:38px;line-height:.9}.overview-score span{color:var(--ink-soft);font-size:10px}.overview-line{position:relative;padding:14px 0 12px;border-bottom:1px solid var(--line)}.overview-line span{display:block;color:var(--ink-soft);font-size:10px}.overview-line b{position:absolute;right:0;top:14px;color:var(--green-deep);font-size:13px}.overview-line i{display:block;width:0;height:4px;margin-top:7px;border-radius:99px;background:var(--gradient-progress)}.overview-line i.partial{background:linear-gradient(90deg,#f7d27b,#eaa52d)}.overview-card>button{width:100%;display:flex;align-items:center;justify-content:center;gap:6px;margin-top:16px;border:0;border-radius:11px;padding:9px;background:rgba(222,250,222,.72);color:var(--green-deep);font-size:10px;font-weight:700;cursor:pointer}.overview-card>button svg{width:13px}.overview-placeholder{padding:28px 4px 12px;text-align:center}.overview-placeholder>svg{width:35px;color:var(--green-accent)}.overview-placeholder strong{display:block;margin-top:11px;font-size:12px}.overview-placeholder p{margin:7px 0 0;color:var(--ink-soft);font-size:9px;line-height:1.6}.pipeline-list{padding:0;margin:18px 0 0;list-style:none}.pipeline-list li{position:relative;display:grid;grid-template-columns:28px minmax(0,1fr);gap:9px;padding-bottom:17px}.pipeline-list li:not(:last-child)::after{content:'';position:absolute;left:13px;top:28px;width:1px;height:calc(100% - 22px);background:var(--line)}.pipeline-list li>span{width:28px;height:28px;display:grid;place-items:center;border-radius:9px;background:rgba(240,248,243,.82);color:var(--ink-faint)}.pipeline-list li>span svg{width:13px}.pipeline-list li.done>span{background:rgba(222,250,222,.86);color:var(--green-deep)}.pipeline-list li.running>span{background:linear-gradient(90deg,#defade,#54dc91,#defade);background-size:200%;color:var(--green-deep);animation:gradient-shift 9s ease infinite}.pipeline-list li.running svg{animation:spin 1.1s linear infinite}.pipeline-list b{display:block;font-size:10px}.pipeline-list small{display:block;margin-top:3px;color:var(--ink-faint);font-size:8px;line-height:1.4}.state-stage{min-height:570px;border-radius:var(--radius-xl);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px;text-align:center;background:radial-gradient(circle at 50% 47%,rgba(222,250,222,.78),rgba(255,255,255,.62) 34%,rgba(255,255,255,.72) 65%)}.state-core{width:70px;height:70px;display:grid;place-items:center;border-radius:23px;background:linear-gradient(135deg,rgba(255,255,255,.94),rgba(189,244,207,.77));color:var(--green-deep);box-shadow:0 16px 34px rgba(16,132,70,.13),inset 0 1px 1px white}.state-core svg{width:28px}.loading-core svg{animation:spin 1s linear infinite}.error-core{background:rgba(255,247,231,.9);color:#d58b1c}.state-stage .eyebrow{margin-top:20px}.state-stage h2{margin:9px 0 7px;font-size:25px}.state-stage p{margin:0;max-width:520px;color:var(--ink-soft);font-size:12px;line-height:1.7}.state-progress{width:260px;height:6px;margin-top:22px;overflow:hidden;border-radius:99px;background:rgba(21,110,63,.08)}.state-progress i{display:block;width:44%;height:100%;border-radius:inherit;background:var(--gradient-progress);animation:loading-slide 1.6s ease-in-out infinite}.state-button{display:flex;align-items:center;gap:7px;margin-top:20px;border-radius:13px;padding:11px 16px;font-weight:700;cursor:pointer}.state-button svg{width:15px}.resource-empty{padding:42px;text-align:center;border-radius:var(--radius-md)}.resource-empty>svg{width:25px;color:var(--green-accent)}.resource-empty b{display:block;margin-top:9px;font-size:13px}.resource-empty p{margin:6px 0 0;color:var(--ink-soft);font-size:10px}.resource-empty button{display:inline-flex;align-items:center;gap:5px;margin-top:13px;border:0;border-radius:10px;padding:8px 11px;background:rgba(222,250,222,.84);color:var(--green-deep);font-size:10px;font-weight:700;cursor:pointer}.resource-empty button svg{width:12px}.dialog-heading{display:flex;align-items:center;gap:12px}.dialog-heading small{color:var(--green-deep);font-size:10px}.dialog-heading h2{margin:3px 0 0;font-size:18px}.dialog-body{margin:0;color:var(--ink-soft);font-size:13px;line-height:1.8}.dialog-source{display:flex;gap:9px;margin-top:20px;padding:13px;border-radius:13px;background:rgba(222,250,222,.64);color:var(--green-deep)}.dialog-source>svg{width:17px}.dialog-source b,.dialog-source span{display:block}.dialog-source b{font-size:11px}.dialog-source span{margin-top:3px;color:var(--ink-soft);font-size:9px}.library-page :deep(.resource-preview-dialog){border-radius:22px;background:rgba(255,255,255,.91);backdrop-filter:blur(28px);box-shadow:0 30px 90px rgba(16,65,39,.18)}
@keyframes pack-float{0%,100%{transform:translate(-50%,-50%) translateY(0)}50%{transform:translate(-50%,-50%) translateY(-7px)}}@keyframes chip-drift{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}@keyframes card-enter{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}@keyframes spin{to{transform:rotate(360deg)}}@keyframes loading-slide{0%{transform:translateX(-115%)}100%{transform:translateX(330%)}}
@media(max-width:1240px){.library-layout{grid-template-columns:210px minmax(0,1fr)}.overview-column{grid-column:1/3;display:grid;grid-template-columns:1fr 1fr}.resource-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.heading-actions{flex:0 1 470px}.search-box{width:100%}}
@media(max-width:820px){.library-page{padding-top:28px}.library-heading{display:block}.heading-actions{margin-top:16px}.search-box{flex:1}.library-layout{display:block}.filter-panel{position:relative;top:auto;margin-bottom:14px}.filter-group:not(.verification-group){display:none}.library-tools{align-items:flex-start;flex-direction:column}.learning-package{grid-template-columns:1fr;padding:22px}.spatial-resource-object{min-height:190px;margin-top:-4px}.resource-preview-grid,.resource-grid{grid-template-columns:1fr}.resource-grid.list-view .resource-card{display:flex}.overview-column{display:block;margin-top:14px}.overview-column>*+*{margin-top:14px}.package-actions{align-items:flex-start;flex-direction:column}.view-switch{display:none}}
@media(max-width:520px){.heading-actions{display:block}.search-box{width:100%}.learning-package{min-height:auto}.spatial-resource-object img{width:300px}.resource-preview-grid{grid-template-columns:1fr}.page-subtitle{font-size:12px}}
/* V2 alignment pass: keep both side rails visually weighted against the resource grid. */
@media (min-width: 1241px) {
  .library-page { --sidebar-height: clamp(780px, calc(100vh - 122px), 830px); }
  .library-layout { align-items: stretch; }
  .filter-panel {
    position: sticky;
    top: 92px;
    height: 100%;
    min-height: var(--sidebar-height);
    padding: 22px 19px;
    display: flex;
    flex-direction: column;
    align-self: stretch;
  }
  .filter-panel .verification-group {
    margin-top: auto;
    padding-top: 24px;
  }
  .overview-column {
    position: sticky;
    top: 92px;
    height: 100%;
    min-height: var(--sidebar-height);
    display: grid;
    grid-template-rows: minmax(0, 1.03fr) minmax(0, .97fr);
    gap: 18px;
    align-self: stretch;
  }
  .overview-column > section {
    min-height: 0;
    height: 100%;
    padding: 22px 19px;
  }
  .overview-card,
  .collection-card { display: flex; flex-direction: column; }
  .overview-score { padding: 28px 0 20px; }
  .overview-line { padding: 19px 0 17px; }
  .overview-line b { top: 19px; }
  .overview-card > button { margin-top: auto; }
  .pipeline-list {
    min-height: 0;
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    margin-top: 22px;
  }
  .pipeline-list li {
    flex: 1;
    min-height: 66px;
    padding-bottom: 18px;
  }
}

/* Reference-led material pass: transparent product surfaces with a stronger hero hierarchy. */
.library-page {
  --pack-hero:
    linear-gradient(124deg, rgba(222,250,222,.68), rgba(250,255,252,.58) 48%, rgba(113,228,158,.18)),
    rgba(246,255,249,.35);
  background: radial-gradient(circle at 75% 22%, rgba(189,244,207,.22), transparent 31%), linear-gradient(180deg, #fdfffe 0%, #f5fbf7 100%);
}
.search-box,
.view-switch {
  border: 1px solid rgba(255,255,255,.78);
  background: linear-gradient(145deg, rgba(255,255,255,.65), rgba(240,255,246,.3)), rgba(255,255,255,.34);
  box-shadow: 0 16px 38px rgba(21,82,51,.07), inset 0 1px 1px rgba(255,255,255,.96);
  backdrop-filter: blur(28px) saturate(152%);
}
.filter-panel,
.overview-card,
.collection-card {
  overflow: hidden;
  isolation: isolate;
  border: 1px solid rgba(255,255,255,.76);
  background: linear-gradient(145deg, rgba(255,255,255,.62), rgba(247,255,250,.34) 55%, rgba(189,244,207,.13)), rgba(250,255,252,.4);
  box-shadow: 0 28px 68px rgba(20,91,55,.085), inset 0 1px 1px rgba(255,255,255,.97), inset 0 -1px 1px rgba(34,181,107,.03);
  backdrop-filter: blur(31px) saturate(154%);
}
.learning-package {
  min-height: 316px;
  border: 1px solid rgba(181,242,204,.72);
  background: var(--pack-hero);
  box-shadow: 0 31px 74px rgba(25,113,64,.115), 0 0 42px rgba(115,232,163,.08), inset 0 1px 1px rgba(255,255,255,.98), inset 0 -1px 1px rgba(34,181,107,.04);
  backdrop-filter: blur(33px) saturate(162%);
}
.learning-package::after {
  background:
    radial-gradient(circle at var(--spot-x) var(--spot-y), rgba(255,255,255,var(--spot-opacity)), transparent 31%),
    linear-gradient(116deg, rgba(255,255,255,.28), transparent 28%, rgba(112,230,159,.07));
}
.spatial-resource-object img { filter: saturate(.98) contrast(1.04) drop-shadow(0 22px 30px rgba(25,121,67,.08)); }
.floating-chip { border-color: rgba(255,255,255,.8); background: linear-gradient(145deg, rgba(255,255,255,.68), rgba(229,253,238,.32)), rgba(255,255,255,.32); box-shadow: 0 12px 27px rgba(19,102,58,.085), inset 0 1px 1px rgba(255,255,255,.96); backdrop-filter: blur(21px) saturate(152%); }
.resource-card {
  border: 1px solid rgba(255,255,255,.75);
  background: linear-gradient(145deg, rgba(255,255,255,.63), rgba(247,255,250,.34) 60%, rgba(189,244,207,.1)), rgba(250,255,252,.38);
  box-shadow: 0 18px 44px rgba(24,83,52,.065), inset 0 1px 1px rgba(255,255,255,.96);
  backdrop-filter: blur(27px) saturate(148%);
}
.resource-card:hover { box-shadow: 0 27px 57px rgba(25,101,59,.13), inset 0 1px 1px rgba(255,255,255,.98); }
.overview-card > button { background: linear-gradient(135deg, rgba(222,250,222,.72), rgba(246,255,249,.54)); box-shadow: inset 0 1px 1px rgba(255,255,255,.95), 0 8px 19px rgba(25,112,63,.06); }
.topic-preview span,
.resource-meta span,
.package-tags span { backdrop-filter: blur(13px) saturate(140%); }

/* Keep the generated resource object complete inside a dedicated spatial stage. */
.learning-package {
  grid-template-columns: minmax(0, 52fr) minmax(330px, 48fr);
  gap: clamp(10px, 1.4vw, 24px);
  min-height: 322px;
  padding: 28px 26px 28px 30px;
}
.package-copy { max-width: 620px; }
.spatial-resource-object {
  width: 100%;
  min-width: 0;
  min-height: 266px;
  align-self: stretch;
  overflow: visible;
  isolation: isolate;
  border-radius: 22px;
  background: radial-gradient(ellipse at 58% 52%, rgba(255,255,255,.72), rgba(222,250,222,.18) 45%, transparent 75%);
}
.spatial-resource-object img {
  left: 50%;
  top: 50%;
  width: 100%;
  height: 100%;
  max-width: none;
  object-fit: contain;
  object-position: center;
  transform: translate(-50%,-50%);
  mix-blend-mode: multiply;
  -webkit-mask-image: radial-gradient(ellipse at 52% 52%, #000 46%, rgba(0,0,0,.82) 64%, transparent 88%);
  mask-image: radial-gradient(ellipse at 52% 52%, #000 46%, rgba(0,0,0,.82) 64%, transparent 88%);
  filter: saturate(.98) contrast(1.03) drop-shadow(0 22px 30px rgba(25,121,67,.07));
}
.pack-halo { top: 54%; width: min(340px,88%); height: 190px; opacity: .72; }
.orbit-one { width: min(390px,96%); }
.orbit-two { width: min(290px,76%); }
.chip-one { left: 3%; top: 22%; }
.chip-two { right: 1%; top: 33%; }
.chip-three { right: 11%; bottom: 9%; }

@media (max-width: 1240px) {
  .learning-package { grid-template-columns: minmax(0, 51fr) minmax(300px, 49fr); }
}
@media (max-width: 820px) {
  .learning-package { grid-template-columns: 1fr; }
  .spatial-resource-object { min-height: 230px; }
  .spatial-resource-object img { width: 100%; height: 100%; }
}
@media (max-width: 520px) {
  .spatial-resource-object { min-height: 205px; }
  .spatial-resource-object img { width: 100%; height: 100%; }
}
.bookmark.active {
  color: #079455;
  background: rgba(222, 250, 222, .74);
  border-radius: 9px;
}
.bookmark.active svg { fill: currentColor; }

/* Final visual audit: give the library the same three-column weight as the reference. */
.library-heading {
  width: calc(100% - 314px);
  margin-left: 314px;
}
.library-layout {
  grid-template-columns: minmax(280px, 290px) minmax(0, 1fr) minmax(280px, 290px);
  gap: 24px;
}
.filter-panel { min-height: 650px; }
.overview-column { min-height: 650px; }
.spatial-resource-object {
  min-height: 266px;
  overflow: visible;
}
.spatial-resource-object img {
  width: 136%;
  height: 136%;
  object-fit: contain;
  object-position: 50% 50%;
}
@media (min-width: 1241px) {
  .library-page { padding-top: 20px; }
  .library-heading {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 720px);
    align-items: start;
    gap: 24px;
    margin-bottom: 8px;
  }
  .library-heading .eyebrow { display: none; }
  .library-heading .page-title { margin-top: 9px; margin-bottom: 6px; }
  .library-heading .page-subtitle { line-height: 1.5; }
  .heading-actions { width: 100%; justify-content: space-between; margin-top: 12px; }
  .search-box { width: 100%; }
  .library-tools { margin-top: 0; margin-bottom: 28px; }
  .library-layout { align-items: start; }
  .filter-panel {
    position: relative;
    top: auto;
    height: 815px;
    min-height: 815px;
    margin-top: -112px;
    align-self: start;
  }
  .overview-column {
    position: relative;
    top: auto;
    height: auto;
    min-height: 0;
    margin-top: -12px;
    display: flex;
    align-self: start;
  }
  .overview-column > section { height: auto; min-height: 0; }
  .learning-package { min-height: 310px; padding-block: 25px; }
  .spatial-resource-object { min-height: 240px; }
  .resource-card { min-height: 145px; padding: 12px; }
  .resource-card-copy h3 { margin-top: 9px; }
  .resource-card-copy p { display: none; }
  .resource-meta { padding-top: 7px; }
  .resource-footer { margin-top: 7px; }
  .overview-card, .collection-card { padding: 17px 19px; }
  .overview-column > .overview-card,
  .overview-column > .collection-card { height: 348px; min-height: 348px; }
  .overview-score { padding-top: 15px; padding-bottom: 10px; }
  .overview-line { padding-top: 10px; padding-bottom: 9px; }
  .overview-card > button { margin-top: 12px; }
  .pipeline-list { margin-top: 13px; }
  .pipeline-list li { padding-bottom: 12px; }
  .package-copy h2 { margin-top: 12px; margin-bottom: 6px; }
  .package-tags { margin-top: 10px; }
  .package-progress { margin-top: 12px; }
  .package-actions { margin-top: 14px; }
}
@media (max-width: 1240px) and (min-width: 821px) {
  .library-heading { width: 100%; margin-left: 0; }
  .library-layout { grid-template-columns: 210px minmax(0, 1fr); gap: 18px; }
  .filter-panel { min-height: 0; }
  .overview-column { min-height: 0; }
}
@media (max-width: 820px) {
  .library-heading { width: 100%; margin-left: 0; }
  .filter-panel { min-height: 0; }
  .overview-column { min-height: 0; }
  .spatial-resource-object img { width: 100%; height: 100%; }
}

/* Desktop legibility pass: make the library read as a full product surface. */
@media (min-width: 1061px) {
  .library-page { padding-top: 30px; }
  .library-heading {
    width: calc(100% - 348px);
    margin-left: 348px;
    gap: 40px;
    margin-bottom: 20px;
  }
  .library-heading .page-title { font-size: clamp(40px, 2.8vw, 52px); }
  .library-heading .page-subtitle { font-size: 16px; line-height: 1.68; }
  .library-heading .heading-actions { gap: 14px; }
  .library-page .search-box { width: 100%; height: 60px; padding: 0 18px; border-radius: 18px; gap: 13px; }
  .library-page .search-box > svg { width: 21px; }
  .library-page .search-box input { font-size: 15px; }
  .library-page .search-box kbd { padding: 5px 8px; font-size: 11px; }
  .library-page .view-switch { gap: 5px; padding: 6px; border-radius: 16px; }
  .library-page .view-switch button { width: 44px; height: 44px; border-radius: 12px; }
  .library-page .view-switch button svg { width: 20px; }
  .library-page .library-layout {
    grid-template-columns: minmax(280px, 300px) minmax(0, 1fr) minmax(280px, 300px);
    gap: 28px;
  }
  .library-page .filter-panel { min-height: 850px; height: auto; margin-top: -128px; padding: 29px; border-radius: 30px; }
  .library-page .filter-title > div > span,
  .library-page .overview-title > div > span,
  .library-page .resource-heading > div > span { margin-bottom: 6px; font-size: 11px; }
  .library-page .filter-title h2,
  .library-page .overview-title h2,
  .library-page .resource-heading h2 { font-size: 21px; }
  .library-page .filter-title button { padding: 8px 10px; border-radius: 11px; font-size: 12px; }
  .library-page .filter-title button svg { width: 14px; }
  .library-page .filter-group { padding-top: 28px; }
  .library-page .filter-group + .filter-group { margin-top: 22px; }
  .library-page .filter-group h3 { gap: 9px; margin-bottom: 17px; font-size: 16px; }
  .library-page .filter-group h3 svg { width: 18px; }
  .library-page .filter-group label { gap: 10px; margin: 14px 0; font-size: 13px; }
  .library-page .filter-group small { font-size: 11px; }
  .library-page .topic-preview { gap: 8px; }
  .library-page .topic-preview span { padding: 7px 9px; border-radius: 9px; font-size: 11px; }
  .library-page .audit-note { gap: 10px; padding: 14px; border-radius: 14px; font-size: 12px; }
  .library-page .library-tools { margin: 4px 0 20px; }
  .library-page .library-tools > span { font-size: 14px; }
  .library-page .type-tabs { gap: 9px; }
  .library-page .type-tabs button { padding: 9px 18px; font-size: 13px; }
  .library-page .learning-package {
    min-height: 365px;
    padding: 36px 38px 34px;
    grid-template-columns: minmax(0, 52fr) minmax(340px, 48fr);
    gap: 20px;
    border-radius: 28px;
  }
  .library-page .package-copy h2 { margin-top: 17px; margin-bottom: 11px; font-size: clamp(30px, 2.05vw, 38px); }
  .library-page .package-copy p { font-size: 14px; line-height: 1.72; }
  .library-page .package-tags { gap: 8px; margin-top: 16px; }
  .library-page .package-tags span { padding: 6px 10px; border-radius: 9px; font-size: 11px; }
  .library-page .package-tags svg { width: 13px; }
  .library-page .package-progress { max-width: 360px; margin-top: 20px; }
  .library-page .package-progress > div:first-child { font-size: 12px; }
  .library-page .progress-track { height: 7px; margin-top: 9px; }
  .library-page .package-actions { gap: 16px; margin-top: 22px; }
  .library-page .package-actions button { padding: 13px 20px; border-radius: 14px; font-size: 14px; }
  .library-page .package-actions button svg { width: 17px; }
  .library-page .package-actions > span { font-size: 12px; }
  .library-page .spatial-resource-object { min-height: 304px; }
  .library-page .spatial-resource-object img { width: 118%; height: 118%; }
  .library-page .pack-halo { width: min(390px, 92%); height: 210px; }
  .library-page .orbit-one { width: min(430px, 104%); height: 160px; }
  .library-page .orbit-two { width: min(320px, 82%); height: 108px; }
  .library-page .floating-chip { padding: 8px 11px; gap: 6px; font-size: 11px; }
  .library-page .floating-chip svg { width: 14px; }
  .library-page .resource-section { margin-top: 28px; }
  .library-page .resource-heading { margin-bottom: 15px; }
  .library-page .resource-heading em { font-size: 12px; }
  .library-page .resource-grid { gap: 16px; }
  .library-page .resource-card { min-height: 224px; padding: 19px; border-radius: 20px; }
  .library-page .resource-card-top { gap: 9px; }
  .library-page .resource-icon { width: 46px; height: 46px; border-radius: 14px; }
  .library-page .resource-icon svg { width: 21px; }
  .library-page .resource-type { font-size: 11px; }
  .library-page .bookmark { width: 34px; height: 34px; }
  .library-page .bookmark svg { width: 17px; }
  .library-page .resource-card-copy h3 { margin: 16px 0 7px; font-size: 16px; line-height: 1.42; }
  .library-page .resource-card-copy p { display: block; font-size: 12px; line-height: 1.62; }
  .library-page .resource-meta { gap: 6px; padding-top: 13px; }
  .library-page .resource-meta span { padding: 5px 7px; border-radius: 8px; font-size: 10px; }
  .library-page .resource-meta svg { width: 11px; }
  .library-page .resource-footer { gap: 12px; margin-top: 12px; }
  .library-page .mini-progress { height: 6px; }
  .library-page .resource-footer button { gap: 5px; font-size: 11px; }
  .library-page .resource-footer button svg { width: 13px; }
  .library-page .overview-column { gap: 18px; min-height: 850px; }
  .library-page .overview-column > .overview-card,
  .library-page .overview-column > .collection-card { height: auto; min-height: 400px; padding: 28px; border-radius: 30px; }
  .library-page .overview-title em { padding: 6px 9px; font-size: 10px; }
  .library-page .overview-score { gap: 9px; padding: 28px 0 20px; }
  .library-page .overview-score strong { font-size: 48px; }
  .library-page .overview-score span { font-size: 12px; }
  .library-page .overview-line { padding: 18px 0 16px; }
  .library-page .overview-line span { font-size: 12px; }
  .library-page .overview-line b { top: 18px; font-size: 15px; }
  .library-page .overview-line i { height: 6px; margin-top: 9px; }
  .library-page .overview-card > button { margin-top: 20px; padding: 12px; border-radius: 13px; font-size: 12px; }
  .library-page .overview-card > button svg { width: 15px; }
  .library-page .pipeline-list { margin-top: 24px; }
  .library-page .pipeline-list li { grid-template-columns: 34px minmax(0,1fr); gap: 11px; padding-bottom: 20px; }
  .library-page .pipeline-list li:not(:last-child)::after { left: 16px; top: 34px; height: calc(100% - 25px); }
  .library-page .pipeline-list li > span { width: 34px; height: 34px; border-radius: 10px; }
  .library-page .pipeline-list li > span svg { width: 16px; }
  .library-page .pipeline-list b { font-size: 13px; }
  .library-page .pipeline-list small { margin-top: 4px; font-size: 11px; }
}

/* The path is a first-class learning outcome, not a hidden resource card. */
.library-result-count { display: block; width: 100%; text-align: right; }
.library-path { margin-top: 16px; padding: 17px 19px; border: 1px solid rgba(255,255,255,.8); border-radius: 18px; background: linear-gradient(145deg, rgba(255,255,255,.54), rgba(231,252,239,.3)); box-shadow: inset 0 1px 1px rgba(255,255,255,.94); }
.library-path-heading { display: flex; align-items: center; justify-content: space-between; gap: 15px; }
.library-path-heading span { display: block; color: var(--green-deep); font-size: 9px; font-weight: 800; letter-spacing: .04em; }
.library-path-heading h2 { margin: 3px 0 0; font-size: 15px; }
.library-path-heading em { padding: 5px 8px; border-radius: 999px; background: rgba(222,250,222,.78); color: var(--green-deep); font-size: 9px; font-style: normal; font-weight: 700; }
.library-path ol { position: relative; display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 10px; margin: 14px 0 0; padding: 0; list-style: none; }
.library-path ol::before { content: ''; position: absolute; left: 13%; right: 13%; top: 16px; height: 1px; border-top: 1px dashed rgba(34,181,107,.36); }
.library-path li { position: relative; z-index: 1; text-align: center; }
.library-path li > span { display: grid; place-items: center; width: 32px; height: 32px; margin: 0 auto; border: 1px solid rgba(34,181,107,.2); border-radius: 50%; background: rgba(250,255,252,.9); color: var(--green-deep); box-shadow: 0 6px 14px rgba(23,107,62,.07); font-size: 9px; font-weight: 800; }
.library-path li.current > span { border-color: transparent; background: var(--gradient-primary); color: #fff; box-shadow: 0 0 0 5px rgba(222,250,222,.56), 0 9px 19px rgba(15,164,91,.18); }
.library-path li.completed > span { color: var(--green-deep); background: rgba(222,250,222,.9); }
.library-path li > div { min-height: 48px; margin-top: 9px; padding: 7px 6px; border-radius: 10px; background: rgba(255,255,255,.34); }
.library-path b,.library-path small { display: block; }
.library-path b { font-size: 10px; }
.library-path small { margin-top: 4px; color: var(--ink-soft); font-size: 8px; line-height: 1.4; }
.resource-document { display: grid; gap: 13px; }
.document-section { padding: 14px 15px; border: 1px solid rgba(231,247,237,.95); border-radius: 14px; background: linear-gradient(145deg, rgba(255,255,255,.66), rgba(241,255,246,.4)); }
.document-section > span { color: var(--green-deep); font-size: 9px; font-weight: 800; letter-spacing: .04em; }
.document-section h3 { margin: 4px 0 7px; color: var(--ink); font-size: 14px; }
.document-section p { margin: 0; color: var(--ink-soft); font-size: 12px; line-height: 1.75; }
.document-section p + p { margin-top: 8px; }
.document-section ol { margin: 0; padding-left: 18px; color: var(--ink-soft); font-size: 12px; line-height: 1.8; }
.document-summary { border-color: rgba(191,239,207,.72); }
.document-checkpoint { background: linear-gradient(135deg, rgba(222,250,222,.72), rgba(255,255,255,.63)); }
.dialog-actions { display: flex; justify-content: flex-end; gap: 9px; margin-top: 16px; }
.dialog-actions button { min-height: 38px; padding: 0 13px; border: 1px solid var(--line); border-radius: 11px; background: rgba(255,255,255,.62); color: var(--ink-soft); cursor: pointer; font-size: 11px; font-weight: 700; }
.dialog-actions .primary-gradient-button { display: inline-flex; align-items: center; gap: 6px; border: 0; color: #fff; }
.dialog-actions .primary-gradient-button svg { width: 14px; }
@media (max-width: 820px) { .library-path ol { grid-template-columns: 1fr; gap: 8px; } .library-path ol::before { display: none; } .library-path li { display: grid; grid-template-columns: 32px 1fr; gap: 9px; text-align: left; align-items: center; } .library-path li > div { min-height: auto; margin: 0; } .dialog-actions { justify-content: stretch; flex-direction: column; } }

/* Stable heading grid: prevent the title from collapsing into a vertical strip
   when a wide search box and view switch share the same desktop row. */
@media (min-width: 1241px) {
  .library-page .library-heading {
    width: calc(100% - 328px);
    margin-left: 328px;
    display: grid;
    grid-template-columns: minmax(320px, 410px) minmax(460px, 1fr);
    align-items: center;
    gap: 30px;
  }
  .library-page .heading-copy { min-width: 320px; max-width: none; }
  .library-page .heading-copy .page-title { white-space: nowrap; word-break: keep-all; }
  .library-page .heading-actions { min-width: 0; margin-top: 0; }
  .library-page .search-box { min-width: 0; }
  .library-page .library-content,
  .library-page .overview-column { min-width: 0; }
}
@media (max-width: 1240px) and (min-width: 821px) {
  .library-page .library-heading {
    width: 100%;
    margin-left: 0;
    grid-template-columns: minmax(260px, .72fr) minmax(380px, 1.28fr);
    gap: 24px;
  }
  .library-page .heading-copy .page-title { white-space: nowrap; word-break: keep-all; }
}

/* Mid-size desktop: retain three columns without starving the learning stage. */
@media (min-width: 1061px) and (max-width: 1450px) {
  .library-page .library-heading {
    width: calc(100% - 228px);
    margin-left: 228px;
    grid-template-columns: minmax(300px, 390px) minmax(0, 1fr);
    gap: 22px;
  }
  .library-page .library-layout {
    grid-template-columns: 210px minmax(0, 1fr) 220px;
    gap: 18px;
  }
  .library-page .filter-panel {
    min-height: 760px;
    margin-top: -110px;
    padding: 21px 19px;
    border-radius: 24px;
  }
  .library-page .filter-group { padding-top: 22px; }
  .library-page .filter-group + .filter-group { margin-top: 16px; }
  .library-page .filter-group label { margin: 11px 0; }
  .library-page .learning-package {
    min-height: 330px;
    grid-template-columns: minmax(300px, 1.08fr) minmax(250px, .92fr);
    gap: 14px;
    padding: 27px 25px;
  }
  .library-page .package-copy h2 {
    font-size: clamp(27px, 2.25vw, 34px);
    line-height: 1.16;
    word-break: keep-all;
  }
  .library-page .spatial-resource-object { min-height: 270px; }
  .library-page .overview-column { gap: 15px; min-height: 760px; }
  .library-page .overview-column > .overview-card,
  .library-page .overview-column > .collection-card {
    min-height: 360px;
    padding: 22px 19px;
    border-radius: 24px;
  }
}
</style>
