"""HN 单 story enrich:Algolia 评论 + 外链正文。

Algolia API: GET /api/v1/items/{id}
- root.text 是 Show HN / Ask HN 的 post 正文
- root.children[] 是顶层评论(按 HN ranking 排序)

外链正文优先走 Jina Reader (https://r.jina.ai/<url>, 返回 markdown),
失败回退到直接 GET + html_to_markdown。JINA_API_KEY 可选,配置后免费额度更高。
"""

import asyncio
import os
from typing import Dict, List, Optional, Tuple

import aiohttp

from src.processor import html_to_markdown

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

JINA_READER_BASE = "https://r.jina.ai"


def _is_internal_hn_url(url: str) -> bool:
    return url.startswith("https://news.ycombinator.com/item?id=")


async def _fetch_algolia_item(
    session: aiohttp.ClientSession, item_id: str, algolia_base: str, timeout: int
) -> Dict:
    url = f"{algolia_base}/items/{item_id}"
    async with session.get(
        url, timeout=aiohttp.ClientTimeout(total=timeout)
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Algolia /items/{item_id} 返回 {resp.status}")
        return await resp.json()


async def _fetch_url_html(
    session: aiohttp.ClientSession, url: str, timeout: int
) -> str:
    async with session.get(
        url, timeout=aiohttp.ClientTimeout(total=timeout)
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"外链 {url} 返回 {resp.status}")
        return await resp.text()


async def _fetch_via_jina(
    session: aiohttp.ClientSession, url: str, timeout: int
) -> str:
    """通过 Jina Reader 拉取外链 markdown。JINA_API_KEY 可选,配置后免费额度更高。"""
    jina_url = f"{JINA_READER_BASE}/{url}"
    headers = {"Accept": "text/markdown"}
    api_key = os.environ.get("JINA_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with session.get(
        jina_url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Jina Reader {url} 返回 {resp.status}")
        return await resp.text()


async def _fetch_external_markdown(
    session: aiohttp.ClientSession, url: str, timeout: int
) -> str:
    """获取外链正文 markdown:先走 Jina Reader,失败回退到直接 GET + html_to_markdown。"""
    try:
        return await _fetch_via_jina(session, url, timeout)
    except Exception:
        html = await _fetch_url_html(session, url, timeout)
        return html_to_markdown(html, base_url=url)


async def enrich_story(
    session: aiohttp.ClientSession,
    story: Dict,
    top_comments: int,
    comment_max_chars: int,
    link_content_max_chars: int,
    algolia_base: str,
    timeout: int,
) -> Dict:
    """对单 story enrich。任一子任务失败 → 对应字段留空,不抛。"""
    item_id = story["id"]
    is_internal = _is_internal_hn_url(story["url"])

    tasks = [
        _fetch_algolia_item(
            session, item_id, algolia_base=algolia_base, timeout=timeout
        )
    ]
    if not is_internal:
        tasks.append(
            _fetch_external_markdown(session, story["url"], timeout=timeout)
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    algolia_result = results[0]
    external_markdown_result = results[1] if not is_internal else None

    comments_list: List[str] = []
    post_text = ""
    if not isinstance(algolia_result, Exception) and algolia_result:
        post_text = algolia_result.get("text") or ""
        children = algolia_result.get("children") or []
        for child in children[:top_comments]:
            raw = (child or {}).get("text") or ""
            if not raw:
                continue
            md = html_to_markdown(raw)
            comments_list.append(md[:comment_max_chars])

    link_content = ""
    if is_internal:
        if post_text:
            link_content = html_to_markdown(post_text)[:link_content_max_chars]
    else:
        if (
            not isinstance(external_markdown_result, Exception)
            and external_markdown_result
        ):
            link_content = external_markdown_result[:link_content_max_chars]

    return {
        **story,
        "link_content": link_content,
        "top_comments": comments_list,
    }


async def enrich_stories(
    stories: List[Dict],
    top_comments: int,
    comment_max_chars: int,
    link_content_max_chars: int,
    algolia_base: str = "https://hn.algolia.com/api/v1",
    timeout: int = 10,
) -> Tuple[List[Dict], List[str]]:
    """并发 enrich 多个 stories。"""
    errors: List[str] = []
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        results = await asyncio.gather(
            *[
                enrich_story(
                    session,
                    s,
                    top_comments,
                    comment_max_chars,
                    link_content_max_chars,
                    algolia_base,
                    timeout,
                )
                for s in stories
            ],
            return_exceptions=True,
        )
    enriched: List[Dict] = []
    for r, src in zip(results, stories):
        if isinstance(r, Exception):
            errors.append(f"enrich story {src['id']} 失败: {r}")
        else:
            enriched.append(r)
    return enriched, errors
