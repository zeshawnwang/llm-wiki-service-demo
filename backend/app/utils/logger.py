"""
统一日志工具模块
提供项目中所有模块使用的统一日志接口
"""
import logging
from typing import Optional


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取统一配置的logger
    
    Args:
        name: logger名称，通常使用 __name__
    
    Returns:
        配置好的logger实例
    """
    logger = logging.getLogger(name or __name__)
    
    # 如果已经配置过，直接返回
    if logger.handlers:
        return logger
    
    # 设置日志级别
    logger.setLevel(logging.INFO)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 设置日志格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(console_handler)
    logger.propagate = False
    
    return logger


# 创建全局logger实例
logger = get_logger("llm-wiki-service")
