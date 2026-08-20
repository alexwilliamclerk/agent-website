import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/api/request'

// 仅供本地界面验收使用。未设置时（含生产构建）仍按正常账户权限保护页面。
const publicPreview = import.meta.env.DEV && import.meta.env.VITE_PUBLIC_PREVIEW === 'true'

const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomePage.vue'),
    // 首页只展示产品流程与示例，不读取用户私密数据，允许未登录访问。
    meta: { title: '首页', noAuth: true },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginPage.vue'),
    meta: { title: '登录', noAuth: true },
  },
  {
    path: '/input',
    name: 'input',
    component: () => import('@/views/InputPage.vue'),
    meta: { title: '资料审查' },
  },
  {
    path: '/diagnosis/:id?',
    name: 'diagnosis',
    component: () => import('@/views/DiagnosisPage.vue'),
    meta: { title: '能力诊断' },
  },
  {
    path: '/library',
    name: 'library',
    component: () => import('@/views/ResourcesPage.vue'),
    meta: { title: '资料库' },
  },
  {
    path: '/resources/:assessmentId',
    name: 'resourcesLegacy',
    component: () => import('@/views/ResourcesPage.vue'),
    meta: { title: '资料库' },
  },
  {
    path: '/resource/:id',
    name: 'resourceDetail',
    component: () => import('@/views/ResourceDetailPage.vue'),
    meta: { title: '资源详情' },
  },
  {
    path: '/path',
    name: 'path',
    component: () => import('@/views/PathPage.vue'),
    meta: { title: '学习路径' },
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('@/views/ProfilePage.vue'),
    meta: { title: '个人中心' },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 导航守卫
router.beforeEach((to, _from, next) => {
  // 修改页面标题
  document.title = (to.meta.title as string) || '职学导航'

  // 无需登录的页面直接放行
  if (to.meta.noAuth) {
    next()
    return
  }

  // 本地预览模式只解除路由跳转，接口层仍会要求有效账户令牌。
  // ?demo=1 是开发环境中用于演示多轮对话状态的显式开关，生产构建不会生效。
  const explicitDemo = import.meta.env.DEV && to.query.demo === '1'
  if (publicPreview || explicitDemo) {
    next()
    return
  }

  // 检查 token：无 token → 重定向 /login
  const token = getToken()
  if (!token) {
    next('/login')
    return
  }

  next()
})

export default router
