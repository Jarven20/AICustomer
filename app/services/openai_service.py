import json
import httpx
import asyncio
from typing import Dict, List, Any, Optional
from app.core.config import settings
from app.services.rag_service import rag_service
from app.services.redis_service import redis_service

class OpenAIService:
    def __init__(self):
        """初始化 OpenAI 服务"""
        self.api_key = settings.OPENAI_API_KEY
        self.api_url = settings.OPENAI_API_URL 
        self.model = "gpt-4o"  # 默认模型
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "x-auth-key": settings.OPENAI_AUTH_KEY
        }
        # Strapi配置
        self.strapi_url = settings.LOCAL_STRAPI_API_URL.rstrip('/')
        self.strapi_headers = {
            "Content-Type": "application/json"
        }
        # 如果有token则添加授权头
        if settings.LOCAL_STRAPI_API_TOKEN:
            self.strapi_headers["Authorization"] = f"Bearer {settings.LOCAL_STRAPI_API_TOKEN}"
        
        self.rag_service = rag_service  # 初始化 RAG 服务
        self.redis_service = redis_service  # 初始化 Redis 服务
    
    async def generate_response(self, messages: List[Dict[str, str]], 
                             temperature: float = 0.7, 
                             max_tokens: int = 1000) -> Dict[str, Any]:
        """
        通过 OpenAI API 生成回答
        
        Args:
            messages (List[Dict[str, str]]): 消息列表，包含角色和内容
            temperature (float): 温度参数，控制随机性
            max_tokens (int): 最大令牌数
            
        Returns:
            Dict[str, Any]: 包含生成回答的字典
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                
                # 提取回答内容
                if "choices" in result and len(result["choices"]) > 0:
                    return {
                        "content": result["choices"][0]["message"]["content"],
                        "role": "assistant",
                        "model": result.get("model", self.model),
                        "usage": result.get("usage", {})
                    }
                else:
                    return {"content": "抱歉，无法生成回答。", "role": "assistant"}
                    
        except Exception as e:
            print(f"OpenAI API 请求错误: {str(e)}")
            return {"content": f"抱歉，请求出错: {str(e)}", "role": "assistant"}
    
    async def generate_rag_response(self, session_id: str, query: Optional[str] = None) -> str:
        """
        使用 RAG 提示词模板生成回答
        
        Args:
            session_id (str): 会话 ID
            query (Optional[str]): 当前查询，如果为 None，则使用会话历史中的最后一个用户查询
            
        Returns:
            Dict[str, Any]: 包含生成回答的字典，包括内容、图片URL等
        """
        # 获取 RAG 提示词模板和图片URL
        rag_prompt = self.rag_service.build_rag_prompt(session_id, query)
        
        # 打印提示词模板 - 添加分隔线使其在终端中更易读
        print("\n" + "="*50)
        print("📝 输入到LLM的提示词模板:")
        print("="*50)
        print(rag_prompt)
        print("="*50 + "\n")
        
        # 构建消息
        messages = [{"role": "user", "content": rag_prompt}]
        
        # 生成回答
        response = await self.generate_response(messages)
        
        # # 添加图片URL到响应中
        # response["app_image_urls"] = app_image_urls
        # response["pc_image_urls"] = pc_image_urls
        
        return response
    
    def set_model(self, model_name: str) -> None:
        """
        设置使用的模型
        
        Args:
            model_name (str): 模型名称，例如 "gpt-3.5-turbo", "gpt-4" 等
        """
        self.model = model_name

    async def update_redis_conversation_history(self, session_id: str, query: str, response: str) -> None:
        """
        更新会话历史记录
        
        Args:
            session_id (str): 会话 ID
            query (str): 用户查询
            response (str): AI 响应
        """
        try:
            # 记录用户查询
            self.redis_service.record_user_query(session_id, query)
            
            # 记录AI响应
            self.redis_service.record_ai_response(session_id, response)
            
            print(f"✅ 成功更新会话历史记录: session_id={session_id}")
        except Exception as e:
            print(f"❌ 更新会话历史记录失败: {str(e)}")

    async def save_conversation_to_strapi(self, session_id: str, query: str, response: str) -> None:
        """
        保存会话历史到Strapi
        
        Args:
            session_id (str): 会话 ID
            query (str): 用户查询
            response (str): AI 响应
        """
        try:
            # 获取完整的会话历史
            full_history = self.redis_service.get_conversation_history(session_id)
            
            # 检查是否已存在该session的记录
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 查询是否存在 - 不使用过滤器，直接获取所有记录然后筛选
                search_url = f"{self.strapi_url}/api/ai-support-sessions"
                
                search_response = await client.get(
                    search_url,
                    headers=self.strapi_headers
                )
                
                print(f"🔍 Strapi查询URL: {search_url}")
                print(f"🔍 Strapi响应状态: {search_response.status_code}")
                
                if search_response.status_code == 200:
                    # 添加调试信息，查看响应结构
                    search_data = search_response.json()
                    print(f"🔍 Strapi响应数据结构: {search_data}")
                    
                if search_response.status_code == 200:
                    search_data = search_response.json()
                    
                    payload = {
                        "data": {
                            "session_id": session_id,
                            "history": full_history
                        }
                    }
                    
                    # 在客户端过滤匹配的session_id
                    existing_record = None
                    if search_data.get("data"):
                        for record in search_data["data"]:
                            if record.get("attributes", {}).get("session_id") == session_id:
                                existing_record = record
                                break
                    
                    if existing_record:
                        # 更新现有记录
                        record_id = existing_record["id"]
                        update_url = f"{self.strapi_url}/api/ai-support-sessions/{record_id}"
                        
                        response = await client.put(
                            update_url,
                            headers=self.strapi_headers,
                            json=payload
                        )
                        print(f"✅ 成功更新Strapi会话记录: session_id={session_id}, record_id={record_id}")
                    else:
                        # 创建新记录
                        create_url = f"{self.strapi_url}/api/ai-support-sessions"
                        
                        response = await client.post(
                            create_url,
                            headers=self.strapi_headers,
                            json=payload
                        )
                        print(f"✅ 成功创建Strapi会话记录: session_id={session_id}")
                        
                    if response.status_code not in [200, 201]:
                        print(f"❌ Strapi操作失败: {response.status_code}, {response.text}")
                else:
                    print(f"❌ Strapi查询失败: {search_response.status_code}, {search_response.text}")
                        
        except Exception as e:
            print(f"❌ 保存到Strapi失败: {str(e)}")

# 创建 OpenAI 服务实例
openai_service = OpenAIService()
