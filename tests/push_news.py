#!/usr/bin/env python3
"""推送功能测试 (Step 2)

测试内容：
1. 读取已获取的新闻数据
2. 测试推送到所有已启用的平台
3. 验证推送格式和内容

使用方法:
    python tests/push_news.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date

from dotenv import load_dotenv
from src.config import load_config
from src.push import send_to_platforms
from src.storage import convert_fetch_json_to_md, get_fetch_file, read_entries

load_dotenv()


async def test_push():
    """测试推送功能"""
    print("=" * 60)
    print("📤 推送功能测试 (Step 2)")
    print("=" * 60)

    # 加载配置
    print("\n📋 加载配置...")
    config = load_config()

    # 读取今天的新闻
    print("\n📖 读取新闻数据...")
    fetch_file = get_fetch_file(date.today(), data_dir="tests/news-data")
    entries = read_entries(fetch_file)
    print(f"   文件: {fetch_file}")
    print(f"   获取到 {len(entries)} 条新闻")

    # 同时生成 Markdown 版本便于阅读
    md_file = str(fetch_file).replace(".json", ".md")
    convert_fetch_json_to_md(fetch_file, md_file)
    print(f"   Markdown版本: {md_file}")

    if not entries:
        print("\n⚠️ 没有新闻数据，请先运行 fetch_news.py")
        return

    # 构建测试消息
    print("\n📝 构建推送消息...")
    content = build_test_message(entries[:5])  # 只取前5条测试
    print(f"   消息长度: {len(content)} 字符")

    # 推送到所有已启用平台
    print("\n📤 推送消息...")
    try:
        await send_to_platforms(content, config["push"], title="📰 新闻推送测试")
    except Exception as e:
        print(f"   ❌ 推送失败: {e}")
        raise

    print("\n" + "=" * 60)
    print("✅ Step 2 完成: 推送测试")
    print("=" * 60)


def build_test_message(entries: list) -> str:
    """构建测试消息"""
    lines = [
        "📰 **新闻推送测试**",
        "",
        f"共获取 {len(entries)} 条新闻：",
        "",
    ]

    for i, entry in enumerate(entries, 1):
        title = entry.get("title", "无标题")
        source = entry.get("source", "未知来源")
        link = entry.get("link", "")
        published = entry.get("published", "")
        content = entry.get("content", "")[:100]  # 限制内容长度

        lines.append(f"**{i}. {title}**")
        lines.append(f"   📰 来源: {source}")
        if published:
            lines.append(f"   ⏰ 时间: {published}")
        if link:
            lines.append(f"   🔗 链接: {link}")
        if content:
            lines.append(f"   📝 内容: {content}...")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(test_push())
