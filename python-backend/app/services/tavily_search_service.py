"""Tavily Web 搜索服务（第 11 期新增）"""

import logging
from typing import List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class TavilySearchService:
    """Tavily 搜索服务"""

    def __init__(self):
        self.api_key = settings.tavily_api_key
        self.enabled = settings.tavily_enabled and bool(self.api_key)
        self.max_results = settings.tavily_max_results
        self.timeout = settings.tavily_timeout

    def is_enabled(self) -> bool:
        """检查是否启用搜索服务"""
        return self.enabled

    async def search(
        self,
        queries: List[dict],
        max_results_per_query: Optional[int] = None
    ) -> dict:
        """
        执行 Web 搜索
        
        Args:
            queries: 搜索查询列表，每个查询包含 type 和 query
            max_results_per_query: 每个查询的最大结果数，默认使用配置值
        
        Returns:
            包含 queries 和 results 的字典
        """
        if not self.is_enabled():
            logger.info("Tavily 搜索未启用，跳过搜索")
            return {"queries": queries, "results": []}

        if max_results_per_query is None:
            max_results_per_query = max(1, self.max_results // len(queries) if queries else 1)

        all_results = []
        seen_urls = set()  # 用于 URL 去重

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for query_item in queries:
                query_type = query_item.get("type", "general")
                query_text = query_item.get("query", "")

                if not query_text:
                    continue

                try:
                    response = await client.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": self.api_key,
                            "query": query_text,
                            "max_results": max_results_per_query,
                            "include_answer": False,
                            "include_raw_content": False,
                        }
                    )
                    response.raise_for_status()
                    data = response.json()

                    # 处理搜索结果
                    results = data.get("results", [])
                    for result in results:
                        url = result.get("url", "")
                        # URL 去重
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append({
                                "title": result.get("title", ""),
                                "url": url,
                                "content": self._truncate_content(result.get("content", "")),
                                "queryType": query_type,
                                "query": query_text,
                            })

                    logger.info(
                        "Tavily 搜索成功, query=%s, resultsCount=%d",
                        query_text,
                        len(results)
                    )

                except httpx.TimeoutException:
                    logger.warning("Tavily 搜索超时, query=%s", query_text)
                except httpx.HTTPStatusError as e:
                    logger.warning("Tavily 搜索 HTTP 错误, query=%s, status=%s", query_text, e.response.status_code)
                except Exception as e:
                    logger.warning("Tavily 搜索异常, query=%s, error=%s", query_text, str(e))

        # 限制总结果数
        max_total_results = self.max_results * 2  # 最多允许 2 倍配置值
        final_results = all_results[:max_total_results]

        logger.info(
            "Tavily 搜索完成, queryCount=%d, totalResults=%d",
            len(queries),
            len(final_results)
        )

        return {
            "queries": queries,
            "results": final_results,
        }

    def _truncate_content(self, content: str, max_length: int = 500) -> str:
        """截断内容，避免 Prompt 过长"""
        if not content:
            return ""
        content = content.strip()
        if len(content) <= max_length:
            return content
        return content[:max_length] + "..."

    def build_search_context_prompt(self, search_data: dict) -> str:
        """
        构建搜索上下文 Prompt
        
        Args:
            search_data: 搜索服务返回的数据，包含 queries 和 results
        
        Returns:
            用于注入到 LLM Prompt 的搜索上下文文本
        """
        results = search_data.get("results", [])
        
        if not results:
            return ""

        prompt_parts = [
            "\n\n## 参考搜索资料",
            "\n以下是基于您选题搜索到的最新资料，请在创作时参考：\n"
        ]

        for i, result in enumerate(results, 1):
            title = result.get("title", "")
            url = result.get("url", "")
            content = result.get("content", "")

            prompt_parts.append(f"\n### 来源 {i}: {title}")
            prompt_parts.append(f"链接: {url}")
            prompt_parts.append(f"内容摘要: {content}")

        prompt_parts.append("\n\n**重要提示**:")
        prompt_parts.append("1. 仅使用上述资料中出现的事实、数据、事件和观点")
        prompt_parts.append("2. 不要编造或歪曲来源信息")
        prompt_parts.append("3. 如需引用，请确保准确性")
        prompt_parts.append("4. 如资料与您当前认知冲突，优先以搜索资料为准")

        return "\n".join(prompt_parts)


# 全局单例
tavily_search_service = TavilySearchService()