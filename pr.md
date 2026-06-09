# 发布历史重设计 + 一键填写封面修复 — v0.6.0

## 概述

将发布历史从 4 张零散表（`publish_tasks` / `publish_logs` / `image_publish_tasks` / `image_publish_logs`）合并为统一的主-子表结构（`publish_batches` + `publish_details`），并把 `PublishHistory.vue` 从平铺表格重写为按"批次"分组的卡片式 UI。同步修了一键填写对话框的封面图 bug，并把 S3 视频下载缓存纳入了系统设置的"缓存清理"功能。

---

## 核心变更

### 1. 数据模型（`backend/init_db.py`）

- **删除**：`publish_tasks` / `publish_logs` / `image_publish_tasks` / `image_publish_logs` 共 4 张旧表
- **新增**：
  - `publish_batches`（主表）：每次"发布"=1 行，存标题/描述/封面素材 ID/视频素材 ID/图文素材 ID 集/整体状态/账号数
  - `publish_details`（明细表）：每账号 1 行，FK→`publish_batches.id`，存平台/账号/状态/错误信息/`publish_url`（预留字段）
- **索引**：`publish_batches.created_at`、`publish_batches.status`、`publish_details.batch_id`、`publish_details.status`、`publish_details.platform`
- 不做数据迁移（功能尚未正式使用）

### 2. 后端读取端点

- `GET /api/v2/history`：按 `publish_batches` 分组返回，每项含 `items[]` 明细子数组；支持 `type` / `status` / `timeRange` 过滤 + 分页
- `GET /api/v2/publish-templates`：读 `publish_batches` 中至少部分成功的批次，按 `account_configs` 非空过滤；`thumbnail_path` 解析为 `materials.stored_path`（commit `4152de1` 修复）
- `GET /api/v2/tasks`（TaskCenter 用）：从 `publish_details` 读，含 `batch_id` 关联 + `batch_title` 字段
- `GET /api/materials/{id}`（新增，供一键填写封面修复用）

### 3. 后端写入端点

- `POST /postVideo`：`_before_publish` 插 1 batch + 1 detail；`_after_publish` 聚合 batch 状态
- `POST /api/image-publish/publish`：单账号 + `batchId` 入参；不再插 `image_publish_tasks`/`image_publish_logs`
- `POST /api/image-publish/drafts/execute-publish`：同步新表
- `task_queue.py`：`PublishTask` 加 `batch_id` 字段；`_insert_db` / `_update_db` 重写
- 全部接受新参数：`batchId` / `videoMaterialId` / `landscapeCoverMaterialId` / `portraitCoverMaterialId` / `accountId`
- `thumbnailLandscape` / `thumbnailPortrait` 存进 `account_configs` JSON（commit `49bd6de` 修复），供 `_resolve_cover_url` 在 material_id 缺失时回退

### 4. 前端改造

- **`PublishHistory.vue` 完全重写**：从 `<el-table>` 改为卡片列表（封面+标题+描述+账号汇总+状态徽标+时间），点击展开内联明细（账号/平台/耗时/状态/错误/publish_url）；stat cards / filter / pagination 全部保留，加了 `typeFilter`（视频/图文/全部）
- **`PublishCenter.vue`**：`publishAll()` 入口生成 UUID 作为 `batchId`；每次 `/postVideo` 调用带上 `batchId` + 3 个素材 ID + `accountId`
- **`ImagePublish.vue` + 3 个 panel + `useChannelForm.js`**：循环 N 个账号，每次调 `/api/image-publish/publish`（单账号 + 共享 `batchId`）
- **`OneClickFillDialog.vue`**：封面 URL 改为走 `/api/materials/file/{path}`（之前是 `/uploads/...` 不通）
- **`TaskCenter.vue`**：字段名 `title` → `batch_title` 适配
- **`api/v2.js`**：`historyApi` 注释更新
- **`platforms.js`**：加 `platformNameToKey` 映射（一键填写按平台填 platformConfigs 时用）

### 5. 一键填写 bug 修复

- 封面图：`OneClickFillDialog.vue` 调用 `/api/materials/list?id=X`，但 list 端点不识别 `id` 参数（静默忽略），导致图文物料封面错乱。改为调用新的 `GET /api/materials/{id}` 端点
- 账号复原：原 `handleOneClickFill` 只填 `platformConfigs`，不动 `publishAccountIds`。现在按模板 `channels` 自动勾选对应平台下所有账号
- 表单填入：原代码把 `record.account_configs` 当成平台嵌套 dict 处理（实际是单 detail 扁平配置），字符串字段被 `typeof === 'object'` 过滤掉，导致表单一直没填。改为按 `channels` 逐个平台应用单份配置
- 中英文 key 不匹配：`platformConfigs` 用英文 key（`douyin`），`channels[].platform` 是中文名（`抖音`），写入了不存在的 key。修复：加 `platformNameToKey` 映射

### 6. S3 视频缓存管理

- `_download_s3_to_cache` 在帧提取前把 S3 视频下载到 `data/s3_video_cache/`（ffmpeg 需要本地文件）
- 308MB 起步且持续累积的运行时缓存
- 修复：
  - 加进 `.gitignore`（`data/s3_video_cache/`）
  - 系统设置 → 缓存管理 → 新增"S3 视频缓存"清理项

### 7. 杂项

- 版本号 `0.5.0` → `0.6.0`
- 删除 `/api/image-publish/history` 端点（前端的图片历史统一走 `/api/v2/history?type=image`）
- `start.bat` 换行符统一为 CRLF

---

## 文件变更统计

```
38 files changed, 7964 insertions(+), 1491 deletions(-)
```

**主要文件**：
- 后端：`init_db.py` (-76/+48)、`app.py` (-24/+83)、`blueprints/image_publish_bp.py` (-121/+91)、`blueprints/materials_bp.py` (+17)、`ext_api/__init__.py`（多处）、`ext_api/task_queue.py`、`routes/frames.py` (+26)
- 前端：`PublishHistory.vue`（完全重写，683 行）、`PublishCenter.vue`、`ImagePublish.vue`、`OneClickFillDialog.vue`、`TaskCenter.vue`、`Settings.vue`、`platforms.js`、`useChannelForm.js`、3 个 image panel
- 测试：7 个测试文件
- 文档：`specs/2026-06-08-publish-history-redesign-design.md`、`plans/2026-06-08-publish-history-redesign.md`

---

## 测试

- 后端：40/40 通过
- 前端构建：0 error
- 端到端 curl 冒烟：5/5 关键端点正常

---

## 测试计划

合并后人工验证：
- [ ] PublishCenter 选 2 个账号发布一次 → DB 有 1 batch + 2 detail
- [ ] PublishHistory 显示 1 张卡片（不是 2 张），展开后看到 2 行明细
- [ ] ImagePublish 选 2 个图文账号发布 → DB 有 1 batch + 2 detail
- [ ] PublishHistory `typeFilter` 切换"视频/图文/全部"过滤正常
- [ ] 视频一键填写：封面图正常显示（`/api/materials/file/...` 走得通）
- [ ] 图文一键填写：封面图正常显示（封面 bug 已修）
- [ ] 一键填写选中后：账号被自动勾选 + 平台表单字段被自动填入
- [ ] TaskCenter 显示任务列表，含 `batch_title` 列
- [ ] 系统设置 → 缓存管理：3 项缓存都有正确的 count + size + 清理按钮

---

## 注意事项

- 已有 legacy 数据（如果有）需要走一次性迁移脚本。本分支内不做迁移（功能未正式使用 + 用户明确要求"不需要迁移历史表"）
- `create_task` POST 端点仍写旧 `publish_tasks` 表。当前没有前端调用，TaskCenter 只用 GET；如需启用 POST 再补迁移
- `/api/v2/stats` 之前查询 `publish_tasks` 全部 500，已在 commit `b4d16e6` 修复（改读 `publish_batches` + `publish_details`）
