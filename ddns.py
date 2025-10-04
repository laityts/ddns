#!/usr/bin/env python3
"""
DDNS IP健康检查与自动管理脚本
功能：检查域名DNS记录的IP可用性，自动从优选反代文件替换失效IP
作者：根据用户需求编写
日期：2025-10-04
版本：v2.5 - 添加重复IP检查，确保不添加已存在的IP
"""

import requests
import json
import time
import logging
import os
import re
from typing import List, Dict, Any, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器，支持环境变量和配置文件"""
    
    def __init__(self):
        self.config_file = os.path.expanduser("~/.cloudflare_ddns_config")
        
    def load_config(self) -> Dict[str, str]:
        """
        加载配置，优先级：环境变量 > 配置文件 > 默认值
        如果配置文件不存在，自动创建
        
        Returns:
            配置字典
        """
        config = {}
        
        # 从环境变量读取
        config['ZONE_ID'] = os.getenv('CLOUDFLARE_ZONE_ID', '')
        config['AUTH_EMAIL'] = os.getenv('CLOUDFLARE_AUTH_EMAIL', '')
        config['AUTH_KEY'] = os.getenv('CLOUDFLARE_AUTH_KEY', '')
        config['DOMAIN'] = os.getenv('CLOUDFLARE_DOMAIN', 'sg.616049.xyz')
        config['CHECK_PORT'] = os.getenv('CLOUDFLARE_CHECK_PORT', '8888')
        config['BOT_TOKEN'] = os.getenv('TELEGRAM_BOT_TOKEN', '')
        config['CHAT_ID'] = os.getenv('TELEGRAM_CHAT_ID', '')
        
        # 如果环境变量没有完整配置，检查配置文件
        if not all([config['ZONE_ID'], config['AUTH_EMAIL'], config['AUTH_KEY']]):
            file_config = self._load_config_file()
            if file_config:
                for key in ['ZONE_ID', 'AUTH_EMAIL', 'AUTH_KEY', 'DOMAIN', 'CHECK_PORT', 'BOT_TOKEN', 'CHAT_ID']:
                    if not config.get(key) and file_config.get(key):
                        config[key] = file_config[key]
        
        return config
    
    def _load_config_file(self) -> Dict[str, str]:
        """
        从配置文件读取配置
        如果文件不存在，自动创建配置文件模板
        
        Returns:
            配置字典，如果文件不存在返回空字典
        """
        # 如果配置文件不存在，自动创建
        if not os.path.exists(self.config_file):
            print(f"📁 配置文件不存在: {self.config_file}")
            print("🔄 自动创建配置文件模板...")
            if self.create_config_file():
                print(f"✅ 配置文件已创建: {self.config_file}")
                print("📝 请编辑该文件并填入您的实际信息，然后重新运行脚本")
            return {}
            
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = {}
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
                return config
        except Exception as e:
            logger.error(f"读取配置文件失败: {e}")
            return {}
    
    def create_config_file(self) -> bool:
        """创建配置文件模板"""
        config_template = """# Cloudflare DDNS 配置文件
# 请将以下值替换为您的实际信息

# Cloudflare 区域ID (在域名的概述页面找到)
ZONE_ID=your_zone_id_here

# Cloudflare 账户邮箱
AUTH_EMAIL=your_email@example.com

# Cloudflare 全局API密钥
AUTH_KEY=your_global_api_key_here

# 要管理的域名 (默认: sg.616049.xyz)
DOMAIN=sg.616049.xyz

# 健康检查端口 (默认: 8888)
CHECK_PORT=8888

# Telegram 机器人令牌 (可选，用于发送通知)
BOT_TOKEN=your_bot_token_here

# Telegram 聊天ID (可选，用于发送通知)
CHAT_ID=your_chat_id_here
"""
        try:
            # 确保目录存在
            config_dir = os.path.dirname(self.config_file)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, mode=0o700)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(config_template)
            os.chmod(self.config_file, 0o600)  # 设置文件权限为仅用户可读写
            return True
        except Exception as e:
            logger.error(f"创建配置文件失败: {e}")
            return False
    
    def print_config_help(self):
        """打印配置帮助信息"""
        print("\n🔧 配置方法 (任选其一):")
        print("\n方法1: 设置环境变量 (推荐)")
        print("  export CLOUDFLARE_ZONE_ID=\"您的区域ID\"")
        print("  export CLOUDFLARE_AUTH_EMAIL=\"您的邮箱\"")
        print("  export CLOUDFLARE_AUTH_KEY=\"您的API密钥\"")
        print("  export CLOUDFLARE_DOMAIN=\"sg.616049.xyz\"")
        print("  export CLOUDFLARE_CHECK_PORT=\"8888\"")
        print("  export TELEGRAM_BOT_TOKEN=\"您的机器人令牌\"")
        print("  export TELEGRAM_CHAT_ID=\"您的聊天ID\"")
        print("\n  在Termux中，可以将这些命令添加到 ~/.bashrc 文件中")
        
        print("\n方法2: 使用配置文件")
        print(f"  脚本会在 {self.config_file} 自动创建配置文件模板")
        print("  请编辑该文件并填入您的实际信息")

class TelegramNotifier:
    """Telegram消息通知器"""
    
    def __init__(self, bot_token: str, chat_id: str):
        """
        初始化Telegram通知器
        
        Args:
            bot_token: Telegram机器人令牌
            chat_id: Telegram聊天ID
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        
        if self.enabled:
            logger.info("📱 Telegram通知功能已启用")
        else:
            logger.info("📱 Telegram通知功能未配置")
    
    def send_message(self, message: str, domain: str = "") -> bool:
        """
        发送Telegram消息
        
        Args:
            message: 消息内容
            domain: 域名（用于消息格式化）
            
        Returns:
            bool: 发送是否成功
        """
        if not self.enabled:
            return False
            
        try:
            # 构建消息内容
            if domain:
                formatted_message = f"🔍 <b>DDNS健康检查通知 - {domain}</b>\n\n{message}"
            else:
                formatted_message = f"🔍 <b>DDNS健康检查通知</b>\n\n{message}"
            
            # 构建API URL
            url = f"https://api.tg.090227.xyz/bot{self.bot_token}/sendMessage"
            params = {
                "chat_id": self.chat_id,
                "parse_mode": "HTML",
                "text": formatted_message
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("ok", False):
                logger.info("✅ Telegram消息发送成功")
                return True
            else:
                error_msg = result.get("description", "未知错误")
                logger.error(f"Telegram消息发送失败: {error_msg}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"发送Telegram消息时网络错误: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"发送Telegram消息时发生未知错误: {str(e)}")
            return False
    
    def send_health_alert(self, domain: str, failed_ips: List[Dict], deleted_count: int, added_count: int, skipped_ips: List[str] = None) -> bool:
        """
        发送健康检查警报
        
        Args:
            domain: 域名
            failed_ips: 失败的IP列表
            deleted_count: 删除的记录数量
            added_count: 添加的记录数量
            skipped_ips: 跳过的重复IP列表
            
        Returns:
            bool: 发送是否成功
        """
        if not self.enabled:
            return False
            
        message_lines = []
        
        if failed_ips:
            message_lines.append("❌ <b>健康检查失败IP:</b>")
            for ip_info in failed_ips:
                message_lines.append(f"   • {ip_info['ip']} - {ip_info.get('error', '未知错误')}")
        
        if deleted_count > 0:
            message_lines.append(f"🗑️  <b>已删除记录:</b> {deleted_count} 条")
        
        if added_count > 0:
            message_lines.append(f"➕ <b>已添加记录:</b> {added_count} 条")
        
        if skipped_ips:
            message_lines.append(f"⏭️  <b>跳过重复IP:</b> {len(skipped_ips)} 个")
            for ip in skipped_ips:
                message_lines.append(f"   • {ip}")
        
        if not message_lines:
            message_lines.append("✅ 所有DNS记录状态良好")
        
        message_lines.append(f"\n⏰ 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        message = "\n".join(message_lines)
        return self.send_message(message, domain)

class CloudflareDDNSManager:
    def __init__(self, zone_id: str, auth_email: str, auth_key: str, domain: str, bot_token: str = "", chat_id: str = ""):
        """
        初始化Cloudflare DDNS管理器（使用旧版API认证）
        
        Args:
            zone_id: Cloudflare区域ID
            auth_email: Cloudflare账户邮箱
            auth_key: Cloudflare全局API密钥
            domain: 要管理的域名(如:sg.616049.xyz)
            bot_token: Telegram机器人令牌
            chat_id: Telegram聊天ID
        """
        self.zone_id = zone_id
        self.auth_email = auth_email
        self.auth_key = auth_key
        self.domain = domain
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "X-Auth-Email": auth_email,
            "X-Auth-Key": auth_key,
            "Content-Type": "application/json"
        }
        self.notifier = TelegramNotifier(bot_token, chat_id)
        self.print_banner("Cloudflare DDNS 管理器初始化")
        logger.info(f"🌐 域名: {domain}")
        logger.info(f"🔑 区域ID: {zone_id}")
        
    def print_banner(self, title: str):
        """打印美观的标题横幅"""
        print("\n" + "=" * 60)
        print(f"✨ {title}")
        print("=" * 60)
        
    def print_section(self, title: str):
        """打印章节标题"""
        print(f"\n🎯 {title}")
        print("-" * 40)
        
    def print_status(self, message: str, status: str = "info"):
        """打印状态消息"""
        icons = {
            "info": "📝",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "debug": "🐛"
        }
        icon = icons.get(status, "📝")
        print(f"{icon} {message}")
        
    def get_current_dns_records(self) -> List[Dict[str, Any]]:
        """
        获取域名当前的DNS记录
        
        Returns:
            DNS记录列表
        """
        self.print_section("获取当前DNS记录")
        logger.info(f"正在获取域名 {self.domain} 的DNS记录...")
        try:
            url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
            params = {
                "name": self.domain,
                "type": "A"  # 只获取A记录
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if not result.get("success", False):
                error_msg = result.get('errors', [{'message': '未知错误'}])[0].get('message', '未知错误')
                self.print_status(f"获取DNS记录失败: {error_msg}", "error")
                return []
                
            records = result.get("result", [])
            self.print_status(f"成功获取到 {len(records)} 条DNS记录", "success")
            
            for i, record in enumerate(records):
                logger.info(f"记录 {i+1}: ID={record.get('id')}, IP={record.get('content')}, "
                          f"类型={record.get('type')}, TTL={record.get('ttl')}")
                
            return records
            
        except requests.exceptions.RequestException as e:
            self.print_status(f"网络错误: {str(e)}", "error")
            return []
        except json.JSONDecodeError as e:
            self.print_status(f"JSON解析失败: {str(e)}", "error")
            return []
        except Exception as e:
            self.print_status(f"未知错误: {str(e)}", "error")
            return []
    
    def check_ip_health(self, ip: str, port: int = 80) -> Tuple[bool, Dict[str, Any]]:
        """
        检查IP地址的健康状态
        
        Args:
            ip: 要检查的IP地址
            port: 检查的端口号
            
        Returns:
            Tuple[bool, Dict]: (是否健康, 详细检查结果)
        """
        logger.info(f"检查IP {ip}:{port} 的健康状态...")
        try:
            # 构建检查URL
            check_url = f"https://check.proxyip.eytan.qzz.io/check?proxyip={ip}:{port}"
            
            response = requests.get(check_url, timeout=15)
            response.raise_for_status()
            
            result = response.json()
            
            success = result.get("success", False)
            
            if success:
                self.print_status(f"IP {ip}:{port} 健康检查通过", "success")
                return True, result
            else:
                error_info = result.get("error", "未知错误")
                self.print_status(f"IP {ip}:{port} 健康检查失败: {error_info}", "warning")
                return False, result
            
        except requests.exceptions.Timeout:
            self.print_status(f"IP {ip}:{port} 检查超时(15秒)", "error")
            return False, {"error": "请求超时"}
        except requests.exceptions.RequestException as e:
            self.print_status(f"IP {ip}:{port} 检查网络错误: {str(e)}", "error")
            return False, {"error": f"网络错误: {str(e)}"}
        except json.JSONDecodeError as e:
            self.print_status(f"IP {ip}:{port} 检查响应JSON解析失败: {str(e)}", "error")
            return False, {"error": "JSON解析错误"}
        except Exception as e:
            self.print_status(f"IP {ip}:{port} 检查发生未知错误: {str(e)}", "error")
            return False, {"error": f"未知错误: {str(e)}"}
    
    def delete_dns_record(self, record_id: str, ip: str) -> bool:
        """
        删除DNS记录
        
        Args:
            record_id: 要删除的记录ID
            ip: 对应的IP地址(用于日志)
            
        Returns:
            bool: 删除是否成功
        """
        logger.info(f"删除DNS记录 - IP: {ip}")
        try:
            url = f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}"
            
            response = requests.delete(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("success", False):
                self.print_status(f"成功删除DNS记录: {ip}", "success")
                return True
            else:
                errors = result.get('errors', [{'message': '未知错误'}])
                error_msg = errors[0].get('message', '未知错误') if errors else '未知错误'
                self.print_status(f"删除DNS记录失败: {error_msg}", "error")
                return False
                
        except requests.exceptions.RequestException as e:
            self.print_status(f"删除DNS记录时发生网络错误: {str(e)}", "error")
            return False
        except Exception as e:
            self.print_status(f"删除DNS记录时发生未知错误: {str(e)}", "error")
            return False
    
    def create_dns_record(self, ip: str) -> bool:
        """
        创建新的DNS记录
        
        Args:
            ip: 要添加的IP地址
            
        Returns:
            bool: 创建是否成功
        """
        logger.info(f"创建DNS记录 - IP: {ip}")
        try:
            url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
            
            data = {
                "type": "A",
                "name": self.domain,
                "content": ip,
                "ttl": 1,  # 自动TTL
                "proxied": False  # 不经过Cloudflare代理
            }
            
            response = requests.post(url, headers=self.headers, data=json.dumps(data), timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("success", False):
                record_id = result.get('result', {}).get('id', '未知')
                self.print_status(f"成功创建DNS记录: {ip}", "success")
                return True
            else:
                errors = result.get('errors', [{'message': '未知错误'}])
                error_msg = errors[0].get('message', '未知错误') if errors else '未知错误'
                self.print_status(f"创建DNS记录失败: {error_msg}", "error")
                return False
                
        except requests.exceptions.RequestException as e:
            self.print_status(f"创建DNS记录时发生网络错误: {str(e)}", "error")
            return False
        except Exception as e:
            self.print_status(f"创建DNS记录时发生未知错误: {str(e)}", "error")
            return False
    
    def read_optimal_ips_from_file(self, filename: str = "优选反代.txt") -> List[str]:
        """
        从优选反代文件读取IP列表
        支持格式: 43.175.234.243:8888#22ms
        
        Args:
            filename: 优选IP文件名
            
        Returns:
            IP地址列表
        """
        self.print_section("读取优选IP文件")
        logger.info(f"正在读取文件 {filename} ...")
        
        if not os.path.exists(filename):
            self.print_status(f"优选IP文件不存在: {filename}", "error")
            return []
        
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                lines = file.readlines()
            
            ips = []
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # 解析格式: 43.175.234.243:8888#22ms
                # 提取IP部分（冒号之前的部分）
                ip_match = re.match(r'^([\d\.]+):', line)
                if ip_match:
                    ip = ip_match.group(1)
                    if self._is_valid_ip(ip):
                        ips.append(ip)
                        self.print_status(f"第{line_num}行: 找到IP {ip}", "success")
                    else:
                        self.print_status(f"第{line_num}行: 无效IP格式 '{ip}'", "warning")
                else:
                    # 如果没有冒号，尝试直接验证整行是否为IP
                    if self._is_valid_ip(line):
                        ips.append(line)
                        self.print_status(f"第{line_num}行: 找到IP {line}", "success")
                    else:
                        self.print_status(f"第{line_num}行: 无法解析IP '{line}'", "warning")
            
            self.print_status(f"成功读取 {len(ips)} 个有效IP", "success")
            if ips:
                print("📋 优选IP列表:")
                for ip in ips:
                    print(f"   • {ip}")
            
            return ips
            
        except Exception as e:
            self.print_status(f"读取优选IP文件失败: {str(e)}", "error")
            return []
    
    def _is_valid_ip(self, ip: str) -> bool:
        """
        简单验证IP地址格式
        
        Args:
            ip: IP地址字符串
            
        Returns:
            bool: 是否为有效IP格式
        """
        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(ip_pattern, ip):
            return False
        
        # 验证每个部分在0-255之间
        parts = ip.split('.')
        for part in parts:
            if not part.isdigit() or not 0 <= int(part) <= 255:
                return False
        return True
    
    def get_optimal_ips(self, count: int, existing_ips: List[str]) -> Tuple[List[str], List[str]]:
        """
        从优选反代文件获取指定数量的IP列表，排除已存在的IP
        
        Args:
            count: 需要获取的IP数量
            existing_ips: 已存在的IP列表（用于去重）
            
        Returns:
            Tuple[List[str], List[str]]: (选中的IP列表, 跳过的重复IP列表)
        """
        logger.info(f"需要获取 {count} 个优选IP，排除 {len(existing_ips)} 个已存在IP")
        
        all_ips = self.read_optimal_ips_from_file()
        
        if not all_ips:
            self.print_status("没有从文件获取到任何优选IP，无法替换失效记录", "error")
            return [], []
        
        # 过滤掉已存在的IP
        unique_ips = []
        skipped_ips = []
        
        for ip in all_ips:
            if ip in existing_ips:
                skipped_ips.append(ip)
                self.print_status(f"跳过重复IP: {ip}", "warning")
            else:
                unique_ips.append(ip)
        
        # 返回前count个唯一IP
        selected_ips = unique_ips[:count]
        
        self.print_status(f"选择 {len(selected_ips)} 个优选IP，跳过 {len(skipped_ips)} 个重复IP", "success")
        
        if selected_ips:
            print("📋 将要添加的IP列表:")
            for ip in selected_ips:
                print(f"   ➕ {ip}")
        
        if skipped_ips:
            print("📋 跳过的重复IP列表:")
            for ip in skipped_ips:
                print(f"   ⏭️  {ip}")
        
        return selected_ips, skipped_ips
    
    def manage_dns_records(self, check_port: int = 8888):
        """
        主管理函数：检查并管理DNS记录
        
        Args:
            check_port: 检查IP时使用的端口号
        """
        self.print_banner(f"开始管理域名 {self.domain}")
        print(f"🔧 检查端口: {check_port}")
        
        # 1. 获取当前DNS记录
        self.print_section("获取当前DNS记录")
        current_records = self.get_current_dns_records()
        if not current_records:
            self.print_status("未找到DNS记录，退出管理", "error")
            return
        
        # 2. 检查每个IP的健康状态
        self.print_section("健康状态检查")
        failed_records = []
        healthy_records = []
        health_details = []
        
        for record in current_records:
            record_id = record.get("id")
            record_ip = record.get("content")
            record_type = record.get("type")
            
            if record_type != "A":
                self.print_status(f"跳过非A记录: 类型={record_type}", "warning")
                continue
                
            is_healthy, health_info = self.check_ip_health(record_ip, check_port)
            health_details.append({
                "ip": record_ip,
                "healthy": is_healthy,
                "details": health_info
            })
            
            if is_healthy:
                healthy_records.append(record)
            else:
                failed_records.append({
                    "record": record,
                    "ip": record_ip,
                    "error": health_info.get("error", "未知错误")
                })
            
            # 添加短暂延迟，避免检查过于频繁
            time.sleep(1)
        
        # 输出健康检查汇总
        self.print_section("健康检查汇总")
        print("📊 详细结果:")
        for detail in health_details:
            status = "✅ 健康" if detail["healthy"] else "❌ 失败"
            error_info = detail["details"].get("error", "无错误信息")
            print(f"   {detail['ip']}: {status}")
            if not detail["healthy"]:
                print(f"     错误: {error_info}")
        
        print(f"\n📈 总体统计:")
        print(f"   • 总记录: {len(current_records)}")
        print(f"   • 健康: {len(healthy_records)}")
        print(f"   • 失败: {len(failed_records)}")
        
        # 3. 删除失败的DNS记录
        self.print_section("处理失败记录")
        deleted_count = 0
        if failed_records:
            for failed_info in failed_records:
                record = failed_info["record"]
                record_id = record.get("id")
                record_ip = record.get("content")
                
                if self.delete_dns_record(record_id, record_ip):
                    deleted_count += 1
                
                # 添加短暂延迟，避免API限制
                time.sleep(1)
            self.print_status(f"成功删除 {deleted_count} 条失败记录", "success")
        else:
            self.print_status("没有需要删除的失败记录", "info")
        
        # 4. 添加新的优选IP（避免重复）
        self.print_section("补充优选IP")
        added_count = 0
        skipped_ips = []
        
        if deleted_count > 0:
            self.print_status(f"需要补充 {deleted_count} 个新IP", "info")
            
            # 获取当前健康IP列表（用于去重）
            current_healthy_ips = [record.get("content") for record in healthy_records]
            self.print_status(f"当前有 {len(current_healthy_ips)} 个健康IP需要避免重复", "info")
            
            # 获取优选IP（排除已存在的）
            optimal_ips, skipped_ips = self.get_optimal_ips(deleted_count, current_healthy_ips)
            
            if optimal_ips:
                for ip in optimal_ips:
                    if self.create_dns_record(ip):
                        added_count += 1
                    
                    # 添加短暂延迟，避免API限制
                    time.sleep(1)
                
                self.print_status(f"成功添加 {added_count} 个新IP", "success")
            else:
                self.print_status("没有可用的优选IP，无法补充新记录", "warning")
        else:
            self.print_status("没有需要补充的新IP", "info")
        
        # 5. 发送Telegram通知
        if failed_records or deleted_count > 0 or added_count > 0:
            self.print_section("发送通知")
            self.notifier.send_health_alert(
                domain=self.domain,
                failed_ips=failed_records,
                deleted_count=deleted_count,
                added_count=added_count,
                skipped_ips=skipped_ips
            )
        
        # 6. 最终状态汇总
        self.print_banner("管理任务完成")
        print("📊 最终统计报告:")
        print(f"   🗑️  删除失败记录: {deleted_count} 条")
        print(f"   ➕ 添加优选IP: {added_count} 个")
        print(f"   ⏭️  跳过重复IP: {len(skipped_ips)} 个")
        print(f"   💚 当前健康记录: {len(healthy_records)} 条")
        
        if added_count == 0 and deleted_count == 0:
            self.print_status("所有DNS记录状态良好，无需变更", "success")
        else:
            self.print_status("DNS记录已更新完成", "success")

def main():
    """
    主函数 - 从环境变量或配置文件读取配置
    """
    config_manager = ConfigManager()
    config = config_manager.load_config()
    
    # 检查必要配置
    if not all([config.get('ZONE_ID'), config.get('AUTH_EMAIL'), config.get('AUTH_KEY')]):
        print("\n❌ 配置缺失")
        print("=" * 40)
        print("未找到完整的Cloudflare配置信息")
        
        config_manager.print_config_help()
        
        # 检查配置文件是否存在，如果不存在已经自动创建了
        if os.path.exists(config_manager.config_file):
            print(f"\n📁 配置文件已自动创建: {config_manager.config_file}")
            print("📝 请编辑该文件并填入您的实际信息，然后重新运行脚本")
        else:
            print(f"\n❌ 配置文件创建失败: {config_manager.config_file}")
            
        return
    
    # 使用配置
    ZONE_ID = config['ZONE_ID']
    AUTH_EMAIL = config['AUTH_EMAIL']
    AUTH_KEY = config['AUTH_KEY']
    DOMAIN = config.get('DOMAIN', 'sg.616049.xyz')
    CHECK_PORT = int(config.get('CHECK_PORT', '8888'))
    BOT_TOKEN = config.get('BOT_TOKEN', '')
    CHAT_ID = config.get('CHAT_ID', '')
    
    # 优选IP文件路径
    OPTIMAL_IPS_FILE = "优选反代.txt"
    
    # 检查优选IP文件是否存在
    if not os.path.exists(OPTIMAL_IPS_FILE):
        print(f"\n⚠️  文件提示")
        print(f"优选IP文件 {OPTIMAL_IPS_FILE} 不存在")
        print("💡 请创建优选反代.txt文件，格式示例:")
        print("   43.175.234.243:8888#22ms")
        print("   43.175.235.243:8888#24ms")
        print("\n📝 您可以从以下位置获取优选IP:")
        print("   - 从网络搜索'Cloudflare优选IP'")
        print("   - 使用IP扫描工具获取")
        print("   - 从相关社区或论坛获取")
    
    # 创建管理器实例
    manager = CloudflareDDNSManager(ZONE_ID, AUTH_EMAIL, AUTH_KEY, DOMAIN, BOT_TOKEN, CHAT_ID)
    
    # 执行管理任务
    try:
        manager.manage_dns_records(CHECK_PORT)
    except KeyboardInterrupt:
        print("\n⏹️  用户中断执行")
    except Exception as e:
        print(f"\n💥 执行管理任务时发生严重错误: {str(e)}")
        import traceback
        logger.debug(f"详细错误信息:\n{traceback.format_exc()}")

if __name__ == "__main__":
    main()