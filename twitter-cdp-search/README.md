# twitter-cdp-search

通过命令行搜索 Twitter/X，无需 API Key。

利用 Chrome DevTools Protocol (CDP) 读取已登录浏览器的搜索结果。不需要 Twitter API，不需要 Token，不需要申请开发者账号，没有频率限制——只需要你的浏览器。

## 原理

```
你（命令行） → Chrome CDP（端口 9222） → Twitter/X（已登录的会话）
```

脚本连接到一个开启了远程调试的 Chrome 实例，导航到 Twitter 搜索页，滚动加载推文，通过 DOM 查询提取内容。

## 安装

**1. 安装依赖**

```bash
pip install websocket-client
```

**2. 启动 Chrome（开启远程调试）**

macOS:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-debug
```

Linux:
```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

Windows:
```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 --user-data-dir=%TEMP%\chrome-debug
```

**3. 在该 Chrome 窗口中登录 Twitter/X**

## 用法

```bash
# 基本搜索
python3 twitter_search.py "bitcoin"

# 搜索某用户的推文
python3 twitter_search.py "from:elonmusk"

# 搜索中文推文
python3 twitter_search.py "@arc lang:zh-cn"

# 搜索标签
python3 twitter_search.py "#ethereum"

# 加载更多推文（增加滚动次数）
python3 twitter_search.py "solana" --scroll 10

# 限制返回数量
python3 twitter_search.py "crypto" --limit 20

# 输出 JSON（可以管道到文件或 jq）
python3 twitter_search.py "defi" --json > tweets.json
python3 twitter_search.py "nft" --json | jq '.[].text'

# 使用不同的 Chrome 调试端口
python3 twitter_search.py "web3" --port 9223

# 不自动导航，读取当前打开的页面
python3 twitter_search.py "" --no-open
```

## Twitter 搜索运算符

| 运算符 | 示例 | 说明 |
|--------|------|------|
| `from:` | `from:elonmusk` | 某用户发的推文 |
| `to:` | `to:elonmusk` | 回复某用户的推文 |
| `@` | `@vitalik` | 提及某用户 |
| `lang:` | `lang:zh-cn` | 按语言过滤 |
| `since:` | `since:2026-01-01` | 某日期之后 |
| `until:` | `until:2026-04-01` | 某日期之前 |
| `min_faves:` | `min_faves:100` | 最少点赞数 |
| `min_retweets:` | `min_retweets:50` | 最少转发数 |
| `filter:links` | `bitcoin filter:links` | 只看带链接的推文 |
| `filter:images` | `nft filter:images` | 只看带图片的推文 |
| `-` | `bitcoin -scam` | 排除关键词 |

可以组合使用：`"@arc lang:zh-cn since:2026-04-01 min_faves:10"`

## JSON 输出格式

```json
[
  {
    "user": "昵称 @handle ...",
    "text": "推文内容...",
    "time": "2026-04-13T08:30:00.000Z",
    "link": "https://x.com/handle/status/123456789"
  }
]
```

## 环境要求

- Python 3.10+
- `websocket-client` 包
- Chrome/Chromium 并启用 `--remote-debugging-port`
- 已登录的 Twitter/X 会话

## License

MIT
