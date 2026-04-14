#!/usr/bin/env python3
"""
Twitter/X 搜索工具 - 通过 Chrome DevTools Protocol (CDP) 搜索推特。

无需 API Key，无需 Token，无需申请开发者账号。
只需要一个已登录 Twitter/X 的 Chrome 浏览器。

原理：
  你(命令行) → Chrome CDP(端口9222) → Twitter/X(已登录的会话)

用法：
  python3 twitter_search.py "bitcoin"
  python3 twitter_search.py "@elonmusk lang:en"
  python3 twitter_search.py "from:vitalik" --scroll 10 --limit 50
  python3 twitter_search.py "defi" --json > tweets.json

前提：
  1. pip install websocket-client
  2. Chrome 以远程调试模式启动：
     /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
       --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
  3. 在该 Chrome 窗口中登录 Twitter/X
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request

import websocket


# 默认 Chrome 远程调试端口
DEFAULT_CDP_PORT = 9222

# ── 推文提取 JS ──────────────────────────────────────────────
# 在浏览器中执行，遍历页面上所有 tweet article 元素，
# 提取用户名、正文、时间、链接，并去重后返回 JSON 数组。
EXTRACT_JS = """
(() => {
    const tweets = [];
    const seen = new Set();
    document.querySelectorAll('article[data-testid="tweet"]').forEach(article => {
        // 用户名区域（包含昵称和 @handle）
        const userEl = article.querySelector('[data-testid="User-Name"]');
        // 推文正文
        const textEl = article.querySelector('[data-testid="tweetText"]');
        // 发布时间
        const timeEl = article.querySelector('time');
        // 推文永久链接
        const linkEl = article.querySelector('a[href*="/status/"]');

        const user = userEl ? userEl.innerText.replace(/\\n/g, ' ') : '';
        const text = textEl ? textEl.innerText : '';
        const dt = timeEl ? timeEl.getAttribute('datetime') : '';
        const link = linkEl ? linkEl.href : '';

        if (text) {
            // 用 用户名前30字+正文前50字 作为去重 key
            const key = user.slice(0, 30) + text.slice(0, 50);
            if (!seen.has(key)) {
                seen.add(key);
                tweets.push({user, text, time: dt, link});
            }
        }
    });
    return JSON.stringify(tweets);
})()
"""


class CDPClient:
    """Chrome DevTools Protocol 客户端，封装与 Chrome 的通信。"""

    def __init__(self, port: int = DEFAULT_CDP_PORT):
        self.base = f"http://localhost:{port}"
        self._mid = 0  # CDP 消息自增 ID

    def get_tabs(self) -> list[dict]:
        """获取 Chrome 所有标签页信息。"""
        return json.loads(urllib.request.urlopen(f"{self.base}/json", timeout=5).read())

    def find_tab(self, keyword: str) -> str | None:
        """根据 URL 关键词查找标签页，返回其 WebSocket 调试地址。"""
        for t in self.get_tabs():
            if t.get("type") == "page" and keyword in t.get("url", ""):
                return t.get("webSocketDebuggerUrl")
        return None

    def connect(self, ws_url: str):
        """建立 WebSocket 连接到指定标签页。"""
        return websocket.create_connection(ws_url, timeout=20, sslopt={"cert_reqs": ssl.CERT_NONE})

    def send(self, ws, method: str, params: dict | None = None) -> dict:
        """发送 CDP 命令并等待响应。"""
        self._mid += 1
        msg = {"id": self._mid, "method": method}
        if params:
            msg["params"] = params
        ws.send(json.dumps(msg))
        # 循环接收消息，直到收到与当前 ID 匹配的响应
        while True:
            resp = json.loads(ws.recv())
            if resp.get("id") == self._mid:
                return resp.get("result", {})

    def open_search(self, query: str) -> str | None:
        """导航到 Twitter 搜索页面，返回该页面的 WebSocket 调试地址。"""
        encoded = urllib.parse.quote(query)
        url = f"https://x.com/search?q={encoded}&src=typed_query"

        # 优先复用已有的搜索标签页（避免开太多 tab）
        for t in self.get_tabs():
            if t.get("type") == "page" and "x.com/search" in t.get("url", ""):
                ws_url = t["webSocketDebuggerUrl"]
                ws = self.connect(ws_url)
                self.send(ws, "Page.navigate", {"url": url})
                ws.close()
                time.sleep(4)  # 等待页面加载
                return self.find_tab("x.com/search")

        # 没有已有搜索页，新开一个标签页
        try:
            new_tab = json.loads(
                urllib.request.urlopen(
                    f"{self.base}/json/new?{urllib.parse.quote(url, safe='')}",
                    timeout=5,
                ).read()
            )
            time.sleep(4)  # 等待页面加载
            return new_tab.get("webSocketDebuggerUrl") or self.find_tab("x.com/search")
        except Exception:
            return None


def extract_tweets(cdp: CDPClient, ws, scroll_times: int = 3) -> list[dict]:
    """提取页面上的推文，通过滚动页面加载更多内容。

    Args:
        cdp: CDP 客户端实例
        ws: WebSocket 连接
        scroll_times: 滚动次数，越多加载越多推文

    Returns:
        去重后的推文列表
    """
    all_tweets = []
    seen_keys = set()

    for i in range(scroll_times + 1):
        # 第一次直接提取，之后每次先滚动到底部再提取
        if i > 0:
            cdp.send(ws, "Runtime.evaluate",
                     {"expression": "window.scrollTo(0, document.body.scrollHeight)"})
            time.sleep(2.5)  # 等待新内容加载

        # 执行 JS 提取当前页面上的推文
        result = cdp.send(ws, "Runtime.evaluate",
                          {"expression": EXTRACT_JS, "returnByValue": True})
        data = json.loads(result.get("result", {}).get("value", "[]"))

        # 去重合并
        for t in data:
            key = t["user"][:30] + t["text"][:50]
            if key not in seen_keys:
                seen_keys.add(key)
                all_tweets.append(t)

        print(f"\r  已加载 {len(all_tweets)} 条推文（滚动 {i}/{scroll_times}）", end="", file=sys.stderr)

    print(file=sys.stderr)
    return all_tweets


def format_tweets(tweets: list[dict]) -> str:
    """将推文列表格式化为终端可读的文本。"""
    lines = [f"共找到 {len(tweets)} 条推文:\n"]
    for i, t in enumerate(tweets, 1):
        date_str = t["time"][:10] if t.get("time") else "未知"
        # 分离昵称和 @handle
        user_parts = t.get("user", "").split(" @")
        name = user_parts[0]
        handle = f"@{user_parts[1].split(' ')[0]}" if len(user_parts) > 1 else ""
        lines.append(f"[{i}] {name} {handle}  ({date_str})")
        text = t.get("text", "")
        lines.append(f"    {text[:400]}")
        if len(text) > 400:
            lines.append(f"    ...（共 {len(text)} 字）")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="推特搜索工具 - 通过 Chrome CDP 搜索 Twitter/X",
        epilog="需要 Chrome 以 --remote-debugging-port=9222 启动，并已登录 Twitter。",
    )
    parser.add_argument("query", help="搜索关键词，如 '@arc lang:zh-cn', 'from:elonmusk', '#bitcoin'")
    parser.add_argument("--limit", type=int, default=100, help="最多返回条数（默认: 100）")
    parser.add_argument("--scroll", type=int, default=5, help="滚动次数，越多加载越多（默认: 5）")
    parser.add_argument("--port", type=int, default=DEFAULT_CDP_PORT, help="Chrome 调试端口（默认: 9222）")
    parser.add_argument("--no-open", action="store_true", help="不自动导航，读取当前打开的页面")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    cdp = CDPClient(port=args.port)

    # ── 1. 检查 Chrome 连接 ──
    try:
        cdp.get_tabs()
    except Exception:
        print(f"错误：无法连接 Chrome（端口 {args.port}）。", file=sys.stderr)
        print(f"请先启动 Chrome：chrome --remote-debugging-port={args.port}", file=sys.stderr)
        sys.exit(1)

    # ── 2. 打开搜索页面 ──
    if args.no_open:
        ws_url = cdp.find_tab("x.com")
        if not ws_url:
            print("错误：未找到已打开的 Twitter 页面。", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"正在搜索: {args.query}", file=sys.stderr)
        ws_url = cdp.open_search(args.query)
        if not ws_url:
            print("错误：无法打开搜索页面。", file=sys.stderr)
            sys.exit(1)

    # ── 3. 提取推文 ──
    ws = cdp.connect(ws_url)
    tweets = extract_tweets(cdp, ws, scroll_times=args.scroll)
    ws.close()

    tweets = tweets[:args.limit]

    # ── 4. 输出结果 ──
    if args.json:
        print(json.dumps(tweets, ensure_ascii=False, indent=2))
    else:
        print(format_tweets(tweets))


if __name__ == "__main__":
    main()
