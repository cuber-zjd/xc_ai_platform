"""保守正文清洗：只移除明确界面行，疑似业务资料保留待核。"""

import re
from hashlib import sha256
from typing import Any


UI_LINES = frozenset({"首页", "登录", "注册", "联系我们", "分享", "收藏", "取消", "进入全屏",
                      "点击按住可拖动视频", "打开今日头条查看完整视频", "直播", "00:00", "Reset", "Send",
                      "重設", "送出", "扫码下载智通APP", "退出", "切换繁体",
                      "第一步： 点击底部工具", '第二步： 在弹出框中点击"添加到主屏幕"'})


def assess_body(content: str, title: str = "") -> tuple[str, dict[str, Any]]:
    original = content or ""
    kept, removed, seen = [], [], set()
    for line in original.splitlines():
        plain = line.strip()
        if plain in UI_LINES:
            removed.append({"reason": "界面控件", "text": line})
            continue
        # 只去掉完全重复的长段落；短标签、表头和数字行可能有业务含义。
        if len(plain) >= 100 and plain in seen:
            removed.append({"reason": "完全重复长段落", "text": line})
            continue
        if plain:
            seen.add(plain)
        kept.append(line)
    cleaned = "\n".join(kept).strip()
    readable = re.sub(r"!?\[([^\]]*)\]\([^\n)]*\)", r"\1", cleaned)
    readable = re.sub(r"https?://\S+", "", readable)
    flags = []
    kind = "article"
    if any(word in title for word in ("企查查", "天眼查", "厂家批发", "供应商", "产品报价")):
        kind = "reference"
        flags.append("企业档案或供需资料，不等同新闻正文")
    if "查看完整视频" in original or "点击按住可拖动视频" in original:
        kind = "video_description"
        flags.append("视频文字简介，未核验视频全文")
    links = len(re.findall(r"\]\(https?://", cleaned))
    if links > 20:
        flags.append("链接密集，疑似推荐或导航混入")
    # 免责声明也可能是公告正文；只标记待核，不按关键词截掉后续业务事实。
    if re.search(r"(?im)^\s*[|#* ]*(?:disclaimer|免責聲明|免责声明)\s*[|* ]*$", cleaned):
        flags.append("含独立免责声明区域，需确认正文边界")
    if re.search(r"(?i)\]\(<?javascript:", cleaned):
        flags.append("含网页交互控件链接，需确认正文污染")
    if re.search(r"(?im)^\s*[|#* ]*(?:sitemap|網站地圖|网站地图)\s*[|* ]*$", cleaned):
        flags.append("含网站地图区域，需确认正文边界")
    if sum(cleaned.count(x) for x in ("网站地图", "用户协议", "隐私政策", "联系我们", "登录", "注册")) >= 5:
        flags.append("导航或登录区域残留")
    if re.search(r"(?:全文|剩余内容|阅读全文).{0,15}(?:登录|付费|订阅)|(?:订阅|登录).{0,15}(?:全文|剩余内容)", readable):
        flags.append("疑似付费或登录截断")
    if readable.rstrip().endswith(("...", "…", "...\\")):
        flags.append("结尾疑似截断")
    if len(readable.strip()) < 200:
        flags.append("有效文字不足200字，保留待核")
    # 标题匹配只提示，不据此丢弃；改写标题、英文缩写可能导致误报。
    terms = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", title)
    grams = [part[i:i+3] for part in terms for i in range(max(1, len(part)-2))]
    if grams and not any(word.lower() in readable.lower() for word in grams):
        flags.append("标题与正文未找到共同词，需核对")
    return cleaned, {"version": 2, "status": "needs_review" if flags else "passed_rules",
                     "kind": kind, "issues": flags, "original_chars": len(original),
                     "readable_chars": len(readable), "cleaned_chars": len(cleaned),
                     "original_sha256": sha256(original.encode()).hexdigest(),
                     "cleaned_sha256": sha256(cleaned.encode()).hexdigest(), "removed": removed}
