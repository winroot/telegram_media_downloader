# Telegram 媒体下载器 (增强版)

<p align="center">
<a href="https://github.com/winroot/telegram_media_downloader/blob/master/LICENSE"><img alt="License: MIT" src="https://black.readthedocs.io/en/stable/_static/license.svg"></a>
<a href="https://github.com/python/black"><img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
<a href="https://claude.ai/code"><img alt="Built with: Claude Code" src="https://img.shields.io/badge/使用Claude%20Code开发-blueviolet"></a>
</p>

<h3 align="center">
  <a href="./README.md">English</a> · 
  <a href="https://github.com/winroot/telegram_media_downloader/issues">报告问题</a> · 
  <a href="https://github.com/winroot/telegram_media_downloader/discussions">讨论区</a>
</h3>

> 🚀 **基于 [tangyoha/telegram_media_downloader](https://github.com/tangyoha/telegram_media_downloader) 使用 Claude Code 优化增强**

## ✨ 关于此分支

这是 Telegram Media Downloader 的优化版本，使用 **[Claude Code](https://claude.ai/code)** - Anthropic 的 AI 驱动开发助手进行开发和增强。所有优化、错误修复和新功能都是通过与 Claude 协作开发实现的。

## 🎯 主要改进

### 修复的关键问题
- ✅ `/task_info` 命令现在正确显示下载进度
- ✅ 修复了下载队列未清理导致的内存泄漏
- ✅ Bot 命令正确注册到 Telegram 菜单
- ✅ 自动处理 FloodWait 错误并智能重试

### 新增功能
- 🔄 **热重载** - 无需重启即可更新代码 (`/reload`)
- 📊 **高级进度显示** - 进度条、速度、剩余时间
- 📡 **网络监控** - 连接丢失时自动恢复
- 🗂️ **智能日志** - 错误、警告、FloodWait 分层日志

### 性能优化
- ⚡ 移除动态更新以减少 API 调用
- ⚡ 自动清理已完成的下载
- ⚡ 优化任务队列管理
- ⚡ 更好的内存管理

## 📱 Bot 命令列表

我们的增强版本包含以下 Bot 命令：

| 命令 | 说明 |
|---------|------------|
| `/start` | 启动机器人并显示欢迎信息 |
| `/help` | 显示帮助信息 |
| `/download` | 开始从聊天/频道下载 |
| `/forward` | 转发消息到另一个聊天 |
| `/listen_forward` | 启用监听转发消息功能 |
| `/forward_to_comments` | 转发消息到频道评论 |
| `/stop` | 停止下载/转发任务（交互式菜单） |
| `/task_info` | 显示活动下载的详细进度 |
| `/pause_download [ID]` | 暂停指定下载 |
| `/resume_download [ID]` | 恢复暂停的下载 |
| `/get_info` | 获取聊天或消息信息 |
| `/set_language` | 更改机器人语言 (EN/ZH/RU/UA) |
| `/add_filter` | 为聊天添加下载过滤器 |
| `/show_floodwait` | 显示当前 FloodWait 设置 |
| `/set_floodwait` | 配置 FloodWait 处理方式 |
| `/reload` | 热重载代码无需重启 |
| `/save_state` | 保存当前应用状态 |
| `/restore_state` | 恢复保存的应用状态 |
| `/network_status` | 检查网络监控状态 |
| `/analyze_logs` | 分析日志文件查找问题 |
| `/update_commands` | 更新 Telegram 菜单中的机器人命令 |

## 🚀 快速开始

### 安装

```bash
# 克隆这个增强版本
git clone https://github.com/winroot/telegram_media_downloader.git
cd telegram_media_downloader

# 安装依赖
pip3 install -r requirements.txt
```

### 配置

1. 从 [my.telegram.org](https://my.telegram.org/apps) 获取你的 Telegram API 凭证
2. 使用你的 API 密钥和 bot token 配置 `config.yaml`
3. 设置你的下载偏好和聊天 ID

### 运行

```bash
python3 media_downloader.py
```

### Web 界面

打开浏览器访问 `http://localhost:5000` （远程访问需配置 `web_host: 0.0.0.0`）

## 📋 配置示例

```yaml
api_hash: your_api_hash
api_id: your_api_id
bot_token: your_bot_token  # 可选，用于机器人命令

chat:
- chat_id: -1001234567890
  last_read_message_id: 0
  download_filter: message_date >= 2024-01-01 00:00:00

media_types:
- photo
- video
- document

save_path: /path/to/downloads
max_download_task: 5
```

## 🐳 Docker

```bash
# 使用我们的优化镜像
docker pull winroot/telegram_media_downloader:latest

# 或从源代码构建
docker build -t telegram_media_downloader .
docker run -v /path/to/config:/app/config telegram_media_downloader
```

## 📚 文档

- [CLAUDE.md](./CLAUDE.md) - 开发指南和故障排查
- [OPTIMIZATIONS.md](./OPTIMIZATIONS.md) - 详细优化说明
- [BOT_COMMANDS.md](./BOT_COMMANDS.md) - Bot 命令使用指南

## 🛠️ 使用 Claude Code 开发

此项目展示了 AI 辅助开发的强大功能。所有增强功能都通过以下方式实现：

1. **智能调试** - Claude Code 分析日志并识别根本原因
2. **代码生成** - 在 AI 协助下编写新功能
3. **测试与验证** - 自动生成全面的测试用例
4. **文档编写** - 与 Claude 协作编写所有文档

体验 AI 驱动的开发：[试试 Claude Code](https://claude.ai/code)

## 🤝 贡献

欢迎贡献！请：
1. Fork 仓库
2. 创建功能分支
3. 提交你的更改
4. 推送到分支
5. 开启 Pull Request

## 📄 许可证

MIT 许可证 - 查看 [LICENSE](LICENSE) 文件

## 🙏 致谢

- 原始项目由 [tangyoha](https://github.com/tangyoha) 开发
- 使用 Anthropic 的 [Claude Code](https://claude.ai/code) 增强
- 社区贡献者和测试者

---

<p align="center">
  使用 Claude Code 用 ❤️ 制作
</p>