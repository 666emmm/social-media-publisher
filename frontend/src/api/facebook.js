import { http } from "@/utils/request"

// Facebook 公共主页相关 API（后端 blueprint: backend/blueprints/facebook_bp.py）
export const facebookApi = {
  // 获取账号管理的公共主页列表
  getPages(accountId) {
    return http.get(`/api/facebook/pages?account_id=${accountId}`)
  },
}
