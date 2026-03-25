#!/usr/bin/env python3
"""
更新 Cloudflare DNS 记录的 IP 地址
支持从本地配置文件读取 API Token、域名、记录名、IP、代理等敏感信息
"""

import os
import sys
import json
import argparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT = 30

def create_session(retries=DEFAULT_RETRIES, proxies=None):
    """创建带重试和代理的 requests Session"""
    session = requests.Session()
    # 重试策略
    retry_strategy = Retry(
        total=retries,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "PUT"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # 设置代理
    if proxies:
        session.proxies.update(proxies)
    return session

def load_config(config_file):
    """从 JSON 文件加载配置"""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        print(f"警告：配置文件 {config_file} 不存在，将仅使用命令行参数。", file=sys.stderr)
        return {}
    except json.JSONDecodeError as e:
        print(f"错误：配置文件 {config_file} 格式错误: {e}", file=sys.stderr)
        sys.exit(1)

def get_zone_id(session, api_token, domain):
    """获取域名的 Zone ID"""
    url = f"https://api.cloudflare.com/client/v4/zones?name={domain}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "User-Agent": "Cloudflare-DNS-Updater/1.0"
    }
    try:
        response = session.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if not data['success']:
            raise Exception(f"API 错误: {data['errors']}")
        zones = data['result']
        if not zones:
            raise Exception(f"未找到域名 {domain} 对应的 Zone")
        return zones[0]['id']
    except requests.exceptions.RequestException as e:
        raise Exception(f"获取 Zone ID 失败: {e}")

def get_dns_record_id(session, api_token, zone_id, record_name, record_type):
    """通过名称和类型获取 DNS 记录 ID"""
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    params = {"name": record_name, "type": record_type}
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "User-Agent": "Cloudflare-DNS-Updater/1.0"
    }
    try:
        response = session.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if not data['success']:
            raise Exception(f"API 错误: {data['errors']}")
        records = data['result']
        if not records:
            raise Exception(f"未找到 {record_type} 记录: {record_name}")
        return records[0]['id']
    except requests.exceptions.RequestException as e:
        raise Exception(f"获取 DNS 记录 ID 失败: {e}")

def update_dns_record(session, api_token, zone_id, record_id, record_name,
                      record_type, new_ip, ttl=1, proxied=False):
    """更新 DNS 记录的 IP 地址"""
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "User-Agent": "Cloudflare-DNS-Updater/1.0"
    }
    data = {
        "type": record_type,
        "name": record_name,
        "content": new_ip,
        "ttl": ttl,
        "proxied": proxied
    }
    try:
        response = session.put(url, headers=headers, json=data, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        result = response.json()
        if not result['success']:
            raise Exception(f"API 错误: {result['errors']}")
        return result
    except requests.exceptions.RequestException as e:
        raise Exception(f"更新 DNS 记录失败: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="更新 Cloudflare DNS 记录的 IP 地址（支持本地配置文件及代理）"
    )
    parser.add_argument("--config", default="cf_config.json",
                        help="本地配置文件路径（JSON 格式），默认 cf_config.json")
    parser.add_argument("--domain", help="主域名，如 example.com")
    parser.add_argument("--name", help="完整记录名，如 sub.example.com")
    parser.add_argument("--type", default="A", help="记录类型 (A, AAAA 等，默认 A)")
    parser.add_argument("--ip", help="新的 IP 地址")
    parser.add_argument("--ttl", type=int, default=1,
                        help="TTL 秒数，1 表示自动 (默认 1)")
    parser.add_argument("--proxied", action="store_true",
                        help="启用 Cloudflare 代理（橙色云）")
    parser.add_argument("--api-token",
                        help="Cloudflare API Token（优先级高于配置文件）")
    parser.add_argument("--proxy", help="代理地址，如 http://127.0.0.1:7890（优先级高于配置文件）")
    args = parser.parse_args()

    # 加载本地配置文件
    config = load_config(args.config)

    # 合并配置：命令行参数 > 配置文件 > 默认值
    domain = args.domain or config.get("domain")
    name = args.name or config.get("name")
    record_type = args.type or config.get("type", "A")
    new_ip = args.ip or config.get("ip")
    ttl = args.ttl if args.ttl != 1 else config.get("ttl", 1)
    proxied = args.proxied or config.get("proxied", False)
    api_token = args.api_token or config.get("api_token")
    # 代理配置：支持字符串格式（如 "http://127.0.0.1:7890"）或字典格式（如 {"http": "...", "https": "..."}）
    proxy_conf = args.proxy or config.get("proxy")
    proxies = None
    if proxy_conf:
        if isinstance(proxy_conf, dict):
            proxies = proxy_conf
        elif isinstance(proxy_conf, str):
            # 如果代理是字符串，同时用于 http 和 https
            proxies = {"http": proxy_conf, "https": proxy_conf}
        else:
            print("警告：代理配置格式不正确，应为字符串或字典，已忽略", file=sys.stderr)

    # 检查必需参数
    if not domain:
        print("错误：缺少域名（--domain 或配置文件中的 domain）", file=sys.stderr)
        sys.exit(1)
    if not name:
        print("错误：缺少记录名（--name 或配置文件中的 name）", file=sys.stderr)
        sys.exit(1)
    if not new_ip:
        print("错误：缺少 IP 地址（--ip 或配置文件中的 ip）", file=sys.stderr)
        sys.exit(1)
    if not api_token:
        print("错误：未提供 API Token（--api-token 或配置文件中的 api_token）", file=sys.stderr)
        sys.exit(1)

    # 创建带代理和重试的 Session
    session = create_session(proxies=proxies)

    try:
        print("正在获取 Zone ID...")
        zone_id = get_zone_id(session, api_token, domain)

        print("正在获取 DNS 记录 ID...")
        record_id = get_dns_record_id(session, api_token, zone_id, name, record_type)

        print(f"正在更新 {name} 的 IP 到 {new_ip}...")
        update_dns_record(session, api_token, zone_id, record_id, name,
                          record_type, new_ip, ttl, proxied)

        print(f"成功！记录 {name} 已更新为 {new_ip}")
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()