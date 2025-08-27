"""Download Stat"""
import asyncio
import time
from enum import Enum

from pyrogram import Client

from module.app import TaskNode


class DownloadState(Enum):
    """Download state"""

    Downloading = 1
    StopDownload = 2


_download_result: dict = {}
_total_download_speed: int = 0
_total_download_size: int = 0
_last_download_time: float = time.time()
_download_state: DownloadState = DownloadState.Downloading


def get_download_result() -> dict:
    """get global download result"""
    return _download_result


def get_total_download_speed() -> int:
    """get total download speed"""
    return _total_download_speed


def get_download_state() -> DownloadState:
    """get download state"""
    return _download_state


# pylint: disable = W0603
def set_download_state(state: DownloadState):
    """set download state"""
    global _download_state
    _download_state = state


def clear_download_result(chat_id: int, message_id: int):
    """清理已完成的下载记录"""
    global _download_result
    if chat_id in _download_result and message_id in _download_result[chat_id]:
        del _download_result[chat_id][message_id]
        # 如果该chat没有其他下载任务，删除整个chat记录
        if not _download_result[chat_id]:
            del _download_result[chat_id]


async def update_download_status(
    down_byte: int,
    total_size: int,
    message_id: int,
    file_name: str,
    start_time: float,
    node: TaskNode,
    client: Client,
):
    """update_download_status"""
    cur_time = time.time()
    # pylint: disable = W0603
    global _total_download_speed
    global _total_download_size
    global _last_download_time

    # 更新当前文件下载信息到TaskNode
    import os
    # 只保存文件名，不要完整路径
    simple_filename = os.path.basename(file_name) if file_name else file_name
    node.current_download_file = simple_filename
    node.current_file_size = total_size
    node.current_downloaded = down_byte
    
    # 调试日志（每10秒记录一次）
    if not hasattr(node, '_last_progress_log_time'):
        node._last_progress_log_time = 0
    
    if cur_time - node._last_progress_log_time > 10:
        from loguru import logger
        progress_percent = (down_byte / total_size * 100) if total_size > 0 else 0
        logger.debug(f"📊 下载进度 - 文件: {file_name}, 进度: {progress_percent:.1f}%, 大小: {down_byte}/{total_size}")
        node._last_progress_log_time = cur_time
    
    if node.is_stop_transmission:
        client.stop_transmission()

    chat_id = node.chat_id

    while get_download_state() == DownloadState.StopDownload:
        if node.is_stop_transmission:
            client.stop_transmission()
        await asyncio.sleep(1)

    if not _download_result.get(chat_id):
        _download_result[chat_id] = {}

    if _download_result[chat_id].get(message_id):
        last_download_byte = _download_result[chat_id][message_id]["down_byte"]
        last_time = _download_result[chat_id][message_id]["end_time"]
        download_speed = _download_result[chat_id][message_id]["download_speed"]
        each_second_total_download = _download_result[chat_id][message_id][
            "each_second_total_download"
        ]
        end_time = _download_result[chat_id][message_id]["end_time"]

        _total_download_size += down_byte - last_download_byte
        each_second_total_download += down_byte - last_download_byte

        if cur_time - last_time >= 1.0:
            download_speed = int(each_second_total_download / (cur_time - last_time))
            end_time = cur_time
            each_second_total_download = 0

        download_speed = max(download_speed, 0)

        # 更新TaskNode的下载速度
        node.download_speed = download_speed
        
        _download_result[chat_id][message_id]["down_byte"] = down_byte
        _download_result[chat_id][message_id]["end_time"] = end_time
        _download_result[chat_id][message_id]["download_speed"] = download_speed
        _download_result[chat_id][message_id]["file_name"] = simple_filename  # 更新文件名为简单名称
        _download_result[chat_id][message_id][
            "each_second_total_download"
        ] = each_second_total_download
    else:
        each_second_total_download = down_byte
        _download_result[chat_id][message_id] = {
            "down_byte": down_byte,
            "total_size": total_size,
            "file_name": simple_filename,
            "start_time": start_time,
            "end_time": cur_time,
            "download_speed": down_byte / (cur_time - start_time),
            "each_second_total_download": each_second_total_download,
            "task_id": node.task_id,
        }
        _total_download_size += down_byte

    if cur_time - _last_download_time >= 1.0:
        # update speed
        _total_download_speed = int(
            _total_download_size / (cur_time - _last_download_time)
        )
        _total_download_speed = max(_total_download_speed, 0)
        _total_download_size = 0
        _last_download_time = cur_time
