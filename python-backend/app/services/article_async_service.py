"""文章异步任务服务"""

import json
import logging
from typing import Any, Dict, Optional

from app.schemas.article import ArticleState, OutlineSection, OutlineResult, TitleResult
from app.models.enums import ArticlePhaseEnum, ArticleStatusEnum, SseMessageTypeEnum
from app.services.article_agent_service import ArticleAgentService
from app.services.article_service import ArticleService
from app.managers.sse_manager import sse_emitter_manager
from app.database import database

logger = logging.getLogger(__name__)


class ArticleAsyncService:
    """文章异步任务服务"""

    async def execute_phase1(
        self,
        task_id: str,
        topic: str,
        style: Optional[str] = None,
        enable_web_search: bool = False,  # 第 11 期新增
    ):
        """阶段1：异步生成标题方案"""
        logger.info("阶段1异步任务开始, taskId=%s, topic=%s, style=%s, enableWebSearch=%s", 
                    task_id, topic, style, enable_web_search)
        article_agent_service = ArticleAgentService()
        article_service = ArticleService(database)

        try:
            await article_service.update_article_status(task_id, ArticleStatusEnum.PROCESSING)
            await article_service.update_phase(task_id, ArticlePhaseEnum.TITLE_GENERATING)

            state = ArticleState()
            state.task_id = task_id
            state.topic = topic
            state.style = style
            state.enable_web_search = enable_web_search

            # 第 11 期：如果启用联网搜索，先执行搜索
            if enable_web_search:
                await self._prepare_web_search_context(task_id, topic, style, article_agent_service, article_service, state)

            await article_agent_service.execute_phase1_generate_titles(
                state,
                lambda message: self._handle_agent_message(task_id, message, state)
            )

            await article_service.save_title_options(task_id, state.title_options or [])
            await article_service.update_phase(task_id, ArticlePhaseEnum.TITLE_SELECTING)

            self._send_sse_message(
                task_id,
                SseMessageTypeEnum.TITLES_GENERATED,
                {
                    "titleOptions": [
                        item.model_dump(by_alias=True) for item in (state.title_options or [])
                    ]
                },
            )

            logger.info("阶段1异步任务完成, taskId=%s", task_id)
        except Exception as e:
            logger.error("阶段1异步任务失败, taskId=%s, error=%s", task_id, e)
            await article_service.update_article_status(
                task_id,
                ArticleStatusEnum.FAILED,
                str(e)
            )
            self._send_sse_message(
                task_id,
                SseMessageTypeEnum.ERROR,
                {"message": str(e)}
            )
            sse_emitter_manager.complete(task_id)

    async def _prepare_web_search_context(
        self,
        task_id: str,
        topic: str,
        style: Optional[str],
        article_agent_service: ArticleAgentService,
        article_service: ArticleService,
        state: ArticleState,
    ):
        """准备 Web 搜索上下文（第 11 期新增）"""
        from app.services.tavily_search_service import tavily_search_service
        
        try:
            logger.info("开始生成搜索查询, taskId=%s", task_id)
            
            # 1. 使用 LLM 生成搜索 query
            search_queries = await article_agent_service.generate_search_queries(topic, style)
            
            if not search_queries:
                # 查询生成失败，降级为使用 topic 作为唯一 query
                logger.warning("搜索查询生成失败，降级为使用 topic 作为查询, taskId=%s", task_id)
                search_queries = [{"type": "general", "query": topic}]
            
            logger.info("生成搜索查询成功, taskId=%s, queryCount=%d", task_id, len(search_queries))
            
            # 2. 执行搜索
            search_data = await tavily_search_service.search(search_queries)
            
            # 3. 保存搜索上下文到数据库
            if search_data.get("results"):
                state.web_search_context = search_data
                await article_service.save_web_search_context(task_id, search_data)
                logger.info("搜索完成并保存上下文, taskId=%s, resultsCount=%d", 
                           task_id, len(search_data.get("results", [])))
            else:
                logger.info("搜索未返回结果, taskId=%s", task_id)
                
        except Exception as e:
            logger.error("Web 搜索上下文准备失败，降级为普通生成, taskId=%s, error=%s", task_id, e)
            # 搜索失败不影响创作流程
            state.enable_web_search = False

    async def execute_phase2(self, task_id: str):
        """阶段2：异步生成大纲"""
        logger.info("阶段2异步任务开始, taskId=%s", task_id)
        article_agent_service = ArticleAgentService()
        article_service = ArticleService(database)

        try:
            article = await article_service.get_by_task_id(task_id)
            if not article:
                raise RuntimeError("文章不存在")
            article_dict = dict(article)
            await article_service.update_phase(task_id, ArticlePhaseEnum.OUTLINE_GENERATING)

            state = ArticleState()
            state.task_id = task_id
            state.style = article_dict["style"]
            state.user_description = article_dict["userDescription"]
            state.title = TitleResult(
                mainTitle=article_dict["mainTitle"],
                subTitle=article_dict["subTitle"],
            )
            # 第 11 期：恢复 Web 搜索上下文
            state.enable_web_search = bool(article_dict.get("enableWebSearch"))
            if article_dict.get("webSearchContext"):
                try:
                    state.web_search_context = json.loads(article_dict["webSearchContext"])
                except json.JSONDecodeError:
                    state.web_search_context = None

            await article_agent_service.execute_phase2_generate_outline(
                state,
                lambda message: self._handle_agent_message(task_id, message, state)
            )
            await article_service.save_outline(task_id, state.outline.sections if state.outline else [])
            await article_service.update_phase(task_id, ArticlePhaseEnum.OUTLINE_EDITING)

            self._send_sse_message(
                task_id,
                SseMessageTypeEnum.OUTLINE_GENERATED,
                {
                    "outline": [
                        item.model_dump() for item in (state.outline.sections if state.outline else [])
                    ]
                },
            )
            logger.info("阶段2异步任务完成, taskId=%s", task_id)
        except Exception as e:
            logger.error("阶段2异步任务失败, taskId=%s, error=%s", task_id, e)
            await article_service.update_article_status(task_id, ArticleStatusEnum.FAILED, str(e))
            self._send_sse_message(task_id, SseMessageTypeEnum.ERROR, {"message": str(e)})
            sse_emitter_manager.complete(task_id)

    async def execute_phase3(self, task_id: str):
        """阶段3：异步生成正文与配图"""
        logger.info("阶段3异步任务开始, taskId=%s", task_id)
        article_agent_service = ArticleAgentService()
        article_service = ArticleService(database)

        try:
            article = await article_service.get_by_task_id(task_id)
            if not article:
                raise RuntimeError("文章不存在")
            article_dict = dict(article)
            await article_service.update_phase(task_id, ArticlePhaseEnum.CONTENT_GENERATING)

            outline_data = json.loads(article_dict["outline"]) if article_dict["outline"] else []
            state = ArticleState()
            state.task_id = task_id
            state.style = article_dict["style"]
            state.enabled_image_methods = (
                json.loads(article_dict["enabledImageMethods"])
                if article_dict["enabledImageMethods"]
                else None
            )
            state.title = TitleResult(
                mainTitle=article_dict["mainTitle"],
                subTitle=article_dict["subTitle"],
            )
            state.outline = OutlineResult(
                sections=[OutlineSection(**item) for item in outline_data]
            )
            # 第 11 期：恢复 Web 搜索上下文
            state.enable_web_search = bool(article_dict.get("enableWebSearch"))
            if article_dict.get("webSearchContext"):
                try:
                    state.web_search_context = json.loads(article_dict["webSearchContext"])
                except json.JSONDecodeError:
                    state.web_search_context = None

            await article_agent_service.execute_phase3_generate_content(
                state,
                lambda message: self._handle_agent_message(task_id, message, state)
            )
            await article_service.save_article_content(task_id, state)
            await article_service.update_article_status(task_id, ArticleStatusEnum.COMPLETED)

            self._send_sse_message(
                task_id,
                SseMessageTypeEnum.ALL_COMPLETE,
                {"taskId": task_id}
            )
            sse_emitter_manager.complete(task_id)
            logger.info("阶段3异步任务完成, taskId=%s", task_id)
        except Exception as e:
            logger.error("阶段3异步任务失败, taskId=%s, error=%s", task_id, e)
            await article_service.update_article_status(task_id, ArticleStatusEnum.FAILED, str(e))
            self._send_sse_message(task_id, SseMessageTypeEnum.ERROR, {"message": str(e)})
            sse_emitter_manager.complete(task_id)

    def _handle_agent_message(self, task_id: str, message: str, state: ArticleState):
        """处理智能体消息并推送"""
        data = self._build_message_data(message, state)
        if data is not None:
            sse_emitter_manager.send(task_id, json.dumps(data, ensure_ascii=False))
    
    def _build_message_data(self, message: str, state: ArticleState) -> Dict[str, Any]:
        """构建消息数据"""
        # 处理流式消息（带冒号分隔符）
        streaming_prefix2 = SseMessageTypeEnum.AGENT2_STREAMING.get_streaming_prefix()
        streaming_prefix3 = SseMessageTypeEnum.AGENT3_STREAMING.get_streaming_prefix()
        image_complete_prefix = SseMessageTypeEnum.IMAGE_COMPLETE.get_streaming_prefix()
        
        if message.startswith(streaming_prefix2):
            return self._build_streaming_data(
                SseMessageTypeEnum.AGENT2_STREAMING,
                message[len(streaming_prefix2):]
            )
        
        if message.startswith(streaming_prefix3):
            return self._build_streaming_data(
                SseMessageTypeEnum.AGENT3_STREAMING,
                message[len(streaming_prefix3):]
            )
        
        if message.startswith(image_complete_prefix):
            image_json = message[len(image_complete_prefix):]
            return self._build_image_complete_data(image_json)
        
        # 处理完成消息（枚举值）
        return self._build_complete_message_data(message, state)
    
    def _build_streaming_data(self, type_enum: SseMessageTypeEnum, content: str) -> Dict[str, Any]:
        """构建流式输出数据"""
        return {
            "type": type_enum.value,
            "content": content
        }
    
    def _build_image_complete_data(self, image_json: str) -> Dict[str, Any]:
        """构建图片完成数据"""
        return {
            "type": SseMessageTypeEnum.IMAGE_COMPLETE.value,
            "image": json.loads(image_json)
        }
    
    def _build_complete_message_data(self, message: str, state: ArticleState) -> Dict[str, Any]:
        """构建完成消息数据"""
        data = {}
        
        if message == SseMessageTypeEnum.AGENT1_COMPLETE.value:
            data["type"] = SseMessageTypeEnum.AGENT1_COMPLETE.value
            data["titleOptions"] = [
                item.model_dump(by_alias=True) for item in (state.title_options or [])
            ]
        elif message == SseMessageTypeEnum.AGENT2_COMPLETE.value:
            data["type"] = SseMessageTypeEnum.AGENT2_COMPLETE.value
            data["outline"] = [s.model_dump() for s in state.outline.sections] if state.outline else []
        elif message == SseMessageTypeEnum.AGENT3_COMPLETE.value:
            data["type"] = SseMessageTypeEnum.AGENT3_COMPLETE.value
        elif message == SseMessageTypeEnum.AGENT4_COMPLETE.value:
            data["type"] = SseMessageTypeEnum.AGENT4_COMPLETE.value
            data["imageRequirements"] = [
                req.model_dump(by_alias=True) for req in state.image_requirements
            ] if state.image_requirements else []
        elif message == SseMessageTypeEnum.AGENT5_COMPLETE.value:
            data["type"] = SseMessageTypeEnum.AGENT5_COMPLETE.value
            data["images"] = [
                img.model_dump(by_alias=True) for img in state.images
            ] if state.images else []
        elif message == SseMessageTypeEnum.MERGE_COMPLETE.value:
            data["type"] = SseMessageTypeEnum.MERGE_COMPLETE.value
            data["fullContent"] = state.full_content
        else:
            return None
        
        return data
    
    def _send_sse_message(
        self,
        task_id: str,
        type_enum: SseMessageTypeEnum,
        additional_data: Dict[str, Any]
    ):
        """发送 SSE 消息"""
        data = {"type": type_enum.value}
        data.update(additional_data)
        sse_emitter_manager.send(task_id, json.dumps(data, ensure_ascii=False))


# 全局单例
article_async_service = ArticleAsyncService()
