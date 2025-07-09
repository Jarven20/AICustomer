from fastapi import APIRouter, HTTPException
from app.services.rag_service import rag_service
from app.models.schemas import ChatRequest, ChatResponse, SearchHintRequest, SearchHintResponse, FeedbackRequest, FeedbackResponse
from app.services.openai_service import openai_service
from app.services.scheduler_service import scheduler_service
from app.services.hint_service import hint_service
from app.services.strapi_service import strapi_service
from app.services.redis_service import redis_service
import asyncio
import uuid
import traceback
import json

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """处理聊天请求"""
    try:
        # 生成回复
        response = await openai_service.generate_rag_response(
            session_id=request.session_id, 
            query=request.query
        )
        
        # 创建响应对象
        chat_response = ChatResponse(
            content=response["content"],
            session_id=request.session_id,

        )
        
        # 异步更新redis会话历史
        asyncio.create_task(
            openai_service.update_redis_conversation_history(
                session_id=request.session_id,
                query=request.query,
                response=response["content"]
            )
        )
        
        # 异步存储会话历史到Strapi
        asyncio.create_task(
            openai_service.save_conversation_to_strapi(
                session_id=request.session_id,
                query=request.query,
                response=response["content"]
            )
        )
        
        return chat_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update-knowledge")
async def update_knowledge():
    """手动触发知识库增量更新"""
    try:
        updated = strapi_service.incremental_update_knowledge_base(hours=24)
        return {
            "status": "success" if updated else "info",
            "message": "知识库增量更新成功" if updated else "无需更新或更新失败"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"知识库增量更新失败: {str(e)}")

@router.post("/update-knowledge/full")
async def update_knowledge_full():
    """手动触发知识库全量更新"""
    try:
        print("🚀 开始执行知识库全量更新...")

        # 1. 从 Strapi 获取最新数据并保存为 strapi_knowledge_full.json
        print("étape 1: 从 Strapi 获取最新数据...")
        full_json_path = strapi_service.fetch_and_save_knowledge()
        if not full_json_path:
            raise HTTPException(status_code=500, detail="从 Strapi 获取数据失败")
        print(f"✅ 数据已保存到: {full_json_path}")

        # 2. 解析完整数据，生成 strapi_knowledge_parsed.json
        print("étape 2: 解析数据...")
        parsed_json_path = strapi_service.parse_knowledge_json(input_file="strapi_knowledge_full.json")
        if not parsed_json_path:
             raise HTTPException(status_code=500, detail="解析 Strapi 数据失败")
        print(f"✅ 解析后的数据已保存到: {parsed_json_path}")

        # 3. 将解析后的数据存储到 ChromaDB，并重建集合
        print("étape 3: 将数据存储到 ChromaDB...")
        # 使用 store_faq_in_chromadb 方法，设置 recreate_collection=True
        updated = strapi_service.store_faq_in_chromadb(recreate_collection=True)
        if not updated:
            # store_faq_in_chromadb 内部已经打印了错误，这里直接抛出异常
            raise HTTPException(status_code=500, detail="将数据存储到 ChromaDB 失败")
        print("✅ 数据成功存储到 ChromaDB")

        # 4. 刷新搜索提示 (store_faq_in_chromadb 内部也会尝试刷新，这里保留显式调用以防万一)
        # 注意：store_faq_in_chromadb 内部已包含刷新逻辑，这里的调用可能重复，但为了保险起见保留
        print("étape 4: 刷新搜索提示...")
        try:
            hint_service.refresh()
            print("✅ 搜索提示列表已刷新")
        except Exception as e:
            # 允许刷新失败，只记录警告
            print(f"⚠️ 刷新搜索提示列表失败: {str(e)}")

        print("🎉 知识库全量更新成功完成！")
        return {
            "status": "success",
            "message": "知识库全量更新成功"
        }
    except HTTPException as http_exc:
        # 直接重新抛出 HTTP 异常
        raise http_exc
    except Exception as e:
        print(f"❌ 知识库全量更新过程中发生意外错误: {str(e)}")
        traceback.print_exc() # 打印详细错误堆栈
        # 返回通用错误
        raise HTTPException(status_code=500, detail=f"知识库全量更新失败: {str(e)}")

@router.get("/scheduler-jobs")
async def get_scheduler_jobs():
    """获取所有调度任务信息"""
    try:
        jobs = scheduler_service.get_jobs()
        return {
            "status": "success",
            "data": {
                "is_running": scheduler_service.is_running,
                "jobs": jobs
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取调度任务失败: {str(e)}")

@router.post("/refresh-search-hints")
async def refresh_search_hints():
    """手动刷新搜索提示列表"""
    try:
        hint_service.refresh()
        hint_count = len(hint_service.hint_list)
        return {
            "status": "success", 
            "message": "搜索提示列表刷新成功", 
            "hint_count": hint_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刷新搜索提示失败: {str(e)}")

@router.post("/searchHint", response_model=SearchHintResponse)
async def search_hint(request: SearchHintRequest):
    """根据用户部分输入，提供可能的问题补全"""
    try:
        # 确保初始化
        if not hint_service.is_initialized:
            hint_service.initialize()
            
        # 获取匹配的提示列表
        suggestions = hint_service.search_hints(
            query=request.query,
            limit=request.limit
        )
        
        # 判断是否所有结果来自同一个知识库项
        source_id = None
        if len(suggestions) == 1:
            source_id = hint_service.get_hint_source(suggestions[0])
        elif len(suggestions) > 1:
            sources = set(hint_service.get_hint_source(hint) for hint in suggestions)
            if len(sources) == 1:
                source_id = sources.pop()
        
        return SearchHintResponse(
            suggestions=suggestions,
            source_id=source_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索提示失败: {str(e)}")

@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(request: FeedbackRequest):
    """处理用户对AI回答的反馈（点赞/点踩）"""
    try:
        # 1. 获取请求参数
        satisfaction = request.satisfaction
        tag = request.tag
        commit = request.commit
        session_id = request.session_id
        feedback_id = request.feedback_id

        # 2. 从Redis获取会话历史记录
        session_history = redis_service.get_conversation_history(session_id)
        
        # 3. 处理空会话历史
        if not session_history:
            print(f"⚠️ 警告: Redis中没有找到会话历史记录 (session_id: {session_id})，此次反馈可能超过三个月，请检查")
            session_history = [{"role": "system", "content": "没有历史记录 - 可能超过三个月"}]
        
        # 4. 将会话历史转换为JSON，以便在Strapi中存储
        session_history_json = json.dumps(session_history)

        # 5. 将反馈信息存储到Strapi
        success, message = strapi_service.submit_feedback(
            feedback_id=feedback_id,
            good_or_bad=satisfaction,
            session_history=session_history_json,
            session_id=session_id
        )
        
        # 6. 返回结果
        return FeedbackResponse(
            success=success,
            message=message,
            feedback_id=feedback_id,
            session_id=session_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理反馈失败: {str(e)}")