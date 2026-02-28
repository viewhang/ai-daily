"""推送平台基类"""
from abc import ABC, abstractmethod
from typing import Dict


class PushPlatform(ABC):
    """推送平台抽象基类"""

    def __init__(self, config: Dict):
        self.config = config

    @abstractmethod
    def validate_config(self, config: Dict) -> bool:
        """验证配置是否有效"""
        pass

    @abstractmethod
    async def send(self, content: str, title: str = None):
        """发送内容"""
        pass
