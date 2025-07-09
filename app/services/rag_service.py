import json
from app.services.redis_service import redis_service
from app.services.strapi_service import strapi_service

class RAGService:
    def __init__(self):
        """初始化 RAG 服务"""
        self.redis_service = redis_service
        self.strapi_service = strapi_service
    
    def get_relevant_knowledge(self, query):
        """
        从知识库中获取与查询相关的知识
        
        Args:
            query (str): 用户查询
            
        Returns:
            str: 相关知识文本
        """
        try:
            print(f"\n🔍 开始获取与查询 '{query}' 相关的知识...")
            
            # 初始化图片URL列表
            app_image_urls = []
            pc_image_urls = []
            
            # 1. 获取相似问题的ID
            try:
                faq_ids = strapi_service.get_similar_faq_ids(query, n_results=3)
                if not faq_ids:
                    print("⚠️ 未找到相关的FAQ")
                    return "未找到相关的知识内容。", [], []
            except Exception as e:
                
                return "获取相似问题失败，请确保向量数据库已正确初始化并包含数据。", [], []
            
            # 2. 获取FAQ详细信息
            try:
                faq_details = strapi_service.get_faq_details_by_ids(faq_ids)
                if not faq_details:
                    print("⚠️ 无法获取FAQ详细信息")
                    return "无法获取相关的知识内容。", [], []
            except Exception as e:
                print(f"❌ 获取FAQ详细信息失败: {str(e)}")
                return "获取知识详情失败，请确保知识库文件存在且格式正确。", [], []
            
            # 4. 格式化FAQ信息为RAG文本
            try:
                formatted_text = strapi_service.format_faq_for_rag(faq_details)
                if not formatted_text:
                    print("⚠️ 格式化FAQ信息失败")
                    return "格式化知识内容失败。", [], []
            except Exception as e:
                print(f"❌ 格式化FAQ信息失败: {str(e)}")
                return "格式化知识内容时发生错误。", [], []
            
            print("✅ 成功获取相关知识")
            print(f"找到 {len(app_image_urls)} 个APP图片和 {len(pc_image_urls)} 个PC图片")
            
            return formatted_text
            
        except Exception as e:
            print(f"❌ 获取相关知识失败: {str(e)}")
            return f"获取相关知识时发生错误: {str(e)}", [], []
    
    def format_knowledge(self, relevant_knowledge):
        """
        使用 strapi_service 的 format_faq_for_rag 函数格式化相关知识。
        
        Args:
            relevant_knowledge (str): 相关知识文本
            
        Returns:
            str: 格式化后的知识文本
        """
        try:
            # 假设 relevant_knowledge 是一个 FAQ 详细信息列表
            formatted_knowledge = self.strapi_service.format_faq_for_rag(relevant_knowledge)
            return formatted_knowledge
        except Exception as e:
            print(f"❌ 格式化知识失败: {str(e)}")
            return ""
    
    def format_conversation_history(self, history):
        """
        将会话历史记录格式化为字符串
        
        Args:
            history (list): 会话历史记录列表
            [
                {"role": "user", "content": "你好，我有个问题"},
                {"role": "assistant", "content": "您好，请问有什么可以帮助您的？"},
                {"role": "user", "content": "如何使用这个系统？"}
            ]
            
        Returns:
            str: 格式化后的会话历史记录
            "用户: 你好，我有个问题\n助手: 您好，请问有什么可以帮助您的？\n用户: 如何使用这个系统？"
        """
        formatted_history = ""
        for message in history:
            role = "用户" if message["role"] == "user" else "助手"
            formatted_history += f"{role}: {message['content']}\n"
        return formatted_history.strip()  #
    
    def build_rag_prompt(self, session_id, query=None):
        """
        构建 RAG 提示词模板
        
        Args:
            session_id (str): 会话 ID
            query (str, optional): 当前查询，如果为 None，则使用会话历史中的最后一个用户查询
            
        Returns:
            tuple: (RAG提示词模板, APP图片URL列表, PC图片URL列表)
        """
        # 获取会话历史
        full_history = self.redis_service.get_conversation_history(session_id)
        
        # 限制历史记录为最近3轮对话
        history = []
        if full_history:
            # 将消息分组为轮次（一个用户消息和一个助手消息为一轮）
            rounds = []
            current_round = []
            
            for msg in full_history:
                current_round.append(msg)
                # 当收集到助手消息时，完成一轮对话
                if msg["role"] == "assistant":
                    rounds.append(current_round)
                    current_round = []
            
            # 处理可能的未完成轮次（只有用户消息，没有助手回复）
            if current_round:
                rounds.append(current_round)
            
            # 只保留最后3轮
            limited_rounds = rounds[-3:] if len(rounds) > 3 else rounds
            
            # 展平轮次列表，获得最终历史
            for r in limited_rounds:
                history.extend(r)
            
            print(f"📜 会话历史已限制为{len(limited_rounds)}轮（共{len(rounds)}轮）")
        
        # 如果提供了查询且不为空，则使用提供的查询
        if query:
            current_query = query
        else:
            # 从历史记录中提取最后一个用户查询
            user_queries = [msg["content"] for msg in history if msg["role"] == "user"]
            if user_queries:
                current_query = user_queries[-1]
            else:
                current_query = ""
        
        # 获取相关知识和图片URL
        relevant_knowledge = self.get_relevant_knowledge(current_query)
        # 格式化会话历史
        formatted_history = self.format_conversation_history(history)
        
        print(f"🔄 使用了{len(history)}条历史消息构建RAG提示")
        
        # 构建 RAG 提示词模板
        prompt_template = f"""你是AiCoin应用的智能聊天助手，会根据用户的问题和提供的相关知识给出准确、全面的回答。

            ## 会话历史
            {formatted_history}

            ## 当前问题
            {current_query}

            ## 相关知识
            {relevant_knowledge}

            ## 回答要求
            请基于以上信息提供专业、简洁且全面的回答。请遵循以下原则：

            1. **内容准确性**：以提供的相关知识为主要依据，减少自主生成的信息
            2. **关联性判断**：自行判断相关知识与用户问题的匹配度，优先选择最相关的内容
            3. **补充完善**：如果相关知识不足以完整回答问题，可基于你的知识进行合理补充

            ## 图片展示规则
            当相关知识中包含图片URL时，请根据以下情况智能展示：

            **需要展示图片的场景：**
            - 用户询问操作步骤、使用方法、功能介绍
            - 问题涉及界面、按钮、设置等可视化内容
            - 回答中引用的知识点包含图片说明

            **图片展示格式：**
            - 如果知识点同时包含PC端和移动端图片，优先展示移动端图片（APP端图片）
            - 使用markdown格式：`![图片描述](图片URL)`
            - 图片描述应简洁明了，如"操作步骤图"、"界面示意图"、"设置页面"等
            - 将图片放在回答的相关段落后或回答末尾

            **示例：**
            如果回答中使用了包含以下内容的知识点：
            - APP端图片: https://example.com/app-guide.png
            - PC端图片: https://example.com/pc-guide.png

            请在回答适当位置添加：
            ![操作指引](https://example.com/app-guide.png)

            请注意，只有在回答操作类问题且相关知识中包含图片URL时才需要添加图片。
            """
        return prompt_template

# 创建 RAG 服务实例
rag_service = RAGService()
