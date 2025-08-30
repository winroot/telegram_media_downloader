#!/usr/bin/env python3
"""
测试程序优雅关闭功能
"""

import asyncio
import signal
import sys
import time
from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stderr, level="DEBUG", format="{time:HH:mm:ss} | {level} | {message}")

class MockClient:
    """模拟 Pyrogram 客户端"""
    def __init__(self):
        self.is_connected = True
        self.sessions = []
        
    async def stop(self):
        """模拟客户端停止"""
        logger.info("正在停止客户端...")
        # 模拟可能出现的并发读取错误
        if self.sessions:
            raise RuntimeError("read() called while another coroutine is already waiting for incoming data")
        await asyncio.sleep(0.5)
        self.is_connected = False
        logger.info("客户端已停止")

async def worker_task(task_id):
    """模拟下载任务"""
    try:
        logger.info(f"任务 {task_id} 开始运行")
        while True:
            await asyncio.sleep(1)
            logger.debug(f"任务 {task_id} 正在工作...")
    except asyncio.CancelledError:
        logger.info(f"任务 {task_id} 被取消")
        raise

async def network_monitor():
    """模拟网络监控"""
    try:
        logger.info("网络监控已启动")
        while True:
            await asyncio.sleep(2)
            logger.debug("检查网络状态...")
    except asyncio.CancelledError:
        logger.info("网络监控已停止")
        raise

async def stop_server_safe(client):
    """安全停止服务器"""
    try:
        await asyncio.sleep(0.1)
        if client.is_connected:
            await client.stop()
    except RuntimeError as e:
        if "read() called while another coroutine" in str(e):
            logger.debug(f"关闭时的并发读取冲突已忽略: {e}")
        else:
            logger.error(f"关闭客户端时出错: {e}")
    except ConnectionResetError as e:
        logger.debug(f"关闭时的连接重置已忽略: {e}")
    except Exception as e:
        logger.error(f"关闭客户端时发生未知错误: {e}")

async def main():
    """主函数"""
    client = MockClient()
    client.sessions = ["session1", "session2"]  # 模拟活跃会话
    
    # 创建任务
    tasks = []
    for i in range(3):
        task = asyncio.create_task(worker_task(i))
        tasks.append(task)
    
    network_task = asyncio.create_task(network_monitor())
    
    # 设置信号处理
    def signal_handler(sig, frame):
        logger.info("⌨️ 收到中断信号 (Ctrl+C)")
        asyncio.create_task(shutdown(client, tasks, network_task))
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        logger.success("程序已启动 (按 Ctrl+C 停止)")
        await asyncio.sleep(10)  # 模拟运行
    except KeyboardInterrupt:
        pass

async def shutdown(client, tasks, network_task):
    """优雅关闭"""
    logger.info("🔄 正在优雅关闭程序...")
    
    # 1. 先取消所有任务
    for task in tasks:
        task.cancel()
    network_task.cancel()
    
    # 2. 等待任务取消完成
    all_tasks = tasks + [network_task]
    if all_tasks:
        await asyncio.gather(*all_tasks, return_exceptions=True)
    
    # 3. 停止客户端
    await stop_server_safe(client)
    
    logger.success("✅ 程序已优雅关闭")
    sys.exit(0)

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("测试优雅关闭功能")
    logger.info("=" * 50)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被中断")
    except Exception as e:
        logger.error(f"程序异常: {e}")
    
    logger.info("测试完成")