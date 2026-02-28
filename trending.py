#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI早报自动生成脚本
支持：Hugging Face Papers + 机器之心 + TechCrunch + GitHub Trending + 官方博客
"""

import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import feedparser
import requests
from bs4 import BeautifulSoup

# ==================== 配置区域 ====================
CONFIG = {
    "db_path": "ai_news.db",
    "output_dir": "./daily_reports",
    "retention_days": 7,  # 数据保留7天
    "request_timeout": 10,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "min_desc_length": 20,  # 最小描述长度过滤
}

# 信息源配置
SOURCES = {
    "hf_papers": {
        "name": "📄 Hugging Face Daily Papers",
        "type": "json_api",
    },
    "jiqizhixin": {
        "name": "🇨🇳 机器之心",
        "url": "https://www.jiqizhixin.com/rss",
        "type": "rss",
    },
    "techcrunch": {
        "name": "🇺🇸 TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "type": "rss",
    },
    "github_trending": {
        "name": "⭐ GitHub Trending (AI/ML)",
        "urls": [
            "https://github.com/trending/python?since=daily",
            "https://github.com/trending/jupyter-notebook?since=daily",
        ],
        "keywords": [
            "ai",
            "ml",
            "llm",
            "machine-learning",
            "deep-learning",
            "gpt",
            "neural",
            "pytorch",
            "tensorflow",
        ],
        "type": "web_scrape",
    },
    "openai": {
        "name": "🅾️ OpenAI Blog",
        "url": "https://openai.com/news/",
        "type": "web_scrape",
        "selectors": {
            "container": "div[class*='item']",  # 需要根据实际页面调整
            "title": "h3",
            "link": "a",
            "date": "time",
        },
    },
    "anthropic": {
        "name": "🅰️ Anthropic News",
        "url": "https://www.anthropic.com/news",
        "type": "web_scrape",
        "selectors": {
            "container": "article, .news-item, [class*='news'], [class*='post']",  # 修复：内部用单引号
            "title": "h2, h3, .title",
            "link": "a",
            "summary": "p, .description, [class*='excerpt']",  # 修复：内部用单引号
        },
    },
    "google_ai": {
        "name": "🔵 Google AI Blog",
        "url": "https://blog.google/technology/ai/",
        "type": "web_scrape",
        "selectors": {
            "container": "article, .post, [class*='story']",  # 修复：内部用单引号
            "title": "h2, h3, .headline",
            "link": "a",
        },
    },
}


# ==================== 数据库管理 ====================
class NewsDatabase:
    """管理已处理新闻的去重数据库"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_news (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE,
                title TEXT,
                source TEXT,
                content_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at ON processed_news(created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_source ON processed_news(source)
        """)
        self.conn.commit()

    def generate_id(self, url: str, title: str) -> str:
        """生成唯一ID（基于清理后的URL+标题）"""
        # 清理URL参数（去掉utm_source等追踪参数）
        clean_url = url.split("?")[0].rstrip("/").lower()
        # 清理标题（去掉空格和特殊字符，转小写）
        clean_title = re.sub(r"\s+", "", title).lower()[:50]
        content = f"{clean_url}|{clean_title}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def is_new(self, url: str, title: str) -> bool:
        """检查是否为新内容"""
        content_id = self.generate_id(url, title)
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM processed_news WHERE id = ?", (content_id,))
        return cursor.fetchone() is None

    def mark_as_processed(
        self, url: str, title: str, source: str, description: str = ""
    ):
        """标记为已处理"""
        content_id = self.generate_id(url, title)
        desc_hash = (
            hashlib.md5(description.encode("utf-8")).hexdigest()[:16]
            if description
            else ""
        )

        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO processed_news (id, url, title, source, content_hash) VALUES (?, ?, ?, ?, ?)",
                (content_id, url, title, source, desc_hash),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass

    def cleanup_old(self, days: int = 7):
        """清理N天前的记录"""
        cutoff = datetime.now() - timedelta(days=days)
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM processed_news WHERE created_at < ?", (cutoff.isoformat(),)
        )
        deleted = cursor.rowcount
        self.conn.commit()
        print(f"🗑️ 清理了 {deleted} 条过期记录")
        return deleted

    def get_stats(self) -> Dict:
        """获取统计信息"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT source, COUNT(*) FROM processed_news GROUP BY source")
        return dict(cursor.fetchall())


# ==================== 抓取器 ====================
class BaseFetcher:
    """基础抓取类"""

    def __init__(self, headers: Dict):
        self.headers = headers

    def fetch(self, url: str) -> Optional[str]:
        """获取网页内容"""
        try:
            time.sleep(0.5)  # 礼貌延迟
            response = requests.get(
                url, headers=self.headers, timeout=CONFIG["request_timeout"]
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"❌ 请求失败 {url}: {e}")
            return None


class HFPapersFetcher(BaseFetcher):
    """Hugging Face Daily Papers"""

    def fetch_papers(self) -> List[Dict]:
        try:
            response = requests.get(
                SOURCES["hf_papers"]["url"],
                headers=self.headers,
                timeout=CONFIG["request_timeout"],
            )
            data = response.json()

            papers = []
            for paper in data.get("papers", [])[:5]:  # 只取前5篇
                papers.append(
                    {
                        "title": paper.get("title", ""),
                        "url": f"https://huggingface.co/papers/{paper.get('id', '')}",
                        "summary": paper.get("summary", "")[:200] + "..."
                        if len(paper.get("summary", "")) > 200
                        else paper.get("summary", ""),
                        "authors": ", ".join(paper.get("authors", [])[:3]),
                        "source": "hf_papers",
                    }
                )
            return papers
        except Exception as e:
            print(f"❌ HF Papers获取失败: {e}")
            return []


class RSSFetcher(BaseFetcher):
    """RSS订阅抓取"""

    def fetch_feed(self, source_key: str) -> List[Dict]:
        config = SOURCES[source_key]
        try:
            feed = feedparser.parse(config["url"])
            articles = []

            for entry in feed.entries[:5]:  # 取前5条
                articles.append(
                    {
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "summary": entry.get("summary", entry.get("description", ""))[
                            :150
                        ],
                        "published": entry.get("published", ""),
                        "source": source_key,
                    }
                )
            return articles
        except Exception as e:
            print(f"❌ RSS获取失败 {source_key}: {e}")
            return []


class GitHubTrendingFetcher(BaseFetcher):
    """GitHub Trending抓取（AI相关项目）"""

    def fetch_trending(self) -> List[Dict]:
        repos = []
        keywords = SOURCES["github_trending"]["keywords"]

        for url in SOURCES["github_trending"]["urls"]:
            try:
                html = self.fetch(url)
                if not html:
                    continue

                soup = BeautifulSoup(html, "html.parser")
                articles = soup.find_all("article", class_="Box-row")

                for article in articles[:3]:  # 每种语言取前3
                    link = (
                        article.find("h2", class_="h3").find("a")
                        if article.find("h2", class_="h3")
                        else None
                    )
                    if not link:
                        continue

                    repo_name = (
                        link.get_text(strip=True).replace(" ", "").replace("\n", "")
                    )
                    repo_url = f"https://github.com{link['href']}"

                    desc_tag = article.find("p", class_="col-9")
                    description = desc_tag.get_text(strip=True) if desc_tag else ""

                    # 检查是否与AI相关（关键词匹配）
                    text_to_check = f"{repo_name} {description}".lower()
                    if any(kw in text_to_check for kw in keywords):
                        repos.append(
                            {
                                "title": f"⭐ {repo_name}",
                                "url": repo_url,
                                "summary": description[:120]
                                if description
                                else "热门AI开源项目",
                                "source": "github_trending",
                            }
                        )

            except Exception as e:
                print(f"❌ GitHub Trending获取失败: {e}")
                continue

        return repos[:5]  # 总共最多5个


class BlogScraper(BaseFetcher):
    """官方博客爬虫"""

    def scrape_blog(self, source_key: str) -> List[Dict]:
        config = SOURCES[source_key]
        articles = []

        try:
            html = self.fetch(config["url"])
            if not html:
                return []

            soup = BeautifulSoup(html, "html.parser")

            # 通用抓取逻辑（基于常见博客结构）
            containers = soup.find_all(
                ["article", "div"], class_=re.compile(r"post|entry|item|blog|news|card")
            )

            if not containers:
                # 如果找不到特定class，尝试找包含链接的标题
                containers = soup.find_all(["h2", "h3"], limit=5)

            for container in containers[:5]:
                try:
                    # 查找链接
                    link_tag = (
                        container.find("a") if container.name != "a" else container
                    )
                    if not link_tag or not link_tag.get("href"):
                        continue

                    url = link_tag["href"]
                    if url.startswith("/"):
                        base_url = "/".join(config["url"].split("/")[:3])
                        url = base_url + url

                    # 查找标题
                    title_tag = (
                        container.find(
                            ["h2", "h3", "h4", "span", "div"],
                            class_=re.compile(r"title|headline"),
                        )
                        or link_tag
                    )
                    title = title_tag.get_text(strip=True)

                    # 查找摘要
                    summary_tag = container.find(
                        ["p", "div"], class_=re.compile(r"summary|desc|excerpt|content")
                    )
                    summary = (
                        summary_tag.get_text(strip=True)[:150] if summary_tag else ""
                    )

                    if title and len(title) > 10:
                        articles.append(
                            {
                                "title": title,
                                "url": url,
                                "summary": summary,
                                "source": source_key,
                            }
                        )

                except Exception as e:
                    continue

        except Exception as e:
            print(f"❌ {source_key} 抓取失败: {e}")

        return articles


# ==================== 早报生成器 ====================
class ReportGenerator:
    """生成格式化的AI早报"""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(self, all_news: Dict[str, List[Dict]], stats: Dict) -> str:
        """生成Markdown格式早报"""
        today = datetime.now().strftime("%Y年%m月%d日")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        lines = [
            f"# 🤖 AI早报 - {today}",
            "",
            f"> 自动生成时间：{timestamp}",
            f"> 今日更新：学术论文 {stats.get('hf_papers', 0)} 条 | 产业新闻 {stats.get('jiqizhixin', 0) + stats.get('techcrunch', 0)} 条 | 开源项目 {stats.get('github_trending', 0)} 条 | 官方动态 {stats.get('openai', 0) + stats.get('anthropic', 0) + stats.get('google_ai', 0)} 条",
            "",
            "---",
            "",
        ]

        # 1. 学术论文
        if all_news.get("hf_papers"):
            lines.extend(["## 📄 今日论文 (Hugging Face)", ""])
            for item in all_news["hf_papers"]:
                lines.extend(
                    [
                        f"### {item['title']}",
                        f"👤 {item.get('authors', 'N/A')}  \n"
                        f"🔗 [查看详情]({item['url']})",
                        f"> {item.get('summary', '')}",
                        "",
                    ]
                )

        # 2. 产业新闻（中文）
        if all_news.get("jiqizhixin"):
            lines.extend(["## 🇨🇳 国内AI动态", ""])
            for item in all_news["jiqizhixin"]:
                lines.extend(self._format_news_item(item))

        # 3. 产业新闻（国际）
        if all_news.get("techcrunch"):
            lines.extend(["## 🇺🇸 国际AI动态", ""])
            for item in all_news["techcrunch"]:
                lines.extend(self._format_news_item(item))

        # 4. 官方博客
        official_news = (
            all_news.get("openai", [])
            + all_news.get("anthropic", [])
            + all_news.get("google_ai", [])
        )
        if official_news:
            lines.extend(["## 🏢 大厂官方动态", ""])
            source_emojis = {"openai": "🅾️", "anthropic": "🅰️", "google_ai": "🔵"}
            for item in official_news:
                emoji = source_emojis.get(item["source"], "🔹")
                lines.extend(
                    [
                        f"### {emoji} {item['title']}",
                        f"🔗 [阅读原文]({item['url']})",
                        f"> {item.get('summary', '')}",
                        "",
                    ]
                )

        # 5. GitHub趋势
        if all_news.get("github_trending"):
            lines.extend(["## ⭐ 开源项目趋势", ""])
            for item in all_news["github_trending"]:
                lines.extend(
                    [
                        f"**{item['title']}**  ",
                        f"🔗 [GitHub]({item['url']})  ",
                        f">{item.get('summary', '')}",
                        "",
                    ]
                )

        lines.extend(["---", "", "*本早报由AI自动生成，仅供参考*"])

        return "\n".join(lines)

    def _format_news_item(self, item: Dict) -> List[str]:
        """格式化单条新闻"""
        return [
            f"**{item['title']}**  ",
            f"🔗 [原文链接]({item['url']})",
            f"> {item.get('summary', '')}",
            "",
        ]

    def save(self, content: str):
        """保存到文件"""
        filename = f"ai_report_{datetime.now().strftime('%Y%m%d')}.md"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"✅ 早报已保存: {filepath}")
        return filepath


# ==================== 主流程 ====================
class AINewsAggregator:
    """主控制器"""

    def __init__(self):
        self.db = NewsDatabase(CONFIG["db_path"])
        self.generator = ReportGenerator(CONFIG["output_dir"])
        self.headers = {"User-Agent": CONFIG["user_agent"]}

        # 初始化抓取器
        self.hf_fetcher = HFPapersFetcher(self.headers)
        self.rss_fetcher = RSSFetcher(self.headers)
        self.github_fetcher = GitHubTrendingFetcher(self.headers)
        self.blog_scraper = BlogScraper(self.headers)

    def run(self):
        """运行完整流程"""
        print(f"🚀 开始生成AI早报 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 50)

        all_news = {}
        new_counts = {}

        # 1. 抓取 Hugging Face Papers
        print("\n📚 正在获取 Hugging Face Papers...")
        papers = self.hf_fetcher.fetch_papers()
        all_news["hf_papers"] = self._filter_and_store(papers, "hf_papers")
        new_counts["hf_papers"] = len(all_news["hf_papers"])
        print(f"   新论文: {new_counts['hf_papers']} 篇")

        # 2. 抓取机器之心
        print("\n🇨🇳 正在获取 机器之心...")
        jiqizhixin = self.rss_fetcher.fetch_feed("jiqizhixin")
        all_news["jiqizhixin"] = self._filter_and_store(jiqizhixin, "jiqizhixin")
        new_counts["jiqizhixin"] = len(all_news["jiqizhixin"])
        print(f"   新文章: {new_counts['jiqizhixin']} 篇")

        # 3. 抓取 TechCrunch
        print("\n🇺🇸 正在获取 TechCrunch AI...")
        techcrunch = self.rss_fetcher.fetch_feed("techcrunch")
        all_news["techcrunch"] = self._filter_and_store(techcrunch, "techcrunch")
        new_counts["techcrunch"] = len(all_news["techcrunch"])
        print(f"   新文章: {new_counts['techcrunch']} 篇")

        # 4. 抓取 GitHub Trending
        print("\n⭐ 正在获取 GitHub Trending...")
        github = self.github_fetcher.fetch_trending()
        all_news["github_trending"] = self._filter_and_store(github, "github_trending")
        new_counts["github_trending"] = len(all_news["github_trending"])
        print(f"   新项目: {new_counts['github_trending']} 个")

        # 5. 抓取官方博客
        for source in ["openai", "anthropic", "google_ai"]:
            print(f"\n🏢 正在获取 {SOURCES[source]['name']}...")
            news = self.blog_scraper.scrape_blog(source)
            all_news[source] = self._filter_and_store(news, source)
            new_counts[source] = len(all_news[source])
            print(f"   新动态: {new_counts[source]} 条")

        # 6. 生成早报
        print("\n📝 正在生成早报...")
        report_content = self.generator.generate(all_news, new_counts)

        # 7. 保存
        filepath = self.generator.save(report_content)

        # 8. 清理旧数据
        print("\n🧹 清理过期数据...")
        self.db.cleanup_old(CONFIG["retention_days"])

        # 9. 输出统计
        print("\n" + "=" * 50)
        print("📊 本次更新统计:")
        total = 0
        for source, count in new_counts.items():
            if count > 0:
                print(f"   {SOURCES.get(source, {}).get('name', source)}: {count}")
                total += count
        print(f"   总计新增: {total} 条")
        print(f"   数据库记录: {sum(self.db.get_stats().values())} 条")

        return filepath

    def _filter_and_store(self, articles: List[Dict], source: str) -> List[Dict]:
        """过滤已存在的内容并存储新内容"""
        new_articles = []
        for article in articles:
            url = article.get("url", "")
            title = article.get("title", "")

            # 基础验证
            if not url or not title or len(title) < 5:
                continue

            # 去重检查
            if self.db.is_new(url, title):
                # 先提取summary避免多行参数问题
                summary = article.get("summary", "")
                self.db.mark_as_processed(url, title, source, summary)
                new_articles.append(article)

        return new_articles


# ==================== 入口 ====================
if __name__ == "__main__":
    aggregator = AINewsAggregator()
    report_path = aggregator.run()

    # 可选：将结果发送到其他渠道（邮件、Slack、微信等）
    # 这里仅保存到本地文件
    print(f"\n✨ 完成！早报位置: {report_path}")
