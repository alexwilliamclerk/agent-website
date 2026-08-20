<template>
  <div class="home-page">
    <section class="hero content-width">
      <div class="hero-copy motion-enter">
        <span class="glass-pill hero-pill"><span class="live-dot"></span>AI Agent 赋能 · 精准评估 · 智能成长</span>
        <h1>
          <span class="headline-line">用 AI 看见能力差距，</span>
          <span class="headline-line">生成属于你的<span class="gradient-title">成长路径</span></span>
        </h1>
        <p>职学导航通过多 Agent 协同评估知识、技能与项目经历，对照岗位能力模型形成证据链，生成可追溯的诊断结果与下一步行动路径。</p>
        <div class="hero-actions">
          <button class="hero-primary primary-gradient-button" type="button" @click="startAssessment()">开始测评 <ArrowRight /></button>
        </div>
      </div>

      <div class="spatial-hub motion-enter motion-delay-2" aria-label="AI 多智能体能力分析中枢示意" @pointermove="moveSpotlight" @pointerleave="resetSpotlight">
        <img class="hub-visual hub-visual-back" src="/assets/spatial-agent-core.png" alt="绿色玻璃质感的 AI Agent 空间分析核心" />
        <article class="float-card score-card depth-front">
          <div class="card-kicker"><DataAnalysis /> 能力评分</div>
          <div class="score-row"><strong>86</strong><span>/100</span></div>
          <small>超过 82% 同岗位学习者</small>
        </article>
        <article class="float-card radar-card depth-back">
          <div class="card-kicker"><Aim /> 能力雷达图</div>
          <div ref="heroRadarRef" class="hero-radar" aria-label="工程能力、项目经验、学习潜力、基础能力和软实力示例雷达图"></div>
        </article>
        <article class="float-card agent-card depth-middle">
          <span class="agent-icon"><Service /></span>
          <div><b>AI Agent</b><p>工程实践表现较好，下一阶段建议加强系统设计能力。</p></div>
        </article>
        <article class="float-card path-card depth-front">
          <div class="card-kicker"><Guide /> 个性化学习路径</div>
          <div class="path-line"><span>基础补强</span><i><b style="width:60%"></b></i><em>60%</em></div>
          <div class="path-line"><span>项目进阶</span><i><b style="width:25%"></b></i><em>25%</em></div>
          <div class="path-line muted"><span>综合实战</span><i></i><em>待开始</em></div>
        </article>
        <img class="hub-visual hub-visual-front" src="/assets/spatial-agent-core.png" alt="" aria-hidden="true" />
      </div>
    </section>

    <section class="workflow content-width motion-enter motion-delay-1" aria-label="产品使用流程">
      <template v-for="(step, index) in workflow" :key="step.title">
        <div class="workflow-step">
          <span class="workflow-index">0{{ index + 1 }}</span>
          <span class="workflow-icon"><component :is="step.icon" /></span>
          <span><b>{{ step.title }}</b><small>{{ step.detail }}</small></span>
        </div>
        <span v-if="index < workflow.length - 1" class="workflow-arrow"><ArrowRight /></span>
      </template>
    </section>

    <section id="roles" class="role-section content-width">
      <div class="section-heading">
        <div><span class="eyebrow">目标岗位能力模型</span><h2>从一个岗位做深，到多个方向扩展</h2></div>
        <p>每个方向都由岗位要求、能力证据标准和领域知识库共同支撑，诊断与推荐结果保留可追溯依据。</p>
      </div>

      <div v-if="jobsLoading" class="role-grid"><div v-for="i in 4" :key="i" class="role-tile skeleton"></div></div>
      <div v-else-if="jobsError" class="role-state glass-surface"><b>岗位能力模型暂时无法加载</b><button type="button" @click="loadJobs">重新加载</button></div>
      <div v-else class="role-grid">
        <button v-for="(job, index) in jobs" :key="job.id" class="role-tile glass-surface" :class="`role-${index + 1}`" type="button" @click="startAssessment(job.id)">
          <span class="role-object"><component :is="roleMeta[index % roleMeta.length].icon" /></span>
          <div class="role-copy"><h3>{{ job.job_title }}</h3><p>{{ roleMeta[index % roleMeta.length].summary }}</p></div>
          <span class="role-more">了解更多 <ArrowRight /></span>
        </button>
      </div>
    </section>

    <section class="proof-section content-width">
      <article v-for="item in proofPoints" :key="item.title" class="proof-point">
        <span class="proof-icon"><component :is="item.icon" /></span>
        <div><h3>{{ item.title }}</h3><p>{{ item.detail }}</p></div>
      </article>
    </section>

    <footer class="app-footer home-footer">
      <span class="footer-brand"><span class="footer-mark"><Connection /></span><b>职学导航</b><em>AI 驱动的学习与成长评估平台</em></span>
      <span class="footer-links"><router-link to="/input">资料审查</router-link><router-link to="/diagnosis">能力诊断</router-link><router-link to="/library">资料库</router-link></span>
      <span>© 2026 职学导航</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import type { Component } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import {
  Aim, ArrowRight, Box, Briefcase, CircleCheck, Cloudy, Connection,
  DataAnalysis, DocumentChecked, Files, Guide, MagicStick, Monitor, Service, UserFilled,
} from '@element-plus/icons-vue'
import { getJobList, type JobInfo } from '@/api/jobs'
import { previewJobs } from '@/fixtures/previewJobs'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const store = useUserStore()
const publicPreview = import.meta.env.DEV && import.meta.env.VITE_PUBLIC_PREVIEW === 'true'
const jobs = ref<JobInfo[]>([])
const jobsLoading = ref(true)
const jobsError = ref(false)
const heroRadarRef = ref<HTMLDivElement | null>(null)
let heroRadar: echarts.ECharts | null = null

const workflow: Array<{ icon: Component; title: string; detail: string }> = [
  { icon: Briefcase, title: '岗位选择', detail: '选择目标职业方向' },
  { icon: DocumentChecked, title: '资料审查', detail: 'AI 审查学习与项目资料' },
  { icon: DataAnalysis, title: '能力诊断', detail: '多维度能力精准评估' },
  { icon: MagicStick, title: '个性化学习建议', detail: '生成专属成长路径' },
]
const roleMeta: Array<{ icon: Component; summary: string }> = [
  { icon: Monitor, summary: '构建高性能、体验稳定的 Web 产品与交互。' },
  { icon: Box, summary: '设计稳定可扩展的服务与高质量业务系统。' },
  { icon: Cloudy, summary: '保障系统高可用、安全与自动化运维。' },
  { icon: UserFilled, summary: '洞察需求，定义产品价值并推动落地。' },
]
const proofPoints: Array<{ icon: Component; title: string; detail: string }> = [
  { icon: Connection, title: '多 Agent 协同', detail: '多角色 Agent 分工分析，过程可见、决策可解释。' },
  { icon: Files, title: '证据驱动', detail: '结论绑定学习资料与项目证据，可追溯、可复核。' },
  { icon: CircleCheck, title: '审核纠偏', detail: '生成内容经过来源校验与交叉审核，降低幻觉风险。' },
  { icon: Guide, title: '路径生成', detail: '结合岗位要求与个人差距，生成可执行学习路径。' },
]

async function loadJobs() {
  jobsLoading.value = true
  jobsError.value = false
  if (publicPreview) {
    jobs.value = previewJobs
    jobsLoading.value = false
    return
  }
  try { jobs.value = await getJobList() } catch { jobsError.value = true } finally { jobsLoading.value = false }
}
function startAssessment(jobId?: string) {
  if (!store.isLoggedIn && !publicPreview) {
    router.push({ path: '/login', query: { next: jobId ? `/input?job=${jobId}` : '/input' } })
    return
  }
  router.push({ path: '/input', query: publicPreview ? { ...(jobId ? { job: jobId } : {}), demo: '1' } : (jobId ? { job: jobId } : undefined) })
}
function moveSpotlight(event: PointerEvent) {
  const element = event.currentTarget as HTMLElement
  const rect = element.getBoundingClientRect()
  element.style.setProperty('--spot-x', `${event.clientX - rect.left}px`)
  element.style.setProperty('--spot-y', `${event.clientY - rect.top}px`)
  element.style.setProperty('--hub-shift-x', `${((event.clientX - rect.left) / rect.width - .5) * 8}px`)
  element.style.setProperty('--hub-shift-y', `${((event.clientY - rect.top) / rect.height - .5) * 6}px`)
}
function resetSpotlight(event: PointerEvent) {
  const element = event.currentTarget as HTMLElement
  element.style.setProperty('--spot-x', '50%')
  element.style.setProperty('--spot-y', '50%')
  element.style.setProperty('--hub-shift-x', '0px')
  element.style.setProperty('--hub-shift-y', '0px')
}
function renderHeroRadar() {
  if (!heroRadarRef.value) return
  heroRadar?.dispose()
  heroRadar = echarts.init(heroRadarRef.value)
  heroRadar.setOption({
    animationDuration: 700,
    radar: {
      center: ['50%', '53%'], radius: '62%', splitNumber: 4,
      indicator: ['工程能力', '项目经验', '学习潜力', '基础能力', '软实力'].map(name => ({ name, max: 100 })),
      axisName: { color: '#617168', fontSize: 8 },
      splitArea: { areaStyle: { color: ['rgba(222,250,222,.06)', 'rgba(222,250,222,.2)'] } },
      splitLine: { lineStyle: { color: 'rgba(7,148,85,.17)' } },
      axisLine: { lineStyle: { color: 'rgba(7,148,85,.17)' } },
    },
    series: [{ type: 'radar', symbol: 'circle', symbolSize: 3, lineStyle: { color: '#079455', width: 1.5 }, itemStyle: { color: '#079455' }, areaStyle: { color: 'rgba(34,181,107,.31)' }, data: [{ value: [86, 76, 90, 82, 78] }] }],
  })
}
function handleResize() { heroRadar?.resize() }
onMounted(async () => { await loadJobs(); await nextTick(); renderHeroRadar(); window.addEventListener('resize', handleResize) })
onBeforeUnmount(() => { heroRadar?.dispose(); window.removeEventListener('resize', handleResize) })
</script>

<style scoped>
.home-page {
  position: relative;
  overflow: hidden;
  min-height: calc(100vh - 78px);
  padding: 6px 24px 8px;
  isolation: isolate;
  background:
    radial-gradient(ellipse at 75% 26%, rgba(222,250,222,.52), rgba(245,255,248,.18) 31%, transparent 61%),
    radial-gradient(ellipse at 64% 98%, rgba(158,239,194,.16), transparent 43%),
    linear-gradient(180deg, #fff 0%, #fbfefc 58%, #f8fcfa 100%);
}
.home-page .content-width { width: min(1360px, 100%); }
.hero {
  height: 408px;
  display: grid;
  grid-template-columns: minmax(0, 40fr) minmax(0, 60fr);
  align-items: center;
  gap: 0;
  position: relative;
}
.hero-copy { position: relative; z-index: 9; padding-left: clamp(0px, 1.6vw, 26px); transform: translateY(-2px); }
.hero-pill { margin-bottom: 20px; }
.live-dot { height: 7px; width: 7px; border-radius: 50%; background: var(--gradient-primary); box-shadow: 0 0 10px rgba(34,181,107,.42); animation: breathe 2.5s ease-in-out infinite; }
.hero h1 { margin: 0; color: var(--ink); font-size: clamp(50px, 3.4vw, 62px); line-height: 1.11; font-weight: 850; letter-spacing: 0; }
.headline-line { display: block; white-space: nowrap; }
.gradient-title { color: transparent; background: var(--gradient-number); background-clip: text; -webkit-background-clip: text; }
.hero-copy > p { max-width: 560px; margin: 23px 0 25px; color: var(--ink-soft); line-height: 1.72; font-size: 14px; }
.hero-actions { display: flex; gap: 12px; flex-wrap: wrap; }
.hero-primary, .hero-secondary { min-height: 48px; padding: 0 22px; border-radius: 15px; display: inline-flex; align-items: center; gap: 11px; font-size: 14px; font-weight: 750; cursor: pointer; }
.hero-primary svg, .hero-secondary svg { width: 17px; }
.hero-secondary { color: var(--ink); background: rgba(255,255,255,.57); border: 1px solid rgba(20,86,53,.1); box-shadow: inset 0 1px 0 rgba(255,255,255,.94), 0 9px 23px rgba(33,82,58,.055); backdrop-filter: blur(17px); transition: transform .2s ease, box-shadow .2s ease; }
.hero-secondary:hover { transform: translateY(-2px); box-shadow: inset 0 1px 0 #fff, 0 14px 26px rgba(33,82,58,.1); }
.hero-secondary svg { color: var(--green-deep); }

.spatial-hub {
  --spot-x: 50%;
  --spot-y: 50%;
  --hub-shift-x: 0px;
  --hub-shift-y: 0px;
  width: calc(100% + 28px);
  height: 418px;
  margin: -9px 0 -1px -40px;
  position: relative;
  justify-self: start;
  z-index: 2;
  isolation: isolate;
  overflow: visible;
  perspective: 1180px;
  transform-style: preserve-3d;
}
.spatial-hub::before {
  content: '';
  position: absolute;
  inset: 2% 0 0 3%;
  z-index: 2;
  pointer-events: none;
  background: radial-gradient(300px circle at var(--spot-x) var(--spot-y), rgba(255,255,255,.4), transparent 69%);
  opacity: .74;
}
.hub-visual {
  position: absolute;
  left: -25%;
  top: -12%;
  width: 125%;
  height: 124%;
  object-fit: cover;
  object-position: center;
  mix-blend-mode: multiply;
  pointer-events: none;
  transform: translate3d(var(--hub-shift-x), var(--hub-shift-y), 0) perspective(1100px) rotateX(2deg) rotateZ(-.42deg);
  transform-origin: 56% 57%;
  transition: transform .38s cubic-bezier(.2,.8,.2,1);
}
.hub-visual-back { z-index: 0; filter: saturate(.96) contrast(.99); mask-image: linear-gradient(90deg, transparent 0%, rgba(0,0,0,.44) 11%, #000 27%, #000 100%); }
.hub-visual-front { z-index: 4; opacity: .34; filter: saturate(1.06) contrast(1.02); -webkit-mask-image: linear-gradient(180deg, transparent 0 58%, rgba(0,0,0,.76) 74%, #000 100%), linear-gradient(90deg, transparent 0%, #000 24%, #000 100%); -webkit-mask-composite: source-in; mask-image: linear-gradient(180deg, transparent 0 58%, rgba(0,0,0,.76) 74%, #000 100%); }
.float-card {
  --tilt-x: 0deg;
  --tilt-y: 0deg;
  --tilt-z: 0deg;
  --depth-z: 0px;
  --depth-scale: 1;
  position: absolute;
  z-index: 5;
  box-sizing: border-box;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,.82);
  border-radius: 19px;
  background:
    linear-gradient(142deg, rgba(255,255,255,.64), rgba(247,255,250,.27) 50%, rgba(189,244,207,.16)),
    rgba(249,255,251,.34);
  box-shadow:
    0 29px 64px rgba(16,80,45,.11),
    0 8px 22px rgba(36,133,77,.055),
    8px 13px 38px rgba(96,228,151,.055),
    inset 0 1px 1px rgba(255,255,255,.99),
    inset -1px -1px 1px rgba(49,174,100,.055);
  backdrop-filter: blur(30px) saturate(168%);
  -webkit-backdrop-filter: blur(30px) saturate(168%);
  color: var(--ink);
  transform: rotateX(var(--tilt-x)) rotateY(var(--tilt-y)) rotateZ(var(--tilt-z)) translate3d(0,0,var(--depth-z)) scale(var(--depth-scale));
  transform-style: preserve-3d;
  will-change: transform;
}
.float-card::before { content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none; background: linear-gradient(118deg, rgba(255,255,255,.74), transparent 25%, rgba(132,235,174,.08) 62%, rgba(255,255,255,.24)); opacity: .86; }
.float-card::after { content: ''; position: absolute; inset: 1px; border-radius: inherit; pointer-events: none; background: linear-gradient(180deg, rgba(255,255,255,.24), transparent 37%), radial-gradient(circle at 78% 110%, rgba(111,231,160,.13), transparent 45%); }
.float-card > * { position: relative; z-index: 1; }
.depth-front { --depth-scale: 1; opacity: .98; }
.depth-middle { --depth-scale: .96; opacity: .93; }
.depth-back { --depth-scale: .93; opacity: .88; filter: saturate(.95); }
.card-kicker { display: flex; align-items: center; gap: 6px; color: var(--ink-soft); font-size: 10px; font-weight: 700; }
.card-kicker svg { width: 14px; height: 14px; color: var(--green-deep); }
.score-card { --tilt-x: 2deg; --tilt-y: 6deg; --tilt-z: -1.1deg; --depth-z: 26px; left: 19%; top: 3%; width: 144px; height: 160px; padding: 16px 15px; z-index: 3; animation: spatial-float 5.7s .2s ease-in-out infinite; }
.score-row { display: flex; align-items: end; gap: 3px; margin-top: 12px; }
.score-row strong { font-size: 39px; line-height: 1; color: transparent; background: var(--gradient-number); background-clip: text; -webkit-background-clip: text; }
.score-row span { margin-bottom: 4px; color: var(--ink-faint); font-size: 11px; }
.score-card small { display: block; margin-top: 12px; color: var(--green-deep); font-size: 9px; line-height: 1.55; }
.radar-card { --tilt-x: 2.3deg; --tilt-y: -6deg; --tilt-z: .9deg; --depth-z: -10px; right: 4%; top: 2%; width: 190px; height: 174px; padding: 13px 14px; transform-origin: right top; animation: spatial-float 6.2s ease-in-out infinite; }
.hero-radar { height: 139px; width: 100%; }
.agent-card { --tilt-x: -1.6deg; --tilt-y: 7deg; --tilt-z: -.7deg; --depth-z: 7px; left: 11%; bottom: 11%; width: 208px; height: 116px; padding: 15px; display: flex; gap: 12px; align-items: flex-start; z-index: 3; transform-origin: left center; animation: spatial-float 5.2s .5s ease-in-out infinite; }
.agent-icon { width: 40px; height: 40px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 50%; color: #fff; background: var(--gradient-primary); box-shadow: inset 0 1px 1px rgba(255,255,255,.63), 0 9px 19px rgba(15,164,91,.2); animation: agent-bob 3.4s ease-in-out infinite; }
.agent-icon svg { width: 22px; }
.agent-card b { font-size: 12px; }
.agent-card p { margin: 6px 0 0; color: var(--ink-soft); font-size: 10px; line-height: 1.5; }
.path-card { --tilt-x: -2deg; --tilt-y: -6deg; --tilt-z: .65deg; --depth-z: 22px; right: 2%; bottom: 7%; width: 238px; height: 137px; padding: 15px 16px; animation: spatial-float 6s .7s ease-in-out infinite; }
.path-line { margin-top: 9px; display: grid; grid-template-columns: 57px 1fr auto; align-items: center; gap: 7px; font-size: 8px; color: var(--ink-soft); }
.path-line i { height: 5px; overflow: hidden; border-radius: 99px; background: rgba(44,126,80,.1); }
.path-line i b { display: block; height: 100%; border-radius: inherit; background: var(--gradient-progress); }
.path-line em { min-width: 31px; color: var(--green-deep); font-style: normal; text-align: right; }
.path-line.muted { opacity: .55; }
@keyframes spatial-float {
  0%,100% { transform: rotateX(var(--tilt-x)) rotateY(var(--tilt-y)) rotateZ(var(--tilt-z)) translate3d(0,0,var(--depth-z)) scale(var(--depth-scale)); }
  50% { transform: rotateX(var(--tilt-x)) rotateY(var(--tilt-y)) rotateZ(var(--tilt-z)) translate3d(0,-6px,var(--depth-z)) scale(var(--depth-scale)); }
}
@keyframes agent-bob { 0%,100% { transform: translateY(0) rotate(-2deg); } 50% { transform: translateY(-3px) rotate(2deg); } }

.workflow {
  position: relative;
  z-index: 10;
  min-height: 76px;
  margin-top: -8px;
  padding: 10px 22px;
  display: grid;
  grid-template-columns: 1fr auto 1fr auto 1fr auto 1fr;
  align-items: center;
  gap: 12px;
  border: 1px solid rgba(255,255,255,.88);
  border-radius: 20px;
  background: linear-gradient(110deg, rgba(255,255,255,.64), rgba(239,255,245,.36));
  box-shadow: 0 18px 42px rgba(25,87,55,.07), inset 0 1px 1px #fff;
  backdrop-filter: blur(23px) saturate(145%);
}
.workflow-step { min-width: 0; display: grid; grid-template-columns: auto auto 1fr; align-items: center; gap: 10px; }
.workflow-index { color: var(--green-deep); font-size: 15px; }
.workflow-icon { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 12px; color: var(--green-deep); background: rgba(222,250,222,.66); box-shadow: inset 0 1px 0 #fff, 0 8px 19px rgba(35,142,81,.06); }
.workflow-icon svg { width: 18px; }
.workflow-step b, .workflow-step small { display: block; }
.workflow-step b { font-size: 12px; }
.workflow-step small { margin-top: 2px; color: var(--ink-soft); font-size: 9px; white-space: nowrap; }
.workflow-arrow { width: 22px; color: rgba(7,148,85,.48); }
.workflow-arrow svg { width: 18px; }

.role-section { padding-top: 12px; }
.section-heading { min-height: 40px; display: flex; align-items: end; justify-content: space-between; gap: 26px; margin-bottom: 9px; }
.section-heading h2 { margin: 4px 0 0; font-size: 25px; line-height: 1.18; }
.section-heading p { max-width: 490px; margin: 0 0 1px; color: var(--ink-soft); font-size: 10px; line-height: 1.55; text-align: right; }
.role-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.role-tile {
  height: 146px;
  padding: 17px 18px;
  position: relative;
  overflow: hidden;
  border-radius: 19px;
  color: var(--ink);
  text-align: left;
  cursor: pointer;
  transition: transform .28s ease, box-shadow .28s ease, border-color .28s ease;
}
.role-tile:hover { transform: translateY(-4px); border-color: rgba(189,244,207,.82); box-shadow: var(--surface-shadow-raised), inset 0 1px 1px #fff; }
.role-object { position: absolute; right: 14px; bottom: 13px; width: 72px; height: 72px; display: grid; place-items: center; border-radius: 21px; color: #fff; background: linear-gradient(145deg, rgba(169,245,198,.88), rgba(34,181,107,.88) 58%, rgba(7,148,85,.96)); border: 1px solid rgba(255,255,255,.72); box-shadow: inset 0 1px 1px rgba(255,255,255,.66), 0 16px 30px rgba(15,164,91,.17), -8px -8px 22px rgba(222,250,222,.34); transform: perspective(300px) rotateX(5deg) rotateY(-9deg); transition: transform .28s ease; }
.role-object::after { content: ''; position: absolute; inset: 8px; border-radius: 15px; border: 1px solid rgba(255,255,255,.34); pointer-events: none; }
.role-object svg { width: 31px; height: 31px; }
.role-tile:hover .role-object { transform: perspective(300px) translateY(-3px) rotateX(3deg) rotateY(-5deg); }
.role-2 .role-object { border-radius: 17px; transform: perspective(300px) rotateX(5deg) rotateY(8deg) rotateZ(2deg); }
.role-3 .role-object { border-radius: 24px 24px 17px 17px; transform: perspective(300px) rotateX(7deg) rotateY(-7deg); }
.role-4 .role-object { border-radius: 50%; transform: perspective(300px) rotateX(4deg) rotateY(8deg); }
.role-copy { max-width: 66%; }
.role-copy h3 { margin: 0; font-size: 16px; }
.role-copy p { margin: 8px 0 0; color: var(--ink-soft); font-size: 10px; line-height: 1.55; }
.role-more { position: absolute; left: 18px; bottom: 15px; display: inline-flex; align-items: center; gap: 7px; color: var(--green-deep); font-size: 10px; font-weight: 700; }
.role-more svg { width: 13px; }
.role-state { padding: 24px; border-radius: var(--radius-lg); display: flex; gap: 16px; align-items: center; justify-content: space-between; }
.role-state button { border: 0; border-radius: 10px; padding: 9px 13px; background: var(--gradient-primary); color: #fff; cursor: pointer; }
.skeleton { background: linear-gradient(100deg, #f2faf5 30%, #fcfffd 47%, #f2faf5 63%); background-size: 200% 100%; animation: loading 1.4s infinite; }
@keyframes loading { to { background-position: -200% 0; } }
.proof-section { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; margin-top: 10px; padding: 10px 7px; border-radius: 18px; background: linear-gradient(110deg, rgba(255,255,255,.57), rgba(239,255,245,.3)); border: 1px solid rgba(255,255,255,.86); box-shadow: 0 15px 36px rgba(25,87,55,.055), inset 0 1px 1px #fff; backdrop-filter: blur(23px) saturate(145%); }
.proof-point { min-height: 58px; padding: 5px 17px; display: flex; gap: 11px; align-items: center; border-right: 1px solid var(--line); }
.proof-point:last-child { border-right: 0; }
.proof-icon { width: 34px; height: 34px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 50%; color: var(--green-deep); background: rgba(222,250,222,.68); box-shadow: inset 0 1px 0 #fff; }
.proof-icon svg { width: 18px; }
.proof-point h3 { margin: 0 0 4px; font-size: 12px; }
.proof-point p { margin: 0; color: var(--ink-soft); font-size: 9px; line-height: 1.45; }
.home-footer { min-height: 38px; margin-top: 7px; padding: 6px 2px 0; font-size: 10px; }
.footer-brand { display: inline-flex; align-items: center; gap: 8px; }
.footer-brand em { color: var(--ink-faint); font-style: normal; font-weight: 400; }
.footer-mark { width: 26px; height: 26px; display: grid; place-items: center; border-radius: 9px; color: #fff; background: var(--gradient-primary); }
.footer-mark svg { width: 15px; }
.footer-links { display: flex; gap: 26px; }
.footer-links a { color: var(--ink-soft); text-decoration: none; }
.footer-links a:hover { color: var(--green-deep); }

@media (max-width: 1366px) {
  .home-page { padding-top: 3px; }
  .hero { height: 366px; grid-template-columns: minmax(0, 42fr) minmax(0, 58fr); }
  .hero h1 { font-size: 47px; }
  .hero-pill { margin-bottom: 16px; }
  .hero-copy > p { margin-block: 18px 21px; font-size: 12px; }
  .hero-primary, .hero-secondary { min-height: 44px; }
  .spatial-hub { height: 380px; margin-left: -35px; }
  .score-card { left: 17%; top: 2%; transform-origin: left top; }
  .radar-card { right: 3%; top: 1%; transform-origin: right top; }
  .agent-card { left: 8%; bottom: 9%; }
  .path-card { right: 1%; bottom: 5%; }
  .workflow { min-height: 70px; margin-top: -4px; padding-block: 8px; }
  .role-section { padding-top: 8px; }
  .section-heading { min-height: 36px; margin-bottom: 7px; }
  .section-heading h2 { font-size: 22px; }
  .role-tile { height: 136px; }
  .proof-section { margin-top: 8px; padding-block: 7px; }
  .proof-point { min-height: 52px; }
}
@media (max-width: 1160px) {
  .hero { grid-template-columns: 1fr 1fr; gap: 0; }
  .hero h1 { font-size: 43px; }
  .headline-line { white-space: normal; }
  .spatial-hub { width: calc(100% + 8px); margin-left: -18px; }
  .score-card { left: 12%; }
  .agent-card { left: 4%; }
  .radar-card, .path-card { right: 1%; }
  .role-grid, .proof-section { grid-template-columns: repeat(2, 1fr); }
  .proof-point:nth-child(2) { border-right: 0; }
  .proof-point:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
  .role-tile { height: 142px; }
  .footer-links { display: none; }
}
@media (max-width: 760px) {
  .home-page { padding: 10px 14px 20px; }
  .hero { height: auto; grid-template-columns: 1fr; }
  .hero-copy { padding: 0 3px; transform: none; }
  .hero h1 { font-size: clamp(28px, 8.25vw, 32px); }
  .headline-line { white-space: nowrap; }
  .spatial-hub { width: auto; height: 350px; justify-self: stretch; order: -1; margin: -22px -36px 0; overflow: hidden; }
  .hub-visual { left: -34%; width: 142%; }
  .float-card { animation: none; }
  .score-card { left: 12%; top: 5%; transform: scale(.72) rotateZ(-1deg); transform-origin: left top; }
  .radar-card { right: 3%; top: 4%; transform: scale(.65) rotateZ(1deg); transform-origin: right top; }
  .agent-card { left: 8%; bottom: 7%; transform: scale(.72) rotateZ(-.6deg); transform-origin: left bottom; }
  .path-card { right: 1%; bottom: 5%; transform: scale(.67) rotateZ(.6deg); transform-origin: right bottom; }
  .workflow { grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 22px; padding: 13px; }
  .workflow-arrow { display: none; }
  .workflow-step small { white-space: normal; }
  .role-section { padding-top: 30px; }
  .section-heading { display: block; }
  .section-heading p { margin-top: 10px; text-align: left; }
  .role-grid, .proof-section { grid-template-columns: 1fr; }
  .role-tile { height: 148px; }
  .proof-point { border-right: 0; border-bottom: 1px solid var(--line); }
  .proof-point:last-child { border-bottom: 0; }
  .home-footer { align-items: flex-start; }
  .footer-brand em { display: none; }
}

/* Desktop readability: the homepage canvas stays compact, but its product
   controls and supporting labels must remain legible at normal viewing scale. */
@media (min-width: 1061px) {
  .workflow {
    min-height: 88px;
    padding: 14px 28px;
    gap: 16px;
  }
  .workflow-step { gap: 13px; }
  .workflow-index { font-size: 17px; }
  .workflow-icon { width: 44px; height: 44px; border-radius: 14px; }
  .workflow-icon svg { width: 21px; height: 21px; }
  .workflow-step b { font-size: 14px; }
  .workflow-step small { margin-top: 4px; font-size: 11px; }
  .workflow-arrow { width: 26px; }
  .workflow-arrow svg { width: 21px; height: 21px; }

  .role-section { padding-top: 20px; }
  .section-heading { min-height: 52px; margin-bottom: 14px; }
  .section-heading h2 { margin-top: 6px; font-size: 30px; }
  .section-heading p { max-width: 560px; font-size: 12px; line-height: 1.65; }
  .role-grid { gap: 16px; }
  .role-tile { height: 166px; padding: 21px 22px; border-radius: 21px; }
  .role-object { right: 18px; bottom: 16px; width: 82px; height: 82px; border-radius: 24px; }
  .role-object svg { width: 35px; height: 35px; }
  .role-copy { max-width: 69%; }
  .role-copy h3 { font-size: 18px; }
  .role-copy p { margin-top: 10px; font-size: 12px; line-height: 1.65; }
  .role-more { left: 22px; bottom: 18px; gap: 8px; font-size: 12px; }
  .role-more svg { width: 15px; height: 15px; }
  .role-state { padding: 30px; border-radius: 22px; }
  .role-state b { font-size: 16px; }
  .role-state button { padding: 11px 16px; font-size: 13px; }

  .proof-section { min-height: 166px; margin-top: 16px; padding: 14px 10px; border-radius: 21px; }
  .proof-point { min-height: 136px; padding: 16px 22px; gap: 16px; }
  .proof-icon { width: 52px; height: 52px; }
  .proof-icon svg { width: 25px; height: 25px; }
  .proof-point h3 { margin-bottom: 7px; font-size: 16px; }
  .proof-point p { font-size: 12px; line-height: 1.65; }
  .home-footer { min-height: 46px; margin-top: 11px; padding-top: 8px; font-size: 11px; }
  .footer-mark { width: 30px; height: 30px; border-radius: 10px; }
  .footer-mark svg { width: 17px; height: 17px; }
}

/* Keep route links optically centered regardless of the brand/copyright width. */
.home-footer { display: grid; grid-template-columns: minmax(0,1fr) auto minmax(0,1fr); align-items: center; }
.home-footer > :last-child { justify-self: end; }
@media (max-width: 760px) { .home-footer { display: flex; justify-content: space-between; } }
</style>
