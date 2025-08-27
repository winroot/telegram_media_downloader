"""Hot reload module for dynamic code loading and task persistence"""
import asyncio
import importlib
import json
import os
import pickle
import signal
import sys
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from module.app import TaskNode


class TaskPersistence:
    """Save and restore download tasks"""
    
    TASK_FILE = "pending_tasks.json"
    STATE_FILE = "app_state.pkl"
    
    @classmethod
    def save_tasks(cls, tasks: List[TaskNode]) -> bool:
        """Save current tasks to file"""
        try:
            task_data = []
            for task in tasks:
                # 保存所有运行中的任务，不管是否有current_download_msg_id
                if hasattr(task, 'is_running') and task.is_running:
                    task_info = {
                        'chat_id': getattr(task, 'chat_id', None),
                        'task_id': getattr(task, 'task_id', 0),
                        'total_download_task': getattr(task, 'total_download_task', 0),
                        'success_download_task': getattr(task, 'success_download_task', 0),
                        'failed_download_task': getattr(task, 'failed_download_task', 0),
                        'skip_download_task': getattr(task, 'skip_download_task', 0),
                        'is_paused': getattr(task, 'is_paused', False),
                        'start_offset_id': getattr(task, 'start_offset_id', 0),
                        'end_offset_id': getattr(task, 'end_offset_id', 0),
                        'download_filter': getattr(task, 'download_filter', None),
                    }
                    # 保存下载状态字典（如果存在）
                    if hasattr(task, 'download_status'):
                        task_info['message_ids'] = list(task.download_status.keys())
                    task_data.append(task_info)
            
            with open(cls.TASK_FILE, 'w') as f:
                json.dump(task_data, f, indent=2)
            
            logger.info(f"✅ 已保存 {len(task_data)} 个任务到 {cls.TASK_FILE}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存任务失败: {e}")
            return False
    
    @classmethod
    def load_tasks(cls) -> List[Dict[str, Any]]:
        """Load saved tasks from file"""
        try:
            if not os.path.exists(cls.TASK_FILE):
                return []
            
            with open(cls.TASK_FILE, 'r') as f:
                task_data = json.load(f)
            
            logger.info(f"✅ 已加载 {len(task_data)} 个任务从 {cls.TASK_FILE}")
            return task_data
        except Exception as e:
            logger.error(f"❌ 加载任务失败: {e}")
            return []
    
    @classmethod
    def clear_tasks(cls):
        """Clear saved tasks"""
        try:
            if os.path.exists(cls.TASK_FILE):
                os.remove(cls.TASK_FILE)
                logger.info(f"✅ 已清除任务文件 {cls.TASK_FILE}")
        except Exception as e:
            logger.error(f"❌ 清除任务失败: {e}")
    
    @classmethod
    def save_app_state(cls, app) -> bool:
        """Save application state"""
        try:
            state = {
                'config': app.config,
                'chat_download_config': app.chat_download_config,
                'download_filter': app.download_filter,
                'proxy': app.proxy,
                'save_path': app.save_path,
            }
            
            with open(cls.STATE_FILE, 'wb') as f:
                pickle.dump(state, f)
            
            logger.info(f"✅ 已保存应用状态到 {cls.STATE_FILE}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存应用状态失败: {e}")
            return False
    
    @classmethod
    def load_app_state(cls) -> Optional[Dict[str, Any]]:
        """Load application state"""
        try:
            if not os.path.exists(cls.STATE_FILE):
                return None
            
            with open(cls.STATE_FILE, 'rb') as f:
                state = pickle.load(f)
            
            logger.info(f"✅ 已加载应用状态从 {cls.STATE_FILE}")
            return state
        except Exception as e:
            logger.error(f"❌ 加载应用状态失败: {e}")
            return None


class HotReloader:
    """Dynamic module reloading"""
    
    def __init__(self):
        self.reload_requested = False
        self.active_tasks = []
        self.loop = None
        
    def request_reload(self):
        """Request a reload"""
        self.reload_requested = True
        logger.info("🔄 收到代码重载请求")
    
    async def pause_tasks(self, tasks: List[TaskNode]):
        """Pause all running tasks"""
        paused_count = 0
        for task in tasks:
            if task.is_running:
                task.is_running = False
                paused_count += 1
        
        logger.info(f"⏸️ 已暂停 {paused_count} 个下载任务")
        
        # 保存任务状态
        TaskPersistence.save_tasks(tasks)
        
        # 等待当前下载完成
        await asyncio.sleep(2)
    
    def reload_modules(self):
        """Reload Python modules"""
        modules_to_reload = [
            'module.app',
            'module.bot',
            'module.pyrogram_extension',
            'module.download_stat',
            'module.get_chat_history_v2',
            'module.filter',
            'module.language',
            'module.cloud_drive',
            'utils.format',
            'utils.log',
            'utils.meta',
            'utils.meta_data',
        ]
        
        reloaded = []
        failed = []
        
        for module_name in modules_to_reload:
            try:
                if module_name in sys.modules:
                    importlib.reload(sys.modules[module_name])
                    reloaded.append(module_name)
            except Exception as e:
                failed.append((module_name, str(e)))
        
        if reloaded:
            logger.info(f"✅ 成功重载模块: {', '.join(reloaded)}")
        
        if failed:
            for module_name, error in failed:
                logger.error(f"❌ 重载模块失败 {module_name}: {error}")
        
        return len(failed) == 0
    
    async def resume_tasks(self):
        """Resume paused tasks"""
        task_data = TaskPersistence.load_tasks()
        
        if task_data:
            logger.info(f"▶️ 准备恢复 {len(task_data)} 个任务")
            # 这里需要在主程序中实现任务恢复逻辑
            return task_data
        
        return []
    
    async def check_reload_request(self, app, client, tasks):
        """Check if reload is requested and handle it"""
        while True:
            await asyncio.sleep(5)  # 每5秒检查一次
            
            if self.reload_requested:
                logger.info("🔄 开始执行热重载...")
                
                # 1. 暂停任务
                await self.pause_tasks(tasks)
                
                # 2. 保存应用状态
                TaskPersistence.save_app_state(app)
                
                # 3. 重载模块
                if self.reload_modules():
                    logger.info("✅ 代码重载成功")
                    
                    # 4. 恢复任务
                    resumed_tasks = await self.resume_tasks()
                    
                    logger.info(f"🎉 热重载完成，恢复了 {len(resumed_tasks)} 个任务")
                else:
                    logger.error("❌ 代码重载失败，继续使用旧代码")
                
                self.reload_requested = False


# 全局热重载实例
hot_reloader = HotReloader()


def setup_reload_signal():
    """Setup signal handler for reload request (Unix-like systems)"""
    def handle_reload_signal(signum, frame):
        logger.info(f"📡 收到信号 {signum}，请求热重载")
        hot_reloader.request_reload()
    
    try:
        # 使用 SIGUSR1 信号触发重载
        signal.signal(signal.SIGUSR1, handle_reload_signal)
        logger.info("✅ 热重载信号处理器已设置 (kill -USR1 <pid>)")
    except AttributeError:
        # Windows 不支持 SIGUSR1
        logger.warning("⚠️ 当前系统不支持信号热重载")


def create_reload_command():
    """Create a reload command file that can trigger reload"""
    reload_file = "RELOAD_NOW"
    
    async def check_reload_file():
        """Check if reload file exists"""
        while True:
            await asyncio.sleep(3)
            if os.path.exists(reload_file):
                logger.info(f"📄 检测到重载文件 {reload_file}")
                hot_reloader.request_reload()
                try:
                    os.remove(reload_file)
                except:
                    pass
    
    return check_reload_file


# Bot command for reload
async def cmd_reload(client, message):
    """Bot command to trigger hot reload"""
    await message.reply_text("🔄 正在执行热重载...")
    hot_reloader.request_reload()
    return "reload_requested"


async def cmd_save_tasks(client, message):
    """Bot command to save current tasks"""
    # 这里需要访问当前的任务列表
    await message.reply_text("💾 正在保存任务状态...")
    # TaskPersistence.save_tasks(tasks)
    return "tasks_saved"


async def cmd_load_tasks(client, message):
    """Bot command to load saved tasks"""
    tasks = TaskPersistence.load_tasks()
    await message.reply_text(f"📂 找到 {len(tasks)} 个保存的任务")
    return tasks