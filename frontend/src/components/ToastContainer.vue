<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="toast-item"
          :class="'toast-' + toast.type"
        >
          <v-icon :icon="iconMap[toast.type]" size="20" class="toast-icon" />
          <span class="toast-text">{{ toast.text }}</span>
          <div class="toast-actions">
            <button
              v-if="toast.actionText"
              type="button"
              class="toast-btn toast-btn-action"
              @click="handleAction(toast)"
            >{{ toast.actionText }}</button>
            <button
              type="button"
              class="toast-btn toast-btn-close"
              @click="removeToast(toast.id)"
            >Закрыть</button>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useToast, type Toast } from '../composables/useToast'

const { toasts, removeToast } = useToast()

const iconMap: Record<string, string> = {
  success: 'mdi-check-circle',
  error: 'mdi-alert-circle',
  info: 'mdi-information',
  warning: 'mdi-alert',
}

function handleAction(toast: Toast) {
  toast.onAction?.()
  removeToast(toast.id)
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
  max-width: 420px;
}

.toast-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
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

.toast-icon { flex-shrink: 0; margin-top: 1px; }
.toast-text { flex: 1; white-space: pre-line; word-break: break-word; padding-top: 1px; }

.toast-actions {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.toast-btn {
  border: none;
  background: rgba(255,255,255,0.18);
  color: inherit;
  font: inherit;
  font-weight: 600;
  font-size: 12px;
  line-height: 1;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}
.toast-btn:hover { background: rgba(255,255,255,0.32); }
.toast-btn-action { background: rgba(255,255,255,0.28); }
.toast-btn-action:hover { background: rgba(255,255,255,0.42); }

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
