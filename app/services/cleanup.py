import os
import glob
from datetime import datetime, timedelta

def delete_update_file(update_file, data_dir):
    """
    删除指定的更新文件
    
    Args:
        update_file (str): 更新文件名或路径
        data_dir (str): 数据目录路径
        
    Returns:
        bool: 是否成功删除
    """
    try:
        # 处理相对路径和绝对路径
        file_path = update_file if os.path.isabs(update_file) else os.path.join(data_dir, update_file)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"✅ 已删除临时JSON文件: {file_path}")
            return True
        else:
            print(f"⚠️ 找不到临时JSON文件: {file_path}")
            return False
    except Exception as e:
        print(f"⚠️ 删除临时JSON文件失败: {str(e)}")
        return False 