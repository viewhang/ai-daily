"""
RSS 订阅源读取并保存到


"""

import html
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List

import feedparser


class RSSDigest:
    def __init__(self, hours_limit: int = 24, max_workers: int = 10):
        self.hours_limit = hours_limit
        self.cutoff_time = datetime.now() - timedelta(hours=hours_limit)
        self.max_workers = max_workers

    def parse_opml(self, opml_path: str) -> List[Dict]:
        """解析 OPML 获取订阅源列表"""
        tree = ET.parse(opml_path)
        root = tree.getroot()
        feeds = []

        for outline in root.findall(".//outline[@type='rss']"):
            feeds.append(
                {
                    "name": outline.get("title", "Unknown"),
                    "url": outline.get("xmlUrl"),
                    "category": outline.get("category", "未分类"),
                }
            )
        return feeds

    def fetch_entries(self, feed_info: Dict) -> List[Dict]:
        """获取单个源的条目"""
        entries = []
        try:
            feed = feedparser.parse(feed_info["url"])

            for entry in feed.entries:
                # 解析时间
                pub_date = None
                if hasattr(entry, "published_parsed"):
                    pub_date = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed"):
                    pub_date = datetime(*entry.updated_parsed[:6])

                # 时间过滤
                if pub_date and pub_date < self.cutoff_time:
                    continue

                # 提取内容（优先使用 description，其次 summary/content）
                content = ""
                if hasattr(entry, "description"):
                    content = entry.description
                elif hasattr(entry, "summary"):
                    content = entry.summary
                elif hasattr(entry, "content"):
                    content = entry.content[0].value if entry.content else ""

                entries.append(
                    {
                        "title": entry.get("title", "无标题"),
                        "link": entry.get("link", "#"),
                        "published": pub_date or datetime.now(),
                        "source": feed_info["name"],
                        "category": feed_info["category"],
                        "content": content,  # 保留原始 HTML
                        "author": entry.get(
                            "author", entry.get("dc_creator", feed_info["name"])
                        ),
                    }
                )
        except Exception as e:
            print(f"⚠️ 获取失败 {feed_info['name']}: {e}")

        return entries

    def fetch_all_entries(self, feeds: List[Dict]) -> List[Dict]:
        """并发获取所有源的条目"""
        all_entries = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_feed = {
                executor.submit(self.fetch_entries, feed): feed for feed in feeds
            }

            for future in as_completed(future_to_feed):
                feed = future_to_feed[future]
                try:
                    entries = future.result()
                    all_entries.extend(entries)
                    print(f"📡 {feed['name']}: {len(entries)} 条")
                except Exception as e:
                    print(f"⚠️ 获取失败 {feed['name']}: {e}")

        return all_entries

    def generate_html(self, entries: List[Dict], output: str = "rss_digest.html"):
        """生成阅读友好的 HTML"""
        if not entries:
            print("⚠️ 没有获取到任何条目")
            return

        # 按日期分组排序
        entries.sort(key=lambda x: x["published"], reverse=True)
        grouped = defaultdict(list)
        for e in entries:
            date_key = e["published"].strftime("%Y-%m-%d (%a)")
            grouped[date_key].append(e)

        # 生成来源过滤选项
        sources = sorted(set(e["source"] for e in entries))
        source_filters = "\n".join(
            [
                f'<button class="filter-btn" onclick="filterSource(\'{html.escape(s)}\')">{html.escape(s)}</button>'
                for s in sources
            ]
        )

        # 生成内容卡片
        cards_html = ""
        for date, items in sorted(grouped.items(), reverse=True):
            cards_html += (
                f'<div class="date-group"><h2 class="date-header">📅 {date}</h2>'
            )

            for item in items:
                time_str = item["published"].strftime("%H:%M")
                # 对 title 和 source 做 HTML 转义，但 content 保持原样（因为是富文本）
                safe_title = html.escape(item["title"])
                safe_source = html.escape(item["source"])
                safe_author = html.escape(item["author"])

                cards_html += f"""
                <article class="card" data-source="{safe_source}">
                    <div class="card-header">
                        <div class="meta">
                            <span class="source-tag">{safe_source}</span>
                            <span class="time">🕐 {time_str}</span>
                            <span class="author">👤 {safe_author}</span>
                        </div>
                        <h3 class="title">
                            <a href="{item["link"]}" target="_blank" rel="noopener">{safe_title}</a>
                        </h3>
                    </div>
                    <div class="content-body">
                        {item["content"]}
                    </div>
                    <div class="card-footer">
                        <a href="{item["link"]}" target="_blank" class="read-original">查看原文 →</a>
                    </div>
                </article>
                """
            cards_html += "</div>"

        html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RSS 阅读 - 过去{self.hours_limit}小时</title>
    <style>
        :root {{
            --bg: #f5f5f0;
            --card: #ffffff;
            --text: #1a1a1a;
            --text-secondary: #666666;
            --accent: #0066cc;
            --border: #e0e0e0;
            --hover: #f0f7ff;
        }}

        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg: #1a1a1a;
                --card: #2d2d2d;
                --text: #e0e0e0;
                --text-secondary: #999999;
                --accent: #4da6ff;
                --border: #404040;
                --hover: #3d3d3d;
            }}
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 20px;
        }}

        .container {{
            max-width: 800px;
            margin: 0 auto;
        }}

        header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
        }}

        h1 {{ font-size: 1.8em; margin-bottom: 10px; }}

        .stats {{
            color: var(--text-secondary);
            font-size: 0.9em;
            margin-bottom: 20px;
        }}

        .controls {{
            background: var(--card);
            padding: 15px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            position: sticky;
            top: 10px;
            z-index: 100;
        }}

        .search-box {{
            width: 100%;
            padding: 10px 15px;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--bg);
            color: var(--text);
            font-size: 14px;
            margin-bottom: 10px;
        }}

        .filter-group {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}

        .filter-btn {{
            padding: 6px 12px;
            border: 1px solid var(--border);
            background: var(--bg);
            color: var(--text-secondary);
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.85em;
            transition: all 0.2s;
        }}

        .filter-btn:hover, .filter-btn.active {{
            background: var(--accent);
            color: white;
            border-color: var(--accent);
        }}

        .date-group {{
            margin-bottom: 30px;
        }}

        .date-header {{
            font-size: 1.1em;
            color: var(--text-secondary);
            margin-bottom: 15px;
            padding-bottom: 8px;
            border-bottom: 2px solid var(--border);
        }}

        .card {{
            background: var(--card);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            border: 1px solid var(--border);
            transition: transform 0.2s;
        }}

        .card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}

        .card-header {{
            margin-bottom: 15px;
        }}

        .meta {{
            display: flex;
            gap: 12px;
            align-items: center;
            margin-bottom: 8px;
            flex-wrap: wrap;
            font-size: 0.85em;
        }}

        .source-tag {{
            background: rgba(0,102,204,0.1);
            color: var(--accent);
            padding: 2px 10px;
            border-radius: 12px;
            font-weight: 500;
        }}

        .time, .author {{
            color: var(--text-secondary);
        }}

        .title {{
            font-size: 1.25em;
            line-height: 1.4;
        }}

        .title a {{
            color: var(--text);
            text-decoration: none;
        }}

        .title a:hover {{
            color: var(--accent);
            text-decoration: underline;
        }}

        .content-body {{
            color: var(--text-secondary);
            line-height: 1.8;
            margin: 15px 0;
            overflow-wrap: break-word;
        }}

        /* 针对 RSS 中常见 HTML 元素的样式重置 */
        .content-body img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            margin: 10px 0;
        }}

        .content-body video {{
            max-width: 100%;
            border-radius: 8px;
        }}

        .content-body a {{
            color: var(--accent);
            text-decoration: none;
        }}

        .content-body a:hover {{
            text-decoration: underline;
        }}

        .content-body blockquote {{
            border-left: 3px solid var(--accent);
            padding-left: 15px;
            margin: 10px 0;
            color: var(--text-secondary);
        }}

        .card-footer {{
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid var(--border);
        }}

        .read-original {{
            color: var(--accent);
            text-decoration: none;
            font-size: 0.9em;
            font-weight: 500;
        }}

        .hidden {{ display: none !important; }}

        @media (max-width: 600px) {{
            body {{ padding: 10px; }}
            .card {{ padding: 15px; }}
            .title {{ font-size: 1.1em; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📰 RSS 摘要</h1>
            <div class="stats">过去{self.hours_limit}小时 • 共 {len(entries)} 条</div>
        </header>

        <div class="controls">
            <input type="text" class="search-box" placeholder="搜索标题..."
                   oninput="filterText(this.value)">
            <div class="filter-group">
                <button class="filter-btn active" onclick="filterSource('all')">全部</button>
                {source_filters}
            </div>
        </div>

        <main>
            {cards_html}
        </main>
    </div>

    <script>
        function filterSource(source) {{
            document.querySelectorAll('.filter-btn').forEach(btn => {{
                btn.classList.remove('active');
                if(btn.textContent === source || (source === 'all' && btn.textContent === '全部')) {{
                    btn.classList.add('active');
                }}
            }});

            document.querySelectorAll('.card').forEach(card => {{
                if (source === 'all' || card.dataset.source === source) {{
                    card.classList.remove('hidden');
                }} else {{
                    card.classList.add('hidden');
                }}
            }});
        }}

        function filterText(keyword) {{
            const lower = keyword.toLowerCase();
            document.querySelectorAll('.card').forEach(card => {{
                const text = card.innerText.toLowerCase();
                card.classList.toggle('hidden', !text.includes(lower));
            }});
        }}
    </script>
</body>
</html>
"""

        with open(output, "w", encoding="utf-8") as f:
            f.write(html_template)

        print(f"✅ 已生成: {output} ({len(entries)} 条)")
        return output


# 使用示例
if __name__ == "__main__":
    start_time = time.time()

    digest = RSSDigest(hours_limit=24, max_workers=10)
    feeds = digest.parse_opml("resources/rss.ompl")

    all_entries = digest.fetch_all_entries(feeds)

    elapsed = time.time() - start_time

    if all_entries:
        digest.generate_html(all_entries, "resources/rss_reader.html")
    else:
        print("⚠️ 未获取到内容")

    print(f"⏱️ 总耗时: {elapsed:.2f}秒")
