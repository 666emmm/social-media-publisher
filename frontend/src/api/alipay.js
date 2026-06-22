import { http } from '@/utils/request'

// 支付宝内容创作平台相关 API(后端 blueprint: backend/blueprints/alipay_bp.py)
export const alipayApi = {
  // 搜索合集(后端通过 CloakBrowser 拦截 queryCompilationsByPublicId.json)
  searchCompilation(accountId, keyword) {
    return http.get(`/api/alipay/compilation-search?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}`)
  },

  // 获取图集背景音乐列表(后端打开 short-content 页 + 拦截音乐列表接口,分页)
  musicList(accountId, pageNum = 1) {
    return http.get(`/api/alipay/music-list?account_id=${accountId}&page_num=${pageNum}`)
  },
}
