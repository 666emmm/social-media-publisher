<template>
  <div class="publish-stats">
    <div
      v-for="item in metrics"
      :key="item.key"
      class="stat-item"
      :class="[
        `stat-item--${item.theme}`,
        { 'stat-item--placeholder': isPlaceholder(item.value) },
      ]"
    >
      <el-tooltip
        :content="'数据统计功能开发中'"
        placement="top"
        :disabled="false"
      >
        <div class="stat-inner">
          <el-icon class="stat-icon" :size="16">
            <component :is="item.icon" />
          </el-icon>
          <span class="stat-label">{{ item.label }}</span>
          <span class="stat-value">{{ formatValue(item.value) }}</span>
        </div>
      </el-tooltip>
    </div>
  </div>
</template>

<script setup>
import { VideoPlay, Star, Collection, ChatLineRound } from '@element-plus/icons-vue'

const props = defineProps({
  views: { type: [Number, String, null], default: null },
  likes: { type: [Number, String, null], default: null },
  favorites: { type: [Number, String, null], default: null },
  comments: { type: [Number, String, null], default: null },
})

const metrics = [
  { key: 'views', label: '播放', value: props.views, icon: VideoPlay, theme: 'blue' },
  { key: 'likes', label: '点赞', value: props.likes, icon: Star, theme: 'rose' },
  { key: 'favorites', label: '收藏', value: props.favorites, icon: Collection, theme: 'cyan' },
  { key: 'comments', label: '评论', value: props.comments, icon: ChatLineRound, theme: 'green' },
]

function formatValue(v) {
  if (v == null) return '--'
  if (typeof v === 'number') {
    if (v >= 10000) return (v / 10000).toFixed(1) + 'w'
    return v.toLocaleString('zh-CN')
  }
  return v
}

function isPlaceholder(v) {
  return v == null
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.publish-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.stat-item {
  border: 1px solid $border;
  border-radius: $radius-base;
  background: rgba(255, 255, 255, 0.02);
  padding: 12px 14px;
  transition: $transition-base;
  cursor: default;

  &:hover {
    border-color: $border-active;
    background: rgba(255, 255, 255, 0.04);
  }
}

// 4 个主题色（基于项目已有 platform/accent 调色板，轻量区分）
.stat-item--blue {
  background: linear-gradient(135deg, rgba($platform-channels, 0.08), rgba(255, 255, 255, 0.02));

  .stat-icon {
    color: $platform-channels;
  }
}

.stat-item--rose {
  background: linear-gradient(135deg, rgba($accent-rose, 0.08), rgba(255, 255, 255, 0.02));

  .stat-icon {
    color: $accent-rose;
  }
}

.stat-item--cyan {
  background: linear-gradient(135deg, rgba($accent-cyan, 0.08), rgba(255, 255, 255, 0.02));

  .stat-icon {
    color: $accent-cyan;
  }
}

.stat-item--green {
  background: linear-gradient(135deg, rgba($accent-green, 0.08), rgba(255, 255, 255, 0.02));

  .stat-icon {
    color: $accent-green;
  }
}

// null 占位色（统一为 muted；空值时数字/标签同时降到 muted 视觉层级）
.stat-item--placeholder {
  .stat-label {
    color: $text-placeholder;
  }
  .stat-value {
    color: $text-placeholder;
    font-weight: 500;
  }
}

.stat-inner {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-icon {
  flex-shrink: 0;
}

.stat-label {
  font-size: 12px;
  color: $text-muted;
  flex: 1;
}

.stat-value {
  font-size: 14px;
  font-weight: 600;
  color: $text-primary;
  font-variant-numeric: tabular-nums;
}
</style>
