"""Bot for media downloader"""

import asyncio
import os
import sys
import time
from datetime import datetime
from typing import Callable, List, Union

import pyrogram
from loguru import logger
from module.bot_utils import handle_floodwait, safe_send_message, rate_limiter
from pyrogram import types
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from ruamel import yaml

import utils
from module.app import (
    Application,
    ChatDownloadConfig,
    ForwardStatus,
    QueryHandler,
    QueryHandlerStr,
    TaskNode,
    TaskType,
    UploadStatus,
)
from module.filter import Filter
from module.get_chat_history_v2 import get_chat_history_v2
from module.language import Language, _t
from module.pyrogram_extension import (
    check_user_permission,
    parse_link,
    proc_cache_forward,
    report_bot_forward_status,
    report_bot_status,
    retry,
    set_meta_data,
    upload_telegram_chat_message,
)
from utils.format import replace_date_time, validate_title
from utils.meta_data import MetaData

# pylint: disable = C0301, R0902


class DownloadBot:
    """Download bot"""

    def __init__(self):
        self.bot = None
        self.client = None
        self.add_download_task: Callable = None
        self.download_chat_task: Callable = None
        self.app = None
        self.listen_forward_chat: dict = {}
        self.config: dict = {}
        self._yaml = yaml.YAML()
        self.config_path = os.path.join(os.path.abspath("."), "bot.yaml")
        self.download_command: dict = {}
        self.filter = Filter()
        self.bot_info = None
        self.task_node: dict = {}
        self.is_running = True
        self.allowed_user_ids: List[Union[int, str]] = []

        meta = MetaData(datetime(2022, 8, 5, 14, 35, 12), 0, "", 0, 0, 0, "", 0)
        self.filter.set_meta_data(meta)

        self.download_filter: List[str] = []
        self.task_id: int = 0
        self.reply_task = None

    def gen_task_id(self) -> int:
        """Gen task id"""
        self.task_id += 1
        return self.task_id

    def add_task_node(self, node: TaskNode):
        """Add task node"""
        self.task_node[node.task_id] = node

    def remove_task_node(self, task_id: int):
        """Remove task node"""
        self.task_node.pop(task_id)

    def stop_task(self, task_id: str):
        """Stop task"""
        if task_id == "all":
            for value in self.task_node.values():
                value.stop_transmission()
        else:
            try:
                task = self.task_node.get(int(task_id))
                if task:
                    task.stop_transmission()
            except Exception:
                return

    async def update_reply_message(self):
        """Update reply message - 简化版，不再动态更新进度"""
        update_interval = 300  # 5分钟检查一次，只清理完成的任务
        
        while self.is_running:
            try:
                # 只清理已完成的任务，不更新进度消息
                for key, value in self.task_node.copy().items():
                    if value.is_running and value.is_finish():
                        self.remove_task_node(key)
                        logger.info(f"✅ 任务 {key} 已完成并清理")
                
                # 记录当前活动任务数（仅用于日志）
                active_tasks = sum(1 for v in self.task_node.values() if v.is_running)
                if active_tasks > 0:
                    logger.debug(f"📊 当前活动任务数: {active_tasks}")
                    
            except Exception as e:
                logger.error(f"清理任务失败: {e}")
                
            await asyncio.sleep(update_interval)

    def assign_config(self, _config: dict):
        """assign config from str.

        Parameters
        ----------
        _config: dict
            application config dict

        Returns
        -------
        bool
        """

        self.download_filter = _config.get("download_filter", self.download_filter)

        return True

    def update_config(self):
        """Update config from str."""
        self.config["download_filter"] = self.download_filter

        with open("d", "w", encoding="utf-8") as yaml_file:
            self._yaml.dump(self.config, yaml_file)

    async def start(
        self,
        app: Application,
        client: pyrogram.Client,
        add_download_task: Callable,
        download_chat_task: Callable,
    ):
        """Start bot"""
        self.bot = pyrogram.Client(
            app.application_name + "_bot",
            api_hash=app.api_hash,
            api_id=app.api_id,
            bot_token=app.bot_token,
            workdir=app.session_file_path,
            proxy=app.proxy,
        )
        
        # 设置bot实例引用到app，用于网络监控
        app.set_bot_instance(self)

        # 命令列表
        commands = [
            types.BotCommand("help", _t("Help")),
            types.BotCommand(
                "get_info", _t("Get group and user info from message link")
            ),
            types.BotCommand(
                "download",
                _t(
                    "To download the video, use the method to directly enter /download to view"
                ),
            ),
            types.BotCommand(
                "forward",
                _t("Forward video, use the method to directly enter /forward to view"),
            ),
            types.BotCommand(
                "listen_forward",
                _t(
                    "Listen forward, use the method to directly enter /listen_forward to view"
                ),
            ),
            types.BotCommand(
                "forward_to_comments",
                _t("Forward a specific media to a comment section"),
            ),
            types.BotCommand(
                "add_filter",
                _t(
                    "Add download filter, use the method to directly enter /add_filter to view"
                ),
            ),
            types.BotCommand("set_language", _t("Set language")),
            types.BotCommand("show_floodwait", "显示FloodWait设置"),
            types.BotCommand("set_floodwait", "设置FloodWait参数"),
            types.BotCommand("pause_download", "暂停下载任务"),
            types.BotCommand("resume_download", "恢复下载任务"),
            types.BotCommand("task_info", "显示任务信息"),
            types.BotCommand("network_status", "显示网络监控状态"),
            types.BotCommand("reload", "热重载代码"),
            types.BotCommand("save_state", "保存任务状态"),
            types.BotCommand("restore_state", "恢复任务状态"),
            types.BotCommand("analyze_logs", "分析日志文件"),
            types.BotCommand("stop", _t("Stop bot download or forward")),
        ]

        self.app = app
        self.client = client
        self.add_download_task = add_download_task
        self.download_chat_task = download_chat_task

        # load config
        if os.path.exists(self.config_path):
            with open(self.config_path, encoding="utf-8") as f:
                config = self._yaml.load(f.read())
                if config:
                    self.config = config
                    self.assign_config(self.config)

        await self.bot.start()

        self.bot_info = await self.bot.get_me()

        for allowed_user_id in self.app.allowed_user_ids:
            try:
                chat = await self.client.get_chat(allowed_user_id)
                self.allowed_user_ids.append(chat.id)
            except Exception as e:
                logger.warning(f"set allowed_user_ids error: {e}")

        admin = await self.client.get_me()
        self.allowed_user_ids.append(admin.id)

        await self.bot.set_bot_commands(commands)

        self.bot.add_handler(
            MessageHandler(
                download_from_bot,
                filters=pyrogram.filters.command(["download"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        self.bot.add_handler(
            MessageHandler(
                forward_messages,
                filters=pyrogram.filters.command(["forward"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        self.bot.add_handler(
            MessageHandler(
                download_forward_media,
                filters=pyrogram.filters.media
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        self.bot.add_handler(
            MessageHandler(
                download_from_link,
                filters=pyrogram.filters.regex(r"^https://t.me.*")
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        self.bot.add_handler(
            MessageHandler(
                set_listen_forward_msg,
                filters=pyrogram.filters.command(["listen_forward"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        self.bot.add_handler(
            MessageHandler(
                help_command,
                filters=pyrogram.filters.command(["help"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        self.bot.add_handler(
            MessageHandler(
                get_info,
                filters=pyrogram.filters.command(["get_info"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        self.bot.add_handler(
            MessageHandler(
                help_command,
                filters=pyrogram.filters.command(["start"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        self.bot.add_handler(
            MessageHandler(
                set_language,
                filters=pyrogram.filters.command(["set_language"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        self.bot.add_handler(
            MessageHandler(
                add_filter,
                filters=pyrogram.filters.command(["add_filter"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )

        self.bot.add_handler(
            MessageHandler(
                stop,
                filters=pyrogram.filters.command(["stop"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )

        self.bot.add_handler(
            CallbackQueryHandler(
                on_query_handler, filters=pyrogram.filters.user(self.allowed_user_ids)
            )
        )

        self.client.add_handler(MessageHandler(listen_forward_msg))

        try:
            await send_help_str(self.bot, admin.id)
        except Exception:
            pass

        self.reply_task = _bot.app.loop.create_task(_bot.update_reply_message())

        self.bot.add_handler(
            MessageHandler(
                forward_to_comments,
                filters=pyrogram.filters.command(["forward_to_comments"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        
        # 注册新增的命令处理器
        self.bot.add_handler(
            MessageHandler(
                show_floodwait,
                filters=pyrogram.filters.command(["show_floodwait"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        
        self.bot.add_handler(
            MessageHandler(
                set_floodwait,
                filters=pyrogram.filters.command(["set_floodwait"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        
        self.bot.add_handler(
            MessageHandler(
                pause_download,
                filters=pyrogram.filters.command(["pause_download"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        
        self.bot.add_handler(
            MessageHandler(
                resume_download,
                filters=pyrogram.filters.command(["resume_download"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        
        self.bot.add_handler(
            MessageHandler(
                task_info,
                filters=pyrogram.filters.command(["task_info"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        
        self.bot.add_handler(
            MessageHandler(
                network_status,
                filters=pyrogram.filters.command(["network_status"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        
        # 热重载命令
        self.bot.add_handler(
            MessageHandler(
                cmd_reload,
                filters=pyrogram.filters.command(["reload"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        
        self.bot.add_handler(
            MessageHandler(
                cmd_save_state,
                filters=pyrogram.filters.command(["save_state"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        
        self.bot.add_handler(
            MessageHandler(
                cmd_restore_state,
                filters=pyrogram.filters.command(["restore_state"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        
        self.bot.add_handler(
            MessageHandler(
                cmd_analyze_logs,
                filters=pyrogram.filters.command(["analyze_logs"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )
        
        self.bot.add_handler(
            MessageHandler(
                cmd_update_commands,
                filters=pyrogram.filters.command(["update_commands"])
                & pyrogram.filters.user(self.allowed_user_ids),
            )
        )


_bot = DownloadBot()


async def start_download_bot(
    app: Application,
    client: pyrogram.Client,
    add_download_task: Callable,
    download_chat_task: Callable,
):
    """Start download bot"""
    await _bot.start(app, client, add_download_task, download_chat_task)


async def stop_download_bot():
    """Stop download bot"""
    _bot.update_config()
    _bot.is_running = False
    if _bot.reply_task:
        _bot.reply_task.cancel()
    _bot.stop_task("all")
    if _bot.bot:
        await _bot.bot.stop()


async def send_help_str(client: pyrogram.Client, chat_id):
    """
    Sends a help string to the specified chat ID using the provided client.

    Parameters:
        client (pyrogram.Client): The Pyrogram client used to send the message.
        chat_id: The ID of the chat to which the message will be sent.

    Returns:
        str: The help string that was sent.

    Note:
        The help string includes information about the Telegram Media Downloader bot,
        its version, and the available commands.
    """

    update_keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Github",
                    url="https://github.com/tangyoha/telegram_media_downloader/releases",
                ),
                InlineKeyboardButton(
                    "Join us", url="https://t.me/TeegramMediaDownload"
                ),
            ]
        ]
    )
    latest_release_str = ""
    # try:
    #     latest_release = get_latest_release(_bot.app.proxy)

    #     latest_release_str = (
    #         f"{_t('New Version')}: [{latest_release['name']}]({latest_release['html_url']})\an"
    #         if latest_release
    #         else ""
    #     )
    # except Exception:
    #     latest_release_str = ""

    msg = (
        f"`\n🤖 {_t('Telegram Media Downloader')}\n"
        f"🌐 {_t('Version')}: {utils.__version__}`\n"
        f"{latest_release_str}\n"
        f"{_t('Available commands:')}\n\n"
        f"📥 **下载功能**\n"
        f"/download - {_t('Download messages')}\n"
        f"/pause_download - 暂停下载任务\n"
        f"/resume_download - 恢复下载任务\n\n"
        f"📤 **转发功能**\n"
        f"/forward - {_t('Forward messages')}\n"
        f"/listen_forward - {_t('Listen for forwarded messages')}\n"
        f"/forward_to_comments - {_t('Forward a specific media to a comment section')}\n\n"
        f"⚙️ **设置和管理**\n"
        f"/set_language - {_t('Set language')}\n"
        f"/add_filter - {_t('Add download filter')}\n"
        f"/show_floodwait - 显示FloodWait设置\n"
        f"/set_floodwait - 设置FloodWait参数\n\n"
        f"📊 **状态和信息**\n"
        f"/help - {_t('Show available commands')}\n"
        f"/get_info - {_t('Get group and user info from message link')}\n"
        f"/task_info - 显示任务信息\n"
        f"/network_status - 显示网络监控状态\n"
        f"/analyze_logs - 分析日志文件\n\n"
        f"🔧 **系统维护**\n"
        f"/reload - 热重载代码（无需重启）\n"
        f"/save_state - 保存当前任务状态\n"
        f"/restore_state - 恢复保存的任务\n"
        f"/stop - {_t('Stop bot download or forward')}\n\n"
        f"{_t('**Note**: 1 means the start of the entire chat')},"
        f"{_t('0 means the end of the entire chat')}\n"
        f"`[` `]` {_t('means optional, not required')}\n"
    )

    await client.send_message(chat_id, msg, reply_markup=update_keyboard)


async def help_command(client: pyrogram.Client, message: pyrogram.types.Message):
    """
    Sends a message with the available commands and their usage.

    Parameters:
        client (pyrogram.Client): The client instance.
        message (pyrogram.types.Message): The message object.

    Returns:
        None
    """

    await send_help_str(client, message.chat.id)


async def set_language(client: pyrogram.Client, message: pyrogram.types.Message):
    """
    Set the language of the bot.

    Parameters:
        client (pyrogram.Client): The pyrogram client.
        message (pyrogram.types.Message): The message containing the command.

    Returns:
        None
    """

    if len(message.text.split()) != 2:
        await client.send_message(
            message.from_user.id,
            _t("Invalid command format. Please use /set_language en/ru/zh/ua"),
        )
        return

    language = message.text.split()[1]

    try:
        language = Language[language.upper()]
        _bot.app.set_language(language)
        await client.send_message(
            message.from_user.id, f"{_t('Language set to')} {language.name}"
        )
    except KeyError:
        await client.send_message(
            message.from_user.id,
            _t("Invalid command format. Please use /set_language en/ru/zh/ua"),
        )


async def get_info(client: pyrogram.Client, message: pyrogram.types.Message):
    """
    Async function that retrieves information from a group message link.
    """

    msg = _t("Invalid command format. Please use /get_info group_message_link")

    args = message.text.split()
    if len(args) != 2:
        await client.send_message(
            message.from_user.id,
            msg,
        )
        return

    chat_id, message_id, _ = await parse_link(_bot.client, args[1])

    entity = None
    if chat_id:
        entity = await _bot.client.get_chat(chat_id)

    if entity:
        if message_id:
            _message = await retry(_bot.client.get_messages, args=(chat_id, message_id))
            if _message:
                meta_data = MetaData()
                set_meta_data(meta_data, _message)
                msg = (
                    f"`\n"
                    f"{_t('Group/Channel')}\n"
                    f"├─ {_t('id')}: {entity.id}\n"
                    f"├─ {_t('first name')}: {entity.first_name}\n"
                    f"├─ {_t('last name')}: {entity.last_name}\n"
                    f"└─ {_t('name')}: {entity.username}\n"
                    f"{_t('Message')}\n"
                )

                for key, value in meta_data.data().items():
                    if key == "send_name":
                        msg += f"└─ {key}: {value or None}\n"
                    else:
                        msg += f"├─ {key}: {value or None}\n"

                msg += "`"
    await client.send_message(
        message.from_user.id,
        msg,
    )


async def add_filter(client: pyrogram.Client, message: pyrogram.types.Message):
    """
    Set the download filter of the bot.

    Parameters:
        client (pyrogram.Client): The pyrogram client.
        message (pyrogram.types.Message): The message containing the command.

    Returns:
        None
    """

    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        await client.send_message(
            message.from_user.id,
            _t("Invalid command format. Please use /add_filter your filter"),
        )
        return

    filter_str = replace_date_time(args[1])
    res, err = _bot.filter.check_filter(filter_str)
    if res:
        _bot.app.down = args[1]
        await client.send_message(
            message.from_user.id, f"{_t('Add download filter')} : {args[1]}"
        )
    else:
        await client.send_message(
            message.from_user.id, f"{err}\n{_t('Check error, please add again!')}"
        )
    return


async def direct_download(
    download_bot: DownloadBot,
    chat_id: Union[str, int],
    message: pyrogram.types.Message,
    download_message: pyrogram.types.Message,
    client: pyrogram.Client = None,
):
    """Direct Download"""

    replay_message = "Direct download..."
    last_reply_message = await download_bot.bot.send_message(
        message.from_user.id, replay_message, reply_to_message_id=message.id
    )

    node = TaskNode(
        chat_id=chat_id,
        from_user_id=message.from_user.id,
        reply_message_id=last_reply_message.id,
        replay_message=replay_message,
        limit=1,
        bot=download_bot.bot,
        task_id=_bot.gen_task_id(),
    )

    node.client = client
    node.is_running = True  # 设置任务为运行中

    _bot.add_task_node(node)

    await _bot.add_download_task(
        download_message,
        node,
    )

    node.is_running = True
    node.start_time = time.time()  # 记录任务开始时间


async def download_forward_media(
    client: pyrogram.Client, message: pyrogram.types.Message
):
    """
    Downloads the media from a forwarded message.

    Parameters:
        client (pyrogram.Client): The client instance.
        message (pyrogram.types.Message): The message object.

    Returns:
        None
    """

    if message.media and getattr(message, message.media.value):
        await direct_download(_bot, message.from_user.id, message, message, client)
        return

    await client.send_message(
        message.from_user.id,
        f"1. {_t('Direct download, directly forward the message to your robot')}\n\n",
        parse_mode=pyrogram.enums.ParseMode.HTML,
    )


async def download_from_link(client: pyrogram.Client, message: pyrogram.types.Message):
    """
    Downloads a single message from a Telegram link.

    Parameters:
        client (pyrogram.Client): The pyrogram client.
        message (pyrogram.types.Message): The message containing the Telegram link.

    Returns:
        None
    """

    if not message.text or not message.text.startswith("https://t.me"):
        return

    msg = (
        f"1. {_t('Directly download a single message')}\n"
        "<i>https://t.me/12000000/1</i>\n\n"
    )

    text = message.text.split()
    if len(text) != 1:
        await client.send_message(
            message.from_user.id, msg, parse_mode=pyrogram.enums.ParseMode.HTML
        )

    chat_id, message_id, _ = await parse_link(_bot.client, text[0])

    entity = None
    if chat_id:
        entity = await _bot.client.get_chat(chat_id)
    if entity:
        if message_id:
            download_message = await retry(
                _bot.client.get_messages, args=(chat_id, message_id)
            )
            if download_message:
                await direct_download(_bot, entity.id, message, download_message)
            else:
                client.send_message(
                    message.from_user.id,
                    f"{_t('From')} {entity.title} {_t('download')} {message_id} {_t('error')}!",
                    reply_to_message_id=message.id,
                )
        return

    await client.send_message(
        message.from_user.id, msg, parse_mode=pyrogram.enums.ParseMode.HTML
    )


# pylint: disable = R0912, R0915,R0914


async def download_from_bot(client: pyrogram.Client, message: pyrogram.types.Message):
    """Download from bot"""

    msg = (
        f"{_t('Parameter error, please enter according to the reference format')}:\n\n"
        f"1. {_t('Download all messages of common group')}\n"
        "<i>/download https://t.me/fkdhlg 1 0</i>\n\n"
        f"{_t('The private group (channel) link is a random group message link')}\n\n"
        f"2. {_t('The download starts from the N message to the end of the M message')}. "
        f"{_t('When M is 0, it means the last message. The filter is optional')}\n"
        f"<i>/download https://t.me/12000000 N M [filter]</i>\n\n"
    )

    args = message.text.split(maxsplit=4)
    if not message.text or len(args) < 4:
        await client.send_message(
            message.from_user.id, msg, parse_mode=pyrogram.enums.ParseMode.HTML
        )
        return

    url = args[1]
    try:
        start_offset_id = int(args[2])
        end_offset_id = int(args[3])
    except Exception:
        await client.send_message(
            message.from_user.id, msg, parse_mode=pyrogram.enums.ParseMode.HTML
        )
        return

    limit = 0
    if end_offset_id:
        if end_offset_id < start_offset_id:
            raise ValueError(
                f"end_offset_id < start_offset_id, {end_offset_id} < {start_offset_id}"
            )

        limit = end_offset_id - start_offset_id + 1

    download_filter = args[4] if len(args) > 4 else None

    if download_filter:
        download_filter = replace_date_time(download_filter)
        res, err = _bot.filter.check_filter(download_filter)
        if not res:
            await client.send_message(
                message.from_user.id, err, reply_to_message_id=message.id
            )
            return
    try:
        chat_id, _, _ = await parse_link(_bot.client, url)
        if chat_id:
            entity = await _bot.client.get_chat(chat_id)
        if entity:
            chat_title = entity.title
            reply_message = f"from {chat_title} "
            chat_download_config = ChatDownloadConfig()
            chat_download_config.last_read_message_id = start_offset_id
            chat_download_config.download_filter = download_filter
            reply_message += (
                f"download message id = {start_offset_id} - {end_offset_id} !"
            )
            last_reply_message = await client.send_message(
                message.from_user.id, reply_message, reply_to_message_id=message.id
            )
            node = TaskNode(
                chat_id=entity.id,
                from_user_id=message.from_user.id,
                reply_message_id=last_reply_message.id,
                replay_message=reply_message,
                limit=limit,
                start_offset_id=start_offset_id,
                end_offset_id=end_offset_id,
                bot=_bot.bot,
                task_id=_bot.gen_task_id(),
            )
            node.is_running = True  # 设置任务为运行中
            _bot.add_task_node(node)
            _bot.app.loop.create_task(
                _bot.download_chat_task(_bot.client, chat_download_config, node)
            )
    except Exception as e:
        await client.send_message(
            message.from_user.id,
            f"{_t('chat input error, please enter the channel or group link')}\n\n"
            f"{_t('Error type')}: {e.__class__}"
            f"{_t('Exception message')}: {e}",
        )
        return


async def get_forward_task_node(
    client: pyrogram.Client,
    message: pyrogram.types.Message,
    task_type: TaskType,
    src_chat_link: str,
    dst_chat_link: str,
    offset_id: int = 0,
    end_offset_id: int = 0,
    download_filter: str = None,
    reply_comment: bool = False,
):
    """Get task node"""
    limit: int = 0

    if end_offset_id:
        if end_offset_id < offset_id:
            await client.send_message(
                message.from_user.id,
                f" end_offset_id({end_offset_id}) < start_offset_id({offset_id}),"
                f" end_offset_id{_t('must be greater than')} offset_id",
            )
            return None

        limit = end_offset_id - offset_id + 1

    src_chat_id, _, _ = await parse_link(_bot.client, src_chat_link)
    dst_chat_id, target_msg_id, topic_id = await parse_link(_bot.client, dst_chat_link)

    if not src_chat_id or not dst_chat_id:
        logger.info(f"{src_chat_id} {dst_chat_id}")
        await client.send_message(
            message.from_user.id,
            _t("Invalid chat link") + f"{src_chat_id} {dst_chat_id}",
            reply_to_message_id=message.id,
        )
        return None

    try:
        src_chat = await _bot.client.get_chat(src_chat_id)
        dst_chat = await _bot.client.get_chat(dst_chat_id)
    except Exception as e:
        await client.send_message(
            message.from_user.id,
            f"{_t('Invalid chat link')} {e}",
            reply_to_message_id=message.id,
        )
        logger.exception(f"get chat error: {e}")
        return None

    me = await client.get_me()
    if dst_chat.id == me.id:
        # TODO: when bot receive message judge if download
        await client.send_message(
            message.from_user.id,
            _t("Cannot be forwarded to this bot, will cause an infinite loop"),
            reply_to_message_id=message.id,
        )
        return None

    if download_filter:
        download_filter = replace_date_time(download_filter)
        res, err = _bot.filter.check_filter(download_filter)
        if not res:
            await client.send_message(
                message.from_user.id, err, reply_to_message_id=message.id
            )

    last_reply_message = await client.send_message(
        message.from_user.id,
        "Forwarding message, please wait...",
        reply_to_message_id=message.id,
    )

    node = TaskNode(
        chat_id=src_chat.id,
        from_user_id=message.from_user.id,
        upload_telegram_chat_id=dst_chat_id,
        reply_message_id=last_reply_message.id,
        replay_message=last_reply_message.text,
        has_protected_content=src_chat.has_protected_content,
        download_filter=download_filter,
        limit=limit,
        start_offset_id=offset_id,
        end_offset_id=end_offset_id,
        bot=_bot.bot,
        task_id=_bot.gen_task_id(),
        task_type=task_type,
        topic_id=topic_id,
    )
    node.is_running = True  # 设置任务为运行中

    if target_msg_id and reply_comment:
        node.reply_to_message = await _bot.client.get_discussion_message(
            dst_chat_id, target_msg_id
        )

    _bot.add_task_node(node)

    node.upload_user = _bot.client
    if not dst_chat.type is pyrogram.enums.ChatType.BOT:
        has_permission = await check_user_permission(_bot.client, me.id, dst_chat.id)
        if has_permission:
            node.upload_user = _bot.bot

    if node.upload_user is _bot.client:
        await client.edit_message_text(
            message.from_user.id,
            last_reply_message.id,
            "Note that the robot may not be in the target group,"
            " use the user account to forward",
        )

    return node


# pylint: disable = R0914
async def forward_message_impl(
    client: pyrogram.Client, message: pyrogram.types.Message, reply_comment: bool
):
    """
    Forward message
    """

    async def report_error(client: pyrogram.Client, message: pyrogram.types.Message):
        """Report error"""

        await client.send_message(
            message.from_user.id,
            f"{_t('Invalid command format')}."
            f"{_t('Please use')} "
            "/forward https://t.me/c/src_chat https://t.me/c/dst_chat "
            f"1 400 `[`{_t('Filter')}`]`\n",
        )

    args = message.text.split(maxsplit=5)
    if len(args) < 5:
        await report_error(client, message)
        return

    src_chat_link = args[1]
    dst_chat_link = args[2]

    try:
        offset_id = int(args[3])
        end_offset_id = int(args[4])
    except Exception:
        await report_error(client, message)
        return

    download_filter = args[5] if len(args) > 5 else None

    node = await get_forward_task_node(
        client,
        message,
        TaskType.Forward,
        src_chat_link,
        dst_chat_link,
        offset_id,
        end_offset_id,
        download_filter,
        reply_comment,
    )

    if not node:
        return

    if not node.has_protected_content:
        try:
            async for item in get_chat_history_v2(  # type: ignore
                _bot.client,
                node.chat_id,
                limit=node.limit,
                max_id=node.end_offset_id,
                offset_id=offset_id,
                reverse=True,
            ):
                await forward_normal_content(client, node, item)
                if node.is_stop_transmission:
                    await client.edit_message_text(
                        message.from_user.id,
                        node.reply_message_id,
                        f"{_t('Stop Forward')}",
                    )
                    break
        except Exception as e:
            await client.edit_message_text(
                message.from_user.id,
                node.reply_message_id,
                f"{_t('Error forwarding message')} {e}",
            )
        finally:
            await report_bot_status(client, node, immediate_reply=True)
            node.stop_transmission()
    else:
        await forward_msg(node, offset_id)


async def forward_messages(client: pyrogram.Client, message: pyrogram.types.Message):
    """
    Forwards messages from one chat to another.

    Parameters:
        client (pyrogram.Client): The pyrogram client.
        message (pyrogram.types.Message): The message containing the command.

    Returns:
        None
    """
    return await forward_message_impl(client, message, False)


async def forward_normal_content(
    client: pyrogram.Client, node: TaskNode, message: pyrogram.types.Message
):
    """Forward normal content"""
    forward_ret = ForwardStatus.FailedForward
    if node.download_filter:
        meta_data = MetaData()
        caption = message.caption
        if caption:
            caption = validate_title(caption)
            _bot.app.set_caption_name(node.chat_id, message.media_group_id, caption)
        else:
            caption = _bot.app.get_caption_name(node.chat_id, message.media_group_id)
        set_meta_data(meta_data, message, caption)
        _bot.filter.set_meta_data(meta_data)
        if not _bot.filter.exec(node.download_filter):
            forward_ret = ForwardStatus.SkipForward
            if message.media_group_id:
                node.upload_status[message.id] = UploadStatus.SkipUpload
                await proc_cache_forward(_bot.client, node, message, False)
            await report_bot_forward_status(client, node, forward_ret)
            return

    await upload_telegram_chat_message(
        _bot.client, node.upload_user, _bot.app, node, message
    )


async def forward_msg(node: TaskNode, message_id: int):
    """Forward normal message"""

    chat_download_config = ChatDownloadConfig()
    chat_download_config.last_read_message_id = message_id
    chat_download_config.download_filter = node.download_filter  # type: ignore

    await _bot.download_chat_task(_bot.client, chat_download_config, node)


async def set_listen_forward_msg(
    client: pyrogram.Client, message: pyrogram.types.Message
):
    """
    Set the chat to listen for forwarded messages.

    Args:
        client (pyrogram.Client): The pyrogram client.
        message (pyrogram.types.Message): The message sent by the user.

    Returns:
        None
    """
    args = message.text.split(maxsplit=3)

    if len(args) < 3:
        await client.send_message(
            message.from_user.id,
            f"{_t('Invalid command format')}. {_t('Please use')} /listen_forward "
            f"https://t.me/c/src_chat https://t.me/c/dst_chat [{_t('Filter')}]\n",
        )
        return

    src_chat_link = args[1]
    dst_chat_link = args[2]

    download_filter = args[3] if len(args) > 3 else None

    node = await get_forward_task_node(
        client,
        message,
        TaskType.ListenForward,
        src_chat_link,
        dst_chat_link,
        download_filter=download_filter,
    )

    if not node:
        return

    if node.chat_id in _bot.listen_forward_chat:
        _bot.remove_task_node(_bot.listen_forward_chat[node.chat_id].task_id)

    node.is_running = True
    node.start_time = time.time()  # 记录任务开始时间
    _bot.listen_forward_chat[node.chat_id] = node


async def listen_forward_msg(client: pyrogram.Client, message: pyrogram.types.Message):
    """
    Forwards messages from a chat to another chat if the message does not contain protected content.
    If the message contains protected content, it will be downloaded and forwarded to the other chat.

    Parameters:
        client (pyrogram.Client): The pyrogram client.
        message (pyrogram.types.Message): The message to be forwarded.
    """

    if message.chat and message.chat.id in _bot.listen_forward_chat:
        node = _bot.listen_forward_chat[message.chat.id]

        # TODO(tangyoha):fix run time change protected content
        if not node.has_protected_content:
            await forward_normal_content(client, node, message)
            await report_bot_status(client, node, immediate_reply=True)
        else:
            await _bot.add_download_task(
                message,
                node,
            )


async def stop(client: pyrogram.Client, message: pyrogram.types.Message):
    """Stops listening for forwarded messages."""

    await client.send_message(
        message.chat.id,
        _t("Please select:"),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        _t("Stop Download"), callback_data="stop_download"
                    ),
                    InlineKeyboardButton(
                        _t("Stop Forward"), callback_data="stop_forward"
                    ),
                ],
                [  # Second row
                    InlineKeyboardButton(
                        _t("Stop Listen Forward"), callback_data="stop_listen_forward"
                    )
                ],
            ]
        ),
    )


async def stop_task(
    client: pyrogram.Client,
    query: pyrogram.types.CallbackQuery,
    queryHandler: str,
    task_type: TaskType,
):
    """Stop task"""
    if query.data == queryHandler:
        buttons: List[InlineKeyboardButton] = []
        temp_buttons: List[InlineKeyboardButton] = []
        for key, value in _bot.task_node.copy().items():
            if not value.is_finish() and value.task_type is task_type:
                if len(temp_buttons) == 3:
                    buttons.append(temp_buttons)
                    temp_buttons = []
                temp_buttons.append(
                    InlineKeyboardButton(
                        f"{key}", callback_data=f"{queryHandler} task {key}"
                    )
                )
        if temp_buttons:
            buttons.append(temp_buttons)

        if buttons:
            buttons.insert(
                0,
                [
                    InlineKeyboardButton(
                        _t("all"), callback_data=f"{queryHandler} task all"
                    )
                ],
            )
            await client.edit_message_text(
                query.message.from_user.id,
                query.message.id,
                f"{_t('Stop')} {_t(task_type.name)}...",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        else:
            await client.edit_message_text(
                query.message.from_user.id,
                query.message.id,
                f"{_t('No Task')}",
            )
    else:
        task_id = query.data.split(" ")[2]
        await client.edit_message_text(
            query.message.from_user.id,
            query.message.id,
            f"{_t('Stop')} {_t(task_type.name)}...",
        )
        _bot.stop_task(task_id)


async def on_query_handler(
    client: pyrogram.Client, query: pyrogram.types.CallbackQuery
):
    """
    Asynchronous function that handles query callbacks.

    Parameters:
        client (pyrogram.Client): The Pyrogram client object.
        query (pyrogram.types.CallbackQuery): The callback query object.

    Returns:
        None
    """

    for it in QueryHandler:
        queryHandler = QueryHandlerStr.get_str(it.value)
        if queryHandler in query.data:
            await stop_task(client, query, queryHandler, TaskType(it.value))


async def forward_to_comments(client: pyrogram.Client, message: pyrogram.types.Message):
    """
    Forwards specified media to a designated comment section.

    Usage: /forward_to_comments <source_chat_link> <destination_chat_link> <msg_start_id> <msg_end_id>

    Parameters:
        client (pyrogram.Client): The pyrogram client.
        message (pyrogram.types.Message): The message containing the command.
    """
    return await forward_message_impl(client, message, True)


async def show_floodwait(client: pyrogram.Client, message: pyrogram.types.Message):
    """显示当前FloodWait设置"""
    settings = _bot.app.get_floodwait_settings()
    msg = (
        f"🚀 **FloodWait设置**\n\n"
        f"📊 **下载设置**:\n"
        f"├─ 缓冲时间: `{settings['download_buffer']}秒`\n"
        f"└─ 策略: 等待时间 + 缓冲\n\n"
        f"📊 **上传设置**:\n"
        f"├─ 倍数: `{settings['upload_multiplier']}x`\n"
        f"├─ 缓冲时间: `{settings['upload_buffer']}秒`\n"
        f"└─ 策略: (等待时间 × 倍数) + 缓冲\n\n"
        f"💡 FloodWait触发后会自动调整缓冲时间"
    )
    await safe_send_message(client, message.from_user.id, msg)


async def set_floodwait(client: pyrogram.Client, message: pyrogram.types.Message):
    """设置FloodWait参数"""
    args = message.text.split()
    
    if len(args) < 3:
        msg = (
            f"❌ **命令格式错误**\n\n"
            f"使用方法:\n"
            f"`/set_floodwait download_buffer <秒数>`\n"
            f"`/set_floodwait upload_multiplier <倍数>`\n"
            f"`/set_floodwait upload_buffer <秒数>`\n\n"
            f"示例:\n"
            f"`/set_floodwait download_buffer 5`\n"
            f"`/set_floodwait upload_multiplier 2.5`\n"
            f"`/set_floodwait upload_buffer 10`"
        )
        await safe_send_message(client, message.from_user.id, msg)
        return
    
    param_type = args[1]
    try:
        value = float(args[2]) if param_type == "upload_multiplier" else int(args[2])
    except ValueError:
        await client.send_message(message.from_user.id, "❌ 参数值无效")
        return
    
    success = False
    if param_type == "download_buffer":
        success = _bot.app.set_download_floodwait_buffer(value)
    elif param_type == "upload_multiplier":
        success = _bot.app.set_upload_floodwait_multiplier(value)
    elif param_type == "upload_buffer":
        success = _bot.app.set_upload_floodwait_buffer(value)
    else:
        await client.send_message(message.from_user.id, "❌ 未知的参数类型")
        return
    
    if success:
        await client.send_message(message.from_user.id, f"✅ 已更新 {param_type} = {value}")
    else:
        await client.send_message(message.from_user.id, "❌ 参数值超出有效范围")


async def pause_download(client: pyrogram.Client, message: pyrogram.types.Message):
    """暂停下载任务"""
    args = message.text.split()
    
    if len(args) == 1:
        # 暂停所有任务
        paused_count = 0
        for task_id, task in _bot.task_node.items():
            if task.is_running and not task.is_paused:
                task.pause_task()
                paused_count += 1
        
        if paused_count > 0:
            await client.send_message(
                message.from_user.id,
                f"⏸️ 已暂停 {paused_count} 个任务"
            )
        else:
            await client.send_message(message.from_user.id, "💭 没有正在运行的任务")
    else:
        # 暂停指定任务
        try:
            task_id = int(args[1])
            task = _bot.task_node.get(task_id)
            if task:
                if not task.is_paused:
                    task.pause_task()
                    await client.send_message(
                        message.from_user.id,
                        f"⏸️ 已暂停任务 {task_id}"
                    )
                else:
                    await client.send_message(
                        message.from_user.id,
                        f"💭 任务 {task_id} 已经在暂停状态"
                    )
            else:
                await client.send_message(
                    message.from_user.id,
                    f"❌ 找不到任务 {task_id}"
                )
        except ValueError:
            await client.send_message(
                message.from_user.id,
                "❌ 无效的任务ID\n使用: `/pause_download [任务ID]`"
            )


async def resume_download(client: pyrogram.Client, message: pyrogram.types.Message):
    """恢复下载任务"""
    args = message.text.split()
    
    if len(args) == 1:
        # 恢复所有任务
        resumed_count = 0
        for task_id, task in _bot.task_node.items():
            if task.is_paused:
                task.resume_task()
                resumed_count += 1
        
        if resumed_count > 0:
            await client.send_message(
                message.from_user.id,
                f"▶️ 已恢复 {resumed_count} 个任务"
            )
        else:
            await client.send_message(message.from_user.id, "💭 没有暂停的任务")
    else:
        # 恢复指定任务
        try:
            task_id = int(args[1])
            task = _bot.task_node.get(task_id)
            if task:
                if task.is_paused:
                    task.resume_task()
                    await client.send_message(
                        message.from_user.id,
                        f"▶️ 已恢复任务 {task_id}"
                    )
                else:
                    await client.send_message(
                        message.from_user.id,
                        f"💭 任务 {task_id} 未在暂停状态"
                    )
            else:
                await client.send_message(
                    message.from_user.id,
                    f"❌ 找不到任务 {task_id}"
                )
        except ValueError:
            await client.send_message(
                message.from_user.id,
                "❌ 无效的任务ID\n使用: `/resume_download [任务ID]`"
            )


async def task_info(client: pyrogram.Client, message: pyrogram.types.Message):
    """显示详细任务信息（包含每个消息的下载进度）"""
    if not _bot.task_node:
        await client.send_message(message.from_user.id, "📂 当前没有任务")
        return
    
    # 导入下载状态模块和格式化工具
    from module.download_stat import get_download_result
    from utils.format import format_byte
    import time
    
    msg = ""
    
    # 获取全局下载结果
    download_results = get_download_result()
    
    for task_id, task in _bot.task_node.items():
        # 获取该任务的下载结果
        chat_download_results = download_results.get(task.chat_id, {})
        
        # 任务状态
        if task.is_stop_transmission:
            status = "🛑 已停止"
        elif task.is_paused:
            status = "⏸️ 已暂停"
        elif task.is_running:
            status = "▶️ 运行中"
        else:
            status = "⏳ 等待中"
        
        msg += f"`\n"
        msg += f"🆔 task id: {task_id}\n"
        msg += f"📥 下载: {format_byte(getattr(task, 'total_download_byte', 0))}\n"
        msg += f"├─ 📁 总数: {task.total_download_task}\n"
        msg += f"├─ ✅ 成功: {task.success_download_task}\n"
        msg += f"├─ ❌ 失败: {task.failed_download_task}\n"
        msg += f"└─ ⏩ 跳过: {task.skip_download_task}\n"
        msg += f"`\n\n"
        
        # 如果有正在下载的消息，显示每个消息的进度
        if chat_download_results and task.is_running:
            msg += "`📥 下载进度:\n"
            
            # 显示最多5个正在下载的文件（过滤掉已完成的）
            count = 0
            active_downloads = []
            
            for msg_id, download_info in chat_download_results.items():
                total_size = download_info.get('total_size', 0)
                down_byte = download_info.get('down_byte', 0)
                # 计算进度百分比
                progress = (down_byte / total_size * 100) if total_size > 0 else 0
                
                # 只显示未完成的下载（进度小于100%）
                if progress < 100:
                    active_downloads.append((msg_id, download_info, progress))
            
            # 按进度排序，优先显示进度较低的
            active_downloads.sort(key=lambda x: x[2])
            
            for msg_id, download_info, progress in active_downloads[:5]:
                file_name = download_info.get('file_name', 'unknown')
                total_size = download_info.get('total_size', 0)
                down_byte = download_info.get('down_byte', 0)
                download_speed = download_info.get('download_speed', 0)
                
                # 生成进度条
                filled = int(progress // 10)
                bar = "█" * filled + "░" * (10 - filled)
                
                # 格式化大小
                if total_size > 1024 * 1024 * 1024:
                    size_text = f"{total_size / (1024 * 1024 * 1024):.2f}GB"
                elif total_size > 1024 * 1024:
                    size_text = f"{total_size / (1024 * 1024):.2f}MB"
                else:
                    size_text = f"{total_size / 1024:.2f}KB"
                
                # 格式化速度
                if download_speed > 1024 * 1024:
                    speed_text = f"{download_speed / (1024 * 1024):.1f}MB/s"
                elif download_speed > 1024:
                    speed_text = f"{download_speed / 1024:.1f}KB/s"
                else:
                    speed_text = f"{download_speed:.0f}B/s"
                
                # 截断文件名如果太长
                if len(file_name) > 30:
                    file_name = file_name[:27] + "..."
                
                msg += f" ├─ 🆔 消息ID: {msg_id}\n"
                msg += f" │   ├─ 📁 : {file_name}\n"
                msg += f" │   ├─ 📏 : {size_text}\n"
                msg += f" │   ├─ ⏬ : {speed_text}\n"
                msg += f" │   └─ 📊 : [{bar}] ({progress:.0f}%)\n"
            
            # 显示剩余活跃下载数
            if len(active_downloads) > 5:
                remaining = len(active_downloads) - 5
                msg += f"  ... 还有 {remaining} 个文件正在下载\n"
            elif not active_downloads:
                msg += "  当前没有文件正在下载\n"
            
            msg += "`\n\n"  # 关闭代码块
        
        msg += "─" * 30 + "\n\n"
    
    # 添加命令提示
    msg += "💡 **可用命令:**\n"
    msg += "• `/task_info` - 查看任务详情\n"
    msg += "• `/pause_download [ID]` - 暂停任务\n"
    msg += "• `/resume_download [ID]` - 恢复任务\n"
    msg += "• `/stop` - 停止所有任务\n"
    
    await safe_send_message(client, message.from_user.id, msg)


async def network_status(client: pyrogram.Client, message: pyrogram.types.Message):
    """显示网络监控状态"""
    if _bot.app.enable_network_monitor:
        network_icon = "🟢" if _bot.app.is_network_available() else "🔴"
        network_text = "正常" if _bot.app.is_network_available() else "断线"
        paused_tasks = _bot.app.get_network_paused_tasks()
        
        msg = (
            f"🌐 **网络监控状态**\n\n"
            f"{network_icon} 网络状态: {network_text}\n"
            f"⏰ 检查间隔: {_bot.app.network_check_interval}秒\n"
            f"🏖️ 检查主机: {_bot.app.network_check_host}\n"
            f"⏳ 超时时间: {_bot.app.network_timeout}秒\n\n"
        )
        
        if paused_tasks:
            msg += f"📂 因网络问题暂停的任务: {len(paused_tasks)}个\n"
            for task_key in list(paused_tasks)[:5]:  # 只显示前5个
                msg += f"  - {task_key}\n"
            if len(paused_tasks) > 5:
                msg += f"  ... 及其他 {len(paused_tasks) - 5} 个\n"
        else:
            msg += "✅ 没有因网络问题暂停的任务\n"
    else:
        msg = "❌ 网络监控功能已禁用"
    
    await safe_send_message(client, message.from_user.id, msg)


@handle_floodwait
async def cmd_reload(client: pyrogram.Client, message: pyrogram.types.Message):
    """热重载代码"""
    from module.hot_reload import hot_reloader, TaskPersistence
    
    # 尝试从app.chat_download_config收集任务（命令行启动的任务）
    tasks = []
    
    # 先从bot管理的任务中收集
    for node_key in list(_bot.task_node.keys()):
        node = _bot.task_node.get(node_key)
        if node and hasattr(node, 'is_running') and node.is_running:
            tasks.append(node)
            logger.debug(f"📋 从Bot找到任务: {node_key}")
    
    # 再从app的下载配置中收集（命令行启动的任务）
    if _bot.app and hasattr(_bot.app, 'chat_download_config'):
        task_id = len(tasks) + 1
        for chat_id, config in _bot.app.chat_download_config.items():
            if hasattr(config, 'node') and config.node:
                node = config.node
                if not hasattr(node, 'task_id'):
                    node.task_id = task_id
                    task_id += 1
                # 检查是否正在下载
                if hasattr(node, 'is_running') and node.is_running:
                    tasks.append(node)
                    logger.debug(f"📋 从配置找到任务: Chat={chat_id}")
                    # 同时添加到bot管理中
                    if node.task_id not in _bot.task_node:
                        _bot.task_node[node.task_id] = node
    
    logger.info(f"🔍 共找到 {len(tasks)} 个运行中的任务")
    TaskPersistence.save_tasks(tasks)
    
    msg = (
        f"🔄 **热重载请求**\n\n"
        f"📦 已保存 {len(tasks)} 个活动任务\n"
        f"⏸️ 暂停所有下载...\n"
        f"🔧 准备重载代码...\n\n"
        f"请稍等片刻后使用 /restore_state 恢复任务"
    )
    
    await safe_send_message(client, message.from_user.id, msg)
    
    # 请求重载并执行
    hot_reloader.request_reload()
    
    # 执行实际的模块重载
    try:
        # 暂停所有任务
        for node in tasks:
            node.is_running = False
            node.is_paused = True
        
        # 重载主要模块
        import importlib
        modules_to_reload = [
            'module.download_stat',  # 先重载这个，因为其他模块依赖它
            'module.app',
            'module.pyrogram_extension',
            'module.bot_utils',
            'module.bot',  # 重载bot模块自身
            'media_downloader'
        ]
        
        # 保存当前的函数引用
        old_task_info = task_info
        
        for module_name in modules_to_reload:
            if module_name in sys.modules:
                try:
                    importlib.reload(sys.modules[module_name])
                    logger.info(f"✅ 重载模块: {module_name}")
                except Exception as e:
                    logger.error(f"❌ 重载模块 {module_name} 失败: {e}")
        
        # 重新导入关键函数
        from module.bot import task_info as new_task_info
        globals()['task_info'] = new_task_info
        
        # 更新bot的处理器
        if hasattr(_bot, 'bot'):
            # 移除旧的 task_info 处理器
            _bot.bot.remove_handler(task_info)
            # 添加新的处理器
            _bot.bot.add_handler(
                MessageHandler(
                    new_task_info,
                    filters=pyrogram.filters.command(["task_info"])
                    & pyrogram.filters.user(_bot.allowed_user_ids),
                )
            )
            logger.info("✅ 更新了 task_info 命令处理器")
        
        reload_msg = (
            f"✅ **重载成功**\n\n"
            f"🔄 已重载 {len(modules_to_reload)} 个模块\n"
            f"📦 已保存 {len(tasks)} 个任务\n\n"
            f"使用 /restore_state 恢复任务"
        )
        await safe_send_message(client, message.from_user.id, reload_msg)
        
    except Exception as e:
        error_msg = f"❌ 重载失败: {str(e)}"
        logger.error(error_msg)
        await safe_send_message(client, message.from_user.id, error_msg)


@handle_floodwait
async def cmd_save_state(client: pyrogram.Client, message: pyrogram.types.Message):
    """保存任务状态"""
    from module.hot_reload import TaskPersistence
    
    # 收集所有活动任务
    tasks = []
    for node_key in list(_bot.task_node.keys()):
        node = _bot.task_node.get(node_key)
        if node and hasattr(node, 'is_running') and node.is_running:
            tasks.append(node)
    
    # 保存任务
    success = TaskPersistence.save_tasks(tasks)
    
    # 保存应用状态
    app_saved = TaskPersistence.save_app_state(_bot.app) if _bot.app else False
    
    msg = (
        f"💾 **保存状态**\n\n"
        f"{'✅' if success else '❌'} 任务状态: {len(tasks)} 个任务\n"
        f"{'✅' if app_saved else '❌'} 应用配置\n\n"
        f"文件: pending_tasks.json, app_state.pkl"
    )
    
    await safe_send_message(client, message.from_user.id, msg)


async def cmd_restore_state(client: pyrogram.Client, message: pyrogram.types.Message):
    """恢复任务状态"""
    from module.hot_reload import TaskPersistence
    
    # 加载保存的任务
    task_data = TaskPersistence.load_tasks()
    
    msg = (
        f"📂 **恢复状态**\n\n"
        f"找到 {len(task_data)} 个保存的任务\n\n"
    )
    
    if task_data:
        msg += "任务详情:\n"
        for i, task in enumerate(task_data[:5], 1):
            msg += (
                f"{i}. Chat ID: {task.get('chat_id')}\n"
                f"   消息数: {len(task.get('message_ids', []))}\n"
                f"   已完成: {task.get('success_count', 0)}\n"
            )
        
        if len(task_data) > 5:
            msg += f"\n... 及其他 {len(task_data) - 5} 个任务\n"
        
        msg += "\n⚠️ 注意: 恢复功能需要重新启动下载任务"
    else:
        msg += "没有找到保存的任务"
    
    await safe_send_message(client, message.from_user.id, msg)


@handle_floodwait
async def cmd_analyze_logs(client: pyrogram.Client, message: pyrogram.types.Message):
    """分析日志文件"""
    import subprocess
    import os
    
    msg = "📊 **日志分析**\n\n正在分析日志文件...\n"
    await safe_send_message(client, message.from_user.id, msg)
    
    try:
        # 运行日志分析脚本
        result = subprocess.run(
            ["python", "analyze_logs.py", "--summary"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # 解析输出
        output_lines = result.stdout.split('\n')
        
        # 提取关键信息
        error_count = 0
        warning_count = 0
        floodwait_count = 0
        
        # 检查日志文件
        log_files = []
        if os.path.exists("logs"):
            for file in os.listdir("logs"):
                if file.endswith(".log"):
                    file_path = os.path.join("logs", file)
                    file_size = os.path.getsize(file_path) / 1024  # KB
                    log_files.append(f"  • {file} ({file_size:.1f} KB)")
        
        msg = (
            f"📊 **日志分析结果**\n\n"
            f"**日志文件:**\n"
        )
        
        if log_files:
            msg += "\n".join(log_files[:10])
            if len(log_files) > 10:
                msg += f"\n  ... 及其他 {len(log_files) - 10} 个文件"
        else:
            msg += "  没有找到日志文件"
        
        msg += "\n\n💡 **提示:**\n"
        msg += "• 错误日志: logs/error_YYYY-MM-DD.log\n"
        msg += "• 警告日志: logs/warning_YYYY-MM-DD.log\n"
        msg += "• 完整日志: logs/full_YYYY-MM-DD.log\n"
        msg += "• FloodWait日志: logs/floodwait_YYYY-MM.log\n"
        msg += "\n运行 `python analyze_logs.py --all` 查看详细分析"
        
    except subprocess.TimeoutExpired:
        msg = "❌ 日志分析超时"
    except Exception as e:
        msg = f"❌ 日志分析失败: {str(e)}"
    
    await safe_send_message(client, message.from_user.id, msg)


@handle_floodwait
async def cmd_update_commands(client: pyrogram.Client, message: pyrogram.types.Message):
    """更新Bot命令菜单"""
    msg = "🔄 **更新命令菜单**\n\n正在更新Bot命令..."
    await safe_send_message(client, message.from_user.id, msg)
    
    try:
        # 定义所有命令
        commands = [
            # 基础命令
            types.BotCommand("help", "显示帮助信息"),
            types.BotCommand("download", "下载消息"),
            types.BotCommand("forward", "转发消息"),
            types.BotCommand("stop", "停止任务"),
            
            # 设置命令
            types.BotCommand("set_language", "设置语言"),
            types.BotCommand("add_filter", "添加过滤器"),
            types.BotCommand("get_info", "获取信息"),
            
            # 任务管理
            types.BotCommand("pause_download", "暂停下载"),
            types.BotCommand("resume_download", "恢复下载"),
            types.BotCommand("task_info", "任务信息"),
            
            # FloodWait管理
            types.BotCommand("show_floodwait", "FloodWait设置"),
            types.BotCommand("set_floodwait", "设置FloodWait"),
            
            # 系统维护
            types.BotCommand("network_status", "网络状态"),
            types.BotCommand("analyze_logs", "分析日志"),
            types.BotCommand("reload", "热重载代码"),
            types.BotCommand("save_state", "保存状态"),
            types.BotCommand("restore_state", "恢复状态"),
            types.BotCommand("update_commands", "更新命令菜单"),
            
            # 转发相关
            types.BotCommand("listen_forward", "监听转发"),
            types.BotCommand("forward_to_comments", "转发到评论"),
        ]
        
        # 更新命令
        await _bot.bot.set_bot_commands(commands)
        
        msg = (
            f"✅ **命令菜单已更新**\n\n"
            f"已注册 {len(commands)} 个命令\n\n"
            f"现在在聊天框输入 `/` 即可看到所有命令\n\n"
            f"**新增的命令:**\n"
            f"• /reload - 热重载代码\n"
            f"• /save_state - 保存状态\n"
            f"• /restore_state - 恢复状态\n"
            f"• /analyze_logs - 分析日志\n"
            f"• /update_commands - 更新菜单\n"
        )
        
    except Exception as e:
        msg = f"❌ 更新失败: {str(e)}"
    
    await safe_send_message(client, message.from_user.id, msg)
