#!/usr/bin/env python3
"""
查询 Cloudflare DNS 记录的当前 IP 地址（支持多条同名同类型记录）
使用 cf_config.json 配置文件（或指定其他 JSON 文件）
"""

import sys
import json
import argparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT = 30

def create_session(retries=DEFAULT_RETRIES):
    """创建带重试的 requests Session"""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def load_config(config_file):
    """从 JSON 文件加载配置"""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误：配置文件 {config_file} 不存在", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"错误：配置文件 {config_file} 格式错误: {e}", file=sys.stderr)
        sys.exit(1)

def get_zone_id(session, api_token, domain):
    """获取域名的 Zone ID"""
    url = f"https://api.cloudflare.com/client/v4/zones?name={domain}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "User-Agent": "Cloudflare-DNS-Query/1.0"
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

def query_dns_records(session, api_token, zone_id, record_name, record_type):
    """
    查询 DNS 记录，返回所有匹配的记录列表
    Cloudflare API 默认最多返回 100 条，若需更多可自行添加分页
    """
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    params = {
        "name": record_name,
        "type": record_type
    }
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "User-Agent": "Cloudflare-DNS-Query/1.0"
    }
    try:
        response = session.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if not data['success']:
            raise Exception(f"API 错误: {data['errors']}")
        return data['result']  # 返回所有匹配的记录列表
    except requests.exceptions.RequestException as e:
        raise Exception(f"查询 DNS 记录失败: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="查询 Cloudflare DNS 记录的当前 IP 地址（支持多条同名同类型记录）"
    )
    parser.add_argument("--config", default="cf_config.json",
                        help="本地配置文件路径（JSON 格式），默认 cf_config.json")
    parser.add_argument("--domain", help="主域名，覆盖配置文件中的值")
    parser.add_argument("--name", help="完整记录名，覆盖配置文件中的值")
    parser.add_argument("--type", help="记录类型 (A, AAAA 等)，覆盖配置文件中的值")
    parser.add_argument("--api-token", help="Cloudflare API Token，覆盖配置文件中的值")
    args = parser.parse_args()

    # 加载配置文件
    config = load_config(args.config)

    # 合并配置：命令行 > 配置文件
    api_token = args.api_token or config.get("api_token")
    domain = args.domain or config.get("domain")
    name = args.name or config.get("name")
    record_type = args.type or config.get("type", "A")

    # 检查必需参数
    if not api_token:
        print("错误：未提供 API Token（配置文件或 --api-token）", file=sys.stderr)
        sys.exit(1)
    if not domain:
        print("错误：未提供域名（配置文件或 --domain）", file=sys.stderr)
        sys.exit(1)
    if not name:
        print("错误：未提供记录名（配置文件或 --name）", file=sys.stderr)
        sys.exit(1)

    session = create_session()

    try:
        print(f"正在查询域名 {domain} 的 Zone ID...")
        zone_id = get_zone_id(session, api_token, domain)

        print(f"正在查询 {record_type} 记录 {name}...")
        records = query_dns_records(session, api_token, zone_id, name, record_type)

        if not records:
            print(f"未找到 {record_type} 记录: {name}")
            sys.exit(0)

        print(f"\n共找到 {len(records)} 条匹配的记录：\n")
        # 逐条输出详细信息
        for idx, rec in enumerate(records, 1):
            print(f"记录 #{idx}")
            print(f"  类型: {rec['type']}")
            print(f"  名称: {rec['name']}")
            print(f"  内容: {rec['content']}")
            print(f"  TTL : {rec['ttl']} (1=自动)")
            print(f"  代理: {'是' if rec['proxied'] else '否'}")
            print(f"  ID  : {rec['id']}")
            if idx < len(records):
                print()  # 记录间空行

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()