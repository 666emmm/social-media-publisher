<template>
  <el-dialog
    v-model="visible"
    :width="720"
    :close-on-click-modal="false"
    :show-close="!uploading"
    class="material-uploader-dialog"
    append-to-body
    @closed="onClosed"
  >
    <template #header>
      <div class="mud-header">
        <div class="mud-header-title">
          <span class="mud-header-dot" />
          <span>{{ title }}</span>
        </div>
        <div class="mud-header-hint" v-if="tip">{{ tip }}</div>
      </div>
    </template>

    <div class="mud-body">
      <!-- Drag area + file list -->
      <el-upload
        v-if="!uploading && fileList.length === 0"
        ref="uploadRef"
        :multiple="multiple"
        :accept="accept"
        :auto-upload="false"
        :show-file-list="false"
        :limit="maxCount || 0"
        :on-change="onFileChange"
        drag
        class="mud-dragger"
      >
        <el-icon class="mud-dragger-icon" :size="56"><UploadFilled /></el-icon>
        <div class="mud-dragger-text">
          将文件拖到此处，或<em>点击选择</em>
        </div>
        <div class="mud-dragger-tip" v-if="tip">{{ tip }}</div>
      </el-upload>

      <!-- File list with progress -->
      <div v-else class="mud-filelist">
        <div
          v-for="(f, idx) in fileList"
          :key="f.uid"
          class="mud-file"
          :class="{ 'is-done': f.status === 'success', 'is-failed': f.status === 'failed' }"
        >
          <div class="mud-file-icon">
            <el-icon :size="20">
              <component :is="f.fileType === 'video' ? VideoCamera : Picture" />
            </el-icon>
          </div>
          <div class="mud-file-main">
            <div class="mud-file-name">
              {{ f.name }}
              <span class="mud-file-size">{{ formatSize(f.size) }}</span>
            </div>
            <el-progress
              v-if="f.status === 'uploading'"
              :percentage="f.percent"
              :stroke-width="6"
              :show-text="true"
              :format="(p) => `${p}% · ${formatSpeed(f.speed)}`"
            />
            <div v-else-if="f.status === 'success'" class="mud-file-status ok">
              <el-icon><CircleCheckFilled /></el-icon> 上传完成
            </div>
            <div v-else-if="f.status === 'failed'" class="mud-file-status err">
              <el-icon><CircleCloseFilled /></el-icon> {{ f.error || '上传失败' }}
            </div>
          </div>
          <button
            v-if="f.status === 'failed'"
            class="mud-file-retry"
            @click="retryUpload(idx)"
          >
            重试
          </button>
          <button
            v-else-if="f.status === 'success'"
            class="mud-file-remove"
            @click="removeFile(idx)"
          >
            ×
          </button>
        </div>

        <!-- Add more button (multiple mode, after at least one file) -->
        <el-upload
          v-if="multiple && fileList.length > 0 && !uploading"
          :multiple="true"
          :accept="accept"
          :auto-upload="false"
          :show-file-list="false"
          :on-change="onFileChangeAppend"
          class="mud-addmore"
          action="#"
        >
          <el-icon :size="20"><Plus /></el-icon>
          <span>继续添加</span>
        </el-upload>

        <div v-if="!uploading" class="mud-actions">
          <el-button @click="visible = false" v-if="fileList.some(f => f.status === 'success')">关闭</el-button>
          <el-button
            v-else
            @click="resetState"
          >取消</el-button>
          <el-button
            type="primary"
            :loading="uploading"
            @click="startUpload"
          >开始上传</el-button>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { UploadFilled, VideoCamera, Picture, CircleCheckFilled, CircleCloseFilled, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { materialsApi } from '@/api/materials'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  accept: { type: String, default: '*' },
  multiple: { type: Boolean, default: false },
  maxSize: { type: Number, default: null }, // MB
  maxCount: { type: Number, default: null },
  title: { type: String, default: '上传素材' },
  tip: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'uploaded', 'all-uploaded', 'error', 'closed'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const fileList = ref([])
const uploading = ref(false)
const uploadRef = ref(null)

let _uidCounter = 0
function makeUid() { return `mu-${Date.now()}-${++_uidCounter}` }

function getFileType(file) {
  if (file.type?.startsWith('video/')) return 'video'
  if (file.type?.startsWith('image/')) return 'image'
  // 兜底扩展名
  const name = (file.name || '').toLowerCase()
  if (/\.(mp4|mov|avi|mkv|webm|flv|m4v|wmv|mpeg|mpg)$/.test(name)) return 'video'
  return 'image'
}

function onFileChange(file) {
  // el-upload 会先把 file 放进 uploadFiles（内部 list），再触发 onChange
  if (file.status === 'ready') {
    const item = {
      uid: makeUid(),
      name: file.name,
      size: file.size,
      fileType: getFileType(file),
      raw: file.raw,
      status: 'pending',  // pending | uploading | success | failed
      percent: 0,
      speed: 0,
      error: '',
      _ref: file,  // 保留 el-upload 的 file 引用，便于移除
    }
    if (props.maxSize && file.size > props.maxSize * 1024 * 1024) {
      item.status = 'failed'
      item.error = `超过 ${props.maxSize} MB 限制`
      ElMessage.warning(`${file.name} 超过 ${props.maxSize} MB`)
    }
    fileList.value.push(item)
    // 同步从 el-upload 内部 list 移除（我们用自己管理的 fileList）
    uploadRef.value?.handleRemove(file)
  }
}

function onFileChangeAppend(file) {
  if (file.status === 'ready') {
    onFileChange(file)
  }
}

function removeFile(idx) {
  fileList.value.splice(idx, 1)
}

function resetState() {
  fileList.value = []
  uploading.value = false
}

function onClosed() {
  resetState()
  emit('closed')
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  return (bytes / 1024 / 1024 / 1024).toFixed(1) + ' GB'
}

function formatSpeed(bytesPerSec) {
  if (!bytesPerSec) return ''
  return formatSize(bytesPerSec) + '/s'
}

async function uploadOne(idx) {
  const item = fileList.value[idx]
  if (!item || item.status !== 'pending') return
  item.status = 'uploading'
  item.percent = 0
  item.speed = 0
  const startTime = Date.now()
  const formData = new FormData()
  formData.append('file', item.raw)
  try {
    const resp = await materialsApi.upload(formData, (progressEvent) => {
      const loaded = progressEvent.loaded
      const total = progressEvent.total || item.size
      item.percent = Math.round((loaded / total) * 100)
      const elapsed = (Date.now() - startTime) / 1000
      if (elapsed > 0.1) item.speed = loaded / elapsed
    })
    if (resp.code === 200) {
      item.status = 'success'
      item.percent = 100
      item.response = resp.data
      emit('uploaded', resp.data)
    } else {
      item.status = 'failed'
      item.error = resp.msg || '上传失败'
      emit('error', new Error(item.error))
    }
  } catch (err) {
    item.status = 'failed'
    item.error = err.message || '网络错误'
    emit('error', err)
  }
}

async function startUpload() {
  const pendingItems = fileList.value.filter(f => f.status === 'pending')
  if (pendingItems.length === 0) return
  uploading.value = true
  for (let i = 0; i < fileList.value.length; i++) {
    if (fileList.value[i].status === 'pending') {
      await uploadOne(i)
    }
  }
  uploading.value = false
  const successes = fileList.value.filter(f => f.status === 'success')
  if (successes.length > 0) {
    emit('all-uploaded', successes.map(s => s.response))
  }
}

function retryUpload(idx) {
  fileList.value[idx].status = 'pending'
  fileList.value[idx].error = ''
  fileList.value[idx].percent = 0
  startUpload()
}

watch(visible, (v) => {
  if (!v) resetState()
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.material-uploader-dialog {
  :deep(.el-dialog__header) { padding: 18px 24px; border-bottom: 1px solid $border; }
  :deep(.el-dialog__body) { padding: 0; }
  :deep(.el-dialog__footer) { display: none; }
}

.mud-header {
  display: flex; align-items: center; justify-content: space-between;
  &-title { display: flex; align-items: center; gap: 10px; font-size: 16px; font-weight: 600; color: $text-primary; }
  &-dot { width: 6px; height: 6px; border-radius: 50%; background: $brand-start; box-shadow: 0 0 8px $brand-start; }
  &-hint { font-size: 12px; color: $text-muted; }
}

.mud-body {
  padding: 24px;
  min-height: 280px;
}

.mud-dragger {
  :deep(.el-upload) { width: 100%; }
  :deep(.el-upload-dragger) {
    padding: 48px 24px;
    border: 1.5px dashed $border-active;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.02);
    text-align: center;
    transition: $transition-base;
    &:hover { border-color: $brand-start; background: rgba($brand-start, 0.04); }
  }
}
.mud-dragger-icon { color: $text-muted; margin-bottom: 12px; }
.mud-dragger-text { font-size: 14px; color: $text-primary; em { color: $brand-start; font-style: normal; } }
.mud-dragger-tip { font-size: 12px; color: $text-muted; margin-top: 8px; }

.mud-filelist {
  display: flex; flex-direction: column; gap: 10px;
}

.mud-file {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px;
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-base;
  &.is-done { border-color: rgba(82, 196, 26, 0.3); background: rgba(82, 196, 26, 0.04); }
  &.is-failed { border-color: rgba(245, 108, 108, 0.3); background: rgba(245, 108, 108, 0.04); }
}

.mud-file-icon {
  width: 36px; height: 36px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  display: flex; align-items: center; justify-content: center;
  color: $text-muted; flex-shrink: 0;
}

.mud-file-main { flex: 1; min-width: 0; }
.mud-file-name {
  font-size: 13px; color: $text-primary; font-weight: 500;
  display: flex; align-items: baseline; gap: 8px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  .mud-file-size { font-size: 11px; color: $text-muted; font-weight: 400; }
}
.mud-file-status {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; margin-top: 4px;
  &.ok { color: #67c23a; }
  &.err { color: #f56c6c; }
}

.mud-file-retry, .mud-file-remove {
  background: transparent; border: 1px solid $border; color: $text-muted;
  padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer;
  transition: $transition-base;
  &:hover { color: $brand-start; border-color: $brand-start; }
}
.mud-file-remove { padding: 4px 9px; font-size: 16px; line-height: 1; }

.mud-addmore {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 10px;
  border: 1.5px dashed $border;
  border-radius: 8px;
  color: $text-muted; font-size: 13px; cursor: pointer;
  transition: $transition-base;
  &:hover { border-color: $brand-start; color: $brand-start; }
  :deep(.el-upload) { display: contents; }
}

.mud-actions {
  display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px;
}
</style>
