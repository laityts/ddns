import base64
import sys
import requests
from urllib.parse import urlparse, parse_qs

def decode_base64(data: str) -> str:
    """尝试解码 Base64 字符串，自动处理缺失的填充符"""
    try:
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        return base64.b64decode(data).decode('utf-8')
    except Exception:
        return None

def parse_trojan(node: str):
    """解析 trojan:// 节点，返回包含 host 参数（如果有）的字典"""
    if not node.startswith('trojan://'):
        return None
    parsed = urlparse(node)
    query = parse_qs(parsed.query)
    host_values = query.get('host', [])
    if host_values:
        return {'host': host_values[0]}
    return None

def parse_vless(node: str):
    """解析 vless:// 节点，返回包含 host 参数（如果有）的字典"""
    if not node.startswith('vless://'):
        return None
    parsed = urlparse(node)
    query = parse_qs(parsed.query)
    host_values = query.get('host', [])
    if host_values:
        return {'host': host_values[0]}
    return None

def get_host_from_node(node: str):
    """从节点字符串中提取 host 参数值（仅支持 vless 和 trojan）"""
    node = node.strip()
    if not node:
        return None

    if node.startswith('vless://'):
        config = parse_vless(node)
        if config and config.get('host'):
            return config['host']
    elif node.startswith('trojan://'):
        config = parse_trojan(node)
        if config and config.get('host'):
            return config['host']
    return None

def fetch_subscription(url: str):
    """获取订阅内容，返回节点列表（字符串列表）"""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        content = resp.text.strip()
        # 尝试解码 Base64（订阅通常为 Base64）
        decoded = decode_base64(content)
        if decoded and any(line.startswith(('vless://', 'trojan://')) for line in decoded.splitlines()):
            content = decoded
        # 按行分割，过滤空行
        lines = [line for line in content.splitlines() if line.strip()]
        return lines
    except Exception as e:
        print(f"获取订阅失败 ({url}): {e}")
        return []

def process_subscription(url: str):
    """处理单个订阅，打印找到的 host 值"""
    print(f"\n===== 订阅地址: {url} =====")
    nodes = fetch_subscription(url)
    if not nodes:
        print("未获取到任何节点")
        return

    print(f"共获取到 {len(nodes)} 个节点，正在查找 vless/trojan 节点中的 host 参数值...")
    found = False
    for node in nodes:
        host = get_host_from_node(node)
        if host:
            print(f"找到 host 值: {host}")
            found = True
            break
    if not found:
        print("未在任何 vless/trojan 节点中找到 host 参数")

def main():
    # 如果命令行提供了订阅地址，则使用它们；否则使用默认列表
    if len(sys.argv) > 1:
        urls = sys.argv[1:]
    else:
        # 可以在这里修改默认订阅地址列表，或者直接留空并提示
        urls = ["https://mar.bbc.xx.kg/"]   # 示例默认地址

    if not urls:
        print("未提供任何订阅地址，请通过命令行参数传入，例如：python host.py url1 url2 ...")
        return

    for url in urls:
        process_subscription(url)

if __name__ == "__main__":
    main()