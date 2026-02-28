"""企业微信推送平台"""

import os
import aiohttp
from typing import Dict

from .base import PushPlatform


class WecomPlatform(PushPlatform):
    """企业微信机器人推送"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_key_name = config.get("apiKeyName", "WECOM_KEY")
        self.key = os.environ.get(self.api_key_name, "")
        self.webhook_url = (
            f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={self.key}"
        )

    def validate_config(self, config: Dict) -> bool:
        """检查企业微信配置是否有效"""
        if not config.get("enabled", False):
            return False
        api_key_name = config.get("apiKeyName", "WECOM_KEY")
        key = os.environ.get(api_key_name, "")
        return bool(key and len(key) > 10)

    async def send(self, content: str, title: str = None):
        """发送到企业微信"""
        # 企业微信markdown消息限制4096字节
        chunks = self._split_content(content, limit=4000)

        async with aiohttp.ClientSession() as session:
            for chunk in chunks:
                payload = {
                    "msgtype": "markdown",
                    "markdown": {"content": chunk},
                }
                async with session.post(self.webhook_url, json=payload) as resp:
                    data = await resp.json()
                    if data.get("errcode") != 0:
                        raise RuntimeError(f"企业微信推送失败: {data.get('errmsg')}")

    def _split_content(self, content: str, limit: int = 4000) -> list:
        """分割长消息"""
        if len(content.encode("utf-8")) <= limit:
            return [content]

        chunks = []
        lines = content.split("\n")
        current = ""
        current_bytes = 0

        for line in lines:
            line_bytes = len(line.encode("utf-8"))
            if current_bytes + line_bytes + 1 > limit:
                if current:
                    chunks.append(current)
                current = line
                current_bytes = line_bytes
            else:
                current += "\n" + line if current else line
                current_bytes += line_bytes + 1

        if current:
            chunks.append(current)

        return chunks
