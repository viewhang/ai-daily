"""钉钉推送平台"""

import os
from typing import Dict, List, Optional

import aiohttp

from .base import PushPlatform


class DingTalkPlatform(PushPlatform):
    """钉钉机器人 Webhook 推送"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_key_name = config.get("apiKeyName", "DINGTALK_WEBHOOK_URL")
        self.webhook_url = os.environ.get(self.api_key_name, "")

    def validate_config(self, config: Dict) -> bool:
        """检查钉钉配置是否有效"""
        if not config.get("enabled", False):
            return False
        api_key_name = config.get("apiKeyName", "DINGTALK_WEBHOOK_URL")
        webhook = os.environ.get(api_key_name, "")
        return bool(
            webhook
            and (
                "oapi.dingtalk.com/robot/send" in webhook
                or "api.dingtalk.com" in webhook
            )
        )

    async def send(self, content: str, title: Optional[str] = None):
        """发送到钉钉"""
        chunks = self._split_content(content, limit=4000)

        async with aiohttp.ClientSession() as session:
            for index, chunk in enumerate(chunks, start=1):
                chunk_title = title or "AI Daily 推送"
                if len(chunks) > 1:
                    chunk_title = f"{chunk_title} ({index}/{len(chunks)})"

                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": chunk_title,
                        "text": chunk,
                    },
                }

                async with session.post(self.webhook_url, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"钉钉推送失败: {resp.status} - {text}")

                    data = await resp.json()
                    if data.get("errcode", 0) != 0:
                        raise RuntimeError(
                            f"钉钉推送失败: {data.get('errmsg', 'unknown error')}"
                        )

    def _split_content(self, content: str, limit: int = 4000) -> List[str]:
        """钉钉 markdown 消息分片"""
        if len(content) <= limit:
            return [content]

        chunks = []
        lines = content.split("\n")
        current = ""

        for line in lines:
            if len(current) + len(line) + 1 > limit:
                if current:
                    chunks.append(current)
                current = line
            else:
                current += "\n" + line if current else line

        if current:
            chunks.append(current)

        return chunks
