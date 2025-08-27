# Bot命令完整列表 📋

## 📥 下载功能
- `/download` - 下载频道或群组消息
- `/pause_download` - 暂停所有下载任务
- `/resume_download` - 恢复暂停的下载

## 📤 转发功能  
- `/forward` - 转发消息到其他频道/群组
- `/listen_forward` - 监听转发的消息
- `/forward_to_comments` - 转发媒体到评论区

## ⚙️ 设置和管理
- `/set_language` - 设置语言 (EN/ZH/RU/UA)
- `/add_filter` - 添加下载过滤器
- `/show_floodwait` - 显示FloodWait设置
- `/set_floodwait` - 设置FloodWait参数

## 📊 状态和信息
- `/help` - 显示所有可用命令
- `/get_info` - 获取群组和用户信息
- `/task_info` - 显示详细任务信息
- `/network_status` - 显示网络监控状态
- `/analyze_logs` - 分析日志文件

## 🔧 系统维护
- `/reload` - 热重载代码（无需重启）
- `/save_state` - 保存当前任务状态
- `/restore_state` - 恢复保存的任务
- `/stop` - 停止所有下载或转发

## 使用示例

### 下载任务管理
```
/download https://t.me/channel_name 1 100
/pause_download     # 暂停下载
/task_info         # 查看进度
/resume_download   # 继续下载
```

### FloodWait处理
```
/show_floodwait    # 查看当前设置
/set_floodwait download_buffer=10  # 设置缓冲时间
```

### 热重载功能
```
/save_state        # 保存任务
/reload           # 重载代码
/restore_state    # 恢复任务
```

### 日志分析
```
/analyze_logs     # 在Bot中查看日志摘要
```

命令行分析：
```bash
python analyze_logs.py --all       # 完整分析
python analyze_logs.py --errors    # 错误分析
python analyze_logs.py --floodwait # FloodWait统计
```

## 注意事项
- 所有命令需要授权用户才能使用
- 热重载不会中断正在进行的下载
- 日志文件保存在 `logs/` 目录
- 任务状态保存在 `pending_tasks.json`