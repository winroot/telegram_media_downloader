"""Bot工具函数 - FloodWait处理"""
import asyncio
import functools
import time
from loguru import logger
import pyrogram


def handle_floodwait(func):
    """装饰器：自动处理FloodWait错误"""
    @functools.wraps(func)
    async def wrapper(client: pyrogram.Client, message: pyrogram.types.Message):
        try:
            return await func(client, message)
        except pyrogram.errors.FloodWait as e:
            wait_time = e.value
            logger.warning(
                f"⏳ Bot命令FloodWait: 需要等待 {wait_time} 秒 (约 {wait_time//3600} 小时)\n"
                f"  命令: /{message.command[0] if message.command else 'unknown'}\n"
                f"  用户: {message.from_user.id}"
            )
            
            # 如果等待时间太长，告诉用户
            if wait_time > 60:
                try:
                    await message.reply_text(
                        f"⏳ **FloodWait限制**\n\n"
                        f"Telegram限制了消息发送\n"
                        f"需要等待: {wait_time//60} 分钟\n"
                        f"请稍后再试",
                        quote=True
                    )
                except:
                    pass  # 如果回复也失败，忽略
            
            # 如果等待时间合理（小于5分钟），自动等待并重试
            if wait_time <= 300:
                logger.info(f"⏱️ 自动等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time + 5)  # 额外5秒缓冲
                try:
                    return await func(client, message)
                except Exception as retry_error:
                    logger.error(f"❌ 重试失败: {retry_error}")
            
        except Exception as e:
            logger.error(f"❌ Bot命令错误: {e}")
            try:
                await message.reply_text(
                    f"❌ 命令执行失败\n错误: {str(e)[:100]}",
                    quote=True
                )
            except:
                pass
    
    return wrapper


async def safe_send_message(client: pyrogram.Client, chat_id, text, **kwargs):
    """安全发送消息（处理FloodWait）"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            return await client.send_message(chat_id, text, **kwargs)
        except pyrogram.errors.FloodWait as e:
            wait_time = e.value
            logger.warning(f"⏳ 发送消息FloodWait: {wait_time}秒")
            
            if wait_time > 300:  # 超过5分钟不等待
                raise
            
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time + 5)
            else:
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
            else:
                raise


class RateLimiter:
    """消息发送速率限制器"""
    def __init__(self, messages_per_minute=30):
        self.messages_per_minute = messages_per_minute
        self.min_interval = 60 / messages_per_minute  # 秒
        self.last_send_time = {}
    
    async def wait_if_needed(self, chat_id):
        """必要时等待以避免速率限制"""
        now = time.time()
        last_time = self.last_send_time.get(chat_id, 0)
        
        time_since_last = now - last_time
        if time_since_last < self.min_interval:
            wait_time = self.min_interval - time_since_last
            logger.debug(f"速率限制: 等待 {wait_time:.1f} 秒")
            await asyncio.sleep(wait_time)
        
        self.last_send_time[chat_id] = time.time()


# 全局速率限制器
rate_limiter = RateLimiter(messages_per_minute=20)  # 每分钟最多20条消息