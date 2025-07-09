from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.services.redis_service import redis_service
from app.services.strapi_service import strapi_service
from app.services.scheduler_service import scheduler_service
from app.services.hint_service import hint_service

# 设置环境变量，禁用 CoreML 执行提供程序
import os
os.environ["ONNXRUNTIME_PROVIDERS_TO_DISABLE"] = "CoreMLExecutionProvider"
os.environ["ONNX_PROVIDERS"] = "CPUExecutionProvider"

from app.api.routes import router as api_router
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print("\n🚀 应用启动中...")
    
    try:
        # 根据环境变量决定是否清空 ChromaDB
        clear_db = os.environ.get("CLEAR_CHROMA_ON_STARTUP", "False").lower() == "true"
        if clear_db:
            print("\n⚠️ 检测到 CLEAR_CHROMA_ON_STARTUP=True，将清空 ChromaDB...")
            # 首先清空 ChromaDB 中的所有集合
            strapi_service.clear_chromadb()
        else:
            print("\nℹ️ 跳过清空 ChromaDB 步骤 (CLEAR_CHROMA_ON_STARTUP 未设置为 True)")
        
        # 爬取Strapi语料库知识
        if not settings.SKIP_STRAPI_FETCH:
            print("\n📥 开始抓取Strapi上的所有知识...")
            # 抓取所有知识并保存到_full.json
            full_json_path = strapi_service.fetch_and_save_knowledge()
            print(f"✅ 知识抓取完成，保存到: {full_json_path}")
            
            print("\n🔍 开始解析知识库数据...")
            # 解析_full.json生成_parsed.json
            parsed_json_path = strapi_service.parse_knowledge_json()
            print(f"✅ 知识解析完成，保存到: {parsed_json_path}")
            
        
        # 将Strapi上的知识更新进ChromDB
        if not settings.SKIP_CHROMA_UPDATE:  
            # 如果跳过Strapi获取但需要更新向量库，仍然需要检查向量库
            strapi_service.store_faq_in_chromadb(recreate_collection=True)
        
        # 检查ChromaDB中是否有数据
        strapi_service.inspect_chromadb()
        
        # 检查两个json文件是否存在
        full_json_path = os.path.join(settings.DATA_DIR, "strapi_knowledge_full.json")
        parsed_json_path = os.path.join(settings.DATA_DIR, "strapi_knowledge_parsed.json")
        
        if not os.path.exists(full_json_path):
            print(f"⚠️ 警告: 未找到完整知识库文件 {full_json_path}")
        if not os.path.exists(parsed_json_path):
            print(f"⚠️ 警告: 未找到解析后的知识库文件 {parsed_json_path}")
            
        print("✅ 语料库RAG服务初始化完成")
    except Exception as e:
        print(f"❌ 语料库RAG服务初始化失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # 启动调度服务
    scheduler_service.start()
    print("✅ 调度服务已启动")
    
    # 初始化搜索提示服务
    try:
        hint_service.initialize()
        print(f"✅ 搜索提示服务初始化完成，共加载 {len(hint_service.hint_list)} 个问题")
        # Check if hints are missing and generate if necessary
        if not hint_service.is_initialized or len(hint_service.hint_list) == 0:
             print("💡 提示文件不存在或为空，尝试生成...")
             if hint_service.generate_and_load_hints():
                 print(f"✅ 成功生成并加载了 {len(hint_service.hint_list)} 条搜索提示。")
             else:
                 print("❌ 生成搜索提示失败。服务可能无法提供搜索建议。")

    except Exception as e:
        print(f"❌ 搜索提示服务初始化失败: {str(e)}")
        import traceback
        traceback.print_exc()

    print("✅ 应用启动完成")
    
    yield
    
    # 关闭时执行
    print("\n🛑 应用关闭中...")
    scheduler_service.shutdown()
    print("✅ 应用已关闭")

app = FastAPI(
    title=settings.APP_NAME,
    description="AI Support Service API",
    version="0.1.0",
    lifespan=lifespan
)

# 设置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含路由
app.include_router(api_router)

@app.get("/")
async def root():
    return {"message": "Welcome to AI Support Service API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False) 