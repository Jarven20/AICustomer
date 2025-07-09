from typing import List, Optional
from pydantic import BaseModel, Field

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    """聊天请求模型"""
    query: str = Field(..., description="用户输入的问题或消息")
    session_id: str = Field(..., description="会话唯一标识符")

class ChatResponse(BaseModel):
    """聊天响应模型"""
    content: str = Field(..., description="AI生成的回答内容")
    session_id: str = Field(..., description="会话唯一标识符")


class SearchHintRequest(BaseModel):
    """搜索提示请求模型"""
    query: str = Field(..., description="用户已输入的部分查询")
    limit: int = Field(20, description="返回的提示数量上限")

class SearchHintResponse(BaseModel):
    """搜索提示响应模型"""
    suggestions: List[str] = Field([], description="推荐的问题完成列表")
    source_id: Optional[str] = Field(None, description="如果只有一个来源，则提供其ID")

class FeedbackRequest(BaseModel):
    """用户反馈请求模型"""
    satisfaction: str = Field(..., description="用户满意度文本")
    tag: Optional[str] = Field(None, description="反馈标签")
    commit: Optional[str] = Field(None, description="提交信息或备注")
    session_id: str = Field(..., description="会话唯一标识符")
    feedback_id: str = Field(..., description="反馈唯一标识符")
    session_history: Optional[str] = Field(None, description="会话历史记录（JSON格式文本）")

class FeedbackResponse(BaseModel):
    """用户反馈响应模型"""
    success: bool = Field(..., description="反馈是否保存成功")
    message: str = Field(..., description="反馈结果消息")
    feedback_id: str = Field(..., description="反馈唯一标识符")
    session_id: str = Field(..., description="会话唯一标识符") 