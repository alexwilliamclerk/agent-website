<template>
  <div class="app-shell">
    <AppNavbar />
    <main class="app-main"><router-view /></main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import AppNavbar from '@/components/AppNavbar.vue'
import { useUserStore } from '@/stores/user'

const store = useUserStore()
onMounted(() => {
  if (store.isLoggedIn && !store.userInfo) store.fetchUserInfo().catch(() => undefined)
})
</script>
