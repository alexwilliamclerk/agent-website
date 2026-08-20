<template>
  <main class="access-page">
    <div class="access-backdrop" aria-hidden="true"><i class="halo halo-one"></i><i class="halo halo-two"></i><i class="orbit orbit-one"></i><i class="orbit orbit-two"></i></div>
    <section class="access-layout">
      <aside class="access-intro motion-enter">
        <span class="eyebrow">ZHIXUE NAVIGATION</span>
        <div class="intro-mark"><i></i><i></i><i></i></div>
        <h1>进入你的<br><em>能力成长空间</em></h1>
        <p>围绕目标岗位，把资料审查、能力诊断和可信学习资源串成一条清晰路径。</p>
        <div class="intro-points"><span><b>01</b>资料审查</span><span><b>02</b>能力诊断</span><span><b>03</b>学习资源</span></div>
      </aside>

      <section class="access-card glass-surface motion-enter motion-delay-1" aria-label="账户访问">
        <div class="access-card-header"><div class="mini-mark"><i></i><i></i><i></i></div><div><span>{{ activeTab === 'login' ? 'WELCOME BACK' : 'CREATE ACCOUNT' }}</span><h2>{{ activeTab === 'login' ? '登录职学导航' : '创建学习账户' }}</h2></div></div>
        <p class="access-description">{{ activeTab === 'login' ? '使用你的账户继续查看诊断结果与学习资料。' : '注册后即可创建属于自己的资料审查与能力诊断。' }}</p>

        <div class="access-tabs" role="tablist"><button :class="{ active: activeTab === 'login' }" type="button" role="tab" @click="switchTab('login')">登录</button><button :class="{ active: activeTab === 'register' }" type="button" role="tab" @click="switchTab('register')">注册</button></div>

        <form v-if="activeTab === 'login'" class="access-form" @submit.prevent="handleLogin">
          <label><span>用户名</span><input v-model="loginForm.username" type="text" autocomplete="username" placeholder="输入用户名" @input="loginError = ''" /></label>
          <label><span>密码</span><div class="password-field"><input v-model="loginForm.password" :type="showLoginPwd ? 'text' : 'password'" autocomplete="current-password" name="password" placeholder="输入密码" @input="loginError = ''" /><button class="password-toggle" type="button" :aria-label="showLoginPwd ? '隐藏密码' : '显示密码'" :aria-pressed="showLoginPwd" :title="showLoginPwd ? '隐藏密码' : '显示密码'" @click.prevent.stop="toggleLoginPassword"><component :is="showLoginPwd ? Hide : View" /></button></div></label>
          <p v-if="loginError" class="access-error">{{ loginError }}</p>
          <button class="access-submit" type="submit" :disabled="loginLoading || !canLogin"><i v-if="loginLoading"></i>{{ loginLoading ? '正在登录' : '登录并继续' }} <b>→</b></button>
        </form>

        <form v-else class="access-form" @submit.prevent="handleRegister">
          <label><span>用户名</span><input v-model="registerForm.username" type="text" autocomplete="username" placeholder="设置用户名" @input="registerError = ''" /></label>
          <label><span>密码</span><div class="password-field"><input v-model="registerForm.password" :type="showRegisterPwd ? 'text' : 'password'" autocomplete="new-password" name="password" placeholder="至少 6 位密码" @input="registerError = ''" /><button class="password-toggle" type="button" :aria-label="showRegisterPwd ? '隐藏密码' : '显示密码'" :aria-pressed="showRegisterPwd" :title="showRegisterPwd ? '隐藏密码' : '显示密码'" @click.prevent.stop="toggleRegisterPassword"><component :is="showRegisterPwd ? Hide : View" /></button></div></label>
          <p v-if="registerError" class="access-error">{{ registerError }}</p>
          <button class="access-submit" type="submit" :disabled="registerLoading || !canRegister"><i v-if="registerLoading"></i>{{ registerLoading ? '正在创建' : '创建账户' }} <b>→</b></button>
        </form>

        <button class="access-home" type="button" @click="router.push('/')">暂不登录，返回首页</button>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Hide, View } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const route = useRoute(); const router = useRouter(); const store = useUserStore()
function destination() { const next = route.query.next; return typeof next === 'string' && next.startsWith('/') && !next.startsWith('//') ? next : '/' }
onMounted(() => { if (store.isLoggedIn) router.replace(destination()) })
function getTabFromQuery(): 'login' | 'register' { return route.query.tab === 'register' ? 'register' : 'login' }
const activeTab = ref<'login' | 'register'>(getTabFromQuery())
watch(() => route.query.tab, () => { activeTab.value = getTabFromQuery() })
const loginLoading = ref(false); const loginError = ref(''); const showLoginPwd = ref(false); const loginForm = ref({ username: '', password: '' })
const registerLoading = ref(false); const registerError = ref(''); const showRegisterPwd = ref(false); const registerForm = ref({ username: '', password: '' })
const canLogin = computed(() => loginForm.value.username.trim() !== '' && loginForm.value.password !== '')
const canRegister = computed(() => registerForm.value.username.trim() !== '' && registerForm.value.password.length >= 6)
function toggleLoginPassword() { showLoginPwd.value = !showLoginPwd.value }
function toggleRegisterPassword() { showRegisterPwd.value = !showRegisterPwd.value }
function switchTab(tab: 'login' | 'register') { activeTab.value = tab; showLoginPwd.value = false; showRegisterPwd.value = false; loginError.value = ''; registerError.value = ''; router.replace({ query: tab === 'register' ? { ...route.query, tab } : Object.fromEntries(Object.entries(route.query).filter(([key]) => key !== 'tab')) }) }
async function handleLogin() { if (!canLogin.value) return; loginLoading.value = true; loginError.value = ''; try { await store.login(loginForm.value.username, loginForm.value.password); ElMessage.success('登录成功'); router.replace(destination()) } catch (error: any) { loginError.value = typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : '用户名或密码错误' } finally { loginLoading.value = false } }
async function handleRegister() { if (!canRegister.value) return; registerLoading.value = true; registerError.value = ''; try { await store.register(registerForm.value.username, registerForm.value.password); await store.login(registerForm.value.username, registerForm.value.password); ElMessage.success('注册成功'); router.replace(destination()) } catch (error: any) { registerError.value = typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : '注册失败，请稍后重试' } finally { registerLoading.value = false } }
</script>

<style scoped>
.access-page{position:relative;min-height:calc(100vh - 72px);display:grid;place-items:center;overflow:hidden;padding:46px 24px;background:linear-gradient(137deg,#fbfffc 5%,#effcf2 49%,#fafffc)}.access-backdrop{position:absolute;inset:0;pointer-events:none}.halo{position:absolute;border-radius:50%;filter:blur(2px);opacity:.78}.halo-one{width:420px;height:420px;right:-105px;top:-120px;background:radial-gradient(circle,rgba(185,250,204,.62),rgba(222,250,222,0) 68%)}.halo-two{width:390px;height:390px;left:-170px;bottom:-175px;background:radial-gradient(circle,rgba(191,244,213,.52),rgba(222,250,222,0) 70%)}.orbit{position:absolute;border:1px solid rgba(35,178,91,.15);border-radius:50%;transform:rotate(-22deg)}.orbit-one{width:610px;height:170px;right:-55px;bottom:12%}.orbit-two{width:420px;height:120px;left:6%;top:14%;transform:rotate(25deg)}.access-layout{position:relative;z-index:1;display:grid;grid-template-columns:minmax(0,1.06fr) minmax(390px,.94fr);gap:clamp(46px,8vw,130px);align-items:center;width:min(1110px,100%)}.access-intro{max-width:515px}.access-intro h1{margin:18px 0 20px;color:var(--ink);font-size:clamp(39px,5vw,68px);line-height:1.07;letter-spacing:0}.access-intro h1 em{font-style:normal;color:var(--green)}.access-intro p{max-width:430px;margin:0;color:var(--ink-soft);font-size:15px;line-height:1.9}.intro-mark{position:relative;width:72px;height:72px;margin-top:24px;border:1px solid rgba(255,255,255,.92);border-radius:24px;background:rgba(255,255,255,.55);box-shadow:inset 0 1px 1px white,0 18px 36px rgba(22,126,68,.11);overflow:hidden}.intro-mark i,.mini-mark i{position:absolute;display:block;border:3px solid var(--green);border-radius:50%}.intro-mark i:nth-child(1){width:32px;height:32px;left:19px;top:18px}.intro-mark i:nth-child(2){width:18px;height:18px;left:27px;top:8px;border-color:#6ee49a}.intro-mark i:nth-child(3){width:11px;height:11px;right:10px;bottom:12px;border-color:#95edb6}.intro-points{display:flex;flex-wrap:wrap;gap:10px;margin-top:31px}.intro-points span{padding:8px 11px;border:1px solid rgba(62,172,98,.13);border-radius:99px;background:rgba(255,255,255,.46);color:var(--ink-soft);font-size:11px}.intro-points b{margin-right:5px;color:var(--green-deep);font-size:10px}.access-card{width:100%;padding:32px;border-radius:28px;background:rgba(255,255,255,.64);box-shadow:inset 0 1px 1px rgba(255,255,255,.98),0 24px 70px rgba(29,106,62,.12)}.access-card-header{display:flex;gap:13px;align-items:center}.mini-mark{position:relative;width:42px;height:42px;flex:0 0 42px;overflow:hidden;border-radius:14px;background:linear-gradient(135deg,#d9ffea,#8be7b0)}.mini-mark i:nth-child(1){width:21px;height:21px;left:10px;top:10px;border-width:2px}.mini-mark i:nth-child(2){width:12px;height:12px;left:15px;top:3px;border-width:2px;border-color:#5cd58b}.mini-mark i:nth-child(3){width:7px;height:7px;right:5px;bottom:6px;border-width:2px;border-color:#fff}.access-card-header span{color:var(--green);font-size:9px;font-weight:800;letter-spacing:.12em}.access-card-header h2{margin:3px 0 0;color:var(--ink);font-size:21px}.access-description{margin:19px 0;color:var(--ink-soft);font-size:12px;line-height:1.7}.access-tabs{display:grid;grid-template-columns:1fr 1fr;margin:22px 0 19px;border-bottom:1px solid var(--line)}.access-tabs button{position:relative;border:0;padding:11px;background:transparent;color:var(--ink-faint);font:inherit;font-size:13px;cursor:pointer}.access-tabs button.active{color:var(--green-deep);font-weight:800}.access-tabs button.active::after{content:'';position:absolute;right:20%;bottom:-1px;left:20%;height:2px;border-radius:2px;background:var(--green)}.access-form{display:grid;gap:16px}.access-form label>span{display:block;margin:0 0 7px;color:var(--ink);font-size:12px;font-weight:700}.access-form input{box-sizing:border-box;width:100%;height:45px;border:1px solid rgba(24,113,64,.16);border-radius:13px;padding:0 13px;background:rgba(255,255,255,.7);color:var(--ink);outline:0;font:inherit;font-size:13px;transition:border-color .2s ease,box-shadow .2s ease}.access-form input:focus{border-color:rgba(9,151,79,.58);box-shadow:0 0 0 4px rgba(35,199,115,.1)}.access-form input::placeholder{color:var(--ink-faint)}.password-field{position:relative}.password-field input{padding-right:58px}.password-field button{position:absolute;right:8px;top:7px;height:31px;border:0;border-radius:9px;padding:0 8px;background:rgba(222,250,222,.76);color:var(--green-deep);font:inherit;font-size:10px;cursor:pointer}.access-error{margin:0;color:#b94e4e;font-size:12px}.access-submit{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;height:46px;margin-top:4px;border:1px solid rgba(255,255,255,.8);border-radius:14px;background:linear-gradient(118deg,#28c677,#07844d);color:white;box-shadow:0 10px 21px rgba(7,132,77,.2);font:inherit;font-size:13px;font-weight:800;cursor:pointer}.access-submit b{font-size:18px}.access-submit:disabled{opacity:.45;cursor:not-allowed}.access-submit i{width:14px;height:14px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:spin .75s linear infinite}.access-home{width:100%;margin-top:18px;border:0;background:transparent;color:var(--ink-soft);font:inherit;font-size:11px;cursor:pointer}.access-home:hover{color:var(--green-deep)}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:850px){.access-layout{grid-template-columns:1fr;max-width:530px;gap:32px}.access-intro{max-width:none}.access-intro h1{font-size:43px}.intro-mark{display:none}.access-page{padding:32px 18px}.access-card{padding:26px}}@media(max-width:480px){.access-page{padding:24px 14px}.access-intro h1{font-size:37px}.intro-points{gap:6px}.intro-points span{padding:7px 8px}.access-card{padding:22px 18px;border-radius:22px}}
.password-field button.password-toggle{position:absolute;right:4px;top:4px;width:37px;height:37px;display:grid;place-items:center;border:1px solid rgba(31,145,82,.1);border-radius:10px;padding:0;background:rgba(222,250,222,.62);color:var(--green-deep);cursor:pointer;transition:background .2s ease,transform .2s ease,box-shadow .2s ease}.password-field button.password-toggle svg{width:17px;height:17px}.password-field button.password-toggle:hover,.password-field button.password-toggle:focus-visible{background:rgba(198,244,214,.9);box-shadow:0 0 0 4px rgba(35,199,115,.1);outline:0}.password-field button.password-toggle:active{transform:scale(.94)}
@media (min-width: 851px) { .access-form label>span { font-size: 13px; } .access-form input { font-size: 14px; } .access-submit { font-size: 14px; } }
</style>
