#!/usr/bin/env python3
"""日志分析工具 - 用于分析和诊断下载问题"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint


console = Console()


class LogAnalyzer:
    """日志分析器"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self.errors = []
        self.warnings = []
        self.floodwaits = []
        self.downloads = []
        
    def parse_log_line(self, line: str) -> Dict:
        """解析单行日志"""
        # 匹配日志格式: 时间 | 级别 | 位置 | 消息
        pattern = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{3})?) \| (\w+) \| ([^|]+) \| (.+)"
        match = re.match(pattern, line)
        
        if match:
            return {
                'timestamp': match.group(1),
                'level': match.group(2),
                'location': match.group(3),
                'message': match.group(4)
            }
        return None
    
    def analyze_errors(self, file_path: str):
        """分析错误日志"""
        if not os.path.exists(file_path):
            return
            
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                parsed = self.parse_log_line(line)
                if parsed and parsed['level'] == 'ERROR':
                    self.errors.append(parsed)
    
    def analyze_warnings(self, file_path: str):
        """分析警告日志"""
        if not os.path.exists(file_path):
            return
            
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                parsed = self.parse_log_line(line)
                if parsed and parsed['level'] == 'WARNING':
                    self.warnings.append(parsed)
    
    def analyze_floodwait(self, file_path: str):
        """分析FloodWait日志"""
        if not os.path.exists(file_path):
            return
            
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if 'FloodWait' in line:
                    # 提取等待时间
                    wait_match = re.search(r'(\d+)\s*秒', line)
                    if wait_match:
                        wait_time = int(wait_match.group(1))
                        self.floodwaits.append({
                            'line': line.strip(),
                            'wait_time': wait_time,
                            'timestamp': line[:19] if len(line) > 19 else 'unknown'
                        })
    
    def analyze_downloads(self, file_path: str):
        """分析下载日志"""
        if not os.path.exists(file_path):
            return
            
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '成功下载' in line or 'SUCCESS' in line:
                    self.downloads.append({
                        'line': line.strip(),
                        'timestamp': line[:19] if len(line) > 19 else 'unknown',
                        'status': 'success'
                    })
                elif '下载失败' in line or 'FAILED' in line:
                    self.downloads.append({
                        'line': line.strip(),
                        'timestamp': line[:19] if len(line) > 19 else 'unknown',
                        'status': 'failed'
                    })
    
    def get_error_summary(self) -> Dict:
        """获取错误摘要"""
        error_types = Counter()
        error_locations = Counter()
        
        for error in self.errors:
            # 简化错误消息以分组
            msg = error['message']
            if 'FloodWait' in msg:
                error_types['FloodWait'] += 1
            elif 'Timeout' in msg:
                error_types['Timeout'] += 1
            elif 'Network' in msg or 'network' in msg:
                error_types['Network'] += 1
            elif 'file reference' in msg.lower():
                error_types['FileReference'] += 1
            else:
                error_types['Other'] += 1
            
            # 统计错误位置
            location = error['location'].split(':')[0]
            error_locations[location] += 1
        
        return {
            'total': len(self.errors),
            'types': dict(error_types),
            'locations': dict(error_locations.most_common(10))
        }
    
    def get_floodwait_summary(self) -> Dict:
        """获取FloodWait摘要"""
        if not self.floodwaits:
            return {'total': 0, 'avg_wait': 0, 'max_wait': 0}
        
        wait_times = [fw['wait_time'] for fw in self.floodwaits]
        return {
            'total': len(self.floodwaits),
            'avg_wait': sum(wait_times) // len(wait_times),
            'max_wait': max(wait_times),
            'min_wait': min(wait_times),
            'total_wait_hours': sum(wait_times) / 3600
        }
    
    def get_download_summary(self) -> Dict:
        """获取下载摘要"""
        success = sum(1 for d in self.downloads if d['status'] == 'success')
        failed = sum(1 for d in self.downloads if d['status'] == 'failed')
        
        return {
            'total': len(self.downloads),
            'success': success,
            'failed': failed,
            'success_rate': f"{(success/len(self.downloads)*100):.1f}%" if self.downloads else "0%"
        }
    
    def analyze_all(self):
        """分析所有日志文件"""
        # 获取最近的日志文件
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 分析错误日志
        error_file = os.path.join(self.log_dir, f"error_{today}.log")
        self.analyze_errors(error_file)
        
        # 分析警告日志
        warning_file = os.path.join(self.log_dir, f"warning_{today}.log")
        self.analyze_warnings(warning_file)
        
        # 分析完整日志
        full_file = os.path.join(self.log_dir, f"full_{today}.log")
        if os.path.exists(full_file):
            self.analyze_downloads(full_file)
        
        # 分析FloodWait日志
        month = datetime.now().strftime("%Y-%m")
        floodwait_file = os.path.join(self.log_dir, f"floodwait_{month}.log")
        self.analyze_floodwait(floodwait_file)


def print_summary_table(analyzer: LogAnalyzer):
    """打印摘要表格"""
    # 错误摘要
    error_summary = analyzer.get_error_summary()
    
    error_table = Table(title="📊 错误分析摘要", show_header=True)
    error_table.add_column("类型", style="cyan")
    error_table.add_column("数量", justify="right", style="red")
    
    error_table.add_row("总错误数", str(error_summary['total']))
    for error_type, count in error_summary['types'].items():
        error_table.add_row(f"  {error_type}", str(count))
    
    console.print(error_table)
    
    # FloodWait摘要
    fw_summary = analyzer.get_floodwait_summary()
    
    if fw_summary['total'] > 0:
        fw_table = Table(title="⏱️ FloodWait分析", show_header=True)
        fw_table.add_column("指标", style="cyan")
        fw_table.add_column("值", justify="right", style="yellow")
        
        fw_table.add_row("总次数", str(fw_summary['total']))
        fw_table.add_row("平均等待", f"{fw_summary['avg_wait']}秒")
        fw_table.add_row("最长等待", f"{fw_summary['max_wait']}秒")
        fw_table.add_row("最短等待", f"{fw_summary['min_wait']}秒")
        fw_table.add_row("总等待时间", f"{fw_summary['total_wait_hours']:.1f}小时")
        
        console.print(fw_table)
    
    # 下载摘要
    dl_summary = analyzer.get_download_summary()
    
    if dl_summary['total'] > 0:
        dl_table = Table(title="📥 下载统计", show_header=True)
        dl_table.add_column("指标", style="cyan")
        dl_table.add_column("值", justify="right", style="green")
        
        dl_table.add_row("总下载数", str(dl_summary['total']))
        dl_table.add_row("成功", str(dl_summary['success']))
        dl_table.add_row("失败", str(dl_summary['failed']))
        dl_table.add_row("成功率", dl_summary['success_rate'])
        
        console.print(dl_table)


def print_recent_errors(analyzer: LogAnalyzer, count: int = 10):
    """打印最近的错误"""
    if not analyzer.errors:
        console.print("[yellow]没有发现错误日志[/yellow]")
        return
    
    console.print(f"\n[red]最近 {min(count, len(analyzer.errors))} 条错误:[/red]")
    
    for error in analyzer.errors[-count:]:
        console.print(f"[dim]{error['timestamp']}[/dim] | [red]{error['message'][:100]}[/red]")


def print_floodwait_pattern(analyzer: LogAnalyzer):
    """分析FloodWait模式"""
    if not analyzer.floodwaits:
        return
    
    console.print("\n[yellow]FloodWait时间分布:[/yellow]")
    
    # 按时间段分组
    time_buckets = defaultdict(int)
    for fw in analyzer.floodwaits:
        wait = fw['wait_time']
        if wait < 60:
            time_buckets['<1分钟'] += 1
        elif wait < 300:
            time_buckets['1-5分钟'] += 1
        elif wait < 3600:
            time_buckets['5分钟-1小时'] += 1
        elif wait < 18000:
            time_buckets['1-5小时'] += 1
        else:
            time_buckets['>5小时'] += 1
    
    for bucket, count in sorted(time_buckets.items()):
        bar = '█' * min(count, 50)
        console.print(f"  {bucket:15} [{count:3}] {bar}")


@click.command()
@click.option('--log-dir', default='logs', help='日志目录路径')
@click.option('--errors', '-e', is_flag=True, help='显示最近的错误')
@click.option('--summary', '-s', is_flag=True, help='显示摘要信息')
@click.option('--floodwait', '-f', is_flag=True, help='分析FloodWait模式')
@click.option('--all', '-a', is_flag=True, help='显示所有分析')
def main(log_dir: str, errors: bool, summary: bool, floodwait: bool, all: bool):
    """Telegram Media Downloader 日志分析工具"""
    
    console.print(Panel.fit("📊 Telegram Media Downloader 日志分析", style="bold blue"))
    
    analyzer = LogAnalyzer(log_dir)
    analyzer.analyze_all()
    
    # 如果没有指定选项，默认显示摘要
    if not any([errors, summary, floodwait, all]):
        summary = True
    
    if all:
        errors = summary = floodwait = True
    
    if summary:
        print_summary_table(analyzer)
    
    if errors:
        print_recent_errors(analyzer)
    
    if floodwait:
        print_floodwait_pattern(analyzer)
    
    # 提示信息
    console.print("\n[dim]提示: 使用 --help 查看更多选项[/dim]")
    console.print("[dim]日志文件位置: logs/[/dim]")


if __name__ == '__main__':
    main()