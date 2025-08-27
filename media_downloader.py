"""Downloads media from telegram."""
import asyncio
import logging
import os
import shutil
import time
from typing import List, Optional, Tuple, Union

import pyrogram
from loguru import logger
from pyrogram.types import Audio, Document, Photo, Video, VideoNote, Voice
from rich.logging import RichHandler

from module.app import Application, ChatDownloadConfig, DownloadStatus, TaskNode
from module.bot import start_download_bot, stop_download_bot
from module.download_stat import update_download_status
from module.get_chat_history_v2 import get_chat_history_v2
from module.hot_reload import (
    HotReloader,
    TaskPersistence,
    create_reload_command,
    hot_reloader,
    setup_reload_signal,
)
from module.language import _t
from module.pyrogram_extension import (
    HookClient,
    fetch_message,
    get_extension,
    record_download_status,
    report_bot_download_status,
    set_max_concurrent_transmissions,
    set_meta_data,
    update_cloud_upload_stat,
    upload_telegram_chat,
)
from module.web import init_web
from utils.format import truncate_filename, validate_title
from utils.log import LogFilter
from utils.meta import print_meta
from utils.meta_data import MetaData

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()],
)

CONFIG_NAME = "config.yaml"
DATA_FILE_NAME = "data.yaml"
APPLICATION_NAME = "media_downloader"
app = Application(CONFIG_NAME, DATA_FILE_NAME, APPLICATION_NAME)

queue: asyncio.Queue = asyncio.Queue()
RETRY_TIME_OUT = 3

logging.getLogger("pyrogram.session.session").addFilter(LogFilter())
logging.getLogger("pyrogram.client").addFilter(LogFilter())

# 设置日志级别 - 保留更多调试信息
logging.getLogger("pyrogram").setLevel(logging.INFO)
logging.getLogger("pyrogram.session").setLevel(logging.INFO)
logging.getLogger("pyrogram.connection").setLevel(logging.INFO)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("asyncio.selector_events").setLevel(logging.WARNING)

# 创建日志目录
os.makedirs("logs", exist_ok=True)

# 配置详细的错误日志
logger.add(
    "logs/error_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",  # 保留30天
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
    backtrace=True,
    diagnose=True,
    enqueue=True,  # 异步写入
    catch=True,    # 捕获日志写入错误
    encoding="utf-8"
)

# 配置警告日志
logger.add(
    "logs/warning_{time:YYYY-MM-DD}.log", 
    rotation="1 day",
    retention="14 days",  # 保留14天
    level="WARNING",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
    backtrace=False,
    diagnose=False,
    enqueue=True,
    catch=True,
    encoding="utf-8",
    filter=lambda record: record["level"].name == "WARNING"  # 只记录WARNING级别
)

# 配置完整日志（包含DEBUG信息）
logger.add(
    "logs/full_{time:YYYY-MM-DD}.log",
    rotation="100 MB",  # 100MB轮转
    retention="7 days",  # 保留7天
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
    backtrace=True,
    diagnose=True,
    enqueue=True,
    catch=True,
    encoding="utf-8"
)

# FloodWait专用日志
logger.add(
    "logs/floodwait_{time:YYYY-MM}.log",
    rotation="1 month",
    retention="3 months",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
    filter=lambda record: "FloodWait" in record["message"],
    enqueue=True,
    encoding="utf-8"
)


def _check_download_finish(media_size: int, download_path: str, ui_file_name: str):
    """Check download task if finish

    Parameters
    ----------
    media_size: int
        The size of the downloaded resource
    download_path: str
        Resource download hold path
    ui_file_name: str
        Really show file name

    """
    download_size = os.path.getsize(download_path)
    if media_size == download_size:
        logger.success(f"{_t('Successfully downloaded')} - {ui_file_name}")
    else:
        logger.warning(
            f"{_t('Media downloaded with wrong size')}: "
            f"{download_size}, {_t('actual')}: "
            f"{media_size}, {_t('file name')}: {ui_file_name}"
        )
        os.remove(download_path)
        raise pyrogram.errors.exceptions.bad_request_400.BadRequest()


def _move_to_download_path(temp_download_path: str, download_path: str):
    """Move file to download path

    Parameters
    ----------
    temp_download_path: str
        Temporary download path

    download_path: str
        Download path

    """

    directory, _ = os.path.split(download_path)
    os.makedirs(directory, exist_ok=True)
    shutil.move(temp_download_path, download_path)


def _check_timeout(retry: int, _: int):
    """Check if message download timeout, then add message id into failed_ids

    Parameters
    ----------
    retry: int
        Retry download message times

    message_id: int
        Try to download message 's id

    """
    if retry == 2:
        return True
    return False


def _can_download(_type: str, file_formats: dict, file_format: Optional[str]) -> bool:
    """
    Check if the given file format can be downloaded.

    Parameters
    ----------
    _type: str
        Type of media object.
    file_formats: dict
        Dictionary containing the list of file_formats
        to be downloaded for `audio`, `document` & `video`
        media types
    file_format: str
        Format of the current file to be downloaded.

    Returns
    -------
    bool
        True if the file format can be downloaded else False.
    """
    if _type in ["audio", "document", "video"]:
        allowed_formats: list = file_formats[_type]
        if not file_format in allowed_formats and allowed_formats[0] != "all":
            return False
    return True


def _is_exist(file_path: str) -> bool:
    """
    Check if a file exists and it is not a directory.

    Parameters
    ----------
    file_path: str
        Absolute path of the file to be checked.

    Returns
    -------
    bool
        True if the file exists else False.
    """
    return not os.path.isdir(file_path) and os.path.exists(file_path)


# pylint: disable = R0912


async def _get_media_meta(
    chat_id: Union[int, str],
    message: pyrogram.types.Message,
    media_obj: Union[Audio, Document, Photo, Video, VideoNote, Voice],
    _type: str,
) -> Tuple[str, str, Optional[str]]:
    """Extract file name and file id from media object.

    Parameters
    ----------
    media_obj: Union[Audio, Document, Photo, Video, VideoNote, Voice]
        Media object to be extracted.
    _type: str
        Type of media object.

    Returns
    -------
    Tuple[str, str, Optional[str]]
        file_name, file_format
    """
    if _type in ["audio", "document", "video"]:
        # pylint: disable = C0301
        file_format: Optional[str] = media_obj.mime_type.split("/")[-1]  # type: ignore
    else:
        file_format = None

    file_name = None
    temp_file_name = None
    dirname = validate_title(f"{chat_id}")
    if message.chat and message.chat.title:
        dirname = validate_title(f"{message.chat.title}")

    if message.date:
        datetime_dir_name = message.date.strftime(app.date_format)
    else:
        datetime_dir_name = "0"

    if _type in ["voice", "video_note"]:
        # pylint: disable = C0209
        file_format = media_obj.mime_type.split("/")[-1]  # type: ignore
        file_save_path = app.get_file_save_path(_type, dirname, datetime_dir_name)
        file_name = "{} - {}_{}.{}".format(
            message.id,
            _type,
            media_obj.date.isoformat(),  # type: ignore
            file_format,
        )
        file_name = validate_title(file_name)
        temp_file_name = os.path.join(app.temp_save_path, dirname, file_name)

        file_name = os.path.join(file_save_path, file_name)
    else:
        file_name = getattr(media_obj, "file_name", None)
        caption = getattr(message, "caption", None)

        file_name_suffix = ".unknown"
        if not file_name:
            file_name_suffix = get_extension(
                media_obj.file_id, getattr(media_obj, "mime_type", "")
            )
        else:
            # file_name = file_name.split(".")[0]
            _, file_name_without_suffix = os.path.split(os.path.normpath(file_name))
            file_name, file_name_suffix = os.path.splitext(file_name_without_suffix)
            if not file_name_suffix:
                file_name_suffix = get_extension(
                    media_obj.file_id, getattr(media_obj, "mime_type", "")
                )

        if caption:
            caption = validate_title(caption)
            media_group_id_str = str(message.media_group_id) if message.media_group_id is not None else None
            app.set_caption_name(chat_id, media_group_id_str, caption)
            app.set_caption_entities(
                chat_id, media_group_id_str, message.caption_entities
            )
        else:
            media_group_id_str = str(message.media_group_id) if message.media_group_id is not None else None
            caption = app.get_caption_name(chat_id, media_group_id_str)

        if not file_name and message.photo:
            file_name = f"{message.photo.file_unique_id}"

        gen_file_name = (
            app.get_file_name(message.id, file_name, caption) + file_name_suffix
        )

        file_save_path = app.get_file_save_path(_type, dirname, datetime_dir_name)

        temp_file_name = os.path.join(app.temp_save_path, dirname, gen_file_name)

        file_name = os.path.join(file_save_path, gen_file_name)
    return truncate_filename(file_name), truncate_filename(temp_file_name), file_format


async def add_download_task(
    message: pyrogram.types.Message,
    node: TaskNode,
):
    """Add Download task"""
    if message.empty:
        return False
    node.download_status[message.id] = DownloadStatus.Downloading
    await queue.put((message, node))
    node.total_task += 1
    return True


async def save_msg_to_file(
    app, chat_id: Union[int, str], message: pyrogram.types.Message
):
    """Write message text into file"""
    dirname = validate_title(
        message.chat.title if message.chat and message.chat.title else str(chat_id)
    )
    datetime_dir_name = message.date.strftime(app.date_format) if message.date else "0"

    file_save_path = app.get_file_save_path("msg", dirname, datetime_dir_name)
    file_name = os.path.join(
        app.temp_save_path,
        file_save_path,
        f"{app.get_file_name(message.id, None, None)}.txt",
    )

    os.makedirs(os.path.dirname(file_name), exist_ok=True)

    if _is_exist(file_name):
        return DownloadStatus.SkipDownload, None

    with open(file_name, "w", encoding="utf-8") as f:
        f.write(message.text or "")

    return DownloadStatus.SuccessDownload, file_name


async def download_task(
    client: pyrogram.Client, message: pyrogram.types.Message, node: TaskNode
):
    """Download and Forward media"""

    download_status, file_name = await download_media(
        client, message, app.media_types, app.file_formats, node, app
    )

    if app.enable_download_txt and message.text and not message.media:
        download_status, file_name = await save_msg_to_file(app, node.chat_id, message)

    if not node.bot:
        app.set_download_id(node, message.id, download_status)

    node.download_status[message.id] = download_status
    
    # 如果下载成功，清理download_result中的记录
    if download_status == DownloadStatus.SuccessDownload:
        from module.download_stat import clear_download_result
        clear_download_result(node.chat_id, message.id)

    file_size = os.path.getsize(file_name) if file_name else 0

    # 云盘上传功能已禁用
    # await upload_telegram_chat(
    #     client,
    #     node.upload_user if node.upload_user else client,
    #     app,
    #     node,
    #     message,
    #     download_status,
    #     file_name,
    # )

    # # rclone upload - 已禁用
    # if (
    #     not node.upload_telegram_chat_id
    #     and download_status is DownloadStatus.SuccessDownload
    # ):
    #     ui_file_name = file_name
    #     if app.hide_file_name:
    #         ui_file_name = f"****{os.path.splitext(file_name)[-1]}"
    #     if await app.upload_file(
    #         file_name, update_cloud_upload_stat, (node, message.id, ui_file_name)
    #     ):
    #         node.upload_success_count += 1

    await report_bot_download_status(
        node.bot,
        node,
        download_status,
        file_size,
    )


# pylint: disable = R0915,R0914


@record_download_status
async def download_media(
    client: pyrogram.client.Client,
    message: pyrogram.types.Message,
    media_types: List[str],
    file_formats: dict,
    node: TaskNode,
    app=None,
):
    """
    Download media from Telegram.

    Each of the files to download are retried 3 times with a
    delay of 5 seconds each.

    Parameters
    ----------
    client: pyrogram.client.Client
        Client to interact with Telegram APIs.
    message: pyrogram.types.Message
        Message object retrieved from telegram.
    media_types: list
        List of strings of media types to be downloaded.
        Ex : `["audio", "photo"]`
        Supported formats:
            * audio
            * document
            * photo
            * video
            * voice
    file_formats: dict
        Dictionary containing the list of file_formats
        to be downloaded for `audio`, `document` & `video`
        media types.

    Returns
    -------
    int
        Current message id.
    """

    # pylint: disable = R0912

    file_name: str = ""
    ui_file_name: str = ""
    task_start_time: float = time.time()
    media_size = 0
    _media = None
    message = await fetch_message(client, message)
    try:
        for _type in media_types:
            _media = getattr(message, _type, None)
            if _media is None:
                continue
            file_name, temp_file_name, file_format = await _get_media_meta(
                node.chat_id, message, _media, _type
            )
            media_size = getattr(_media, "file_size", 0)

            ui_file_name = file_name
            if app.hide_file_name:
                ui_file_name = f"****{os.path.splitext(file_name)[-1]}"

            if _can_download(_type, file_formats, file_format):
                if _is_exist(file_name):
                    file_size = os.path.getsize(file_name)
                    if file_size or file_size == media_size:
                        logger.info(
                            f"id={message.id} {ui_file_name} "
                            f"{_t('already download,download skipped')}.\n"
                        )

                        return DownloadStatus.SkipDownload, None
            else:
                return DownloadStatus.SkipDownload, None

            break
    except Exception as e:
        logger.error(
            f"Message[{message.id}]: "
            f"{_t('could not be downloaded due to following exception')}:\n[{e}].",
            exc_info=True,
        )
        return DownloadStatus.FailedDownload, None
    if _media is None:
        return DownloadStatus.SkipDownload, None

    message_id = message.id

    for retry in range(3):
        try:
            temp_download_path = await client.download_media(
                message,
                file_name=temp_file_name,
                progress=update_download_status,
                progress_args=(
                    message_id,
                    ui_file_name,
                    task_start_time,
                    node,
                    client,
                ),
            )

            if temp_download_path and isinstance(temp_download_path, str):
                _check_download_finish(media_size, temp_download_path, ui_file_name)
                await asyncio.sleep(0.5)
                _move_to_download_path(temp_download_path, file_name)
                # TODO: if not exist file size or media
                return DownloadStatus.SuccessDownload, file_name
        except pyrogram.errors.exceptions.bad_request_400.BadRequest:
            logger.warning(
                f"Message[{message.id}]: {_t('file reference expired, refetching')}..."
            )
            await asyncio.sleep(RETRY_TIME_OUT)
            message = await fetch_message(client, message)
            if _check_timeout(retry, message.id):
                # pylint: disable = C0301
                logger.error(
                    f"Message[{message.id}]: "
                    f"{_t('file reference expired for 3 retries, download skipped.')}"
                )
        except pyrogram.errors.exceptions.flood_420.FloodWait as wait_err:
            # FloodWait处理 - 等待指定时间+5秒
            wait_time = wait_err.value
            actual_wait = wait_time + 5  # 额外等待5秒确保安全
            
            logger.warning(
                f"⏱️ FloodWait 错误:\n"
                f"  消息ID: {message.id}\n"
                f"  Telegram要求等待: {wait_time}秒\n"
                f"  实际等待时间: {actual_wait}秒（+5秒缓冲）\n"
                f"  重试次数: {retry + 1}/3"
            )
            
            # 如果等待时间超过1小时，记录警告
            if wait_time > 3600:
                logger.error(f"⚠️ FloodWait时间过长: {wait_time//3600}小时{(wait_time%3600)//60}分钟")
            
            await asyncio.sleep(actual_wait)
            logger.info(f"✅ FloodWait等待完成，继续下载消息[{message.id}]")
            _check_timeout(retry, message.id)
        except TypeError:
            # pylint: disable = C0301
            logger.warning(
                f"{_t('Timeout Error occurred when downloading Message')}[{message.id}], "
                f"{_t('retrying after')} {RETRY_TIME_OUT} {_t('seconds')}"
            )
            await asyncio.sleep(RETRY_TIME_OUT)
            if _check_timeout(retry, message.id):
                logger.error(
                    f"Message[{message.id}]: {_t('Timing out after 3 reties, download skipped.')}"
                )
        except (ConnectionError, OSError, asyncio.TimeoutError) as network_err:
            # 网络相关异常 - 输出详细信息
            error_name = type(network_err).__name__
            logger.error(
                f"🌐 网络异常详情:\n"
                f"  消息ID: {message.id}\n"
                f"  异常类型: {error_name}\n"
                f"  错误信息: {str(network_err)}\n"
                f"  重试次数: {retry + 1}/3\n"
                f"  文件信息: {ui_file_name if 'ui_file_name' in locals() else 'Unknown'}\n"
                f"  媒体大小: {media_size if 'media_size' in locals() else 0} bytes",
                exc_info=True
            )
            
            if app and app.enable_network_monitor:
                logger.info("🔄 网络监控已启用，将自动处理任务暂停和恢复")
            
            await asyncio.sleep(RETRY_TIME_OUT)
            if _check_timeout(retry, message.id):
                logger.error(
                    f"❌ Message[{message.id}]: 网络异常重试3次后失败，跳过下载\n"
                    f"  最终错误: {network_err}"
                )
        except Exception as e:
            # 其他未知异常 - 输出完整堆栈
            logger.error(
                f"❌ 下载失败 - 未知异常:\n"
                f"  消息ID: {message.id}\n"
                f"  异常类型: {type(e).__name__}\n"
                f"  错误信息: {str(e)}\n"
                f"  文件信息: {ui_file_name if 'ui_file_name' in locals() else 'Unknown'}\n"
                f"  聊天ID: {node.chat_id if node else 'Unknown'}\n"
                f"  重试次数: {retry + 1}/3",
                exc_info=True
            )
            break

    return DownloadStatus.FailedDownload, None


def _load_config():
    """Load config"""
    app.load_config()


def _check_config() -> bool:
    """Check config"""
    print_meta(logger)
    try:
        _load_config()
        
        # 创建日志目录
        os.makedirs(app.log_file_path, exist_ok=True)
        os.makedirs("logs", exist_ok=True)  # 为错误日志创建目录
        
        logger.add(
            os.path.join(app.log_file_path, "tdl.log"),
            rotation="10 MB",
            retention="10 days",
            level=app.log_level,
        )
        
        logger.info(f"📝 日志配置完成:")
        logger.info(f"  - 主日志: {os.path.join(app.log_file_path, 'tdl.log')}")
        logger.info(f"  - 错误日志: logs/error_{{time}}.log")
        logger.info(f"  - 日志级别: {app.log_level}")
        
    except Exception as e:
        logger.error(
            f"❌ 配置加载失败:\n"
            f"  错误类型: {type(e).__name__}\n"
            f"  错误信息: {str(e)}\n"
            f"  配置文件: {CONFIG_NAME}",
            exc_info=True
        )
        return False

    return True


async def worker(client: pyrogram.client.Client):
    """Work for download task"""
    while app.is_running:
        try:
            item = await queue.get()
            message = item[0]
            node: TaskNode = item[1]

            if node.is_stop_transmission:
                continue

            # 如果任务暂停，等待恢复
            while node.is_task_paused() and not node.is_stop_transmission:
                logger.info(f"Worker Task {node.task_id}: 任务已暂停，等待恢复...")
                await asyncio.sleep(1)
            
            # 再次检查是否停止
            if node.is_stop_transmission:
                continue

            if node.client:
                await download_task(node.client, message, node)
            else:
                await download_task(client, message, node)
        except (ConnectionError, OSError) as e:
            # 网络连接错误，将任务重新放回队列
            logger.error(
                f"⚠️ Worker 网络错误:\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  错误信息: {str(e)}\n"
                f"  任务ID: {node.task_id if 'node' in locals() else 'Unknown'}\n"
                f"  消息ID: {message.id if 'message' in locals() else 'Unknown'}",
                exc_info=True
            )
            if 'item' in locals():
                await queue.put(item)
                logger.info(f"✅ 任务已重新加入队列，5秒后重试")
            await asyncio.sleep(5)  # 等待5秒后继续
        except Exception as e:
            logger.error(
                f"❌ Worker 未知错误:\n"
                f"  错误类型: {type(e).__name__}\n"
                f"  错误信息: {str(e)}\n"
                f"  任务ID: {node.task_id if 'node' in locals() else 'Unknown'}\n"
                f"  消息ID: {message.id if 'message' in locals() else 'Unknown'}",
                exc_info=True
            )


async def download_chat_task(
    client: pyrogram.Client,
    chat_download_config: ChatDownloadConfig,
    node: TaskNode,
):
    """Download all task"""
    messages_iter = get_chat_history_v2(
        client,
        node.chat_id,
        limit=node.limit,
        max_id=node.end_offset_id,
        offset_id=chat_download_config.last_read_message_id,
        reverse=True,
    )

    chat_download_config.node = node

    if chat_download_config.ids_to_retry:
        logger.info(f"{_t('Downloading files failed during last run')}...")
        skipped_messages: list = await client.get_messages(  # type: ignore
            chat_id=node.chat_id, message_ids=chat_download_config.ids_to_retry
        )

        for message in skipped_messages:
            await add_download_task(message, node)

    async for message in messages_iter:  # type: ignore
        # 检查任务是否停止或暂停
        if node.is_stop_transmission:
            break
            
        # 如果任务暂停，等待恢复
        while node.is_task_paused() and not node.is_stop_transmission:
            logger.info(f"Task {node.task_id}: 任务已暂停，等待恢复...")
            await asyncio.sleep(1)
        
        meta_data = MetaData()

        caption = message.caption
        if caption:
            caption = validate_title(caption)
            media_group_id_str = str(message.media_group_id) if message.media_group_id is not None else None
            app.set_caption_name(node.chat_id, media_group_id_str, caption)
            app.set_caption_entities(
                node.chat_id, media_group_id_str, message.caption_entities
            )
        else:
            media_group_id_str = str(message.media_group_id) if message.media_group_id is not None else None
            caption = app.get_caption_name(node.chat_id, media_group_id_str)
        set_meta_data(meta_data, message, caption)

        if app.need_skip_message(chat_download_config, message.id):
            continue

        if app.exec_filter(chat_download_config, meta_data):
            await add_download_task(message, node)
        else:
            node.download_status[message.id] = DownloadStatus.SkipDownload
            if message.media_group_id:
                # 云盘上传功能已禁用
                # await upload_telegram_chat(
                #     client,
                #     node.upload_user,
                #     app,
                #     node,
                #     message,
                #     DownloadStatus.SkipDownload,
                # )
                pass

    chat_download_config.need_check = True
    chat_download_config.total_task = node.total_task
    node.is_running = True
    node.start_time = time.time()  # 记录任务开始时间


async def download_all_chat(client: pyrogram.Client):
    """Download All chat"""
    # 导入bot模块（如果使用bot模式）
    from module.bot import _bot
    
    task_id = 1  # 从1开始分配任务ID
    
    for key, value in app.chat_download_config.items():
        if not value.enable:
            continue
            
        value.node = TaskNode(chat_id=key)
        value.node.task_id = task_id
        value.node.is_running = True  # 设置任务为运行中状态
        
        # 如果bot模式启用，添加到bot的任务管理中
        if _bot and hasattr(_bot, 'task_node'):
            _bot.task_node[task_id] = value.node
            logger.info(f"添加任务到Bot管理: ID={task_id}, Chat={key}")
        
        task_id += 1
        
        try:
            await download_chat_task(client, value, value.node)
        except Exception as e:
            logger.warning(f"Download {key} error: {e}")
        finally:
            value.need_check = True
            # 任务完成后从bot中移除
            if _bot and hasattr(_bot, 'task_node') and value.node.task_id in _bot.task_node:
                _bot.task_node.pop(value.node.task_id, None)


async def run_until_all_task_finish():
    """Normal download"""
    while True:
        finish: bool = True
        for _, value in app.chat_download_config.items():
            if not value.need_check or value.total_task != value.finish_task:
                finish = False

        if (not app.bot_token and finish) or app.restart_program:
            break

        await asyncio.sleep(1)


def _exec_loop():
    """Exec loop"""

    app.loop.run_until_complete(run_until_all_task_finish())


async def start_server(client: pyrogram.Client):
    """
    Start the server using the provided client with retry logic.
    """
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            await client.start()
            logger.info("成功连接到 Telegram 服务器")
            return
        except pyrogram.errors.SecurityCheckMismatch as e:
            logger.error(f"❌ 会话安全检查失败: {e}")
            logger.info("🔄 尝试重新创建会话...")
            
            # 删除损坏的会话文件
            session_file = f"sessions/{client.name}.session"
            if os.path.exists(session_file):
                os.remove(session_file)
                logger.info(f"✅ 已删除损坏的会话文件: {session_file}")
            
            # 下次循环会重新创建会话
            if attempt < max_retries - 1:
                logger.info(f"等待 {retry_delay} 秒后重试...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("无法修复会话问题")
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"连接失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                logger.info(f"等待 {retry_delay} 秒后重试...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"无法连接到 Telegram 服务器: {e}")
                raise


async def stop_server(client: pyrogram.Client):
    """
    Stop the server using the provided client.
    """
    await client.stop()


def main():
    """Main function of the downloader."""
    tasks = []
    client = HookClient(
        "media_downloader",
        api_id=app.api_id,
        api_hash=app.api_hash,
        proxy=app.proxy,
        workdir=app.session_file_path,
        start_timeout=app.start_timeout,
    )
    try:
        app.pre_run()
        init_web(app)

        set_max_concurrent_transmissions(client, app.max_concurrent_transmissions)

        app.loop.run_until_complete(start_server(client))
        logger.success(_t("Successfully started (Press Ctrl+C to stop)"))

        # 如果有bot_token，先启动bot
        if app.bot_token:
            app.loop.run_until_complete(
                start_download_bot(app, client, add_download_task, download_chat_task)
            )
        
        # 然后再启动下载任务
        app.loop.create_task(download_all_chat(client))
        for _ in range(app.max_download_task):
            task = app.loop.create_task(worker(client))
            tasks.append(task)
        
        # 启动网络监控
        app.loop.run_until_complete(app.start_network_monitor())
        
        _exec_loop()
    except KeyboardInterrupt:
        logger.info("⌨️ 用户中断 (Ctrl+C)")
    except pyrogram.errors.exceptions.bad_request_400.BadRequest as e:
        logger.error(
            f"❌ Telegram API 错误 (400 Bad Request):\n"
            f"  错误信息: {str(e)}\n"
            f"  可能原因: 消息已删除、权限不足或请求参数错误",
            exc_info=True
        )
    except pyrogram.errors.exceptions.unauthorized_401.Unauthorized as e:
        logger.error(
            f"❌ 认证失败 (401 Unauthorized):\n"
            f"  错误信息: {str(e)}\n"
            f"  解决方案: 请检查 API ID/Hash 或重新登录",
            exc_info=True
        )
    except pyrogram.errors.exceptions.forbidden_403.Forbidden as e:
        logger.error(
            f"❌ 访问被拒绝 (403 Forbidden):\n"
            f"  错误信息: {str(e)}\n"
            f"  可能原因: 账号被限制或没有访问权限",
            exc_info=True
        )
    except Exception as e:
        logger.error(
            f"❌ 程序异常退出:\n"
            f"  异常类型: {type(e).__name__}\n"
            f"  错误信息: {str(e)}\n"
            f"  建议: 请将此错误信息提交到 GitHub Issues",
            exc_info=True
        )
    finally:
        app.is_running = False
        # 停止网络监控
        app.loop.run_until_complete(app.stop_network_monitor())
        if app.bot_token:
            app.loop.run_until_complete(stop_download_bot())
        app.loop.run_until_complete(stop_server(client))
        for task in tasks:
            task.cancel()
        logger.info(_t("Stopped!"))
        # check_for_updates(app.proxy)
        logger.info(f"{_t('update config')}......")
        app.update_config()
        logger.success(
            f"{_t('Updated last read message_id to config file')},"
            f"{_t('total download')} {app.total_download_task}, "
            f"{_t('total upload file')} "
            f"{app.cloud_drive_config.total_upload_success_file_count}"
        )


if __name__ == "__main__":
    if _check_config():
        main()
