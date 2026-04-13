<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="toast-item"
          :class="'toast-' + toast.type"
          @click="removeToast(toast.id)"
        >
          <v-icon :icon="iconMap[toast.type]" size="20" class="toast-icon" />
          <span class="toast-text">{{ toast.text }}</span>
          <v-icon icon="mdi-close" size="16" class="toast-close" />
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useToast } from '../composables/useToast'

const { toasts, removeToast } = useToast()

const iconMap: Record<string, string> = {
  success: 'mdi-check-circle',
  error: 'mdi-alert-circle',
  info: 'mdi-information',
  warning: 'mdi-alert',
}
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 56px;
  right: 20px;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
  max-width: 400px;
}

.toast-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 10px;
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
  cursor: pointer;
  pointer-events: all;
  font-size: 14px;
  font-weight: 500;
  min-width: 280px;
  border: 1px solid rgba(255,255,255,0.15);
}

.toast-success {
  background: linear-gradient(135deg, rgba(34,197,94,0.92), rgba(22,163,74,0.92));
  color: white;
}
.toast-error {
  background: linear-gradient(135deg, rgba(239,68,68,0.92), rgba(220,38,38,0.92));
  color: white;
}
.toast-info {
  background: linear-gradient(135deg, rgba(59,130,246,0.92), rgba(37,99,235,0.92));
  color: white;
}
.toast-warning {
  background: linear-gradient(135deg, rgba(245,158,11,0.92), rgba(217,119,6,0.92));
  color: white;
}

.toast-icon { flex-shrink: 0; }
.toast-text { flex: 1; }
.toast-close {
  flex-shrink: 0;
  opacity: 0.6;
  transition: opacity 0.15s;
}
.toast-close:hover { opacity: 1; }

/* TransitionGroup animations */
.toast-enter-active {
  animation: toast-in 0.35s cubic-bezier(0.22, 1, 0.36, 1);
}
.toast-leave-active {
  animation: toast-out 0.25s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}
.toast-move {
  transition: transform 0.3s cubic-bezier(0.22, 1, 0.36, 1);
}

@keyframes toast-in {
  from {
    opacity: 0;
    transform: translateX(100px) scale(0.9);
  }
  to {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
}
@keyframes toast-out {
  from {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
  to {
    opacity: 0;
    transform: translateX(100px) scale(0.8);
  }
}
</style>
