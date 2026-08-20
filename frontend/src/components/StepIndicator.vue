<template>
  <div class="step-indicator">
    <div
      v-for="(step, index) in steps"
      :key="step.num"
      class="step-item"
      :class="{ active: step.num === currentStep, done: step.num < currentStep }"
    >
      <div class="step-circle">
        <span v-if="step.num < currentStep">✓</span>
        <span v-else>{{ step.num }}</span>
      </div>
      <div class="step-label">{{ step.label }}</div>
      <div v-if="index < steps.length - 1" class="step-line" :class="{ filled: step.num < currentStep }"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  currentStep: 1 | 2 | 3
}>()

const steps = [
  { num: 1, label: '资料审查' },
  { num: 2, label: '能力诊断' },
  { num: 3, label: '资源推荐' },
] as const
</script>

<style scoped>
.step-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 0 24px;
  max-width: 600px;
  margin: 0 auto;
}

.step-item {
  display: flex;
  align-items: center;
  position: relative;
}

.step-circle {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  background: #f0f0f0;
  color: #999;
  transition: all 0.3s;
  flex-shrink: 0;
}

.step-item.active .step-circle {
  background: #2563eb;
  color: #fff;
}

.step-item.done .step-circle {
  background: #16a34a;
  color: #fff;
}

.step-label {
  position: absolute;
  top: 40px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 13px;
  color: #999;
  white-space: nowrap;
}

.step-item.active .step-label {
  color: #2563eb;
  font-weight: 600;
}

.step-item.done .step-label {
  color: #16a34a;
}

.step-line {
  width: 100px;
  height: 2px;
  background: #f0f0f0;
  margin: 0 16px;
  transition: background 0.3s;
}

.step-line.filled {
  background: #16a34a;
}
</style>
