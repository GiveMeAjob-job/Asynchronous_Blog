import re
from typing import Optional
import unicodedata


def generate_slug(text: str, max_length: int = 100) -> str:
    """
    生成 URL 友好的 slug

    Args:
        text: 原始文本
        max_length: 最大长度

    Returns:
        slug 字符串
    """
    # 转换为 NFD 格式并移除重音符号
    text = unicodedata.normalize('NFD', text)
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')

    # 转换为小写
    text = text.lower()

    # 替换空格和特殊字符为连字符
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)

    # 移除首尾的连字符
    text = text.strip('-')

    # 限制长度
    if len(text) > max_length:
        text = text[:max_length].rsplit('-', 1)[0]

    return text


def generate_unique_slug(
        text: str,
        existing_slugs: list,
        max_length: int = 100
) -> str:
    """
    生成唯一的 slug

    Args:
        text: 原始文本
        existing_slugs: 已存在的 slug 列表
        max_length: 最大长度

    Returns:
        唯一的 slug 字符串
    """
    base_slug = generate_slug(text, max_length - 10)  # 预留位置给数字后缀

    if base_slug not in existing_slugs:
        return base_slug

    # 如果存在重复，添加数字后缀
    counter = 1
    while True:
        new_slug = f"{base_slug}-{counter}"
        if new_slug not in existing_slugs:
            return new_slug
        counter += 1
