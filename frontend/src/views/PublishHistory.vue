<template>
  <div class="publish-history-page">
    <h1 class="page-title">发布历史</h1>
    <p class="page-subtitle">回顾所有发布记录</p>

    <!-- 3 Stat cards row -->
    <div class="stat-cards">
      <div class="stat-card stat-purple">
        <div class="stat-top">
          <div class="stat-icon">
            <el-icon><Upload /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.total }}</div>
            <div class="stat-label">总发布数</div>
          </div>
        </div>
      </div>

      <div class="stat-card stat-blue">
        <div class="stat-top">
          <div class="stat-icon">
            <el-icon><CircleCheck /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.successRate }}%</div>
            <div class="stat-label">成功率</div>
          </div>
        </div>
      </div>

      <div class="stat-card stat-cyan">
        <div class="stat-top">
          <div class="stat-icon">
            <el-icon><Calendar /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.monthlyTotal }}</div>
            <div class="stat-label">本月发布</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Filter toolbar -->
    <div class="filter-card">
      <div class="filter-row">
        <div class="filter-controls">
          <el-select
            v-model="timeRange"
            placeholder="时间范围"
            class="filter-select"
            @change="handleFilterChange"
          >
            <el-option label="今天" value="today" />
            <el-option label="最近7天" value="7days" />
            <el-option label="最近30天" value="30days" />
            <el-option label="全部" value="all" />
          </el-select>

          <el-select
            v-model="typeFilter"
            placeholder="类型"
            class="filter-select"
            @change="handleFilterChange"
          >
            <el-option label="全部" value="all" />
            <el-option label="视频" value="video" />
            <el-option label="图文" value="image" />
          </el-select>

          <el-select
            v-model="platformFilter"
            placeholder="平台"
            class="filter-select"
            @change="handleFilterChange"
          >
            <el-option label="全部" value="all" />
            <el-option v-for="p in platformList" :key="p.key" :label="p.name" :value="p.key" />
          </el-select>

          <el-select
            v-model="statusFilter"
            placeholder="状态"
            class="filter-select"
            @change="handleFilterChange"
          >
            <el-option label="全部" value="all" />
            <el-option label="全部成功" value="success" />
            <el-option label="部分失败" value="partial" />
            <el-option label="全部失败" value="failed" />
          </el-select>
        </div>

        <el-button
          class="refresh-btn"
          :icon="Refresh"
          @click="fetchHistory"
          :loading="loading"
        >
          刷新
        </el-button>
      </div>
    </div>

    <!-- Cards list (replaces table) -->
    <div class="cards-list" v-loading="loading">
      <div v-if="!loading && batches.length === 0" class="empty-state">
        <el-icon class="empty-icon"><Clock /></el-icon>
        <p>暂无发布记录</p>
      </div>
      <div
        v-for="batch in batches"
        :key="batch.id"
        class="batch-card"
        :class="{ 'is-expanded': expandedBatchId === batch.id }"
      >
        <!-- 卡片主行 -->
        <div class="card-main" @click="toggleExpand(batch.id)">
          <div class="card-cover">
            <img v-if="batch.cover_url" :src="batch.cover_url" :alt="batch.title" />
            <div v-else class="cover-placeholder">
              <el-icon :size="32"><Picture /></el-icon>
            </div>
          </div>
          <div class="card-body">
            <div class="card-title">{{ batch.title || '无标题' }}</div>
            <div class="card-desc">{{ (batch.description || '').slice(0, 100) }}</div>
            <div class="card-meta">
              <span class="meta-item">{{ batch.account_count }}账号 {{ batch.success_count }}成功 {{ batch.failed_count }}失败</span>
              <span class="status-tag" :class="`status-${batch.status}`">{{ statusLabel(batch.status) }}</span>
              <span class="meta-item">{{ formatRelativeTime(batch.created_at) }}</span>
            </div>
          </div>
        </div>
        <!-- 展开的明细 -->
        <div v-if="expandedBatchId === batch.id" class="card-details">
          <div v-for="d in batch.items" :key="d.id" class="detail-row">
            <span class="detail-status" :class="`status-${d.status}`">
              {{ d.status === 'success' ? '✓' : d.status === 'failed' ? '✗' : '○' }}
            </span>
            <span class="detail-name">{{ d.account_name }}</span>
            <span class="detail-platform">· {{ d.platform }}</span>
            <span class="detail-duration" v-if="d.duration">· {{ formatDuration(d.duration) }}</span>
            <a
              v-if="d.publish_url"
              :href="d.publish_url"
              target="_blank"
              rel="noopener noreferrer"
              @click.stop
            >[链接]</a>
            <div v-if="d.status === 'failed' && d.error_message" class="detail-error">
              错误：{{ d.error_message }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div class="pagination-wrapper" v-if="total > 0">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
        background
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Upload, CircleCheck, Calendar, Refresh, Clock, Picture } from '@element-plus/icons-vue'
import { historyApi, statsApi } from '@/api/v2'
import { platformList } from '@/config/platforms'

const batches = ref([])
const expandedBatchId = ref(null)
const stats = ref({ total: 0, successRate: 0, monthlyTotal: 0 })
const loading = ref(false)

// Filters
const timeRange = ref('all')
const typeFilter = ref('all')
const platformFilter = ref('all')
const statusFilter = ref('all')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

// Fetch history (batch list)
const fetchHistory = async () => {
  loading.value = true
  try {
    const params = { page: currentPage.value, pageSize: pageSize.value }
    if (timeRange.value !== 'all') params.timeRange = timeRange.value
    if (typeFilter.value !== 'all') params.type = typeFilter.value
    if (platformFilter.value !== 'all') params.platform = platformFilter.value
    if (statusFilter.value !== 'all') params.status = statusFilter.value
    const res = await historyApi.getHistory(params)
    if (res.code === 200) {
      batches.value = res.data?.items || []
      total.value = res.data?.total || 0
    }
  } catch (e) {
    console.error('Failed to fetch history:', e)
  } finally {
    loading.value = false
  }
}

// Fetch stats
const fetchStats = async () => {
  try {
    const res = await statsApi.getStats()
    if (res.code === 200 && res.data) {
      const d = res.data
      stats.value = {
        total: d.total ?? d.tasks?.total ?? 0,
        successRate: d.successRate ?? d.tasks?.successRate ?? 0,
        monthlyTotal: d.monthlyTotal ?? 0,
      }
    }
  } catch (e) {
    console.error('Failed to fetch stats:', e)
  }
}

const handlePageChange = (page) => {
  currentPage.value = page
  fetchHistory()
}

const handleSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
  fetchHistory()
}

const handleFilterChange = () => {
  currentPage.value = 1
  fetchHistory()
}

// Expand/collapse toggle
const toggleExpand = (id) => {
  expandedBatchId.value = expandedBatchId.value === id ? null : id
}

// Status label (Chinese)
const statusLabel = (status) => ({
  pending: '等待中',
  running: '发布中',
  success: '全部成功',
  partial: '部分失败',
  failed: '全部失败',
  cancelled: '已取消',
}[status] || status)

// Relative time formatter (copy pattern from OneClickFillDialog)
const formatRelativeTime = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = (now - d) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`
  return d.toLocaleDateString('zh-CN')
}

// Duration formatter (Chinese)
const formatDuration = (s) => {
  if (s == null) return ''
  if (s < 60) return `${s}秒`
  return `${Math.floor(s / 60)}分${s % 60}秒`
}

onMounted(() => {
  fetchHistory()
  fetchStats()
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.publish-history-page {
  padding: 0 28px;

  // Page title area
  .page-title {
    font-size: 26px;
    font-weight: 700;
    color: $text-primary;
    margin: 0;
    letter-spacing: -0.5px;
  }

  .page-subtitle {
    font-size: 14px;
    color: $text-muted;
    margin: 4px 0 24px;
  }

  // ========== Stat Cards (3-column) ==========
  .stat-cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
  }

  .stat-card {
    border-radius: $radius-card;
    padding: 20px 24px;
    transition: $transition-base;

    &.stat-purple {
      background: $stat-purple-bg;
      border: 1px solid $stat-purple-border;

      &:hover {
        border-color: rgba($brand-start, 0.35);
        box-shadow: 0 0 24px rgba($brand-start, 0.08);
      }

      .stat-icon {
        background: rgba($brand-start, 0.2);
        .el-icon { color: $brand-start; }
      }
    }

    &.stat-blue {
      background: $stat-blue-bg;
      border: 1px solid $stat-blue-border;

      &:hover {
        border-color: rgba($brand-end, 0.35);
        box-shadow: 0 0 24px rgba($brand-end, 0.08);
      }

      .stat-icon {
        background: rgba($brand-end, 0.2);
        .el-icon { color: $brand-end; }
      }
    }

    &.stat-cyan {
      background: $stat-cyan-bg;
      border: 1px solid $stat-cyan-border;

      &:hover {
        border-color: rgba($accent-cyan, 0.35);
        box-shadow: 0 0 24px rgba($accent-cyan, 0.08);
      }

      .stat-icon {
        background: rgba($accent-cyan, 0.2);
        .el-icon { color: $accent-cyan; }
      }
    }

    .stat-top {
      display: flex;
      align-items: center;
    }

    .stat-icon {
      width: 48px;
      height: 48px;
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.06);
      display: flex;
      align-items: center;
      justify-content: center;
      margin-right: 16px;
      flex-shrink: 0;

      .el-icon {
        font-size: 24px;
      }
    }

    .stat-info {
      .stat-value {
        font-size: 28px;
        font-weight: 700;
        background: $gradient-brand;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        line-height: 1.2;
        letter-spacing: -0.5px;
      }

      .stat-label {
        font-size: 13px;
        color: $text-secondary;
        margin-top: 2px;
      }
    }
  }

  // ========== Filter Toolbar ==========
  .filter-card {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    padding: 16px 20px;
    margin-top: 24px;

    .filter-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }

    .filter-controls {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }

    .filter-select {
      width: 140px;

      :deep(.el-input__wrapper) {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid $border;
        border-radius: $radius-base;
        box-shadow: none;

        &:hover {
          border-color: $border-active;
        }

        &.is-focus {
          border-color: $brand-start;
        }
      }

      :deep(.el-input__inner) {
        color: $text-secondary;
        font-size: 13px;
      }

      :deep(.el-input__suffix) {
        color: $text-muted;
      }
    }

    .refresh-btn {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid $border;
      border-radius: $radius-base;
      color: $text-secondary;
      font-size: 13px;

      &:hover {
        border-color: $border-active;
        color: $brand-start;
        background: rgba($brand-start, 0.06);
      }
    }
  }

  // ========== Cards List (replaces table) ==========
  .cards-list {
    margin-top: 24px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .batch-card {
    border: 1px solid $border;
    border-radius: 12px;
    background: $bg-elevated;
    overflow: hidden;
    transition: all 0.2s;

    &:hover {
      border-color: $brand-start;
    }

    &.is-expanded {
      border-color: $brand-start;
    }
  }

  .card-main {
    display: flex;
    gap: 16px;
    padding: 16px;
    cursor: pointer;
  }

  .card-cover {
    flex-shrink: 0;
    width: 160px;
    aspect-ratio: 16/9;
    background: $bg-surface;
    border-radius: 8px;
    overflow: hidden;
    position: relative;

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .cover-placeholder {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      color: $text-muted;
    }
  }

  .card-body {
    flex: 1;
    min-width: 0;
  }

  .card-title {
    font-size: 16px;
    font-weight: 600;
    color: $text-primary;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .card-desc {
    font-size: 13px;
    color: $text-secondary;
    margin: 6px 0 12px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .card-meta {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
    font-size: 12px;
    color: $text-muted;
  }

  .status-tag {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;

    &.status-success,
    &.status-partial {
      background: rgba(82, 196, 26, 0.15);
      color: #67c23a;
    }

    &.status-failed {
      background: rgba(245, 108, 108, 0.15);
      color: #f56c6c;
    }

    &.status-running {
      background: rgba(64, 158, 255, 0.15);
      color: #409eff;
    }

    &.status-pending,
    &.status-cancelled {
      background: rgba(0, 0, 0, 0.06);
      color: $text-muted;
    }
  }

  .card-details {
    border-top: 1px solid $border;
    padding: 12px 16px;
    background: $bg-surface;
  }

  .detail-row {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 6px 0;
    font-size: 13px;
    flex-wrap: wrap;
    color: $text-secondary;

    .detail-status {
      width: 18px;
      text-align: center;
      font-weight: 600;

      &.status-success { color: #67c23a; }
      &.status-failed { color: #f56c6c; }
    }

    a {
      color: $brand-start;
      text-decoration: none;
      font-size: 12px;

      &:hover {
        color: $brand-end;
        text-decoration: underline;
      }
    }

    .detail-error {
      flex-basis: 100%;
      color: #f56c6c;
      font-size: 12px;
      margin-left: 26px;
    }
  }

  // Empty state
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 20px;

    .empty-icon {
      font-size: 40px;
      color: $text-muted;
      margin-bottom: 12px;
    }

    p {
      font-size: 14px;
      color: $text-muted;
      margin: 0;
    }
  }

  // ========== Pagination ==========
  .pagination-wrapper {
    display: flex;
    justify-content: flex-end;
    margin-top: 20px;
    padding: 16px 20px;
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;

    :deep(.el-pagination) {
      --el-pagination-bg-color: transparent;
      --el-pagination-text-color: #{$text-secondary};
      --el-pagination-button-bg-color: rgba(255, 255, 255, 0.06);
      --el-pagination-hover-color: #{$brand-start};

      .btn-prev,
      .btn-next {
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid $border;
        border-radius: $radius-sm;
        color: $text-secondary;

        &:hover {
          border-color: $border-active;
          color: $brand-start;
        }
      }

      .el-pager li {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid $border;
        border-radius: $radius-sm;
        color: $text-secondary;
        margin: 0 2px;

        &:hover {
          border-color: $border-active;
          color: $brand-start;
        }

        &.is-active {
          background: $gradient-brand;
          border-color: transparent;
          color: #fff;
        }
      }

      .el-pagination__total {
        color: $text-muted;
      }

      .el-pagination__sizes {
        .el-input__wrapper {
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid $border;
          border-radius: $radius-sm;
          box-shadow: none;

          &:hover {
            border-color: $border-active;
          }
        }

        .el-input__inner {
          color: $text-secondary;
        }
      }
    }
  }
}
</style>
