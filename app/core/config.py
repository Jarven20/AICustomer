import os
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)

class Settings(BaseModel):
    APP_NAME: str = os.getenv("APP_NAME", "AI-Support-Terry")  #类型注解（: str）
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
        # 添加 DATA_DIR 配置，指向 app/data 目录
    DATA_DIR: str = os.getenv("DATA_DIR", os.path.join("app", "data"))
    
    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    OPENAI_API_URL: str = os.getenv("OPENAI_API_URL")
    OPENAI_AUTH_KEY: str = os.getenv("OPENAI_AUTH_KEY", "IJWF6iS0aCEv")
    
    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    
    # Strapi Configuration
    STRAPI_API_URL: str = os.getenv("STRAPI_API_URL")
    STRAPI_API_TOKEN: str = os.getenv("STRAPI_API_TOKEN", "")
    
    # Local Strapi Configuration
    LOCAL_STRAPI_API_URL: str = os.getenv("LOCAL_STRAPI_API_URL", "http://localhost:1337/")
    LOCAL_STRAPI_API_TOKEN: str = os.getenv("LOCAL_STRAPI_API_TOKEN", "")
    
    # Debug Configuration
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"
    SKIP_STRAPI_FETCH: bool = os.getenv("SKIP_STRAPI_FETCH", "false").lower() == "true"
    SKIP_CHROMA_UPDATE: bool = os.getenv("SKIP_CHROMA_UPDATE", "false").lower() == "true"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # print(f"Loaded STRAPI_API_URL: {self.STRAPI_API_URL}")
        # print(f"Loaded LOCAL_STRAPI_API_URL: {self.LOCAL_STRAPI_API_URL}")
        # print(f"❗️❗️❗️Loaded STRAPI_API_TOKEN: {self.STRAPI_API_TOKEN}")
        # 打印调试模式状态
        if self.DEBUG_MODE:
            print(f"⚠️ 调试模式已启用")
            if self.SKIP_STRAPI_FETCH:
                print(f"⚠️ Strapi数据抓取已禁用")
            if self.SKIP_CHROMA_UPDATE:
                print(f"⚠️ ChromaDB向量化已禁用")

settings = Settings() 