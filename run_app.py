import uvicorn
import logging
import argparse
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    # 解析命令行参数 (如果命名行中出现了相应的标识，则将action设置为store_true，比如python run_app.py --verbose --clear-db）
    parser = argparse.ArgumentParser(description='运行AI客服API服务')
    parser.add_argument('--verbose', action='store_true', help='启用详细日志模式')
    parser.add_argument('--clear-db', action='store_true', help='启动前清空ChromaDB')   # argparse 模块的一个特性：它会自动将命令行参数中的连字符（-）转换为下划线（_）
    args = parser.parse_args()
    

    # 如果指定了清空数据库参数，设置环境变量
    if args.clear_db:
        print("设置清空数据库环境变量: CLEAR_CHROMA_ON_STARTUP=True")
        os.environ["CLEAR_CHROMA_ON_STARTUP"] = "True"
    
    # 启动FastAPI应用
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    ) 