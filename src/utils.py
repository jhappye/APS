"""工具函数"""
from datetime import datetime, timedelta, date
import random


def today_str(offset: int = 0) -> str:
    """返回当前日期时间字符串"""
    return (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%dT%H:%M:%S")


def date_str(offset: int = 0) -> str:
    """返回当前日期字符串"""
    return (date.today() + timedelta(days=offset)).strftime("%Y-%m-%dT00:00:00")


def rand_order_code() -> str:
    """生成随机订单号"""
    return f"SO{random.randint(20250001, 20259999)}"
