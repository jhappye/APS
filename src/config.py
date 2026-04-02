import os
import logging
from typing import Optional

class Config:
    """统一配置管理"""

    # 模式切换
    MOCK_MODE: bool = os.getenv("MOCK_MODE", "true").lower() in ("true", "1", "yes")

    # APS 配置
    APS_BASE_URL: str = os.getenv("APS_BASE_URL", "http://localhost:8000")

    # AI服务中台配置
    AI_PLATFORM_BASE_URL: str = os.getenv("AI_PLATFORM_BASE_URL", "http://139.224.228.33:8090/v1")
    AI_PLATFORM_CHAT_KEY: str = os.getenv("AI_PLATFORM_CHAT_KEY", "")
    AI_PLATFORM_WORKFLOW_KEY: str = os.getenv("AI_PLATFORM_WORKFLOW_KEY", "")

    # 日志配置
    VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    _LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    if _LOG_LEVEL not in VALID_LOG_LEVELS:
        _LOG_LEVEL = "INFO"
    LOG_LEVEL: str = _LOG_LEVEL
    LOG_FILE: str = os.getenv("LOG_FILE", "/var/log/ai-platform/app.log")

    @classmethod
    def is_mock_mode(cls) -> bool:
        return cls.MOCK_MODE

    @classmethod
    def get_chat_key(cls) -> str:
        if not cls.AI_PLATFORM_CHAT_KEY:
            raise ValueError("AI_PLATFORM_CHAT_KEY cannot be empty")
        return cls.AI_PLATFORM_CHAT_KEY

    @classmethod
    def get_workflow_key(cls) -> str:
        if not cls.AI_PLATFORM_WORKFLOW_KEY:
            raise ValueError("AI_PLATFORM_WORKFLOW_KEY cannot be empty")
        return cls.AI_PLATFORM_WORKFLOW_KEY


# 全局配置实例
config = Config()
