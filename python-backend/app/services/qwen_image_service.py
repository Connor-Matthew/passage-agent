"""Qwen Image（通义千问图像生成）服务"""

import base64
import logging
import re
from typing import Any, Optional

import httpx

from app.config import settings
from app.constants.article import ArticleConstant
from app.models.enums import ImageMethodEnum
from app.schemas.image import ImageData
from app.services.image_search_service import ImageSearchService
from app.schemas.image import ImageRequest

logger = logging.getLogger(__name__)


class QwenImageService(ImageSearchService):
    """Qwen Image AI 生图服务"""

    API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

    def __init__(self):
        self.api_key = settings.dashscope_api_key
        self.model = settings.qwen_image_model
        self.negative_prompt = settings.qwen_image_negative_prompt
        self.prompt_extend = settings.qwen_image_prompt_extend
        self.watermark = settings.qwen_image_watermark
        self.size = settings.qwen_image_size
        self.client = httpx.AsyncClient(timeout=settings.qwen_image_timeout)

    async def search_image(self, keywords: str) -> Optional[str]:
        """兼容旧接口：返回生成图片 URL。"""
        image_data = await self.generate_image_data(keywords)
        return image_data.url if image_data and image_data.url else None

    async def get_image_data(self, request: ImageRequest) -> Optional[ImageData]:
        """获取图片数据。"""
        prompt = request.get_effective_param(True)
        return await self.generate_image_data(prompt)

    async def generate_image_data(self, prompt: str) -> Optional[ImageData]:
        """
        根据提示词生成图片数据。

        DashScope Qwen Image 返回的图片通常是临时 URL；这里先封装为 URL，
        后续由 ImageServiceStrategy 统一下载并上传到 COS。
        """
        if not prompt:
            logger.error("Qwen Image 生图提示词为空")
            return None

        try:
            payload = self._build_payload(prompt)
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            logger.info(f"Qwen Image 开始生成图片, model={self.model}, size={self.size}, prompt={prompt}")
            response = await self.client.post(self.API_URL, headers=headers, json=payload)

            if response.status_code != 200:
                logger.error(f"Qwen Image API 调用失败: status={response.status_code}, body={response.text}")
                return None

            data = response.json()
            image_url = self._extract_image_url(data)
            if image_url:
                logger.info(f"Qwen Image 图片生成成功, url={image_url}")
                return ImageData.from_url(image_url)

            image_bytes = self._extract_image_bytes(data)
            if image_bytes:
                logger.info(f"Qwen Image 图片生成成功, size={len(image_bytes)} bytes")
                return ImageData.from_bytes(image_bytes, "image/png")

            logger.error(f"Qwen Image 响应中未找到图片数据: {data}")
            return None
        except Exception as e:
            logger.error(f"Qwen Image 生成图片异常: {e}")
            return None

    def get_method(self) -> ImageMethodEnum:
        """获取图片服务类型。"""
        return ImageMethodEnum.QWEN_IMAGE

    def get_fallback_image(self, position: int) -> str:
        """获取降级图片。"""
        return ArticleConstant.PICSUM_URL_TEMPLATE.format(position)

    def _build_payload(self, prompt: str) -> dict:
        """构造 DashScope 请求体。"""
        return {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": prompt}
                        ],
                    }
                ]
            },
            "parameters": {
                "negative_prompt": self.negative_prompt,
                "prompt_extend": self.prompt_extend,
                "watermark": self.watermark,
                "size": self.size,
            },
        }

    def _extract_image_url(self, data: Any) -> Optional[str]:
        """从 DashScope 响应中递归提取图片 URL。"""
        if isinstance(data, dict):
            for key in ("image", "url", "image_url"):
                value = data.get(key)
                if isinstance(value, str) and self._looks_like_image_url(value):
                    return value

            for value in data.values():
                result = self._extract_image_url(value)
                if result:
                    return result

        if isinstance(data, list):
            for item in data:
                result = self._extract_image_url(item)
                if result:
                    return result

        return None

    def _extract_image_bytes(self, data: Any) -> Optional[bytes]:
        """从响应中递归提取 base64 图片。"""
        if isinstance(data, dict):
            for key in ("b64_image", "base64", "image_base64", "image"):
                value = data.get(key)
                if isinstance(value, str) and not self._looks_like_image_url(value):
                    return self._decode_base64_image(value)

            for value in data.values():
                result = self._extract_image_bytes(value)
                if result:
                    return result

        if isinstance(data, list):
            for item in data:
                result = self._extract_image_bytes(item)
                if result:
                    return result

        return None

    def _looks_like_image_url(self, value: str) -> bool:
        """判断字符串是否像图片 URL。"""
        return value.startswith("http://") or value.startswith("https://")

    def _decode_base64_image(self, value: str) -> Optional[bytes]:
        """解码 base64 图片内容。"""
        try:
            payload = re.sub(r"^data:image/[^;]+;base64,", "", value)
            return base64.b64decode(payload)
        except Exception:
            return None

    async def close(self):
        """关闭 HTTP 客户端。"""
        await self.client.aclose()
