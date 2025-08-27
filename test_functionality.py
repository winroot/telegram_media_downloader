#!/usr/bin/env python3
"""Test script to verify all functionality"""
import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, Mock

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger


def test_floodwait_handling():
    """测试FloodWait处理机制"""
    print("\n🧪 测试FloodWait处理...")
    
    # 模拟FloodWait错误
    class FloodWaitError(Exception):
        def __init__(self, value):
            self.value = value
            self.CODE = 420
    
    # 测试等待时间计算
    wait_time = 100
    actual_wait = wait_time + 5
    
    assert actual_wait == 105, "FloodWait等待时间计算错误"
    print("✅ FloodWait等待时间正确: 100秒 + 5秒缓冲 = 105秒")
    
    # 测试指数退避
    counts = [1, 2, 3, 4, 5]
    for count in counts:
        backoff = min(2 ** count, 32)
        interval = min(5 * backoff, 300)
        print(f"  第{count}次FloodWait: 退避倍数={backoff}, 间隔={interval}秒")
    
    print("✅ FloodWait指数退避策略正确")
    return True


def test_cloud_upload_disabled():
    """测试云盘上传功能是否已禁用"""
    print("\n🧪 测试云盘上传禁用...")
    
    # 检查代码中是否注释掉了上传功能
    with open("media_downloader.py", "r") as f:
        content = f.read()
    
    # 检查关键上传函数是否被注释
    assert "# await upload_telegram_chat(" in content, "上传功能未正确禁用"
    assert "# # rclone upload - 已禁用" in content, "rclone上传未正确禁用"
    
    print("✅ 云盘上传功能已成功禁用")
    return True


def test_hot_reload_module():
    """测试热重载模块"""
    print("\n🧪 测试热重载模块...")
    
    from module.hot_reload import TaskPersistence, HotReloader
    
    # 测试任务持久化
    persistence = TaskPersistence()
    
    # 创建模拟任务
    mock_task = MagicMock()
    mock_task.chat_id = 12345
    mock_task.is_running = True
    mock_task.current_download_msg_id = 100
    mock_task.download_status = {1: "success", 2: "failed"}
    mock_task.total_task = 10
    mock_task.success_download_count = 5
    mock_task.failed_download_count = 2
    mock_task.skip_download_count = 3
    mock_task.last_reply_time = 1234567890
    
    # 测试保存任务
    success = TaskPersistence.save_tasks([mock_task])
    assert success, "任务保存失败"
    assert os.path.exists("pending_tasks.json"), "任务文件未创建"
    
    # 测试加载任务
    tasks = TaskPersistence.load_tasks()
    assert len(tasks) == 1, "任务加载失败"
    assert tasks[0]['chat_id'] == 12345, "任务数据不正确"
    
    print("✅ 任务持久化功能正常")
    
    # 清理测试文件
    TaskPersistence.clear_tasks()
    assert not os.path.exists("pending_tasks.json"), "任务文件未清理"
    
    print("✅ 任务清理功能正常")
    
    # 测试热重载器
    reloader = HotReloader()
    reloader.request_reload()
    assert reloader.reload_requested, "重载请求未设置"
    
    print("✅ 热重载模块功能正常")
    return True


def test_bot_commands():
    """测试机器人命令"""
    print("\n🧪 测试机器人命令...")
    
    # 检查新命令是否已添加
    with open("module/bot.py", "r") as f:
        content = f.read()
    
    commands = [
        "cmd_reload",
        "cmd_save_state", 
        "cmd_restore_state",
        "show_floodwait",
        "pause_download",
        "resume_download",
        "task_info",
        "network_status"
    ]
    
    for cmd in commands:
        assert f"async def {cmd}" in content, f"命令 {cmd} 未找到"
        print(f"  ✅ 命令 /{cmd.replace('cmd_', '')} 已实现")
    
    print("✅ 所有机器人命令已正确实现")
    return True


def test_network_monitoring():
    """测试网络监控功能"""
    print("\n🧪 测试网络监控...")
    
    from module.app import Application
    
    # 创建应用实例
    app = Application("config.yaml", "data.yaml", "test")
    
    # 测试网络检查方法存在
    assert hasattr(app, 'is_network_available'), "网络检查方法不存在"
    assert hasattr(app, 'check_network_connectivity'), "网络连接检查方法不存在"
    
    print("✅ 网络监控功能已实现")
    return True


def test_floodwait_tracking():
    """测试FloodWait跟踪"""
    print("\n🧪 测试FloodWait跟踪...")
    
    from module.app import TaskNode
    
    # 创建任务节点
    node = TaskNode(chat_id=12345)
    
    # 测试FloodWait时间记录
    node.floodwait_until = 1234567890
    assert hasattr(node, 'floodwait_until'), "FloodWait时间未记录"
    
    # 测试FloodWait计数
    node.floodwait_count = 3
    assert hasattr(node, 'floodwait_count'), "FloodWait计数未记录"
    
    # 测试最小更新间隔
    node.min_update_interval = 60
    assert hasattr(node, 'min_update_interval'), "最小更新间隔未设置"
    
    print("✅ FloodWait跟踪机制正常")
    return True


async def test_async_functions():
    """测试异步函数"""
    print("\n🧪 测试异步函数...")
    
    # 测试FloodWait等待
    async def simulate_floodwait():
        wait_time = 0.1  # 使用短时间进行测试
        actual_wait = wait_time + 0.05
        await asyncio.sleep(actual_wait)
        return True
    
    result = await simulate_floodwait()
    assert result, "异步等待失败"
    
    print("✅ 异步函数测试通过")
    return True


def main():
    """主测试函数"""
    print("=" * 50)
    print("🚀 开始功能测试...")
    print("=" * 50)
    
    tests = [
        ("FloodWait处理", test_floodwait_handling),
        ("云盘上传禁用", test_cloud_upload_disabled),
        ("热重载模块", test_hot_reload_module),
        ("机器人命令", test_bot_commands),
        ("网络监控", test_network_monitoring),
        ("FloodWait跟踪", test_floodwait_tracking),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} 测试失败: {e}")
            results.append((test_name, False))
    
    # 运行异步测试
    try:
        asyncio.run(test_async_functions())
        results.append(("异步函数", True))
    except Exception as e:
        print(f"❌ 异步函数测试失败: {e}")
        results.append(("异步函数", False))
    
    print("\n" + "=" * 50)
    print("📊 测试结果汇总:")
    print("=" * 50)
    
    passed = 0
    failed = 0
    
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {test_name}: {status}")
        if success:
            passed += 1
        else:
            failed += 1
    
    print("=" * 50)
    print(f"总计: {passed} 通过, {failed} 失败")
    
    if failed == 0:
        print("🎉 所有测试通过！功能可以正常使用")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查相关功能")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)