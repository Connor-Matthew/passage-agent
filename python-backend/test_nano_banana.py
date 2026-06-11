#!/usr/bin/env python3
"""测试 Nano Banana (Gemini) 生图功能"""

import asyncio
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.nano_banana_service import NanoBananaService
from app.schemas.image import ImageRequest


async def test_nano_banana():
    """测试 Nano Banana 生图"""
    print("=" * 60)
    print("Nano Banana (Gemini) 生图功能测试")
    print("=" * 60)
    
    # 初始化服务
    service = NanoBananaService()
    
    print(f"\n配置信息:")
    print(f"  - API Key: {service.api_key[:10]}...{service.api_key[-4:] if service.api_key else 'None'}")
    print(f"  - Model: {service.model}")
    print(f"  - Aspect Ratio: {service.aspect_ratio}")
    print(f"  - Image Size: {service.image_size}")
    
    # 测试提示词
    test_prompts = [
        "A cute cat sitting on a windowsill, sunset lighting, photorealistic",
        "A futuristic city with flying cars, cyberpunk style, digital art",
    ]
    
    for i, prompt in enumerate(test_prompts, 1):
        print(f"\n{'=' * 60}")
        print(f"测试 {i}: {prompt[:50]}...")
        print("=" * 60)
        
        request = ImageRequest(
            keywords="",
            prompt=prompt,
            position=i,
            type="section"
        )
        
        print("正在生成图片...")
        try:
            image_data = await service.get_image_data(request)
            
            if image_data and image_data.is_valid():
                print(f"✅ 图片生成成功!")
                print(f"  - MIME Type: {image_data.mime_type}")
                
                # 保存图片到本地测试
                bytes_data = image_data.get_image_bytes()
                if bytes_data:
                    filename = f"test_image_{i}{image_data.get_file_extension()}"
                    with open(filename, "wb") as f:
                        f.write(bytes_data)
                    print(f"  - 文件大小: {len(bytes_data):,} bytes")
                    print(f"  - 保存为: {filename}")
            else:
                print("❌ 图片数据无效")
        except Exception as e:
            print(f"❌ 生成失败: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_nano_banana())