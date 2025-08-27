"""Application module"""

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, List, Optional, Union

from loguru import logger
from ruamel import yaml

from module.cloud_drive import CloudDrive, CloudDriveConfig
from module.filter import Filter
from module.language import Language, set_language
from utils.format import replace_date_time, validate_title
from utils.meta_data import MetaData

_yaml = yaml.YAML()
# pylint: disable = R0902


class DownloadStatus(Enum):
    """Download status"""

    SkipDownload = 1
    SuccessDownload = 2
    FailedDownload = 3
    Downloading = 4


class ForwardStatus(Enum):
    """Forward status"""

    SkipForward = 1
    SuccessForward = 2
    FailedForward = 3
    Forwarding = 4
    StopForward = 5
    CacheForward = 6


class UploadStatus(Enum):
    """Upload status"""

    SkipUpload = 1
    SuccessUpload = 2
    FailedUpload = 3
    Uploading = 4


class TaskType(Enum):
    """Task Type"""

    Download = 1
    Forward = 2
    ListenForward = 3


class QueryHandler(Enum):
    """Query handler"""

    StopDownload = 1
    StopForward = 2
    StopListenForward = 3


@dataclass
class UploadProgressStat:
    """Upload task"""

    file_name: str
    total_size: int
    upload_size: int
    start_time: float
    last_stat_time: float
    upload_speed: float


@dataclass
class CloudDriveUploadStat:
    """Cloud drive upload task"""

    file_name: str
    transferred: str
    total: str
    percentage: str
    speed: str
    eta: str


class QueryHandlerStr:
    """Query handler"""

    _strMap = {
        QueryHandler.StopDownload.value: "stop_download",
        QueryHandler.StopForward.value: "stop_forward",
        QueryHandler.StopListenForward.value: "stop_listen_forward",
    }

    @staticmethod
    def get_str(value):
        """
        Get the string value associated with the given value.

        Parameters:
            value (any): The value for which to retrieve the string value.

        Returns:
            str: The string value associated with the given value.
        """
        return QueryHandlerStr._strMap[value]


class TaskNode:
    """Task node"""

    # pylint: disable = R0913
    def __init__(
        self,
        chat_id: Union[int, str],
        from_user_id: Union[int, str] = None,
        reply_message_id: int = 0,
        replay_message: str = None,
        upload_telegram_chat_id: Union[int, str] = None,
        has_protected_content: bool = False,
        download_filter: str = None,
        limit: int = 0,
        start_offset_id: int = 0,
        end_offset_id: int = 0,
        bot=None,
        task_type: TaskType = TaskType.Download,
        task_id: int = 0,
        topic_id: int = 0,
    ):
        self.chat_id = chat_id
        self.from_user_id = from_user_id
        self.upload_telegram_chat_id = upload_telegram_chat_id
        self.reply_message_id = reply_message_id
        self.reply_message = replay_message
        self.has_protected_content = has_protected_content
        self.download_filter = download_filter
        self.limit = limit
        self.start_offset_id = start_offset_id
        self.end_offset_id = end_offset_id
        self.bot = bot
        self.task_id = task_id
        self.task_type = task_type
        self.total_task = 0
        self.total_download_task = 0
        self.failed_download_task = 0
        self.success_download_task = 0
        self.skip_download_task = 0
        self.last_reply_time = time.time()
        self.last_edit_msg: str = ""
        self.total_download_byte = 0
        self.forward_msg_detail_str: str = ""
        self.upload_user = None
        self.total_forward_task: int = 0
        self.success_forward_task: int = 0
        self.failed_forward_task: int = 0
        self.skip_forward_task: int = 0
        self.is_running: bool = False
        self.client = None
        self.upload_success_count: int = 0
        self.is_stop_transmission = False
        self.is_paused = False  # 暂停状态
        self.is_network_paused = False  # 网络断线暂停状态
        self.media_group_ids: dict = {}
        self.download_status: dict = {}
        self.upload_status: dict = {}
        self.upload_stat_dict: dict = {}
        self.topic_id = topic_id
        self.reply_to_message = None
        self.cloud_drive_upload_stat_dict: dict = {}

    def skip_msg_id(self, msg_id: int):
        """Skip if message id out of range"""
        if self.start_offset_id and msg_id < self.start_offset_id:
            return True

        if self.end_offset_id and msg_id > self.end_offset_id:
            return True

        return False

    def is_finish(self):
        """If is finish"""
        return self.is_stop_transmission or (
            self.is_running
            and self.task_type != TaskType.ListenForward
            and self.total_task == self.total_download_task
        )

    def stop_transmission(self):
        """Stop task"""
        self.is_stop_transmission = True

    def pause_task(self):
        """暂停任务"""
        self.is_paused = True

    def resume_task(self):
        """恢复任务"""
        self.is_paused = False

    def is_task_paused(self):
        """检查任务是否暂停"""
        return self.is_paused or self.is_network_paused
    
    def pause_for_network(self):
        """因网络问题暂停任务"""
        self.is_network_paused = True
    
    def resume_from_network_pause(self):
        """从网络暂停中恢复任务"""
        self.is_network_paused = False
    
    def is_network_paused_only(self):
        """检查是否仅因网络问题暂停"""
        return self.is_network_paused and not self.is_paused

    def stat(self, status: DownloadStatus):
        """
        Updates the download status of the task.

        Args:
            status (DownloadStatus): The status of the download task.

        Returns:
            None
        """
        self.total_download_task += 1
        if status is DownloadStatus.SuccessDownload:
            self.success_download_task += 1
            # 保存最后下载的文件信息（用于显示）
            self.last_download_file = getattr(self, 'current_download_file', None)
            self.last_file_size = getattr(self, 'current_file_size', 0)
            # 清除当前文件下载信息
            self.current_download_file = None
            self.current_file_size = 0
            self.current_downloaded = 0
            self.download_speed = 0
        elif status is DownloadStatus.SkipDownload:
            self.skip_download_task += 1
        else:
            self.failed_download_task += 1

    def stat_forward(self, status: ForwardStatus, count: int = 1):
        """Stat upload"""
        self.total_forward_task += count
        if status is ForwardStatus.SuccessForward:
            self.success_forward_task += count
        elif status is ForwardStatus.SkipForward:
            self.skip_forward_task += count
        else:
            self.failed_forward_task += count

    def has_significant_progress(self):
        """检查是否有显著的进度变化（避免频繁更新）"""
        if not hasattr(self, 'last_reported_progress'):
            self.last_reported_progress = 0
            return True
        
        # 计算当前进度百分比
        if self.total_task > 0:
            current_progress = (self.success_download_count + self.failed_download_count + 
                              self.skip_download_count) / self.total_task
        else:
            current_progress = 0
        
        # 如果进度变化超过5%或任务完成，则认为有显著变化
        progress_change = abs(current_progress - self.last_reported_progress)
        if progress_change > 0.05 or self.is_finish():
            self.last_reported_progress = current_progress
            return True
        
        # 检查时间间隔（至少60秒更新一次）
        cur_time = time.time()
        if cur_time - self.last_reply_time > 60:
            self.last_reported_progress = current_progress
            return True
        
        return False
    
    def can_reply(self):
        """
        Checks if the bot can reply to a message
            based on the time elapsed since the last reply.

        Returns:
            True if the time elapsed since
                the last reply is greater than the minimum interval, False otherwise.
        """
        cur_time = time.time()
        
        # 检查是否在FloodWait期间
        if hasattr(self, 'floodwait_until') and cur_time < self.floodwait_until:
            return False
        
        # 使用指数退避的最小间隔（如果设置了）
        if hasattr(self, 'min_update_interval'):
            min_interval = self.min_update_interval
        else:
            # 动态调整更新间隔，避免FloodWait
            min_interval = 5.0  # 默认5秒
            
            # 根据任务规模调整间隔
            if self.total_download_task > 1000:
                min_interval = 30.0  # 超大任务30秒
            elif self.total_download_task > 500:
                min_interval = 20.0  # 大任务20秒
            elif self.total_download_task > 100:
                min_interval = 10.0  # 中等任务10秒
            elif self.total_download_task > 50:
                min_interval = 7.0  # 小任务7秒
            
            # 如果最近有FloodWait，增加间隔
            if hasattr(self, 'floodwait_until'):
                min_interval = max(min_interval, 30.0)  # FloodWait后至少30秒
        
        if cur_time - self.last_reply_time > min_interval:
            self.last_reply_time = cur_time
            
            # 成功回复后重置FloodWait计数
            if hasattr(self, 'floodwait_count'):
                self.floodwait_count = 0
                if hasattr(self, 'min_update_interval'):
                    del self.min_update_interval  # 恢复正常间隔
            
            return True

        return False


class LimitCall:
    """Limit call"""

    def __init__(
        self,
        max_limit_call_times: int = 0,
        limit_call_times: int = 0,
        last_call_time: float = 0,
    ):
        """
        Initializes the object with the given parameters.

        Args:
            max_limit_call_times (int): The maximum limit of call times allowed.
            limit_call_times (int): The current limit of call times.
            last_call_time (int): The time of the last call.

        Returns:
            None
        """
        self.max_limit_call_times = max_limit_call_times
        self.limit_call_times = limit_call_times
        self.last_call_time = last_call_time

    async def wait(self, node: TaskNode):
        """
        Wait for a certain period of time before continuing execution.

        This function does not take any parameters.

        This function does not return anything.
        """
        while True:
            now = time.time()
            time_span = now - self.last_call_time
            if node.is_stop_transmission:
                break

            if time_span > 60:
                self.limit_call_times = 0
                self.last_call_time = now

            if self.limit_call_times + 1 <= self.max_limit_call_times:
                self.limit_call_times += 1
                break

            # logger.debug("Waiting for 10 seconds...")
            await asyncio.sleep(1)


class ChatDownloadConfig:
    """Chat Message Download Status"""

    def __init__(self):
        self.ids_to_retry_dict: dict = {}

        # need storage
        self.download_filter: str = None
        self.ids_to_retry: list = []
        self.last_read_message_id = 0
        self.total_task: int = 0
        self.finish_task: int = 0
        self.need_check: bool = False
        self.upload_telegram_chat_id: Union[int, str] = None
        self.node: TaskNode = TaskNode(0)


def get_config(config, key, default=None, val_type=str, verbose=True):
    """
    Retrieves a configuration value from the given `config` dictionary
    based on the specified `key`.

    Args:
        config (dict): A dictionary containing the configuration values.
        key (str): The key of the configuration value to retrieve.
        default (Any, optional): The default value to be returned
            if the `key` is not found.
        val_type (type, optional): The data type of the configuration value.
        verbose (bool, optional): A flag indicating whether to print
            a warning message if the `key` is not found.

    Returns:
        The configuration value associated with the specified `key`,
         converted to the specified `type`. If the `key` is not found,
         the `default` value is returned.
    """
    val = config.get(key, default)
    if isinstance(val, val_type):
        return val

    if verbose:
        logger.warning(f"{key} is not {val_type.__name__}")

    return default


class Application:
    """Application load config and update config."""

    def __init__(
        self,
        config_file: str,
        app_data_file: str,
        application_name: str = "UndefineApp",
    ):
        """
        Init and update telegram media downloader config

        Parameters
        ----------
        config_file: str
            Config file name

        app_data_file: str
            App data file

        application_name: str
            Application Name

        """
        self.config_file: str = config_file
        self.app_data_file: str = app_data_file
        self.application_name: str = application_name
        self.download_filter = Filter()
        self.is_running = True

        self.total_download_task = 0

        self.chat_download_config: dict = {}

        self.save_path = os.path.join(os.path.abspath("."), "downloads")
        self.temp_save_path = os.path.join(os.path.abspath("."), "temp")
        self.api_id: str = ""
        self.api_hash: str = ""
        self.bot_token: str = ""
        self._chat_id: str = ""
        self.media_types: List[str] = []
        self.file_formats: dict = {}
        self.proxy: dict = {}
        self.restart_program = False
        self.config: dict = {}
        self.app_data: dict = {}
        self.file_path_prefix: List[str] = ["chat_title", "media_datetime"]
        self.file_name_prefix: List[str] = ["message_id", "file_name"]
        self.file_name_prefix_split: str = " - "
        self.log_file_path = os.path.join(os.path.abspath("."), "log")
        self.session_file_path = os.path.join(os.path.abspath("."), "sessions")
        self.cloud_drive_config = CloudDriveConfig()
        self.hide_file_name = False
        self.caption_name_dict: dict = {}
        self.caption_entities_dict: dict = {}
        self.max_concurrent_transmissions: int = 1
        self.web_host: str = "0.0.0.0"
        self.web_port: int = 5000
        self.max_download_task: int = 5
        self.language = Language.EN
        self.after_upload_telegram_delete: bool = True
        self.web_login_secret: str = ""
        self.debug_web: bool = False
        self.log_level: str = "INFO"
        self.start_timeout: int = 60
        self.allowed_user_ids: yaml.comments.CommentedSeq = yaml.comments.CommentedSeq(
            []
        )
        self.date_format: str = "%Y_%m"
        self.drop_no_audio_video: bool = False
        self.enable_download_txt: bool = False

        # FloodWait 配置
        self.download_floodwait_buffer: int = 2  # 下载FloodWait额外等待时间(秒)
        self.upload_floodwait_multiplier: float = 2.0  # 上传FloodWait倍数
        self.upload_floodwait_buffer: int = 5  # 上传FloodWait额外等待时间(秒)

        # 网络监控配置
        self.enable_network_monitor: bool = True  # 是否启用网络监控
        self.network_check_interval: int = 30  # 网络检查间隔(秒)
        self.network_check_host: str = "1.1.1.1"  # 网络检查主机
        self.network_timeout: int = 5  # 网络检查超时时间(秒)
        self.network_is_available: bool = True  # 当前网络状态
        self.network_paused_tasks: set = set()  # 因网络问题暂停的任务集合
        self.network_monitor_task = None  # 网络监控任务
        self.bot_instance = None  # Bot实例引用

        self.forward_limit_call = LimitCall(max_limit_call_times=33)

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.executor = ThreadPoolExecutor(
            min(32, (os.cpu_count() or 0) + 4), thread_name_prefix="multi_task"
        )

    # pylint: disable = R0915
    def assign_config(self, _config: dict) -> bool:
        """assign config from str.

        Parameters
        ----------
        _config: dict
            application config dict

        Returns
        -------
        bool
        """
        # pylint: disable = R0912
        # TODO: judge the storage if enough,and provide more path
        if _config.get("save_path") is not None:
            self.save_path = _config["save_path"]

        self.api_id = _config["api_id"]
        self.api_hash = _config["api_hash"]
        self.bot_token = _config.get("bot_token", "")

        self.media_types = _config["media_types"]
        self.file_formats = _config["file_formats"]

        self.hide_file_name = _config.get("hide_file_name", False)

        # option
        if _config.get("proxy"):
            self.proxy = _config["proxy"]
        if _config.get("restart_program"):
            self.restart_program = _config["restart_program"]
        if _config.get("file_path_prefix"):
            self.file_path_prefix = _config["file_path_prefix"]
        if _config.get("file_name_prefix"):
            self.file_name_prefix = _config["file_name_prefix"]

        if _config.get("upload_drive"):
            upload_drive_config = _config["upload_drive"]
            if upload_drive_config.get("enable_upload_file"):
                self.cloud_drive_config.enable_upload_file = upload_drive_config[
                    "enable_upload_file"
                ]

            if upload_drive_config.get("rclone_path"):
                self.cloud_drive_config.rclone_path = upload_drive_config["rclone_path"]

            if upload_drive_config.get("remote_dir"):
                self.cloud_drive_config.remote_dir = upload_drive_config["remote_dir"]

            if upload_drive_config.get("before_upload_file_zip"):
                self.cloud_drive_config.before_upload_file_zip = upload_drive_config[
                    "before_upload_file_zip"
                ]

            if upload_drive_config.get("after_upload_file_delete"):
                self.cloud_drive_config.after_upload_file_delete = upload_drive_config[
                    "after_upload_file_delete"
                ]

            if upload_drive_config.get("upload_adapter"):
                self.cloud_drive_config.upload_adapter = upload_drive_config[
                    "upload_adapter"
                ]

        self.file_name_prefix_split = _config.get(
            "file_name_prefix_split", self.file_name_prefix_split
        )
        self.web_host = _config.get("web_host", self.web_host)
        self.web_port = _config.get("web_port", self.web_port)

        # TODO: add check if expression exist syntax error

        self.max_download_task = _config.get(
            "max_download_task", self.max_download_task
        )

        self.max_concurrent_transmissions = self.max_download_task * 5

        self.max_concurrent_transmissions = _config.get(
            "max_concurrent_transmissions", self.max_concurrent_transmissions
        )

        language = _config.get("language", "EN")

        try:
            self.language = Language[language.upper()]
        except KeyError:
            pass

        self.after_upload_telegram_delete = _config.get(
            "after_upload_telegram_delete", self.after_upload_telegram_delete
        )

        self.web_login_secret = str(
            _config.get("web_login_secret", self.web_login_secret)
        )
        self.debug_web = _config.get("debug_web", self.debug_web)
        self.log_level = _config.get("log_level", self.log_level)

        self.start_timeout = get_config(
            _config, "start_timeout", self.start_timeout, int
        )

        self.allowed_user_ids = get_config(
            _config,
            "allowed_user_ids",
            self.allowed_user_ids,
            yaml.comments.CommentedSeq,
        )

        self.date_format = get_config(
            _config,
            "date_format",
            self.date_format,
            str,
        )

        self.drop_no_audio_video = get_config(
            _config, "drop_no_audio_video", self.drop_no_audio_video, bool
        )

        self.enable_download_txt = get_config(
            _config, "enable_download_txt", self.enable_download_txt, bool
        )

        try:
            date = datetime(2023, 10, 31)
            date.strftime(self.date_format)
        except Exception as e:
            logger.warning(f"config date format error: {e}")
            self.date_format = "%Y_%m"

        forward_limit = _config.get("forward_limit", None)
        if forward_limit:
            try:
                forward_limit = int(forward_limit)
                self.forward_limit_call.max_limit_call_times = forward_limit
            except ValueError:
                pass

        if _config.get("chat"):
            chat = _config["chat"]
            for item in chat:
                if "chat_id" in item:
                    self.chat_download_config[item["chat_id"]] = ChatDownloadConfig()
                    self.chat_download_config[
                        item["chat_id"]
                    ].last_read_message_id = item.get("last_read_message_id", 0)
                    self.chat_download_config[
                        item["chat_id"]
                    ].download_filter = item.get("download_filter", "")
                    self.chat_download_config[
                        item["chat_id"]
                    ].upload_telegram_chat_id = item.get(
                        "upload_telegram_chat_id", None
                    )
        elif _config.get("chat_id"):
            # Compatible with lower versions
            self._chat_id = _config["chat_id"]

            self.chat_download_config[self._chat_id] = ChatDownloadConfig()

            if _config.get("ids_to_retry"):
                self.chat_download_config[self._chat_id].ids_to_retry = _config[
                    "ids_to_retry"
                ]
                for it in self.chat_download_config[self._chat_id].ids_to_retry:
                    self.chat_download_config[self._chat_id].ids_to_retry_dict[
                        it
                    ] = True

            self.chat_download_config[self._chat_id].last_read_message_id = _config[
                "last_read_message_id"
            ]
            download_filter_dict = _config.get("download_filter", None)

            self.config["chat"] = [
                {
                    "chat_id": self._chat_id,
                    "last_read_message_id": self.chat_download_config[
                        self._chat_id
                    ].last_read_message_id,
                }
            ]

            if download_filter_dict and self._chat_id in download_filter_dict:
                self.chat_download_config[
                    self._chat_id
                ].download_filter = download_filter_dict[self._chat_id]
                self.config["chat"][0]["download_filter"] = download_filter_dict[
                    self._chat_id
                ]

        # pylint: disable = R1733
        for key, value in self.chat_download_config.items():
            self.chat_download_config[key].download_filter = replace_date_time(
                value.download_filter
            )

        return True

    def assign_app_data(self, app_data: dict) -> bool:
        """Assign config from str.

        Parameters
        ----------
        app_data: dict
            application data dict

        Returns
        -------
        bool
        """
        if app_data.get("ids_to_retry"):
            if self._chat_id:
                self.chat_download_config[self._chat_id].ids_to_retry = app_data[
                    "ids_to_retry"
                ]
                for it in self.chat_download_config[self._chat_id].ids_to_retry:
                    self.chat_download_config[self._chat_id].ids_to_retry_dict[
                        it
                    ] = True
                self.app_data.pop("ids_to_retry")
        else:
            if app_data.get("chat"):
                chats = app_data["chat"]
                for chat in chats:
                    if (
                        "chat_id" in chat
                        and chat["chat_id"] in self.chat_download_config
                    ):
                        chat_id = chat["chat_id"]
                        self.chat_download_config[chat_id].ids_to_retry = chat.get(
                            "ids_to_retry", []
                        )
                        for it in self.chat_download_config[chat_id].ids_to_retry:
                            self.chat_download_config[chat_id].ids_to_retry_dict[
                                it
                            ] = True
        return True

    async def upload_file(
        self,
        local_file_path: str,
        progress_callback: Callable = None,
        progress_args: tuple = (),
    ) -> bool:
        """Upload file"""

        if not self.cloud_drive_config.enable_upload_file:
            logger.debug(f"⛔ 云盘上传未启用: {local_file_path}")
            return False

        ret: bool = False
        try:
            logger.info(f"🌩️ 开始上传文件到云盘: {local_file_path}")
            
            if self.cloud_drive_config.upload_adapter == "rclone":
                ret = await CloudDrive.rclone_upload_file(
                    self.cloud_drive_config,
                    self.save_path,
                    local_file_path,
                    progress_callback,
                    progress_args,
                )
            elif self.cloud_drive_config.upload_adapter == "aligo":
                ret = await self.loop.run_in_executor(
                    self.executor,
                    CloudDrive.aligo_upload_file(
                        self.cloud_drive_config, self.save_path, local_file_path
                    ),
                )
            else:
                logger.error(f"❌ 未知的上传适配器: {self.cloud_drive_config.upload_adapter}")
                
            if ret:
                logger.success(f"✅ 文件上传成功: {local_file_path}")
            else:
                logger.warning(f"⚠️ 文件上传失败: {local_file_path}")
                
        except Exception as e:
            logger.error(
                f"❌ 云盘上传异常:\n"
                f"  文件: {local_file_path}\n"
                f"  适配器: {self.cloud_drive_config.upload_adapter}\n"
                f"  错误: {str(e)}",
                exc_info=True
            )
            ret = False

        return ret

    def get_file_save_path(
        self, media_type: str, chat_title: str, media_datetime: str
    ) -> str:
        """Get file save path prefix.

        Parameters
        ----------
        media_type: str
            see config.yaml media_types

        chat_title: str
            see channel or group title

        media_datetime: str
            media datetime

        Returns
        -------
        str
            file save path prefix
        """

        res: str = self.save_path
        for prefix in self.file_path_prefix:
            if prefix == "chat_title":
                res = os.path.join(res, chat_title)
            elif prefix == "media_datetime":
                res = os.path.join(res, media_datetime)
            elif prefix == "media_type":
                res = os.path.join(res, media_type)
        return res

    def get_file_name(
        self, message_id: int, file_name: Optional[str], caption: Optional[str]
    ) -> str:
        """Get file save path prefix.

        Parameters
        ----------
        message_id: int
            Message id

        file_name: Optional[str]
            File name

        caption: Optional[str]
            Message caption

        Returns
        -------
        str
            File name
        """

        res: str = ""
        for prefix in self.file_name_prefix:
            if prefix == "message_id":
                if res != "":
                    res += self.file_name_prefix_split
                res += f"{message_id}"
            elif prefix == "file_name" and file_name:
                if res != "":
                    res += self.file_name_prefix_split
                res += f"{file_name}"
            elif prefix == "caption" and caption:
                if res != "":
                    res += self.file_name_prefix_split
                res += f"{caption}"
        if res == "":
            res = f"{message_id}"

        return validate_title(res)

    def need_skip_message(
        self, download_config: ChatDownloadConfig, message_id: int
    ) -> bool:
        """if need skip download message.

        Parameters
        ----------
        chat_id: str
            Config.yaml defined

        message_id: int
            Readily to download message id
        Returns
        -------
        bool
        """
        if message_id in download_config.ids_to_retry_dict:
            return True

        return False

    def exec_filter(self, download_config: ChatDownloadConfig, meta_data: MetaData):
        """
        Executes the filter on the given download configuration.

        Args:
            download_config (ChatDownloadConfig): The download configuration object.
            meta_data (MetaData): The meta data object.

        Returns:
            bool: The result of executing the filter.
        """
        if download_config.download_filter:
            try:
                self.download_filter.set_meta_data(meta_data)
                result = self.download_filter.exec(download_config.download_filter)
                
                if not result:
                    logger.debug(
                        f"🔍 消息被过滤器跳过:\n"
                        f"  消息ID: {meta_data.message_id}\n"
                        f"  过滤器: {download_config.download_filter}"
                    )
                return result
            except Exception as e:
                logger.error(
                    f"❌ 执行过滤器失败:\n"
                    f"  过滤器: {download_config.download_filter}\n"
                    f"  错误: {str(e)}\n"
                    f"  消息ID: {meta_data.message_id}",
                    exc_info=True
                )
                # 过滤器错误时默认通过
                return True

        return True

    # pylint: disable = R0912
    def update_config(self, immediate: bool = True):
        """update config

        Parameters
        ----------
        immediate: bool
            If update config immediate,default True
        """
        # TODO: fix this not exist chat
        if not self.app_data.get("chat") and self.config.get("chat"):
            self.app_data["chat"] = [
                {"chat_id": i} for i in range(0, len(self.config["chat"]))
            ]
        idx = 0
        # pylint: disable = R1733
        for key, value in self.chat_download_config.items():
            # pylint: disable = W0201
            unfinished_ids = set(value.ids_to_retry)

            for it in value.ids_to_retry:
                if  value.node.download_status.get(
                    it, DownloadStatus.FailedDownload
                ) in [DownloadStatus.SuccessDownload, DownloadStatus.SkipDownload]:
                    unfinished_ids.remove(it)

            for _idx, _value in value.node.download_status.items():
                if DownloadStatus.SuccessDownload != _value and DownloadStatus.SkipDownload != _value:
                    unfinished_ids.add(_idx)

            self.chat_download_config[key].ids_to_retry = list(unfinished_ids)

            if idx >= len(self.app_data["chat"]):
                self.app_data["chat"].append({})

            if value.finish_task:
                self.config["chat"][idx]["last_read_message_id"] = (
                    value.last_read_message_id + 1
                )

            self.app_data["chat"][idx]["chat_id"] = key
            self.app_data["chat"][idx]["ids_to_retry"] = value.ids_to_retry
            idx += 1

        self.config["save_path"] = self.save_path
        self.config["file_path_prefix"] = self.file_path_prefix

        if self.config.get("ids_to_retry"):
            self.config.pop("ids_to_retry")

        if self.config.get("chat_id"):
            self.config.pop("chat_id")

        if self.config.get("download_filter"):
            self.config.pop("download_filter")

        if self.config.get("last_read_message_id"):
            self.config.pop("last_read_message_id")

        self.config["language"] = self.language.name
        # for it in self.downloaded_ids:
        #    self.already_download_ids_set.add(it)

        # self.app_data["already_download_ids"] = list(self.already_download_ids_set)

        if immediate:
            with open(self.config_file, "w", encoding="utf-8") as yaml_file:
                _yaml.dump(self.config, yaml_file)

        if immediate:
            with open(self.app_data_file, "w", encoding="utf-8") as yaml_file:
                _yaml.dump(self.app_data, yaml_file)

    def set_language(self, language: Language):
        """Set Language"""
        self.language = language
        set_language(language)

    def load_config(self):
        """Load user config"""
        with open(
            os.path.join(os.path.abspath("."), self.config_file), encoding="utf-8"
        ) as f:
            config = _yaml.load(f.read())
            if config:
                self.config = config
                self.assign_config(self.config)

        if os.path.exists(os.path.join(os.path.abspath("."), self.app_data_file)):
            with open(
                os.path.join(os.path.abspath("."), self.app_data_file),
                encoding="utf-8",
            ) as f:
                app_data = _yaml.load(f.read())
                if app_data:
                    self.app_data = app_data
                    self.assign_app_data(self.app_data)

    def pre_run(self):
        """before run application do"""
        self.cloud_drive_config.pre_run()
        if not os.path.exists(self.session_file_path):
            os.makedirs(self.session_file_path)
        set_language(self.language)

    def set_caption_name(
        self, chat_id: Union[int, str], media_group_id: Optional[str], caption: str
    ):
        """set caption name map

        Parameters
        ----------
        chat_id: str
            Unique identifier for this chat.

        media_group_id: Optional[str]
            The unique identifier of a media message group this message belongs to.

        caption: str
            Caption for the audio, document, photo, video or voice, 0-1024 characters.
        """
        if not media_group_id:
            return

        if chat_id in self.caption_name_dict:
            self.caption_name_dict[chat_id][media_group_id] = caption
        else:
            self.caption_name_dict[chat_id] = {media_group_id: caption}

    def get_caption_name(
        self, chat_id: Union[int, str], media_group_id: Optional[str]
    ) -> Optional[str]:
        """set caption name map
                media_group_id: Optional[str]
            The unique identifier of a media message group this message belongs to.

        caption: str
            Caption for the audio, document, photo, video or voice, 0-1024 characters.
        """

        if (
            not media_group_id
            or chat_id not in self.caption_name_dict
            or media_group_id not in self.caption_name_dict[chat_id]
        ):
            return None

        return str(self.caption_name_dict[chat_id][media_group_id])

    def set_caption_entities(
        self, chat_id: Union[int, str], media_group_id: Optional[str], caption_entities
    ):
        """
        set caption entities map
        """
        if not media_group_id:
            return

        if chat_id in self.caption_entities_dict:
            self.caption_entities_dict[chat_id][media_group_id] = caption_entities
        else:
            self.caption_entities_dict[chat_id] = {media_group_id: caption_entities}

    def get_caption_entities(
        self, chat_id: Union[int, str], media_group_id: Optional[str]
    ):
        """
        get caption entities map
        """
        if (
            not media_group_id
            or chat_id not in self.caption_entities_dict
            or media_group_id not in self.caption_entities_dict[chat_id]
        ):
            return None

        return self.caption_entities_dict[chat_id][media_group_id]

    def set_download_id(
        self, node: TaskNode, message_id: int, download_status: DownloadStatus
    ):
        """Set Download status"""
        if download_status is DownloadStatus.SuccessDownload:
            self.total_download_task += 1

        if node.chat_id not in self.chat_download_config:
            return

        self.chat_download_config[node.chat_id].finish_task += 1

        self.chat_download_config[node.chat_id].last_read_message_id = max(
            self.chat_download_config[node.chat_id].last_read_message_id, message_id
        )
    
    def set_bot_instance(self, bot):
        """设置bot实例引用"""
        self.bot_instance = bot
    
    # FloodWait 配置管理方法
    def get_floodwait_settings(self) -> dict:
        """获取当前FloodWait设置"""
        return {
            "download_buffer": self.download_floodwait_buffer,
            "upload_multiplier": self.upload_floodwait_multiplier, 
            "upload_buffer": self.upload_floodwait_buffer
        }
    
    def set_download_floodwait_buffer(self, buffer_seconds: int) -> bool:
        """设置下载FloodWait缓冲时间"""
        if buffer_seconds < 0 or buffer_seconds > 300:
            return False
        self.download_floodwait_buffer = buffer_seconds
        return True
    
    def set_upload_floodwait_multiplier(self, multiplier: float) -> bool:
        """设置上传FloodWait倍数"""
        if multiplier < 1.0 or multiplier > 10.0:
            return False
        self.upload_floodwait_multiplier = multiplier
        return True
        
    def set_upload_floodwait_buffer(self, buffer_seconds: int) -> bool:
        """设置上传FloodWait缓冲时间"""  
        if buffer_seconds < 0 or buffer_seconds > 300:
            return False
        self.upload_floodwait_buffer = buffer_seconds
        return True
    
    def auto_adjust_download_floodwait(self, telegram_wait_time: int) -> int:
        """
        根据Telegram要求的等待时间自动调整下载FloodWait设置
        
        Args:
            telegram_wait_time: Telegram返回的等待时间(秒)
            
        Returns:
            实际等待时间(秒)
        """
        # 自动增加1秒缓冲时间
        old_buffer = self.download_floodwait_buffer
        new_buffer = min(old_buffer + 1, 60)  # 最大不超过60秒
        self.download_floodwait_buffer = new_buffer
        
        # 计算实际等待时间
        actual_wait_time = telegram_wait_time + new_buffer
        
        from loguru import logger
        logger.info(
            "FloodWait自动调整 - 下载缓冲: {}s → {}s, 等待: {}s + {}s = {}s",
            old_buffer, new_buffer, telegram_wait_time, new_buffer, actual_wait_time
        )
        
        return actual_wait_time
    
    def auto_adjust_upload_floodwait(self, telegram_wait_time: int) -> int:
        """
        根据Telegram要求的等待时间自动调整上传FloodWait设置
        
        Args:
            telegram_wait_time: Telegram返回的等待时间(秒)
            
        Returns:
            实际等待时间(秒)  
        """
        # 自动增加1秒缓冲时间
        old_buffer = self.upload_floodwait_buffer
        new_buffer = min(old_buffer + 1, 120)  # 最大不超过120秒
        self.upload_floodwait_buffer = new_buffer
        
        # 计算实际等待时间 
        actual_wait_time = int(telegram_wait_time * self.upload_floodwait_multiplier) + new_buffer
        
        from loguru import logger
        logger.info(
            "FloodWait自动调整 - 上传缓冲: {}s → {}s, 等待: ({}s × {}) + {}s = {}s",
            old_buffer, new_buffer, telegram_wait_time, self.upload_floodwait_multiplier, 
            new_buffer, actual_wait_time
        )
        
        return actual_wait_time

    async def check_network_connectivity(self) -> bool:
        """
        检查网络连通性
        
        Returns:
            bool: 网络是否可用
        """
        try:
            # 使用ping命令检查网络连通性
            # macOS 使用毫秒作为 -W 参数
            process = await asyncio.create_subprocess_exec(
                'ping', '-c', '1', '-W', str(self.network_timeout * 1000), 
                self.network_check_host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 设置超时
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=self.network_timeout + 1
                )
                return process.returncode == 0
            except asyncio.TimeoutError:
                logger.debug(f"ping {self.network_check_host} 超时")
                return False
                
        except FileNotFoundError:
            # ping 命令不存在，尝试使用 socket 连接
            logger.debug("ping 命令不可用，尝试 socket 连接")
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.network_timeout)
                result = sock.connect_ex((self.network_check_host, 443))
                sock.close()
                return result == 0
            except Exception as e:
                logger.debug(f"socket 连接检查失败: {e}")
                return False
        except Exception as e:
            logger.debug(f"网络检查异常: {e}")
            return False
    
    async def start_network_monitor(self):
        """启动网络监控任务"""
        if not self.enable_network_monitor:
            return
            
        logger.info(f"启动网络监控 - 检查间隔: {self.network_check_interval}秒, 目标主机: {self.network_check_host}")
        
        self.network_monitor_task = asyncio.create_task(self._network_monitor_loop())
    
    async def stop_network_monitor(self):
        """停止网络监控任务"""
        if self.network_monitor_task:
            self.network_monitor_task.cancel()
            try:
                await self.network_monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("网络监控已停止")
    
    async def _network_monitor_loop(self):
        """网络监控循环"""
        while self.is_running:
            try:
                # 检查网络连通性
                is_available = await self.check_network_connectivity()
                
                if is_available != self.network_is_available:
                    if is_available:
                        logger.success(
                            f"🟢 网络已恢复\n"
                            f"  检查主机: {self.network_check_host}\n"
                            f"  恢复时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        await self._resume_network_paused_tasks()
                    else:
                        logger.warning(
                            f"🔴 检测到网络断线\n"
                            f"  检查主机: {self.network_check_host}\n"
                            f"  断线时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"  当前任务数: {len(self.chat_download_config)}"
                        )
                        await self._pause_tasks_for_network()
                    
                    self.network_is_available = is_available
                
                await asyncio.sleep(self.network_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"网络监控循环异常: {e}")
                await asyncio.sleep(self.network_check_interval)
    
    async def _pause_tasks_for_network(self):
        """因网络问题暂停所有任务"""
        try:
            # 暂停所有chat_download_config中的任务
            paused_count = 0
            for chat_id, config in self.chat_download_config.items():
                if hasattr(config, 'node') and config.node and config.node.is_running:
                    if not config.node.is_task_paused():
                        config.node.pause_for_network()
                        self.network_paused_tasks.add(chat_id)
                        paused_count += 1
                        logger.info(f"因网络断线暂停任务: {chat_id}")
            
            # 如果有bot实例，暂停bot管理的任务
            if self.bot_instance and hasattr(self.bot_instance, 'task_node'):
                for task_id, task_node in self.bot_instance.task_node.items():
                    if task_node.is_running and not task_node.is_task_paused():
                        task_node.pause_for_network()
                        self.network_paused_tasks.add(f"bot_{task_id}")
                        paused_count += 1
                        logger.info(f"因网络断线暂停Bot任务: {task_id}")
                
            if paused_count > 0:
                logger.warning(f"🔴 网络断线，已暂停 {paused_count} 个下载任务")
        except Exception as e:
            logger.error(f"网络暂停任务失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def _resume_network_paused_tasks(self):
        """恢复因网络问题暂停的任务"""
        try:
            resumed_count = 0
            
            # 恢复所有暂停的任务
            for task_key in self.network_paused_tasks.copy():
                if isinstance(task_key, str) and task_key.startswith("bot_"):
                    # Bot管理的任务
                    if self.bot_instance and hasattr(self.bot_instance, 'task_node'):
                        task_id = int(task_key[4:])  # 去掉"bot_"前缀
                        task_node = self.bot_instance.task_node.get(task_id)
                        if task_node and task_node.is_network_paused:
                            task_node.resume_from_network_pause()
                            resumed_count += 1
                            logger.info(f"网络恢复，自动恢复Bot任务: {task_id}")
                else:
                    # 普通下载任务
                    config = self.chat_download_config.get(task_key)
                    if config and hasattr(config, 'node') and config.node:
                        if config.node.is_network_paused:
                            config.node.resume_from_network_pause()
                            resumed_count += 1
                            logger.info(f"网络恢复，自动恢复任务: {task_key}")
            
            self.network_paused_tasks.clear()
            
            if resumed_count > 0:
                logger.success(f"🟢 网络已恢复，已恢复 {resumed_count} 个下载任务")
        except Exception as e:
            logger.error(f"网络恢复任务失败: {e}")
            import traceback
            traceback.print_exc()
    
    def is_network_available(self) -> bool:
        """获取当前网络状态"""
        return self.network_is_available
    
    def get_network_paused_tasks(self) -> set:
        """获取因网络问题暂停的任务集合"""
        return self.network_paused_tasks.copy()
