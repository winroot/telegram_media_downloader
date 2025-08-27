#!/usr/bin/env python3
"""
测试 /reload 命令的功能
"""

import sys
import importlib
from loguru import logger

def test_module_reload():
    """测试模块重载功能"""
    print("=" * 50)
    print("🧪 测试模块重载功能")
    print("=" * 50)
    
    modules_to_reload = [
        'module.app',
        'module.pyrogram_extension', 
        'module.download_stat',
        'media_downloader'
    ]
    
    print("\n1️⃣ 检查模块是否已加载...")
    for module_name in modules_to_reload:
        if module_name in sys.modules:
            print(f"  ✅ {module_name} - 已加载")
        else:
            print(f"  ❌ {module_name} - 未加载")
    
    print("\n2️⃣ 尝试重载模块...")
    success_count = 0
    failed_modules = []
    
    for module_name in modules_to_reload:
        try:
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
                print(f"  ✅ {module_name} - 重载成功")
                success_count += 1
            else:
                # 尝试导入模块
                module = importlib.import_module(module_name)
                print(f"  ✅ {module_name} - 导入成功")
                success_count += 1
        except Exception as e:
            print(f"  ❌ {module_name} - 重载失败: {str(e)}")
            failed_modules.append((module_name, str(e)))
    
    print("\n3️⃣ 测试结果汇总:")
    print(f"  成功: {success_count}/{len(modules_to_reload)}")
    if failed_modules:
        print(f"  失败的模块:")
        for module, error in failed_modules:
            print(f"    - {module}: {error}")
    
    print("\n4️⃣ 测试任务保存和恢复...")
    try:
        from module.hot_reload import TaskPersistence
        from module.app import TaskNode
        
        # 创建测试任务
        test_task = TaskNode(chat_id=-123456)
        test_task.is_running = True
        test_task.total_download_task = 10
        test_task.success_download_task = 5
        
        # 保存任务
        saved = TaskPersistence.save_tasks([test_task])
        print(f"  {'✅' if saved else '❌'} 任务保存测试")
        
        # 加载任务
        loaded_tasks = TaskPersistence.load_tasks()
        print(f"  {'✅' if loaded_tasks else '❌'} 任务加载测试")
        
    except Exception as e:
        print(f"  ❌ 任务保存/加载测试失败: {e}")
    
    print("\n✅ 测试完成！")
    return success_count == len(modules_to_reload)

if __name__ == "__main__":
    # 设置Python路径
    sys.path.insert(0, '/Users/winroot/telegram_media_downloader')
    
    success = test_module_reload()
    sys.exit(0 if success else 1)