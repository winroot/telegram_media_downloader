#!/usr/bin/env python3
"""强制更新Bot命令菜单"""
import asyncio
import yaml
import pyrogram
from pyrogram.types import BotCommand
import sys

async def force_update_commands():
    """强制更新Bot命令"""
    
    # 读取配置
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # 直接使用配置（新格式）
    if isinstance(config, dict) and 'api_id' in config:
        config_data = config
        config_key = "media_downloader"
    else:
        # 旧格式兼容
        config_key = list(config.keys())[0]
        config_data = config[config_key]
    
    print("=" * 50)
    print("🔧 强制更新Bot命令菜单")
    print("=" * 50)
    
    # 创建客户端
    if 'bot_token' in config_data and config_data['bot_token']:
        # Bot模式
        print("✅ 检测到Bot Token，使用Bot模式")
        client = pyrogram.Client(
            f"sessions/{config_key}_bot",
            api_id=config_data['api_id'],
            api_hash=config_data['api_hash'],
            bot_token=config_data['bot_token']
        )
    else:
        # 用户模式
        print("📱 使用用户模式")
        client = pyrogram.Client(
            f"sessions/{config_key}",
            api_id=config_data['api_id'],
            api_hash=config_data['api_hash']
        )
    
    async with client:
        me = await client.get_me()
        print(f"\n登录为: @{me.username if me.username else me.id}")
        print(f"是否为Bot: {'是' if me.is_bot else '否'}")
        
        if me.is_bot:
            # 定义所有命令
            commands = [
                # 基础命令
                BotCommand("help", "显示帮助信息"),
                BotCommand("download", "下载消息"),
                BotCommand("forward", "转发消息"),
                BotCommand("stop", "停止任务"),
                
                # 设置命令
                BotCommand("set_language", "设置语言"),
                BotCommand("add_filter", "添加过滤器"),
                BotCommand("get_info", "获取信息"),
                
                # 任务管理
                BotCommand("pause_download", "暂停下载"),
                BotCommand("resume_download", "恢复下载"),
                BotCommand("task_info", "任务信息"),
                
                # FloodWait管理
                BotCommand("show_floodwait", "显示FloodWait设置"),
                BotCommand("set_floodwait", "设置FloodWait参数"),
                
                # 系统维护
                BotCommand("network_status", "网络状态"),
                BotCommand("analyze_logs", "分析日志"),
                BotCommand("reload", "热重载代码"),
                BotCommand("save_state", "保存状态"),
                BotCommand("restore_state", "恢复状态"),
                
                # 转发相关
                BotCommand("listen_forward", "监听转发"),
                BotCommand("forward_to_comments", "转发到评论"),
            ]
            
            print(f"\n准备注册 {len(commands)} 个命令...")
            
            # 先清除旧命令
            try:
                await client.delete_bot_commands()
                print("✅ 已清除旧命令")
            except:
                pass
            
            # 设置新命令
            await client.set_bot_commands(commands)
            print(f"✅ 成功注册 {len(commands)} 个命令！")
            
            print("\n已注册的命令:")
            for cmd in commands:
                print(f"  /{cmd.command} - {cmd.description}")
            
            print("\n✅ 命令菜单更新完成！")
            print("现在在Telegram中输入 / 即可看到所有命令")
            
        else:
            print("\n⚠️ 注意: 当前账号不是Bot账号")
            print("Bot命令菜单只能由Bot账号设置")
            print("如果你使用的是用户账号，命令会在Bot启动时自动注册")

if __name__ == "__main__":
    print("🚀 开始更新Bot命令...")
    
    try:
        asyncio.run(force_update_commands())
    except KeyboardInterrupt:
        print("\n⌨️ 用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        print("\n可能的原因:")
        print("1. 配置文件错误")
        print("2. 网络连接问题")
        print("3. Bot Token无效")
        sys.exit(1)