<template>
  <el-drawer
    v-model="visible"
    title="选择音乐"
    direction="rtl"
    size="500px"
    :before-close="handleClose"
  >
    <!-- 提示 -->
    <div class="music-hint">
      <el-icon><InfoFilled /></el-icon>
      <span>添加音乐会提升内容的消费性,帮助内容拿到更多的流量</span>
    </div>

    <!-- 音乐列表 -->
    <div class="music-list" v-loading="loading">
      <div
        v-for="(music, idx) in musicList"
        :key="music.musicId || music.title || idx"
        class="music-item"
        @mouseenter="hoverIdx = idx"
        @mouseleave="hoverIdx = -1"
      >
        <div class="music-left">
          <div class="music-cover" @click="togglePlay(music)">
            <img
              :src="music.coverUrl"
              :alt="music.title"
              @error="onImageError"
            />
            <div class="music-play-icon" :class="{ playing: playingId === (music.musicId || music.title) }">
              <el-icon v-if="playingId === (music.musicId || music.title)"><VideoPause /></el-icon>
              <el-icon v-else><VideoPlay /></el-icon>
            </div>
          </div>
          <div class="music-info">
            <div class="music-title" :title="music.title">{{ music.title }}</div>
            <div class="music-duration">{{ formatDuration(music.duration) }}</div>
          </div>
        </div>
        <div class="music-right">
          <el-button
            v-show="hoverIdx === idx"
            type="primary"
            size="small"
            @click="handleSelect(music)"
          >
            使 用
          </el-button>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!loading && musicList.length === 0" class="empty-state">
        <el-empty description="暂无音乐" />
      </div>
    </div>

    <!-- 分页(支付宝原生用 antd5-pagination,这里用 el-pagination 对应) -->
    <template #footer>
      <div class="drawer-footer">
        <el-pagination
          v-model:current-page="pageNum"
          :page-size="1"
          :total="hasMore ? pageNum + 1 : pageNum"
          layout="prev, pager, next"
          :pager-count="7"
          @current-change="handlePageChange"
        />
        <div class="footer-tip">
          <el-icon><InfoFilled /></el-icon>
          <span>音乐封面以发布后播放页面展示为准</span>
        </div>
      </div>
    </template>

    <!-- 隐藏的 audio 元素用于试听 -->
    <audio
      ref="audioRef"
      :src="currentAudioUrl"
      @ended="onAudioEnded"
      @error="onAudioError"
    />
  </el-drawer>
</template>

<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { VideoPlay, VideoPause, InfoFilled } from '@element-plus/icons-vue'
import { alipayApi } from '@/api/alipay'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  accountId: { type: [String, Number], default: '' },
})
const emit = defineEmits(['update:modelValue', 'select'])

const visible = ref(props.modelValue)
const loading = ref(false)
const musicList = ref([])
const hoverIdx = ref(-1)
const pageNum = ref(1)
const hasMore = ref(true)

// 试听状态(单例播放)
const audioRef = ref(null)
const playingId = ref(null)
const currentAudioUrl = ref('')

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val && musicList.value.length === 0) {
    pageNum.value = 1
    fetchMusicList()
  }
})
watch(visible, (val) => {
  emit('update:modelValue', val)
  if (!val) stopPlay()
})

async function fetchMusicList() {
  if (!props.accountId) return
  loading.value = true
  try {
    const resp = await alipayApi.musicList(props.accountId, pageNum.value)
    if (resp.code === 200) {
      musicList.value = resp.data?.list || []
      hasMore.value = resp.data?.hasMore ?? false
    }
  } catch (e) {
    console.error('[支付宝音乐] 加载失败:', e)
    musicList.value = []
  } finally {
    loading.value = false
  }
}

function handlePageChange(p) {
  stopPlay()
  pageNum.value = p
  fetchMusicList()
}

function togglePlay(music) {
  const id = music.musicId || music.title
  if (playingId.value === id) {
    // 当前正在播放 → 暂停
    stopPlay()
    return
  }
  // 切换到新音乐
  stopPlay()
  if (!music.audioUrl) {
    console.warn('[支付宝音乐] 该音乐无试听 URL:', music.title)
    return
  }
  currentAudioUrl.value = music.audioUrl
  playingId.value = id
  // 等 src 绑定后播放
  setTimeout(() => {
    const el = audioRef.value
    if (el) {
      el.play().catch(err => {
        console.warn('[支付宝音乐] 试听播放失败:', err)
        playingId.value = null
      })
    }
  }, 50)
}

function stopPlay() {
  const el = audioRef.value
  if (el) {
    el.pause()
    el.currentTime = 0
  }
  playingId.value = null
}

function onAudioEnded() {
  playingId.value = null
}

function onAudioError() {
  playingId.value = null
}

function handleSelect(music) {
  stopPlay()
  emit('select', { ...music })
  visible.value = false
}

function handleClose() {
  visible.value = false
}

function formatDuration(duration) {
  // 支付宝返回的 duration 可能是 "00:24" 字符串或秒数
  if (!duration) return '00:00'
  const s = String(duration)
  if (s.includes(':')) return s
  const sec = parseInt(s, 10)
  if (isNaN(sec)) return s
  const m = Math.floor(sec / 60)
  const r = Math.floor(sec % 60)
  return `${m.toString().padStart(2, '0')}:${r.toString().padStart(2, '0')}`
}

function onImageError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDgiIGhlaWdodD0iNDgiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjQ4IiBoZWlnaHQ9IjQ4IiBmaWxsPSIjZjVmNWY1Ii8+PHRleHQgeD0iMjQiIHk9IjI4IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTAiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPuWGm+S6rDwvdGV4dD48L3N2Zz4='
}

onBeforeUnmount(() => stopPlay())
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.music-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  color: #909399;
  font-size: 12px;
  border-bottom: 1px solid $border;
}

.music-list {
  height: calc(100% - 140px);
  overflow-y: auto;
  padding: 8px 16px;
}

.music-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-radius: 4px;
  margin-bottom: 4px;
  transition: background 0.2s;
  cursor: default;

  &:hover {
    background: #F5F5F5;
  }
}

.music-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.music-cover {
  position: relative;
  width: 48px;
  height: 48px;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
  cursor: pointer;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .music-play-icon {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.3);
    color: white;
    font-size: 20px;
    opacity: 0;
    transition: opacity 0.2s;

    &.playing {
      opacity: 1;
    }
  }

  &:hover .music-play-icon {
    opacity: 1;
  }
}

.music-info {
  flex: 1;
  min-width: 0;
}

.music-title {
  font-size: 14px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.music-duration {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.music-right {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.empty-state {
  padding: 40px 0;
}

.drawer-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid $border;
}

.footer-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #909399;
  font-size: 12px;
}
</style>
