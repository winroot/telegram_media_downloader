# Telegram Media Downloader 项目指南

本文档为 Claude Code (claude.ai/code) 提供项目开发指导。

## 项目概述

Telegram Media Downloader 是一个从 Telegram 频道/群组下载媒体文件的应用。支持 Bot 模式和一次性下载模式，提供 Web UI 界面监控下载进度。

## 核心开发命令

### 安装依赖
```bash
# 安装运行依赖
pip3 install -r requirements.txt

# 安装开发依赖
pip3 install -r dev-requirements.txt
```

### 测试命令
```bash
# 运行完整测试套件
py.test --cov media_downloader --cov utils --cov-report term-missing tests/

# 快速功能测试
python test_functionality.py

# 测试日志系统
python test_logging.py

# 测试热重载功能
python test_reload.py
```

### 代码质量检查
```bash
# 类型检查
mypy media_downloader.py utils module --ignore-missing-imports

# 代码规范检查
pylint media_downloader.py utils module -r y

# 代码格式化（使用 black）
black media_downloader.py utils module
```

### 运行应用
```bash
# 启动下载器
python3 media_downloader.py

# Web 界面将在 localhost:5000 运行（或配置的端口）
```

## 架构说明

### 核心组件

1. **主入口** (`media_downloader.py`)
   - 管理 Pyrogram 客户端
   - 协调下载流程
   - 处理 FloodWait 错误

2. **应用核心** (`module/app.py`)
   - `Application` 类：管理配置和任务
   - `TaskNode` 类：单个下载任务管理
   - 下载状态跟踪

3. **Bot 模块** (`module/bot.py`)
   - Telegram Bot 交互
   - 命令处理
   - 任务管理

4. **Web 界面** (`module/web.py`)
   - Flask 实现的监控界面
   - 登录认证
   - 实时状态显示

5. **Pyrogram 扩展** (`module/pyrogram_extension.py`)
   - 进度跟踪
   - 元数据处理
   - FloodWait 处理

### 数据流

1. `config.yaml` - 主配置文件（API 密钥、频道列表、下载设置）
2. `data.yaml` - 持久化状态（最后消息 ID、重试列表）
3. 下载文件组织：`保存路径/频道名/日期/文件名`
4. 日志文件：`logs/` 目录下分类存储

## 最新更新（2025-08）

### 1. FloodWait 优化系统

**自动等待机制**：
- 精确等待时间 + 5 秒缓冲
- 指数退避：2^n 倍增（最大 32 倍，上限 5 分钟）
- 动态消息更新间隔：5-300 秒自适应
- 成功后自动重置计数器

**实现位置**：
- `media_downloader.py`: FloodWait 装饰器和处理逻辑
- `module/pyrogram_extension.py`: 消息更新频率控制
- `module/bot_utils.py`: Bot 命令的 FloodWait 处理

### 2. 进度显示优化

**移除动态更新**：
- 取消自动进度消息更新（避免 FloodWait）
- 所有进度信息通过 `/task_info` 手动查看
- 简化 `update_reply_message()` 仅清理完成任务

**增强的 task_info 显示**：
```
▶️ 任务 1 - 运行中
├ 进度: [████████░░] 80.0%
├ 总计: 100 个文件
├ ✅ 成功: 80
├ ❌ 失败: 0
├ ⏭️ 跳过: 0
├ 📥 正在下载: video.mp4
├ 📊 文件进度: [▓▓▓▓▓░░░░░] 50.0%
├ 📁 大小: 25.00 MB / 50.00 MB
├ ⚡ 速度: 2.50 MB/s
└ ⏱️ 预计剩余: 2.5 分钟
```

### 3. 热重载系统

**功能特点**：
- `/reload` - 不停机更新代码
- 任务持久化到 `pending_tasks.json`
- 应用状态保存到 `app_state.pkl`
- 模块重载包括：app、pyrogram_extension、download_stat、media_downloader

**使用流程**：
1. `/reload` - 保存任务并重载代码
2. `/restore_state` - 恢复保存的任务
3. 任务自动继续下载

### 4. Bot 命令增强

**下载控制**：
- `/task_info` - 查看详细任务进度（含单文件进度条）
- `/pause_download [ID]` - 暂停指定任务
- `/resume_download [ID]` - 恢复指定任务
- `/stop` - 停止所有任务

**系统管理**：
- `/show_floodwait` - 查看 FloodWait 设置
- `/network_status` - 网络监控状态
- `/reload` - 热重载代码
- `/save_state` - 保存当前状态
- `/restore_state` - 恢复保存状态
- `/analyze_logs` - 分析日志文件

**注意**：Bot 命令在启动时自动注册，会出现在 Telegram 命令菜单中（输入 / 时）。

### 5. 网络监控

**自动恢复机制**：
- Ping/Socket 双重检测
- 网络故障自动暂停任务
- 网络恢复自动继续下载
- 配置项：`enable_network_monitor`

### 6. 日志系统

**分级日志**：
```
logs/
├── error_YYYY-MM-DD.log      # 错误日志（保留 30 天）
├── warning_YYYY-MM-DD.log    # 警告日志（保留 14 天）  
├── full_YYYY-MM-DD.log       # 完整日志（保留 7 天，100MB 轮转）
└── floodwait_YYYY-MM.log     # FloodWait 专用（保留 3 个月）
```

**日志分析**：
```bash
# 查看所有分析
python analyze_logs.py --all

# 只看错误
python analyze_logs.py --errors

# FloodWait 分析
python analyze_logs.py --floodwait

# 摘要信息
python analyze_logs.py --summary
```

## 重要实现细节

### FloodWait 处理

1. **装饰器模式** (`@handle_floodwait`)：
   - 自动捕获 FloodWait 异常
   - 等待指定时间 + 缓冲
   - 记录到专用日志

2. **动态间隔调整**：
   - 基于失败次数的指数退避
   - 最小间隔：5 秒
   - 最大间隔：300 秒

3. **任务节点追踪** (`TaskNode`)：
   - `floodwait_count` - 累计次数
   - `min_update_interval` - 当前间隔
   - `last_update_time` - 上次更新时间

### 下载进度跟踪

1. **实时属性更新** (`module/download_stat.py`)：
   - `current_download_file` - 当前文件名
   - `current_file_size` - 文件大小
   - `current_downloaded` - 已下载量
   - `download_speed` - 下载速度

2. **进度回调机制**：
   - Pyrogram 的 `progress` 参数
   - 实时更新 TaskNode 属性
   - 完成后自动清理

### 任务持久化

1. **保存内容**：
   - 任务 ID 和聊天 ID
   - 下载进度统计
   - 消息范围和过滤器
   - 暂停/运行状态

2. **恢复流程**：
   - 加载 JSON 文件
   - 重建 TaskNode 对象
   - 恢复下载队列

## 开发注意事项

### 必须运行的检查
- **测试功能**：`python test_functionality.py`
- **测试重载**：`python test_reload.py`
- **检查日志**：`python analyze_logs.py --summary`

### FloodWait 调试
- 日志标记：⏱️（等待）、📊（统计）、🔄（重试）
- 专用日志：`logs/floodwait_YYYY-MM.log`
- Bot 命令：`/show_floodwait` 查看当前状态

### 文件组织
- 配置文件：`config.yaml`、`data.yaml`
- 会话文件：`sessions/` 目录
- 临时下载：`temp/` 目录
- 任务状态：`pending_tasks.json`、`app_state.pkl`

### 代码规范
- 使用 Black 格式化
- 类型注解（mypy 检查）
- 中文注释说明关键逻辑
- 日志使用表情符号标记

## 故障排除

### SecurityCheckMismatch 错误
```bash
python fix_security_error.py  # 自动诊断和修复
```

### Bot 命令不显示
```bash
python force_update_commands.py  # 强制更新命令菜单
```

### FloodWait 频繁触发
1. 检查 `/show_floodwait` 状态
2. 查看 `logs/floodwait_*.log`
3. 调整消息更新间隔
4. 使用 `/task_info` 替代自动更新

### 网络问题
1. 检查 `/network_status`
2. 配置 `network_check_host`
3. 调整 `network_check_interval`

## 测试文件说明

- `test_functionality.py` - 核心功能测试
- `test_logging.py` - 日志系统测试
- `test_reload.py` - 热重载测试
- `test_task_info.py` - 任务信息显示测试
- `test_bot_fix.py` - Bot 修复测试
- `fix_security_error.py` - 安全错误诊断
- `analyze_logs.py` - 日志分析工具

## 配置示例

### config.yaml 关键配置
```yaml
# API 配置
api_id: YOUR_API_ID
api_hash: YOUR_API_HASH
bot_token: YOUR_BOT_TOKEN  # 可选，用于 Bot 模式

# 下载设置
max_download_task: 2  # 并发下载数
save_path: /path/to/save  # 保存路径

# 网络监控
enable_network_monitor: true
network_check_interval: 30  # 秒
network_check_host: 8.8.8.8

# 媒体类型
media_types:
  - audio
  - video
  - photo
  - document
```

## 版本要求

- Python 3.8+
- Pyrogram 2.1.22（自定义分支）
- 查看 `requirements.txt` 获取完整依赖列表

## 问题诊断：/task_info 不显示下载进度

### 问题描述
通过 Telegram Bot 的 `/download` 命令创建下载任务后，使用 `/task_info` 查看时不显示下载进度，只显示"等待中"状态。

### 根本原因
TaskNode 创建时未设置 `is_running = True` 标志，导致进度显示逻辑被跳过。

### 影响范围
所有通过 Bot 命令创建的任务：
- `/download` - 下载指定消息范围
- 转发消息 - 自动下载转发的媒体
- `/forward` - 转发消息到其他群组

### 解决方案

#### 1. 修复代码位置
**module/bot.py** - 三处创建 TaskNode 的地方：
```python
# download_from_bot 函数（~862行）
node = TaskNode(...)
node.is_running = True  # 添加这行

# download_from_link 函数（~695行）  
node = TaskNode(...)
node.is_running = True  # 添加这行

# get_forward_task_node 函数（~967行）
node = TaskNode(...)
node.is_running = True  # 添加这行
```

**media_downloader.py** - 配置文件任务：
```python
# download_all_chat 函数（~795行）
value.node = TaskNode(chat_id=key)
value.node.task_id = task_id
value.node.is_running = True  # 添加这行
```

#### 2. 初始化顺序优化
确保 Bot 完全初始化后再创建任务：
```python
# media_downloader.py main 函数（~913-920行）
# 先启动 bot
if app.bot_token:
    app.loop.run_until_complete(start_download_bot(...))
    
# 后创建下载任务
app.loop.create_task(download_all_chat(client))
```

### 诊断步骤

1. **检查任务状态**：
   ```python
   # 在 task_info 函数中查看
   logger.info(f"任务属性: is_running={task.is_running}")
   ```

2. **验证任务创建**：
   ```python
   # 在创建 TaskNode 后立即记录
   logger.info(f"创建任务: ID={node.task_id}, is_running={node.is_running}")
   ```

3. **确认下载数据**：
   ```python
   # 检查 download_results 字典
   from module.download_stat import get_download_result
   results = get_download_result()
   logger.info(f"下载数据: {len(results)} 个聊天")
   ```

### 测试验证

1. 重启程序应用修改
2. 使用 `/download` 命令创建新任务
3. 立即使用 `/task_info` 查看
4. 确认显示"▶️ 运行中"状态和进度条

### 经验教训

1. **状态初始化**：对象创建时应设置所有必要的初始状态
2. **代码一致性**：多处创建相同对象时，考虑抽取工厂方法
3. **防御性编程**：进度显示前检查 `is_running` 状态是正确的
4. **调试技巧**：使用带标记的日志（如 `[DEBUG_TASK_INFO]`）便于追踪和清理

## 问题诊断：下载完成文件未从队列移除

### 问题描述
`/task_info` 命令显示大量 100% 进度的已完成文件，这些文件实际已经下载完成，但仍然显示在进度列表中，造成显示混乱。

### 根本原因
1. `_download_result` 字典在文件下载完成后没有清理对应的记录
2. `/task_info` 显示所有在 `_download_result` 中的记录，包括已完成的

### 影响
- 内存占用增加（保留无用的下载记录）
- 显示混乱（大量 100% 进度的文件）
- 难以看清真正在下载的文件

### 解决方案

#### 1. 添加清理函数
**module/download_stat.py:**
```python
def clear_download_result(chat_id: int, message_id: int):
    """清理已完成的下载记录"""
    global _download_result
    if chat_id in _download_result and message_id in _download_result[chat_id]:
        del _download_result[chat_id][message_id]
        # 如果该chat没有其他下载任务，删除整个chat记录
        if not _download_result[chat_id]:
            del _download_result[chat_id]
```

#### 2. 自动清理机制
**media_downloader.py（~388行）:**
```python
# 如果下载成功，清理download_result中的记录
if download_status == DownloadStatus.SuccessDownload:
    from module.download_stat import clear_download_result
    clear_download_result(node.chat_id, message.id)
```

#### 3. 显示过滤优化
**module/bot.py - task_info 函数:**
```python
# 过滤掉已完成的下载（进度 >= 100%）
active_downloads = []
for msg_id, download_info in chat_download_results.items():
    progress = (down_byte / total_size * 100) if total_size > 0 else 0
    # 只显示未完成的下载
    if progress < 100:
        active_downloads.append((msg_id, download_info, progress))

# 按进度排序，优先显示进度较低的
active_downloads.sort(key=lambda x: x[2])
```

### 优化效果

#### 优化前：
```
📥 下载进度:
├─ 消息ID: 33563 [██████████] (100%)  ❌ 已完成但仍显示
├─ 消息ID: 33522 [██████████] (100%)  ❌ 已完成但仍显示
├─ 消息ID: 33565 [██████████] (100%)  ❌ 已完成但仍显示
├─ 消息ID: 33566 [██████████] (100%)  ❌ 已完成但仍显示
├─ 消息ID: 33567 [██████████] (100%)  ❌ 已完成但仍显示
... 还有 7 个文件正在下载
```

#### 优化后：
```
📥 下载进度:
├─ 消息ID: 33570 [███░░░░░░░] (35%)  ✅ 只显示真正在下载的
├─ 消息ID: 33571 [█████░░░░░] (52%)  ✅ 按进度排序
├─ 消息ID: 33572 [███████░░░] (78%)  ✅ 清晰易读
... 还有 2 个文件正在下载
```

### 内存管理改进

1. **即时清理**：文件下载完成立即从内存中删除记录
2. **级联删除**：当 chat 没有活跃下载时，删除整个 chat 记录
3. **防止泄漏**：避免长时间运行导致的内存累积

### 测试验证

1. 启动下载任务
2. 使用 `/task_info` 查看进度
3. 等待部分文件完成
4. 再次使用 `/task_info`，确认已完成文件不再显示
5. 检查内存使用，确认没有泄漏

### 相关代码位置

- `module/download_stat.py:47-54` - 清理函数
- `media_downloader.py:387-390` - 自动清理调用
- `module/bot.py:1511-1527` - 显示过滤逻辑