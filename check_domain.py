#!/usr/bin/env python3
"""
代理检测脚本 (域名解析版本)
从预定义列表中读取域名:端口，解析域名获取IP，然后检测代理可用性
支持并发检测并发送TG通知
"""

import os
import sys
import re
import json
import time
import socket
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 检查是否安装了requests库
try:
    import requests
except ImportError:
    print("错误: requests 库未安装")
    print("请安装 requests: pip install requests")
    sys.exit(1)

# 全局锁，用于保护打印和结果收集
file_lock = threading.Lock()

# 代理列表 - 可以在此添加更多代理
PROXY_LIST = [
    "tw.vlato.site:443",
    "se.vlato.site:443",
    "kr.vlato.site:50001",
    "hk.vlato.site:443"
]

def check_termux():
    """检查是否在Termux环境中"""
    return os.path.exists("/data/data/com.termux/files/usr")

def resolve_domain(domain):
    """解析域名获取所有IP地址"""
    try:
        # 去除端口部分（如果有）
        domain_only = domain.split(':')[0] if ':' in domain else domain
        
        # 解析域名
        ip_list = []
        try:
            # 尝试获取所有地址
            addrinfo = socket.getaddrinfo(domain_only, None)
            for info in addrinfo:
                ip = info[4][0]
                if ip not in ip_list:
                    ip_list.append(ip)
        except:
            # 如果失败，尝试普通解析
            try:
                ip = socket.gethostbyname(domain_only)
                if ip not in ip_list:
                    ip_list.append(ip)
            except:
                pass
        
        return ip_list
    except Exception as e:
        print(f"解析域名 {domain} 失败: {str(e)}")
        return []

def parse_proxy_entry(entry):
    """解析代理条目，返回(域名/IP, 端口)"""
    entry = entry.strip()
    if not entry:
        return None, None
    
    # 分离域名/IP和端口
    if ':' in entry:
        parts = entry.split(':')
        host = parts[0]
        try:
            port = int(parts[1])
            if port < 1 or port > 65535:
                print(f"警告: 端口 {port} 无效，使用默认端口443")
                port = 443
        except ValueError:
            print(f"警告: 端口 '{parts[1]}' 无效，使用默认端口443")
            port = 443
    else:
        host = entry
        port = 443  # 默认端口
    
    return host, port

def check_proxy(proxy, timeout=15):
    """检测单个代理"""
    url = f"https://check.proxyip.vlato.site/check?proxyip={proxy}"
    
    # Termux环境使用更长超时
    if check_termux():
        timeout = 30
    
    try:
        # 发送请求
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        
        # 解析JSON响应
        data = response.json()
        success = data.get('success')
        response_time = data.get('responseTime')
        error_msg = data.get('message') or data.get('error')
        
        return {
            'success': success,
            'response_time': response_time,
            'error_msg': error_msg,
            'raw_response': data
        }
        
    except requests.exceptions.Timeout:
        return {'timeout': True, 'error': '请求超时'}
    except requests.exceptions.ConnectionError:
        return {'error': '连接失败'}
    except requests.exceptions.RequestException as e:
        return {'error': f'请求失败: {str(e)}'}
    except json.JSONDecodeError:
        return {'error': '响应格式错误，非JSON格式'}
    except Exception as e:
        return {'error': f'未知错误: {str(e)}'}

def send_telegram_notification(message):
    """发送Telegram通知"""
    try:
        url = "https://api.tg.vlato.site/"
        headers = {"Content-Type": "application/json"}
        data = {"message": message}
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            print("Telegram通知发送成功")
        else:
            print(f"Telegram通知发送失败: {response.status_code}")
    except Exception as e:
        print(f"发送Telegram通知时出错: {str(e)}")

def process_domain_proxy(domain, port, domain_num):
    """处理域名代理检测"""
    results = []
    messages = []
    
    # 添加域名代理标题
    domain_title = f"🌐 域名代理 #{domain_num}: {domain}:{port}"
    messages.append(domain_title)
    messages.append("─" * 40)
    print(domain_title)
    print("─" * 40)
    
    # 解析域名
    resolve_msg = f"🔍 正在解析域名 {domain}..."
    messages.append(resolve_msg)
    print(resolve_msg)
    
    ip_list = resolve_domain(domain)
    
    if not ip_list:
        fail_msg = f"   ❌ 无法解析域名 {domain}"
        messages.append(fail_msg)
        print(fail_msg)
        messages.append("")  # 空行
        return messages
    
    ip_msg = f"   📍 解析到 {len(ip_list)} 个IP地址:"
    messages.append(ip_msg)
    print(ip_msg)
    
    for ip in ip_list:
        ip_detail = f"      • {ip}"
        messages.append(ip_detail)
        print(ip_detail)
    
    messages.append("")  # 空行
    
    # 对每个IP进行检测
    for i, ip in enumerate(ip_list, 1):
        proxy = f"{ip}:{port}"
        check_msg = f"   📡 检测IP {i}/{len(ip_list)}: {proxy}"
        messages.append(check_msg)
        print(check_msg)
        
        result = check_proxy(proxy)
        
        if 'timeout' in result:
            timeout_msg = f"      ⏰ 请求超时"
            messages.append(timeout_msg)
            print(timeout_msg)
        elif 'error' in result:
            error_msg = f"      ❌ {result['error']}"
            messages.append(error_msg)
            print(error_msg)
        else:
            success = result.get('success')
            response_time = result.get('response_time')
            error_msg = result.get('error_msg')
            
            if success in [True, 'true', 'True']:
                # 格式化响应时间
                rt_str = str(response_time)
                if response_time and not rt_str.endswith('ms'):
                    rt_str = f"{rt_str}ms"
                
                # 评价响应速度
                try:
                    rt_num = int(re.sub(r'[^0-9]', '', str(response_time)))
                    if rt_num < 100:
                        speed = "优秀"
                        icon = "⚡"
                        color = "🟢"
                    elif rt_num < 500:
                        speed = "良好"
                        icon = "⏱️"
                        color = "🟡"
                    else:
                        speed = "较慢"
                        icon = "🐢"
                        color = "🔴"
                except:
                    speed = "正常"
                    icon = "⏱️"
                    color = "🟡"
                
                success_msg = f"      {color} 状态: 可用"
                rt_msg = f"      {icon} 响应时间: {rt_str} ({speed})"
                messages.append(success_msg)
                messages.append(rt_msg)
                print(success_msg)
                print(rt_msg)
            else:
                fail_msg = f"      🔴 状态: 不可用"
                messages.append(fail_msg)
                print(fail_msg)
                if error_msg:
                    error_detail = f"      💬 错误信息: {error_msg}"
                    messages.append(error_detail)
                    print(error_detail)
        
        # 在IP检测结果之间添加空行（除了最后一个）
        if i < len(ip_list):
            messages.append("")
            print("")
    
    messages.append("")  # 空行
    print("")
    
    return messages

def process_ip_proxy(ip, port, proxy_num):
    """处理IP代理检测"""
    proxy = f"{ip}:{port}"
    messages = []
    
    # 添加IP代理标题
    ip_title = f"📡 IP代理 #{proxy_num}: {proxy}"
    messages.append(ip_title)
    messages.append("─" * 40)
    print(ip_title)
    print("─" * 40)
    
    result = check_proxy(proxy)
    
    if 'timeout' in result:
        timeout_msg = f"   ⏰ 请求超时"
        messages.append(timeout_msg)
        print(timeout_msg)
    elif 'error' in result:
        error_msg = f"   ❌ {result['error']}"
        messages.append(error_msg)
        print(error_msg)
    else:
        success = result.get('success')
        response_time = result.get('response_time')
        error_msg = result.get('error_msg')
        
        if success in [True, 'true', 'True']:
            # 格式化响应时间
            rt_str = str(response_time)
            if response_time and not rt_str.endswith('ms'):
                rt_str = f"{rt_str}ms"
            
            # 评价响应速度
            try:
                rt_num = int(re.sub(r'[^0-9]', '', str(response_time)))
                if rt_num < 100:
                    speed = "优秀"
                    icon = "⚡"
                    color = "🟢"
                elif rt_num < 500:
                    speed = "良好"
                    icon = "⏱️"
                    color = "🟡"
                else:
                    speed = "较慢"
                    icon = "🐢"
                    color = "🔴"
            except:
                speed = "正常"
                icon = "⏱️"
                color = "🟡"
            
            success_msg = f"   {color} 状态: 可用"
            rt_msg = f"   {icon} 响应时间: {rt_str} ({speed})"
            messages.append(success_msg)
            messages.append(rt_msg)
            print(success_msg)
            print(rt_msg)
        else:
            fail_msg = f"   🔴 状态: 不可用"
            messages.append(fail_msg)
            print(fail_msg)
            if error_msg:
                error_detail = f"   💬 错误信息: {error_msg}"
                messages.append(error_detail)
                print(error_detail)
    
    messages.append("")  # 空行
    print("")
    
    return messages

def is_ip_address(host):
    """检查是否是IP地址"""
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(ip_pattern, host):
        # 验证每个部分在0-255之间
        parts = host.split('.')
        for part in parts:
            if not 0 <= int(part) <= 255:
                return False
        return True
    return False

def main():
    """主函数"""
    print("域名/IP代理检测脚本")
    print("=" * 60)
    print(f"📋 检测列表中共有 {len(PROXY_LIST)} 个代理")
    
    # 解析并分组代理
    domain_proxies = []  # (domain, port, index)
    ip_proxies = []      # (ip, port, index)
    
    for i, entry in enumerate(PROXY_LIST, 1):
        host, port = parse_proxy_entry(entry)
        if not host:
            continue
        
        if is_ip_address(host):
            ip_proxies.append((host, port, i))
        else:
            domain_proxies.append((host, port, i))
    
    print(f"🌐 找到 {len(domain_proxies)} 个域名代理")
    print(f"📡 找到 {len(ip_proxies)} 个IP代理")
    print("=" * 60)
    
    # 收集所有消息
    all_messages = []
    
    # 添加标题和统计信息
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_messages.append(f"🚀 代理检测报告")
    all_messages.append(f"📅 检测时间: {timestamp}")
    all_messages.append("=" * 40)
    all_messages.append(f"📋 总代理数: {len(PROXY_LIST)}")
    all_messages.append(f"🌐 域名代理: {len(domain_proxies)} 个")
    all_messages.append(f"📡 IP代理: {len(ip_proxies)} 个")
    all_messages.append("=" * 40)
    all_messages.append("")
    
    # 设置并发数
    concurrency = 10
    if check_termux():
        concurrency = 5  # Termux环境使用较少的并发
    
    print(f"⚙️ 使用并发数: {concurrency}")
    print("🔍 开始检测代理...")
    
    # 使用线程池处理IP代理（域名代理需要先解析，所以单独处理）
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        
        # 提交IP代理检测任务
        for ip, port, proxy_num in ip_proxies:
            future = executor.submit(
                process_ip_proxy,
                ip, port, proxy_num
            )
            futures.append(future)
        
        # 处理域名代理（需要先解析）
        for domain, port, proxy_num in domain_proxies:
            # 域名代理需要先解析，然后对每个IP进行检测
            domain_messages = process_domain_proxy(domain, port, proxy_num)
            all_messages.extend(domain_messages)
        
        # 处理IP代理检测结果
        for future in as_completed(futures):
            try:
                ip_messages = future.result()
                all_messages.extend(ip_messages)
            except Exception as e:
                error_msg = f"❌ 处理IP代理时出错: {str(e)}"
                all_messages.append(error_msg)
                print(error_msg)
    
    print("=" * 60)
    print("✅ 检测完成!")
    
    # 添加总结
    all_messages.append("=" * 40)
    all_messages.append(f"📊 检测统计")
    all_messages.append(f"   📅 检测时间: {timestamp}")
    all_messages.append(f"   📋 总代理数: {len(PROXY_LIST)}")
    all_messages.append(f"   🌐 域名代理: {len(domain_proxies)} 个")
    all_messages.append(f"   📡 IP代理: {len(ip_proxies)} 个")
    all_messages.append("=" * 40)
    all_messages.append("✅ 检测完成! 🎉")
    
    # 发送Telegram通知
    notification_text = "\n".join(all_messages)
    print("\n📤 正在发送Telegram通知...")
    send_telegram_notification(notification_text)
    
    print("✅ 检测完成! 🎉")

if __name__ == "__main__":
    main()