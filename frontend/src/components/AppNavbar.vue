<template>
  <header class="glass-navbar" :class="{ 'is-scrolled': isScrolled }">
    <nav class="nav-inner" aria-label="主导航">
      <button class="brand" type="button" aria-label="返回职学导航首页" @click="$router.push('/')">
        <span class="brand-mark"><Connection /></span>
        <span>职学导航</span>
      </button>

      <div class="nav-links">
        <router-link to="/">首页</router-link>
        <router-link :to="inputLink">资料审查</router-link>
        <router-link :to="diagnosisLink">能力诊断</router-link>
        <router-link :to="libraryLink">资料库</router-link>
      </div>

      <div class="nav-actions">
        <template v-if="store.isLoggedIn">
          <button class="profile-chip" type="button" @click="$router.push('/profile')">
            <span class="profile-dot">{{ store.username.slice(0, 1).toUpperCase() }}</span>
            <span>{{ store.username }}</span>
          </button>
          <button class="nav-text-action" type="button" @click="store.logout()">退出</button>
        </template>
        <template v-else-if="!publicPreview">
          <button class="glass-button quiet" type="button" @click="$router.push('/login')">登录</button>
        </template>
        <button class="glass-button primary start-button" type="button" @click="openAssessment">
          开始测评 <ArrowRight />
        </button>
      </div>
    </nav>
  </header>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Connection } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const store = useUserStore()
const router = useRouter()
const publicPreview = import.meta.env.DEV && import.meta.env.VITE_PUBLIC_PREVIEW === 'true'
const isScrolled = ref(false)
const diagnosisLink = computed(() => {
  if (publicPreview) return '/diagnosis?demo=1'
  const id = store.userInfo?.latest_assessment_id
  return id ? `/diagnosis/${id}` : '/diagnosis'
})
const inputLink = computed(() => publicPreview ? '/input?demo=1' : '/input')
const libraryLink = computed(() => publicPreview ? '/library?demo=1' : '/library')
const openAssessment = () => {
  if (publicPreview || store.isLoggedIn) {
    router.push(publicPreview ? '/input?demo=1' : '/input')
    return
  }
  router.push('/login?next=/input')
}
const syncScroll = () => { isScrolled.value = window.scrollY > 12 }
onMounted(() => window.addEventListener('scroll', syncScroll, { passive: true }))
onBeforeUnmount(() => window.removeEventListener('scroll', syncScroll))
</script>

<style scoped>
.glass-navbar {
  position: sticky;
  top: 0;
  z-index: 50;
  height: 78px;
  padding: 7px 20px;
  background: rgba(252, 255, 253, .72);
  border-bottom: 1px solid rgba(10, 74, 43, .035);
  backdrop-filter: blur(10px);
  transition: background .3s ease, box-shadow .3s ease, backdrop-filter .3s ease;
}
.glass-navbar.is-scrolled {
  background: rgba(249, 254, 251, .82);
  backdrop-filter: blur(28px) saturate(150%);
  box-shadow: 0 14px 38px rgba(35, 81, 59, .075);
}
.nav-inner {
  width: min(1490px, 100%);
  height: 64px;
  margin: 0 auto;
  padding: 0 16px;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  border: 1px solid rgba(255,255,255,.48);
  border-radius: 20px;
  background: rgba(255,255,255,.28);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.8);
  transition: background .3s ease, border-color .3s ease;
}
.is-scrolled .nav-inner { background: rgba(255,255,255,.5); border-color: rgba(255,255,255,.78); }
.brand {
  display: inline-flex;
  align-items: center;
  justify-self: start;
  gap: 11px;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--ink);
  font-size: 20px;
  font-weight: 800;
  cursor: pointer;
}
.brand-mark {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  color: #fff;
  background: var(--gradient-primary);
  box-shadow: inset 0 1px 1px rgba(255,255,255,.6), 0 9px 19px rgba(15,164,91,.22);
}
.brand-mark svg { width: 21px; height: 21px; }
.nav-links { height: 100%; display: flex; align-items: center; gap: clamp(28px, 3vw, 58px); }
.nav-links a {
  height: 100%;
  position: relative;
  display: inline-grid;
  place-items: center;
  color: var(--ink-soft);
  text-decoration: none;
  font-size: 14px;
  font-weight: 650;
  transition: color .2s ease;
}
.nav-links a::after {
  content: '';
  position: absolute;
  bottom: 9px;
  width: 8px;
  height: 3px;
  border-radius: 9px;
  background: var(--gradient-primary);
  box-shadow: 0 0 9px rgba(34,181,107,.4);
  opacity: 0;
  transform: scaleX(.35);
  transition: opacity .2s ease, transform .2s ease;
}
.nav-links a.router-link-exact-active, .nav-links a.router-link-active { color: var(--green-deep); }
.nav-links a.router-link-exact-active::after, .nav-links a.router-link-active::after { opacity: 1; transform: scaleX(1); }
.nav-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; }
.glass-button {
  min-height: 40px;
  padding: 0 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid rgba(10,74,43,.12);
  border-radius: 13px;
  background: rgba(255,255,255,.5);
  color: var(--ink);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.92), 0 5px 12px rgba(33,82,58,.04);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: transform .2s ease, box-shadow .2s ease;
}
.glass-button:hover { transform: translateY(-1px); box-shadow: inset 0 1px 0 #fff, 0 12px 23px rgba(33,82,58,.11); }
.glass-button.primary {
  border-color: rgba(255,255,255,.58);
  background: var(--gradient-primary);
  background-size: 160% 160%;
  color: #fff;
  box-shadow: inset 0 1px 1px rgba(255,255,255,.46), 0 10px 20px rgba(10,142,79,.23);
}
.glass-button.primary:hover { background-position: 100% 50%; }
.glass-button svg { width: 16px; }
.start-button { min-width: 122px; }
.profile-chip, .nav-text-action { border: 0; background: transparent; cursor: pointer; color: var(--ink-soft); font-size: 13px; font-weight: 650; }
.profile-chip { display: inline-flex; gap: 8px; align-items: center; }
.profile-dot { height: 29px; width: 29px; display: grid; place-items: center; border-radius: 50%; background: rgba(42,205,127,.17); color: var(--green-deep); font-size: 12px; }
@media (max-width: 850px) {
  .glass-navbar { padding-inline: 8px; }
  .nav-inner { grid-template-columns: auto 1fr auto; padding-inline: 10px; }
  .brand { font-size: 17px; }
  .nav-links { display: none; }
  .nav-actions .quiet, .profile-chip, .nav-text-action { display: none; }
  .start-button { min-width: 0; padding-inline: 13px; }
}
</style>
