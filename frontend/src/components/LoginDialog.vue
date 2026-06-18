<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    :width="mode === 'relogin' ? '420px' : '680px'"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="onDialogOpen"
    @close="handleClose"
  >
    <!-- add 模式: 平台卡片网格 -->
    <div v-if="mode === 'add'" class="login-dialog-body">
      <p class="dialog-hint">选择要登录的平台,点击卡片即开始登录</p>
      <div v-if="cardList.length === 0" class="empty-state">
        所有渠道都已加入黑名单,请先在系统设置中移除后再来登录
      </div>
      <div v-else class="platform-grid">
        <div
          v-for="p in cardList"
          :key="p.key"
          :class="[
            'platform-card',
            `platform-${p.cssClass}`,
            `is-${p.status}`
          ]"
          @click="onCardClick(p)"
        >
          <!-- idle 状态 -->
          <template v-if="p.status === 'idle'">
            <div class="platform-logo-wrap">
              <img v-if="p.logo" :src="p.logo" :alt="p.name" class="platform-logo" />
              <span v-else class="platform-letter">{{ p.letter }}</span>
            </div>
            <div class="platform-name">{{ p.name }}</div>
          </template>

          <!-- logging 状态 -->
          <template v-else-if="p.status === 'logging'">
            <el-icon class="loading-icon is-loading"><Loading /></el-icon>
            <div class="platform-name">{{ p.name }}</div>
            <div class="status-text">登录中...</div>
            <button class="cancel-btn" type="button" @click.stop="cancelLogin(p.key)">取消</button>
          </template>

          <!-- success 状态 -->
          <template v-else-if="p.status === 'success'">
            <el-icon class="success-icon"><Select /></el-icon>
            <div class="platform-name">{{ p.name }}</div>
            <div class="status-text">登录成功</div>
          </template>

          <!-- fail 状态 -->
          <template v-else-if="p.status === 'fail'">
            <el-icon class="fail-icon"><CloseBold /></el-icon>
            <div class="platform-name">{{ p.name }}</div>
            <div class="status-text fail-text">{{ p.errMsg || '登录失败' }}</div>
            <button class="retry-btn" type="button" @click.stop="retryLogin(p.key)">重试</button>
          </template>
        </div>
      </div>
    </div>

    <!-- relogin 模式: 单卡片 -->
    <div v-else class="login-dialog-body relogin-body">
      <div v-if="reloginPlatform" class="relogin-card" :class="`platform-${reloginPlatform.cssClass}`">
        <div class="platform-logo-wrap">
          <img v-if="reloginPlatform.logo" :src="reloginPlatform.logo" :alt="reloginPlatform.name" class="platform-logo" />
          <span v-else class="platform-letter">{{ reloginPlatform.letter }}</span>
        </div>
        <div class="platform-name">{{ reloginPlatform.name }}</div>
        <template v-if="reloginStatus === 'logging'">
          <el-icon class="loading-icon is-loading"><Loading /></el-icon>
          <div class="status-text">登录中...</div>
        </template>
        <template v-else-if="reloginStatus === 'success'">
          <el-icon class="success-icon"><Select /></el-icon>
          <div class="status-text">登录成功</div>
        </template>
        <template v-else-if="reloginStatus === 'fail'">
          <el-icon class="fail-icon"><CloseBold /></el-icon>
          <div class="status-text fail-text">{{ reloginErrMsg || '登录失败' }}</div>
          <button class="retry-btn" type="button" @click="startRelogin">重试</button>
        </template>
        <p class="relogin-hint">正在打开浏览器,请在弹出的浏览器窗口中完成登录</p>
      </div>
      <div v-else class="empty-state">账号信息异常</div>
    </div>

    <template #footer>
      <el-button v-if="mode === 'relogin' && reloginStatus === 'logging'"
                 @click="cancelRelogin">取消登录</el-button>
      <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, Select, CloseBold } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import { platformList, getPlatformByName } from '@/config/platforms'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  mode: { type: String, default: 'add' },  // 'add' | 'relogin'
  account: { type: Object, default: null }
})

const emit = defineEmits(['update:modelValue', 'success', 'fail'])

const appStore = useAppStore()

// add 模式: 多卡片状态
const cardStates = reactive({})  // key -> { status, errMsg }
const eventSources = new Map()   // key -> EventSource(非响应式)

// relogin 模式: 单卡片状态
const reloginStatus = ref('idle')
const reloginErrMsg = ref('')
const reloginPlatform = computed(() => {
  if (props.mode !== 'relogin' || !props.account) return null
  return getPlatformByName(props.account.platform)
})
const reloginKey = computed(() => reloginPlatform.value?.key)

const dialogTitle = computed(() => {
  if (props.mode === 'relogin' && reloginPlatform.value) {
    return `重新登录:${reloginPlatform.value.name}`
  }
  return '添加账号'
})

// 卡片列表(响应式:平台状态变化时自动更新)
const cardList = computed(() =>
  platformList
    .filter(p => !appStore.isPlatformDisabled(p.key))
    .map(p => ({
      ...p,
      status: cardStates[p.key]?.status || 'idle',
      errMsg: cardStates[p.key]?.errMsg || ''
    }))
)

function setCardStatus(key, status, errMsg = '') {
  cardStates[key] = { status, errMsg }
}

function onDialogOpen() {
  if (props.mode === 'add') {
    initCardStates()
  } else if (props.mode === 'relogin') {
    startRelogin()
  }
}

function initCardStates() {
  // 清掉旧状态
  for (const k of Object.keys(cardStates)) delete cardStates[k]
}

function handleClose() {
  // 清理所有 SSE 连接
  for (const key of eventSources.keys()) closeSSE(key)
  emit('update:modelValue', false)
}

// ===== SSE 逻辑在 Task 12 实现 =====
function startLogin(platformKey, accountId = null) {
  // 占位,Task 12 实现
}

function closeSSE(platformKey) {
  const es = eventSources.get(platformKey)
  if (es) {
    es.close()
    eventSources.delete(platformKey)
  }
}

function onCardClick(p) {
  if (p.status === 'idle' || p.status === 'fail') {
    startLogin(p.key)
  }
}

function cancelLogin(platformKey) {
  closeSSE(platformKey)
  setCardStatus(platformKey, 'idle')
  ElMessage.info('已取消登录')
}

function retryLogin(platformKey) {
  closeSSE(platformKey)
  startLogin(platformKey)
}

function startRelogin() {
  if (!reloginKey.value || !props.account) return
  reloginStatus.value = 'logging'
  reloginErrMsg.value = ''
  // Task 12 中实现 startLogin(reloginKey.value, props.account.id) + 监听 status 更新 reloginStatus
}

function cancelRelogin() {
  if (reloginKey.value) closeSSE(reloginKey.value)
  reloginStatus.value = 'idle'
  ElMessage.info('已取消登录')
}
</script>

<style scoped>
.login-dialog-body {
  padding: 0 4px;
}

.dialog-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 0 0 16px 0;
}

.platform-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.platform-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 16px 8px;
  min-height: 130px;
  border: 2px solid var(--el-border-color);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--el-bg-color);
  position: relative;
}

.platform-card.is-idle:hover {
  border-color: var(--el-color-primary);
  transform: translateY(-2px);
}

.platform-card.is-logging {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  cursor: progress;
}

.platform-card.is-success {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-9);
  cursor: default;
}

.platform-card.is-fail {
  border-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.platform-logo-wrap {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 6px;
}

.platform-logo {
  width: 32px;
  height: 32px;
  border-radius: 8px;
}

.platform-letter {
  font-size: 20px;
  font-weight: bold;
}

.platform-name {
  font-size: 13px;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}

.status-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.fail-text {
  color: var(--el-color-danger);
  max-width: 100%;
  word-break: break-all;
  text-align: center;
  padding: 0 4px;
}

.loading-icon {
  font-size: 28px;
  color: var(--el-color-primary);
  margin-bottom: 6px;
}

.success-icon {
  font-size: 28px;
  color: var(--el-color-success);
  margin-bottom: 6px;
}

.fail-icon {
  font-size: 28px;
  color: var(--el-color-danger);
  margin: 6px;
}

.cancel-btn,
.retry-btn {
  margin-top: 6px;
  padding: 2px 10px;
  border: 1px solid currentColor;
  background: transparent;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}

.cancel-btn {
  color: var(--el-text-color-secondary);
}

.retry-btn {
  color: var(--el-color-danger);
}

.empty-state {
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  padding: 40px 20px;
}

/* relogin 模式 */
.relogin-body {
  display: flex;
  justify-content: center;
}

.relogin-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 24px;
  border: 2px solid var(--el-border-color);
  border-radius: 12px;
  min-width: 280px;
}

.relogin-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
}

@media (max-width: 640px) {
  .platform-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
