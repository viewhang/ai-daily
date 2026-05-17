"""测试 HN enrich(Algolia + 外链正文)"""

import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.sections.hackernews.item_enricher import enrich_story


@pytest.mark.asyncio
async def test_enrich_external_link_story():
    story = {
        "id": "111",
        "title": "T",
        "url": "https://example.com/post",
        "site": "example.com",
        "points": 100,
        "comments": 5,
        "comments_url": "https://news.ycombinator.com/item?id=111",
    }
    algolia_payload = {
        "text": None,
        "children": [
            {"text": "<p>comment one</p>"},
            {"text": "<p>comment two</p>"},
            {"text": "<p>comment three</p>"},
            {"text": "<p>comment four</p>"},
        ],
    }

    async def fake_algolia(session, item_id, **kw):
        return algolia_payload

    async def fake_external(session, url, **kw):
        return "link body"

    with patch(
        "src.sections.hackernews.item_enricher._fetch_algolia_item",
        new=AsyncMock(side_effect=fake_algolia),
    ), patch(
        "src.sections.hackernews.item_enricher._fetch_external_markdown",
        new=AsyncMock(side_effect=fake_external),
    ):
        enriched = await enrich_story(
            session=MagicMock(),
            story=story,
            top_comments=3,
            comment_max_chars=500,
            link_content_max_chars=3000,
            algolia_base="https://hn.algolia.com/api/v1",
            timeout=10,
        )

    assert len(enriched["top_comments"]) == 3
    assert "comment one" in enriched["top_comments"][0]
    assert "link body" in enriched["link_content"]


@pytest.mark.asyncio
async def test_enrich_show_hn_uses_root_text_no_external_fetch():
    story = {
        "id": "222",
        "title": "Show HN: T",
        "url": "https://news.ycombinator.com/item?id=222",
        "site": "",
        "points": 200,
        "comments": 10,
        "comments_url": "https://news.ycombinator.com/item?id=222",
    }
    algolia_payload = {
        "text": "<p>post body text</p>",
        "children": [{"text": "<p>c1</p>"}],
    }
    link_calls = []

    async def fake_algolia(session, item_id, **kw):
        return algolia_payload

    async def fake_external(session, url, **kw):
        link_calls.append(url)
        return "should not be called"

    with patch(
        "src.sections.hackernews.item_enricher._fetch_algolia_item",
        new=AsyncMock(side_effect=fake_algolia),
    ), patch(
        "src.sections.hackernews.item_enricher._fetch_external_markdown",
        new=AsyncMock(side_effect=fake_external),
    ):
        enriched = await enrich_story(
            session=MagicMock(),
            story=story,
            top_comments=3,
            comment_max_chars=500,
            link_content_max_chars=3000,
            algolia_base="https://hn.algolia.com/api/v1",
            timeout=10,
        )

    assert link_calls == []
    assert "post body text" in enriched["link_content"]


@pytest.mark.asyncio
async def test_enrich_truncates_comments_and_link():
    story = {
        "id": "333",
        "title": "T",
        "url": "https://example.com/a",
        "site": "example.com",
        "points": 100,
        "comments": 2,
        "comments_url": "x",
    }
    long_comment = "<p>" + ("y" * 2000) + "</p>"
    long_link = "z" * 5000

    async def fake_algolia(session, item_id, **kw):
        return {"text": None, "children": [{"text": long_comment}]}

    async def fake_external(session, url, **kw):
        return long_link

    with patch(
        "src.sections.hackernews.item_enricher._fetch_algolia_item",
        new=AsyncMock(side_effect=fake_algolia),
    ), patch(
        "src.sections.hackernews.item_enricher._fetch_external_markdown",
        new=AsyncMock(side_effect=fake_external),
    ):
        enriched = await enrich_story(
            session=MagicMock(),
            story=story,
            top_comments=3,
            comment_max_chars=100,
            link_content_max_chars=200,
            algolia_base="https://hn.algolia.com/api/v1",
            timeout=10,
        )

    assert len(enriched["top_comments"][0]) <= 100
    assert len(enriched["link_content"]) <= 200


@pytest.mark.asyncio
async def test_enrich_failure_returns_partial():
    story = {
        "id": "444",
        "title": "T",
        "url": "https://example.com/x",
        "site": "example.com",
        "points": 100,
        "comments": 2,
        "comments_url": "x",
    }

    async def fake_algolia(session, item_id, **kw):
        raise RuntimeError("algolia down")

    async def fake_external(session, url, **kw):
        return "ok"

    with patch(
        "src.sections.hackernews.item_enricher._fetch_algolia_item",
        new=AsyncMock(side_effect=fake_algolia),
    ), patch(
        "src.sections.hackernews.item_enricher._fetch_external_markdown",
        new=AsyncMock(side_effect=fake_external),
    ):
        enriched = await enrich_story(
            session=MagicMock(),
            story=story,
            top_comments=3,
            comment_max_chars=500,
            link_content_max_chars=3000,
            algolia_base="https://hn.algolia.com/api/v1",
            timeout=10,
        )

    assert enriched["top_comments"] == []
    assert "ok" in enriched["link_content"]
