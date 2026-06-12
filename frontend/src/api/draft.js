import { http } from '@/utils/request'

export const draftApi = {
  getDrafts(type) {
    const params = type ? `?type=${type}` : ''
    return http.get(`/api/v2/drafts${params}`)
  },
  createDraft(data) {
    return http.post('/api/v2/drafts', data)
  },
  getDraft(id) {
    return http.get(`/api/v2/drafts/${id}`)
  },
  updateDraft(id, data) {
    return http.put(`/api/v2/drafts/${id}`, data)
  },
  deleteDraft(id) {
    return http.delete(`/api/v2/drafts/${id}`)
  },
  // 草稿批量发布（视频）
  batchPublishVideoDrafts(draftIds) {
    return http.post('/api/v2/drafts/batch-publish', { draft_ids: draftIds })
  },
  // 草稿批量删除
  batchDeleteDrafts(draftIds) {
    return http.delete('/api/v2/drafts/batch', { data: { draft_ids: draftIds } })
  },
}
