import json
import redis
import datetime
from app.core.config import settings

class RedisService:
    # 三个月的TTL时间（秒）
    TTL_THREE_MONTHS = 90 * 24 * 60 * 60  # 90天 * 24小时 * 60分钟 * 60秒
    # 命名空间前缀
    NAMESPACE = "ai-support"
    
    def __init__(self):
        """初始化Redis客户端"""
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            decode_responses=True
        )
    
    def _normalize_session_key(self, session_id, add_history_suffix=True):
        """
        将session_id标准化为一致的格式
        1. 移除多余的session:前缀
        2. 移除多余的:history后缀
        3. 根据需要添加正确的前缀和后缀
        4. 添加命名空间前缀
        """
        # 先移除所有可能的前缀和后缀
        key = session_id
        while key.startswith("session:"):
            key = key[8:]
        while key.endswith(":history"):
            key = key[:-8]
            
        # 添加命名空间和标准前缀
        normalized_key = f"{self.NAMESPACE}:session:{key}"
        
        # 如果需要，添加history后缀
        if add_history_suffix:
            normalized_key = f"{normalized_key}:history"
            
        return normalized_key
    
    def get_conversation_history(self, session_id):
        """获取会话历史记录"""
        history_key = self._normalize_session_key(session_id, add_history_suffix=True)
        
        print(f"🔍 尝试从Redis获取历史记录，key: {history_key}")
        history = self.redis_client.get(history_key)
        return json.loads(history) if history else []
    
    def update_conversation_history(self, session_id, history):
        """更新会话历史记录"""
        history_key = self._normalize_session_key(session_id, add_history_suffix=True)
        
        print(f"✅ 更新会话历史记录: {history_key}")
        # 设置数据并添加三个月的过期时间
        self.redis_client.setex(history_key, self.TTL_THREE_MONTHS, json.dumps(history))
    
    def record_user_query(self, session_id, query):
        """记录用户查询"""
        history = self.get_conversation_history(session_id)
        history.append({
            "role": "user", 
            "content": query,
            "timestamp": datetime.datetime.now().isoformat()
        })
        self.update_conversation_history(session_id, history)
    
    def record_ai_response(self, session_id, response):
        """记录AI响应"""
        history = self.get_conversation_history(session_id)
        history.append({
            "role": "assistant", 
            "content": response,
            "timestamp": datetime.datetime.now().isoformat()
        })
        self.update_conversation_history(session_id, history)
    
    def save_feedback(self, session_id, feedback):
        """保存用户反馈"""
        feedback_key = f"{self.NAMESPACE}:session:{session_id}:feedback"
        # 设置数据并添加三个月的过期时间
        self.redis_client.setex(feedback_key, self.TTL_THREE_MONTHS, json.dumps(feedback))
        return True

redis_service = RedisService()