# 优雅关闭问题修复方案

## 问题描述

在使用 Ctrl+C 中断程序时，出现以下错误：
1. `ConnectionResetError [Errno 54] Connection reset by peer` - 连接被重置
2. `RuntimeError: read() called while another coroutine is already waiting for incoming data` - 并发读取冲突

## 根本原因

1. **并发冲突**：多个协程同时尝试读取或关闭同一个连接
2. **关闭顺序不当**：在任务还在运行时就尝试关闭客户端
3. **异常未处理**：关闭过程中的正常异常没有被妥善处理

## 解决方案

### 1. 改进 stop_server 函数

```python
async def stop_server(client: pyrogram.Client):
    """安全停止服务器"""
    try:
        # 先等待一小段时间让其他任务完成
        await asyncio.sleep(0.1)
        
        # 尝试优雅关闭客户端
        if client.is_connected:
            await client.stop()
    except RuntimeError as e:
        # 忽略并发读取冲突
        if "read() called while another coroutine" in str(e):
            logger.debug(f"关闭时的并发读取冲突已忽略: {e}")
        else:
            logger.error(f"关闭客户端时出错: {e}")
    except ConnectionResetError as e:
        # 忽略连接重置错误
        logger.debug(f"关闭时的连接重置已忽略: {e}")
    except Exception as e:
        logger.error(f"关闭客户端时发生未知错误: {e}")
```

### 2. 优化关闭顺序

```python
finally:
    logger.info("🔄 正在优雅关闭程序...")
    app.is_running = False
    
    # 1. 先取消所有下载任务
    for task in tasks:
        task.cancel()
    
    # 2. 等待任务取消完成
    if tasks:
        await_tasks = asyncio.gather(*tasks, return_exceptions=True)
        try:
            app.loop.run_until_complete(await_tasks)
        except:
            pass
    
    # 3. 停止网络监控
    try:
        app.loop.run_until_complete(app.stop_network_monitor())
    except Exception as e:
        logger.debug(f"停止网络监控时出错: {e}")
    
    # 4. 停止bot（如果有）
    if app.bot_token:
        try:
            app.loop.run_until_complete(stop_download_bot())
        except Exception as e:
            logger.debug(f"停止bot时出错: {e}")
    
    # 5. 最后停止客户端
    try:
        app.loop.run_until_complete(stop_server(client))
    except Exception as e:
        logger.debug(f"停止客户端时出错: {e}")
```

## 关键改进点

1. **正确的关闭顺序**：
   - 先取消任务 → 等待任务完成 → 停止监控 → 停止bot → 最后停止客户端

2. **异常处理策略**：
   - 对预期的异常（并发冲突、连接重置）使用 debug 级别日志
   - 对未知异常使用 error 级别日志
   - 使用 try-except 包裹每个关闭步骤，防止一个步骤失败影响其他步骤

3. **缓冲时间**：
   - 在停止客户端前增加 0.1 秒延迟，让其他协程有机会完成

## 测试验证

使用 `test_graceful_shutdown.py` 脚本验证修复效果：

```bash
python test_graceful_shutdown.py
```

测试要点：
1. 程序启动后按 Ctrl+C
2. 观察是否有错误堆栈输出
3. 确认所有任务都被正确取消
4. 确认客户端被正确关闭

## 预期效果

修复后，程序关闭时应该：
1. 显示 "🔄 正在优雅关闭程序..." 提示
2. 依次取消和停止各个组件
3. 最后显示 "Stopped!" 消息
4. 不再出现 RuntimeError 或 ConnectionResetError 的错误堆栈

## 相关文件

- `media_downloader.py:879-900` - stop_server 函数
- `media_downloader.py:970-1005` - main 函数的 finally 块
- `test_graceful_shutdown.py` - 测试脚本

## 更新日期
2025-08-30