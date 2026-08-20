<template>
  <main class="resource-detail-page page-shell">
    <div class="content-width">
      <section class="detail-heading motion-enter">
        <button class="back-link" type="button" @click="$router.back()"><b>←</b> 返回资料库</button>
        <div v-if="resource" class="detail-title-row"><div><span class="eyebrow">AUDITED LEARNING RESOURCE</span><h1>{{ resource.title }}</h1><div class="detail-tags"><span>{{ resource.content_type }}</span><span>{{ resource.knowledge_point }}</span><span v-if="resource.difficulty">难度 {{ resource.difficulty }}/5</span></div></div><div class="source-orb" aria-hidden="true"><i></i><b>AI</b></div></div>
        <div v-else><span class="eyebrow">AUDITED LEARNING RESOURCE</span><h1>学习资料</h1></div>
      </section>

      <section v-if="loading" class="detail-state glass-surface"><i class="loading-ring"></i><b>正在读取学习资料</b><p>正在载入经过来源审核的资源内容。</p></section>
      <section v-else-if="loadError" class="detail-state glass-surface"><span class="state-symbol">!</span><b>{{ loadError }}</b><p>请确认该资料仍属于当前账户，或返回资料库重新选择。</p><button type="button" @click="loadResource">重新加载</button></section>

      <section v-else-if="resource" class="detail-layout motion-enter motion-delay-1">
        <article class="reading-card glass-surface"><div class="reading-status"><span class="source-dot"></span><b>来源审核 {{ reviewText(resource.review_status) }}</b><span>本资料与诊断结果关联展示</span></div><div class="doc-body" v-html="renderedBody"></div></article>
        <aside class="detail-sidebar">
          <section class="detail-meta glass-surface"><span class="card-label">资源信息</span><dl><div><dt>资源类型</dt><dd>{{ resource.content_type }}</dd></div><div><dt>知识主题</dt><dd>{{ resource.knowledge_point }}</dd></div><div><dt>难度等级</dt><dd>{{ resource.difficulty ? `${resource.difficulty} / 5` : '未标注' }}</dd></div><div><dt>审核状态</dt><dd class="reviewed">{{ reviewText(resource.review_status) }}</dd></div></dl></section>
          <section class="learning-state glass-surface">
            <span class="card-label">学习进度</span>
            <b>{{ recordStatusText }}</b>
            <p>{{ learningRecord?.status === 'completed' ? '该资源已纳入你的完成记录。' : '开始后将同步到资料库进度和学习路径。' }}</p>
            <button type="button" :disabled="recordLoading || learningRecord?.status === 'completed'" @click="learningRecord ? completeLearning() : startLearning()">{{ recordLoading ? '正在更新…' : learningRecord?.status === 'completed' ? '已完成' : learningRecord ? '标记完成' : '开始学习' }}</button>
          </section>
          <section class="detail-note glass-surface"><span>✦</span><p>学习完成后可回到能力诊断，录入客观题、实操或专家标注结果，校准本次判断。</p><button type="button" @click="resource.assessment_id ? $router.push(`/diagnosis/${resource.assessment_id}`) : $router.push('/diagnosis')">查看诊断报告 <b>→</b></button></section>
        </aside>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { marked } from 'marked'
import { getResource, type ResourceInfo } from '@/api/resource'
import { completeRecord, getResourceRecord, startResource, type LearningRecordInfo } from '@/api/record'

const route = useRoute()
const resource = ref<ResourceInfo | null>(null); const loading = ref(false); const loadError = ref('')
const learningRecord = ref<LearningRecordInfo | null>(null); const recordLoading = ref(false)
const recordStatusText = computed(() => learningRecord.value?.status === 'completed' ? '学习完成' : learningRecord.value ? '学习进行中' : '尚未开始')
async function loadResource() {
  const id = typeof route.params.id === 'string' ? route.params.id : ''
  if (!id) return
  loading.value = true; loadError.value = ''; learningRecord.value = null
  try {
    resource.value = await getResource(id)
    learningRecord.value = await getResourceRecord(id)
    if (route.query.start === '1' && !learningRecord.value) await startLearning(false)
  } catch (error: any) {
    loadError.value = typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : '无法读取该学习资料'
  } finally { loading.value = false }
}
async function startLearning(showMessage = true) {
  if (!resource.value) return
  recordLoading.value = true
  try { learningRecord.value = await startResource(resource.value.id); if (showMessage) ElMessage.success('已开始学习') }
  catch (error: any) { ElMessage.error(error?.response?.data?.detail || '无法创建学习记录') }
  finally { recordLoading.value = false }
}
async function completeLearning() {
  if (!learningRecord.value || learningRecord.value.status === 'completed') return
  recordLoading.value = true
  try {
    const started = learningRecord.value.started_at ? new Date(learningRecord.value.started_at).getTime() : Date.now()
    const timeSpent = Math.max(60, Math.round((Date.now() - started) / 1000))
    learningRecord.value = await completeRecord(learningRecord.value.id, { time_spent: timeSpent })
    ElMessage.success('学习进度已完成')
  } catch (error: any) { ElMessage.error(error?.response?.data?.detail || '学习进度更新失败') }
  finally { recordLoading.value = false }
}
function cleanBody(body: string): string { return body.split('\n').filter(line => !/^(ID|难度)[：:]/.test(line.trim())).join('\n') }
function sanitizeHtml(html: string): string { const template = document.createElement('template'); template.innerHTML = html; template.content.querySelectorAll('script,style,iframe,object,embed,form,link,meta').forEach(node => node.remove()); template.content.querySelectorAll('*').forEach(element => { [...element.attributes].forEach(attribute => { const name = attribute.name.toLowerCase(); const value = attribute.value.trim().toLowerCase(); if (name.startsWith('on') || name === 'srcdoc' || ((name === 'href' || name === 'src') && /^(javascript:|data:text\/html)/.test(value))) element.removeAttribute(attribute.name) }) }); return template.innerHTML }
const renderedBody = computed(() => resource.value ? sanitizeHtml(marked(cleanBody(resource.value.body)) as string) : '')
function reviewText(status: string | null) { return status === 'passed' ? '已通过' : status === 'partial' ? '部分匹配' : '待复核' }
onMounted(loadResource); watch(() => route.params.id, loadResource)
</script>

<style scoped>
.resource-detail-page{min-height:calc(100vh - 72px);padding:34px 24px 64px;background:radial-gradient(circle at 86% 11%,rgba(201,255,219,.44),transparent 22%),linear-gradient(160deg,#fcfffd,#effaf3)}.detail-heading{padding:10px 0 27px}.back-link{display:inline-flex;align-items:center;gap:8px;border:0;background:transparent;padding:0;color:var(--green-deep);font:inherit;font-size:12px;font-weight:700;cursor:pointer}.back-link b{font-size:18px}.detail-title-row{display:flex;align-items:center;justify-content:space-between;gap:26px;margin-top:21px}.detail-title-row h1,.detail-heading>div>h1{max-width:910px;margin:7px 0 0;color:var(--ink);font-size:clamp(29px,3.2vw,47px);line-height:1.16}.detail-tags{display:flex;gap:7px;flex-wrap:wrap;margin-top:16px}.detail-tags span{padding:5px 8px;border-radius:8px;background:rgba(222,250,222,.72);color:var(--green-deep);font-size:10px}.source-orb{position:relative;width:98px;height:98px;flex:0 0 98px;display:grid;place-items:center;overflow:hidden;border-radius:30px;background:linear-gradient(135deg,rgba(255,255,255,.9),rgba(123,242,171,.77));border:1px solid rgba(255,255,255,.92);box-shadow:inset 0 1px 1px white,0 17px 31px rgba(13,142,75,.17)}.source-orb::before,.source-orb::after{content:'';position:absolute;border:1px solid rgba(16,153,79,.26);border-radius:50%}.source-orb::before{width:68px;height:25px;transform:rotate(-26deg)}.source-orb::after{width:47px;height:15px;transform:rotate(35deg)}.source-orb i{position:absolute;width:13px;height:13px;right:18px;top:15px;border-radius:50%;background:#9df5bc;box-shadow:0 0 13px #5fe58d}.source-orb b{position:relative;z-index:1;color:var(--green-deep);font-size:20px}.detail-layout{display:grid;grid-template-columns:minmax(0,1fr) 244px;gap:20px;align-items:start}.reading-card{min-height:540px;padding:27px 31px;border-radius:var(--radius-lg)}.reading-status{display:flex;gap:8px;align-items:center;padding-bottom:18px;border-bottom:1px solid var(--line);color:var(--ink-soft);font-size:11px}.reading-status b{color:var(--green-deep)}.source-dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 0 5px rgba(23,174,93,.11)}.reading-status span:last-child{margin-left:auto;color:var(--ink-faint)}.doc-body{padding-top:20px;word-break:break-word}.doc-body :deep(h1){margin:0 0 17px;color:var(--ink);font-size:27px}.doc-body :deep(h2){margin:28px 0 12px;color:var(--ink);font-size:21px}.doc-body :deep(h3){margin:23px 0 9px;color:var(--ink);font-size:17px}.doc-body :deep(p),.doc-body :deep(li){color:var(--ink-soft);font-size:14px;line-height:1.9}.doc-body :deep(p){margin:0 0 15px}.doc-body :deep(ul),.doc-body :deep(ol){padding-left:24px;margin:0 0 17px}.doc-body :deep(li){margin:5px 0}.doc-body :deep(code){padding:2px 5px;border-radius:5px;background:rgba(222,250,222,.76);color:var(--green-deep);font:12px Consolas,monospace}.doc-body :deep(pre){overflow:auto;margin:17px 0;padding:17px;border-radius:13px;background:#0d3120;color:#dcffe9;box-shadow:inset 0 1px rgba(255,255,255,.08)}.doc-body :deep(pre code){padding:0;background:transparent;color:inherit}.doc-body :deep(blockquote){margin:17px 0;padding:11px 16px;border-left:3px solid var(--green);border-radius:0 11px 11px 0;background:rgba(222,250,222,.48);color:var(--ink-soft)}.detail-sidebar{display:grid;gap:15px}.detail-meta,.detail-note{padding:18px;border-radius:var(--radius-md)}.card-label{display:block;color:var(--ink-soft);font-size:12px;font-weight:800}.detail-meta dl{margin:15px 0 0}.detail-meta dl>div{padding:13px 0;border-top:1px solid var(--line)}.detail-meta dt{color:var(--ink-faint);font-size:10px}.detail-meta dd{margin:5px 0 0;color:var(--ink);font-size:12px;font-weight:700;word-break:break-word}.detail-meta dd.reviewed{color:var(--green-deep)}.detail-note span{display:grid;place-items:center;width:31px;height:31px;border-radius:10px;background:var(--brand-pale);color:var(--green-deep)}.detail-note p{margin:12px 0;color:var(--ink-soft);font-size:11px;line-height:1.7}.detail-note button{border:0;background:transparent;padding:0;color:var(--green-deep);font:700 11px inherit;cursor:pointer}.detail-state{margin-top:20px;padding:72px 22px;border-radius:var(--radius-lg);text-align:center}.detail-state>b{display:block;margin-top:15px;color:var(--ink);font-size:17px}.detail-state p{margin:8px 0 0;color:var(--ink-soft);font-size:12px}.detail-state button{margin-top:18px;border:0;border-radius:11px;padding:10px 13px;background:var(--green);color:#fff;font:700 12px inherit;cursor:pointer}.loading-ring{display:block;width:36px;height:36px;margin:auto;border:3px solid rgba(19,169,99,.13);border-top-color:var(--green);border-radius:50%;animation:spin .78s linear infinite}.state-symbol{display:grid;place-items:center;width:39px;height:39px;margin:auto;border-radius:13px;background:#fff0eb;color:#c95f42;font-weight:900}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:860px){.detail-layout{grid-template-columns:1fr}.detail-sidebar{grid-template-columns:1fr 1fr}.detail-title-row h1{font-size:34px}}@media(max-width:600px){.resource-detail-page{padding:24px 14px 42px}.detail-title-row{align-items:flex-start}.source-orb{width:65px;height:65px;flex-basis:65px;border-radius:21px}.source-orb::before,.source-orb::after,.source-orb i{display:none}.source-orb b{font-size:14px}.reading-card{padding:20px 17px;border-radius:18px}.reading-status{align-items:flex-start;flex-wrap:wrap}.reading-status span:last-child{width:100%;margin-left:15px}.detail-sidebar{grid-template-columns:1fr}.doc-body :deep(p),.doc-body :deep(li){font-size:13px}.detail-title-row h1{font-size:29px}}
.learning-state { padding: 18px; border-radius: var(--radius-md); }
.learning-state > b { display: block; margin-top: 13px; color: var(--green-deep); font-size: 15px; }
.learning-state > p { margin: 7px 0 13px; color: var(--ink-soft); font-size: 10px; line-height: 1.6; }
.learning-state > button { width: 100%; border: 0; border-radius: 11px; padding: 10px 12px; background: var(--gradient-primary); color: #fff; font: 700 11px inherit; cursor: pointer; }
.learning-state > button:disabled { cursor: default; opacity: .58; }
</style>
