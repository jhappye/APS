"""AI中台统一服务入口"""
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import config
from .aps import router as aps_router
from .gateway import router as gateway_router

# 配置日志
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("uvicorn.access")

# 创建应用
app = FastAPI(
    title="AI中台统一服务",
    version="2.0.0",
    description="APS AI中台 - 统一网关服务"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# 注册路由
app.include_router(aps_router)
app.include_router(gateway_router)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "AI中台统一服务",
        "version": "2.0.0",
        "mode": "mock" if config.is_mock_mode() else "production",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "AI中台统一服务",
        "version": "2.0.0",
        "mode": "mock" if config.is_mock_mode() else "production",
        "endpoints": {
            "登录": "POST /ai/login",
            "触发评估": "POST /ai/rush-order/evaluate/start",
            "轮询状态": "GET /ai/rush-order/evaluate/status/{taskId}",
            "获取AI报告(流式)": "POST /ai/rush-order/evaluate/analyze/{taskId}/stream",
            "业务问答(流式)": "POST /ai/chat/stream",
            "清除对话": "DELETE /ai/conversation/{convId}",
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)