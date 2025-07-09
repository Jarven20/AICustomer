import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.services.strapi_service import strapi_service
from app.core.config import settings
import os
import time
import threading
import schedule
import glob

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self):
        """初始化调度服务"""
        self.running = False
        self.scheduler_thread = None
        print("调度服务已创建")
    
    def update_knowledge_base(self):
        """定期更新知识库的任务"""
        print("\n📅 执行定时任务：更新知识库...")
        try:
            # 检查是否跳过Strapi数据抓取
            if settings.SKIP_STRAPI_FETCH:
                print("⚠️ 调试模式：跳过Strapi数据抓取")
            else:
                # 使用incremental_update_knowledge_base方法，获取最近24小时的数据
                strapi_service.incremental_update_knowledge_base(hours=24)
                
            print("✅ 知识库更新完成")
        except Exception as e:
            print(f"❌ 知识库更新失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def run_scheduler(self):
        """运行调度器"""
        print("调度线程启动")
        
        # 如果在调试模式下跳过了所有操作，则不添加任务
        if settings.DEBUG_MODE and settings.SKIP_STRAPI_FETCH and settings.SKIP_CHROMA_UPDATE:
            print("⚠️ 调试模式：所有数据操作已禁用，调度任务将不执行")
        else:
            # 每30分钟执行一次知识库更新
            schedule.every(30).minutes.do(self.update_knowledge_base)
            print("已设置每30分钟更新一次知识库")
        
        while self.running:
            schedule.run_pending()
            time.sleep(1)
        
        print("调度线程停止")
    
    def start(self):
        """启动调度服务"""
        if not self.running:
            self.running = True
            self.scheduler_thread = threading.Thread(target=self.run_scheduler)
            self.scheduler_thread.daemon = True  # 设置为守护线程，主程序结束时自动退出
            self.scheduler_thread.start()
            print("调度服务已启动")
        else:
            print("调度服务已经在运行")
    
    def shutdown(self):
        """关闭调度服务"""
        if self.running:
            self.running = False
            if self.scheduler_thread:
                self.scheduler_thread.join(timeout=2)  # 等待线程结束，最多等待2秒
            print("调度服务已关闭")
        else:
            print("调度服务未在运行")
            
    def get_jobs(self):
        """获取所有调度任务信息"""
        jobs = []
        
        # 获取schedule库中所有任务的信息
        all_jobs = schedule.jobs if hasattr(schedule, 'jobs') else []
        
        for job in all_jobs:
            try:
                # 提取任务信息
                job_info = {
                    "id": str(id(job)),  # 使用对象ID作为任务ID
                    "name": "知识库更新任务",  # 任务名称
                    "trigger": "interval"  # 触发器类型
                }
                
                # 尝试获取下次运行时间
                if hasattr(job, 'next_run'):
                    job_info["next_run_time"] = job.next_run.strftime("%Y-%m-%d %H:%M:%S") if job.next_run else "未设置"
                else:
                    job_info["next_run_time"] = "未知"
                
                # 固定显示为30分钟间隔，与run_scheduler方法一致
                job_info["interval"] = "每30分钟"
                
                jobs.append(job_info)
            except Exception as e:
                # 如果获取任务信息失败，添加一个错误信息
                jobs.append({
                    "id": str(id(job)) if job else "unknown",
                    "name": "未知任务",
                    "error": str(e)
                })
        
        # 如果没有任务，添加一个说明
        if not jobs:
            jobs.append({
                "id": "none",
                "name": "暂无任务",
                "status": "调度器已启动但没有配置任务"
            })
            
        return jobs
    
    @property
    def is_running(self):
        """获取调度服务运行状态"""
        return self.running

# 创建调度服务实例
scheduler_service = SchedulerService() 