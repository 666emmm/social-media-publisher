/**
 * 内容解析工具 — 将混合平台文案拆分为各平台的标题/描述/标签。
 *
 * 使用方式：
 *   import { parseContent, removeChineseLines, removeEnglishLines } from '@/utils/contentParser'
 */

// ---------------------------------------------------------------------------
// 平台名 → 前端 key 映射
// ---------------------------------------------------------------------------
const PLATFORM_ALIASES = {
  xiaohongshu: ['小红书', 'xiaohongshu', 'redbook', 'xhs'],
  channels: ['视频号', '微信视频号', 'channels', 'wechat', 'wechat channels'],
  douyin: ['抖音', 'douyin', 'tiktok中国'],
  kuaishou: ['快手', 'kuaishou'],
  bilibili: ['B站', 'bilibili', 'b站'],
  baijiahao: ['百家号', 'baijiahao'],
  tiktok: ['TikTok', 'tiktok', 'tt'],
  youtube: ['YouTube', 'youtube', 'yt', '油管'],
  tencent_video: ['腾讯视频', 'tencent_video'],
  iqiyi: ['爱奇艺', 'iqiyi'],
  weibo: ['微博', 'weibo'],
  alipay: ['支付宝', 'alipay'],
  toutiao: ['今日头条', '头条', 'toutiao'],
  zhihu: ['知乎', 'zhihu'],
  csdn: ['CSDN', 'csdn'],
  x: ['X', 'x', 'Twitter', 'twitter', '推特'],
};

// 按别名长度降序排列（长的先匹配，避免"微信视频号"被"微信"截胡）
const HEADER_PLATFORM_KEYS = Object.keys(PLATFORM_ALIASES).sort(
  (a, b) => Math.max(...PLATFORM_ALIASES[b].map(s => s.length)) - Math.max(...PLATFORM_ALIASES[a].map(s => s.length))
);

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

/** 标准化标题行（去掉 markdown 标记、多余空格） */
function normalizeHeading(text) {
  let cleaned = text.trim();
  cleaned = cleaned.replace(/^#{1,6}\s*/, '');
  cleaned = cleaned.replace(/[*_`]/g, '').trim();
  cleaned = cleaned.replace(/\s+/g, ' ');
  return cleaned;
}

/** 清理内容行 */
function cleanLine(text) {
  return text.trim().replace(/[*_`]/g, '').trim();
}

/** 判断是否包含中文 */
function hasChinese(text) {
  return /[\u4e00-\u9fff]/.test(text);
}

// ---------------------------------------------------------------------------
// 导出：删除中文 / 删除英文
// ---------------------------------------------------------------------------

export function removeChineseLines(text) {
  if (!text) return ''
  return text
    .split('\n')
    .map(line => cleanLine(line).replace(/[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]/g, '').replace(/[（()）【】「」『』《》〈〉]/g, ''))
    .filter(line => line.trim())
    .join('\n')
}

export function removeEnglishLines(text) {
  if (!text) return ''
  return text
    .split('\n')
    .map(line => cleanLine(line).replace(/[a-zA-Z0-9]/g, '').replace(/[（）()\[\]{}【】「」『』《》〈〉]/g, '').replace(/\s+/g, ''))
    .filter(line => line.trim() && hasChinese(line))
    .join('\n')
}

// ---------------------------------------------------------------------------
// 核心：按平台拆分内容块
// ---------------------------------------------------------------------------

function splitPlatformBlocks(rawText) {
  const blocks = {};
  for (const key of Object.keys(PLATFORM_ALIASES)) {
    blocks[key] = '';
  }

  if (!rawText.trim()) return blocks;

  let currentPlatform = null;
  let currentLines = [];

  function flush() {
    if (currentPlatform) {
      blocks[currentPlatform] = currentLines.join('\n').trim();
    }
    currentLines = [];
  }

  const lines = rawText.split('\n');
  for (const line of lines) {
    const stripped = line.trim();
    if (!stripped || ['---', '***', '___'].includes(stripped)) continue;

    const heading = normalizeHeading(stripped);
    const headingLower = heading.toLowerCase();
    let matched = null;

    for (const platformKey of HEADER_PLATFORM_KEYS) {
      const aliases = PLATFORM_ALIASES[platformKey];
      if (
        aliases.includes(heading) ||
        aliases.map(a => a.toLowerCase()).includes(headingLower) ||
        aliases.some(a => heading.startsWith(a) || headingLower.startsWith(a.toLowerCase()))
      ) {
        matched = platformKey;
        break;
      }
    }

    if (matched) {
      flush();
      currentPlatform = matched;
      continue;
    }

    if (currentPlatform) {
      currentLines.push(line);
    }
  }

  flush();
  return blocks;
}

// ---------------------------------------------------------------------------
// 提取标签（从文本中识别 #tag）
// ---------------------------------------------------------------------------

function extractTags(text) {
  if (!text) return { tags: [], cleanText: '' };
  const tags = [];
  let cleanText = text;
  const tagRegex = /#([\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af-]+)/g;
  let match;
  while ((match = tagRegex.exec(text)) !== null) {
    tags.push(match[1]);
  }
  cleanText = text.replace(tagRegex, '').replace(/\n{3,}/g, '\n\n').trim();
  return { tags, cleanText };
}

// ---------------------------------------------------------------------------
// 平台特定解析
// ---------------------------------------------------------------------------

function parsePlatformText(platformKey, block) {
  let title = '';
  let description = '';
  let tags = [];

  if (!block) return { title, description, tags };

  if (platformKey === 'youtube' || platformKey === 'bilibili') {
    // YouTube / B站：第一行是标题，后面是描述+标签
    const lines = block.split('\n').map(cleanLine).filter(l => l);
    if (lines.length > 0) {
      title = lines[0];
      const titleResult = extractTags(title);
      if (titleResult.tags.length > 0) {
        title = titleResult.cleanText;
        tags.push(...titleResult.tags);
      }
      const rest = lines.slice(1).join('\n');
      const descResult = extractTags(rest);
      description = descResult.cleanText;
      tags.push(...descResult.tags);
    }
  } else {
    // 其他平台：整体是描述+标签
    const result = extractTags(block);
    description = result.cleanText;
    tags = result.tags;
  }

  return { title, description, tags };
}

// ---------------------------------------------------------------------------
// 主入口
// ---------------------------------------------------------------------------

/**
 * 解析混合平台文案
 *
 * @param {string} rawText - 原始文案
 * @param {{ removeChinese?: boolean, removeEnglish?: boolean }} options
 * @returns {Record<string, { title: string, description: string, tags: string[] }>}
 */
export function parseContent(rawText, options = {}) {
  const { removeChinese = false, removeEnglish = false } = options;

  // 第一步：如果需要，做语言过滤
  let processed = rawText || '';
  if (removeChinese) {
    processed = processed
      .split('\n')
      .map(line => cleanLine(line).replace(/[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]/g, '').replace(/[（()）【】「」『』《》〈〉]/g, ''))
      .filter(line => line.trim())
      .join('\n')
  }
  if (removeEnglish) {
    processed = processed
      .split('\n')
      .map(line => cleanLine(line).replace(/[a-zA-Z0-9]/g, '').replace(/[（）()\[\]{}【】「」『』《》〈〉]/g, '').replace(/\s+/g, ''))
      .filter(line => line.trim() && hasChinese(line))
      .join('\n')
  }

  // 第二步：拆块
  const blocks = splitPlatformBlocks(processed);

  // 第三步：逐平台解析
  const result = {};
  for (const [key, block] of Object.entries(blocks)) {
    if (!block) continue;
    result[key] = parsePlatformText(key, block);
  }

  return result;
}
