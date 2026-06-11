#!/usr/bin/env python3
"""测试 Qwen Image 生图功能"""

import asyncio
import os
import sys

import httpx

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.qwen_image_service import QwenImageService
from app.schemas.image import ImageRequest


async def test_qwen_image():
    """测试 Qwen Image 生图"""
    print("=" * 60)
    print("Qwen Image 生图功能测试")
    print("=" * 60)

    service = QwenImageService()

    print("\n配置信息:")
    print(f"  - API Key: {service.api_key[:10]}...{service.api_key[-4:] if service.api_key else 'None'}")
    print(f"  - Model: {service.model}")
    print(f"  - Size: {service.size}")
    print(f"  - Prompt Extend: {service.prompt_extend}")
    print(f"  - Watermark: {service.watermark}")

    test_prompts = [
        "一只可爱的橘猫坐在窗台上，窗外是日落，摄影写实风格，柔和暖光，细节丰富",
    ]

    for i, prompt in enumerate(test_prompts, 1):
        print(f"\n{'=' * 60}")
        print(f"测试 {i}: {prompt[:50]}...")
        print("=" * 60)

        request = ImageRequest(
            keywords="",
            prompt=prompt,
            position=i,
            type="section",
        )

        print("正在生成图片...")
        try:
            image_data = await service.get_image_data(request)

            if image_data and image_data.is_valid():
                print("✅ 图片生成成功!")
                print(f"  - Data Type: {image_data.data_type}")
                print(f"  - MIME Type: {image_data.mime_type}")
                if image_data.url:
                    print(f"  - URL: {image_data.url}")
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.get(image_data.url)
                        if response.status_code == 200:
                            image_data = image_data.from_bytes(response.content, response.headers.get("content-type", "image/png"))
                        else:
                            print(f"  - 下载图片失败: HTTP {response.status_code}")

                bytes_data = image_data.get_image_bytes()
                if bytes_data:
                    filename = f"test_qwen_image_{i}{image_data.get_file_extension()}"
                    with open(filename, "wb") as f:
                        f.write(bytes_data)
                    print(f"  - 文件大小: {len(bytes_data):,} bytes")
                    print(f"  - 保存为: {filename}")
            else:
                print("❌ 图片数据无效")
        except Exception as e:
            print(f"❌ 生成失败: {e}")

    await service.close()
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_qwen_image())
