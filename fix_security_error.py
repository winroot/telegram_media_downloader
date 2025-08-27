#!/usr/bin/env python3
"""修复SecurityCheckMismatch错误"""
import os
import shutil
from datetime import datetime

def fix_security_error():
    """修复会话安全检查错误"""
    print("=" * 50)
    print("🔧 修复 SecurityCheckMismatch 错误")
    print("=" * 50)
    
    # 1. 备份当前会话文件
    sessions_dir = "sessions"
    backup_dir = f"sessions_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    if os.path.exists(sessions_dir):
        print(f"\n1️⃣ 备份会话文件到 {backup_dir}")
        shutil.copytree(sessions_dir, backup_dir)
        print(f"   ✅ 备份完成")
    
    # 2. 显示解决方案
    print("\n2️⃣ 解决方案:")
    print("\n方案A - 清理会话文件（推荐）:")
    print("   1. 停止程序")
    print("   2. 删除有问题的会话文件:")
    print("      rm sessions/*.session")
    print("   3. 重新启动程序，会自动重新登录")
    
    print("\n方案B - 完全重置会话:")
    print("   1. 停止程序")
    print("   2. 删除整个sessions目录:")
    print("      rm -rf sessions/")
    print("   3. 重新启动程序")
    
    print("\n方案C - 使用备份恢复:")
    print(f"   1. 如果之前有备份: cp -r {backup_dir}/* sessions/")
    
    print("\n3️⃣ 预防措施:")
    print("   • 避免同时运行多个实例")
    print("   • 保持网络稳定")
    print("   • 定期备份sessions目录")
    print("   • 使用最新版本的Pyrogram")
    
    # 3. 检查可能的问题
    print("\n4️⃣ 检查会话文件:")
    if os.path.exists(sessions_dir):
        session_files = [f for f in os.listdir(sessions_dir) if f.endswith('.session')]
        print(f"   找到 {len(session_files)} 个会话文件:")
        for session_file in session_files:
            file_path = os.path.join(sessions_dir, session_file)
            file_size = os.path.getsize(file_path) / 1024  # KB
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            print(f"   • {session_file} ({file_size:.1f} KB) - 修改时间: {file_time}")
    else:
        print("   ❌ sessions目录不存在")
    
    print("\n5️⃣ 建议操作:")
    print("   执行以下命令清理并重启:")
    print("   ```bash")
    print("   # 停止当前程序 (Ctrl+C)")
    print("   # 清理会话")
    print("   rm sessions/*.session")
    print("   # 重新启动")
    print("   python media_downloader.py")
    print("   ```")
    
    return True

def check_pyrogram_version():
    """检查Pyrogram版本"""
    try:
        import pyrogram
        print(f"\n📦 Pyrogram版本: {pyrogram.__version__}")
        
        # 检查是否使用自定义fork
        with open("requirements.txt", "r") as f:
            content = f.read()
            if "tangyoha/pyrogram" in content:
                print("   ✅ 使用自定义Pyrogram fork (正确)")
            else:
                print("   ⚠️ 未使用推荐的Pyrogram fork")
                print("   建议安装: pip install https://github.com/tangyoha/pyrogram/archive/refs/heads/patch.zip")
    except Exception as e:
        print(f"   ❌ 检查版本失败: {e}")

if __name__ == "__main__":
    fix_security_error()
    check_pyrogram_version()
    
    print("\n" + "=" * 50)
    print("💡 快速修复命令:")
    print("=" * 50)
    print("bash -c 'rm sessions/*.session && python media_downloader.py'")