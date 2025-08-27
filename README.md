# Telegram Media Downloader (Enhanced Version)

<p align="center">
<a href="https://github.com/winroot/telegram_media_downloader/blob/master/LICENSE"><img alt="License: MIT" src="https://black.readthedocs.io/en/stable/_static/license.svg"></a>
<a href="https://github.com/python/black"><img alt="Code style: black" src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
<a href="https://claude.ai/code"><img alt="Built with: Claude Code" src="https://img.shields.io/badge/Built%20with-Claude%20Code-blueviolet"></a>
</p>

<h3 align="center">
  <a href="./README_CN.md">中文</a> · 
  <a href="https://github.com/winroot/telegram_media_downloader/issues">Report a bug</a> · 
  <a href="https://github.com/winroot/telegram_media_downloader/discussions">Discussions</a>
</h3>

> 🚀 **Enhanced fork of [tangyoha/telegram_media_downloader](https://github.com/tangyoha/telegram_media_downloader) developed with Claude Code**

## ✨ About This Fork

This is an optimized version of the Telegram Media Downloader, developed and enhanced using **[Claude Code](https://claude.ai/code)** - Anthropic's AI-powered development assistant. All optimizations, bug fixes, and new features were implemented through collaborative development with Claude.

## 🎯 Key Improvements

### Fixed Critical Issues
- ✅ `/task_info` command now correctly shows download progress
- ✅ Fixed memory leak from uncleaned download queue  
- ✅ Bot commands properly registered in Telegram menu
- ✅ Automatic FloodWait error handling with smart retry

### New Features
- 🔄 **Hot Reload** - Update code without restarting (`/reload`)
- 📊 **Advanced Progress Display** - Progress bars, speed, ETA
- 📡 **Network Monitoring** - Auto-recovery on connection loss
- 🗂️ **Smart Logging** - Tiered logs for errors, warnings, FloodWait

### Performance Optimizations
- ⚡ Reduced API calls by removing dynamic updates
- ⚡ Automatic cleanup of completed downloads
- ⚡ Optimized task queue management
- ⚡ Better memory management

## 📱 Bot Commands

Our enhanced version includes these bot commands:

| Command | Description |
|---------|------------|
| `/start` | Start the bot and show welcome message |
| `/help` | Display help information |
| `/download` | Start downloading from a chat/channel |
| `/forward` | Forward messages to another chat |
| `/listen_forward` | Enable listening for forwarded messages |
| `/forward_to_comments` | Forward messages to channel comments |
| `/stop` | Stop download/forward tasks (interactive menu) |
| `/task_info` | Show detailed progress for active downloads |
| `/pause_download [ID]` | Pause a specific download |
| `/resume_download [ID]` | Resume a paused download |
| `/get_info` | Get information about a chat or message |
| `/set_language` | Change bot language (EN/ZH/RU/UA) |
| `/add_filter` | Add download filter for a chat |
| `/show_floodwait` | Show current FloodWait settings |
| `/set_floodwait` | Configure FloodWait handling |
| `/reload` | Hot reload code without restart |
| `/save_state` | Save current application state |
| `/restore_state` | Restore saved application state |
| `/network_status` | Check network monitoring status |
| `/analyze_logs` | Analyze log files for issues |
| `/update_commands` | Update bot commands in Telegram menu |

## 🚀 Quick Start

### Installation

```bash
# Clone this enhanced version
git clone https://github.com/winroot/telegram_media_downloader.git
cd telegram_media_downloader

# Install dependencies
pip3 install -r requirements.txt
```

### Configuration

1. Get your Telegram API credentials from [my.telegram.org](https://my.telegram.org/apps)
2. Configure `config.yaml` with your API keys and bot token
3. Set your download preferences and chat IDs

### Running

```bash
# Direct run (recommended)
python3 media_downloader.py

# Run in background with screen
screen -dmS telegram_downloader python3 media_downloader.py

# View logs
tail -f logs/app_*.log

# Monitor download progress
tail -f logs/download_*.log
```

### Web Interface

Open browser and visit `http://localhost:5000` (configure `web_host: 0.0.0.0` for remote access)

## 📋 Configuration Example

```yaml
api_hash: your_api_hash
api_id: your_api_id
bot_token: your_bot_token  # Optional, for bot commands

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

## 🐳 Docker Support

> ⚠️ **Note**: Docker version has not been tested with our optimizations. We recommend using the direct Python installation method for the best experience with all enhanced features.

If you want to use Docker, you can try the original project's Docker image:

```bash
# Original project Docker image (may not include our enhancements)
docker pull tangyoha/telegram_media_downloader:latest

# Or build from our source (experimental)
git clone https://github.com/winroot/telegram_media_downloader.git
cd telegram_media_downloader
docker build -t telegram_media_downloader .
docker run -v /path/to/config:/app/config telegram_media_downloader
```

For production use with our enhancements, we recommend:
1. Direct Python installation (fully tested)
2. Running with `python3 media_downloader.py`
3. Using systemd or screen for background execution

## 📚 Documentation

- [CLAUDE.md](./CLAUDE.md) - Development guide and troubleshooting
- [OPTIMIZATIONS.md](./OPTIMIZATIONS.md) - Detailed optimization notes
- [BOT_COMMANDS.md](./BOT_COMMANDS.md) - Bot command usage guide

## 🛠️ Development with Claude Code

This project showcases the power of AI-assisted development. All enhancements were implemented through:

1. **Intelligent Debugging** - Claude Code analyzed logs and identified root causes
2. **Code Generation** - New features written with AI assistance
3. **Testing & Validation** - Comprehensive test cases generated automatically
4. **Documentation** - All docs written collaboratively with Claude

Experience AI-powered development: [Try Claude Code](https://claude.ai/code)

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes  
4. Push to the branch
5. Open a Pull Request

## 📄 License

MIT License - See [LICENSE](LICENSE) file

## 🙏 Acknowledgments

- Original project by [tangyoha](https://github.com/tangyoha)
- Enhanced with [Claude Code](https://claude.ai/code) by Anthropic
- Community contributors and testers

---

<p align="center">
  Made with ❤️ using Claude Code
</p>