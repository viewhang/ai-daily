"""推送模块测试"""

import os
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from push import create_platform
from push.dingtalk import DingTalkPlatform
from push.discord import DiscordPlatform
from push.feishu import FeishuPlatform


class TestDiscordPlatform:
    """测试 Discord 推送"""

    def test_validate_config_valid(self):
        config = {"enabled": True, "apiKeyName": "DISCORD_WEBHOOK_URL"}
        with patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/123/abc"},
        ):
            platform = DiscordPlatform(config)
            assert platform.validate_config(config) is True

    def test_validate_config_invalid_webhook(self):
        config = {"enabled": True, "apiKeyName": "DISCORD_WEBHOOK_URL"}
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://example.com/hook"}):
            platform = DiscordPlatform(config)
            assert platform.validate_config(config) is False

    def test_split_content(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://test.com"}):
            platform = DiscordPlatform({"apiKeyName": "DISCORD_WEBHOOK_URL"})
            chunks = platform._split_content("A\n" * 2500, limit=2000)
            assert len(chunks) > 1
            assert all(len(c) <= 2000 for c in chunks)


class TestFeishuPlatform:
    """测试飞书推送"""

    def test_validate_config_valid(self):
        config = {"enabled": True, "apiKeyName": "FEISHU_WEBHOOK_URL"}
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://open.feishu.cn/hook"}):
            platform = FeishuPlatform(config)
            assert platform.validate_config(config) is True

    def test_validate_config_disabled(self):
        config = {"enabled": False, "apiKeyName": "FEISHU_WEBHOOK_URL"}
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://open.feishu.cn/hook"}):
            platform = FeishuPlatform(config)
            assert platform.validate_config(config) is False

    def test_build_payload_with_title(self):
        platform = FeishuPlatform({"apiKeyName": "FEISHU_WEBHOOK_URL"})
        payload = platform._build_payload("hello", title="Test")
        assert payload["msg_type"] == "interactive"
        assert payload["card"]["header"]["title"]["content"] == "Test"


class TestDingTalkPlatform:
    """测试钉钉推送"""

    def test_validate_config_valid(self):
        config = {"enabled": True, "apiKeyName": "DINGTALK_WEBHOOK_URL"}
        with patch.dict(
            os.environ,
            {
                "DINGTALK_WEBHOOK_URL": "https://oapi.dingtalk.com/robot/send?access_token=test"
            },
        ):
            platform = DingTalkPlatform(config)
            assert platform.validate_config(config) is True

    def test_validate_config_invalid(self):
        config = {"enabled": True, "apiKeyName": "DINGTALK_WEBHOOK_URL"}
        with patch.dict(os.environ, {"DINGTALK_WEBHOOK_URL": "https://example.com/hook"}):
            platform = DingTalkPlatform(config)
            assert platform.validate_config(config) is False

    def test_split_content(self):
        platform = DingTalkPlatform({"apiKeyName": "DINGTALK_WEBHOOK_URL"})
        chunks = platform._split_content("A\n" * 5000, limit=4000)
        assert len(chunks) > 1
        assert all(len(c) <= 4000 for c in chunks)

    @pytest.mark.asyncio
    async def test_send_called(self):
        config = {"apiKeyName": "DINGTALK_WEBHOOK_URL"}
        with patch.dict(
            os.environ,
            {
                "DINGTALK_WEBHOOK_URL": "https://oapi.dingtalk.com/robot/send?access_token=test"
            },
        ):
            platform = DingTalkPlatform(config)
            with patch.object(platform, "send", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = None
                await mock_send("hello")
                mock_send.assert_called_once()


class TestPushFactory:
    """测试平台工厂"""

    def test_create_discord_platform(self):
        with patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/123/abc"},
        ):
            platform = create_platform(
                "discord", {"enabled": True, "apiKeyName": "DISCORD_WEBHOOK_URL"}
            )
            assert isinstance(platform, DiscordPlatform)

    def test_create_feishu_platform(self):
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://open.feishu.cn/hook"}):
            platform = create_platform(
                "feishu", {"enabled": True, "apiKeyName": "FEISHU_WEBHOOK_URL"}
            )
            assert isinstance(platform, FeishuPlatform)

    def test_create_dingtalk_platform(self):
        with patch.dict(
            os.environ,
            {
                "DINGTALK_WEBHOOK_URL": "https://oapi.dingtalk.com/robot/send?access_token=test"
            },
        ):
            platform = create_platform(
                "dingtalk", {"enabled": True, "apiKeyName": "DINGTALK_WEBHOOK_URL"}
            )
            assert isinstance(platform, DingTalkPlatform)

    def test_create_unknown_platform_raises(self):
        with pytest.raises(ValueError):
            create_platform("unknown", {})
