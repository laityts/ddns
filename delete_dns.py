#!/usr/bin/env python3
"""
Cloudflare DNS记录交互式管理工具
功能：查询域名DNS记录、根据IP删除DNS记录、添加DNS记录
作者：根据用户需求编写
日期：2025-10-04
版本：v1.1
"""

import requests
import json
import os
import sys
import re
from typing import List, Dict, Any, Optional

class ConfigManager:
    """配置管理器，支持环境变量和配置文件"""
    
    def __init__(self):
        self.config_file = ".cloudflare_ddns_config"
        
    def load_config(self) -> Dict[str, str]:
        """
        加载配置，优先级：环境变量 > 配置文件
        
        Returns:
            配置字典
        """
        config = {}
        
        # 从环境变量读取
        config['ZONE_ID'] = os.getenv('CLOUDFLARE_ZONE_ID', '')
        config['AUTH_EMAIL'] = os.getenv('CLOUDFLARE_AUTH_EMAIL', '')
        config['AUTH_KEY'] = os.getenv('CLOUDFLARE_AUTH_KEY', '')
        config['DOMAIN'] = os.getenv('CLOUDFLARE_DOMAIN', '')
        
        # 如果环境变量没有完整配置，检查配置文件
        if not all([config['ZONE_ID'], config['AUTH_EMAIL'], config['AUTH_KEY']]):
            file_config = self._load_config_file()
            if file_config:
                for key in ['ZONE_ID', 'AUTH_EMAIL', 'AUTH_KEY', 'DOMAIN']:
                    if not config.get(key) and file_config.get(key):
                        config[key] = file_config[key]
        
        return config
    
    def _load_config_file(self) -> Dict[str, str]:
        """
        从配置文件读取配置
        
        Returns:
            配置字典，如果文件不存在返回空字典
        """
        if not os.path.exists(self.config_file):
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
            print(f"❌ 读取配置文件失败: {e}")
            return {}

class DNSManager:
    def __init__(self, zone_id: str, auth_email: str, auth_key: str):
        """
        初始化Cloudflare DNS管理器
        
        Args:
            zone_id: Cloudflare区域ID
            auth_email: Cloudflare账户邮箱
            auth_key: Cloudflare全局API密钥
        """
        self.zone_id = zone_id
        self.auth_email = auth_email
        self.auth_key = auth_key
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "X-Auth-Email": auth_email,
            "X-Auth-Key": auth_key,
            "Content-Type": "application/json"
        }
        
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
            "error": "❌"
        }
        icon = icons.get(status, "📝")
        print(f"{icon} {message}")
    
    def get_all_dns_records(self, domain: str = None) -> List[Dict[str, Any]]:
        """
        获取域名的所有DNS记录
        
        Args:
            domain: 域名，如果为None则获取所有记录
            
        Returns:
            DNS记录列表
        """
        self.print_section("获取DNS记录")
        
        try:
            url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
            params = {}
            if domain:
                params["name"] = domain
                self.print_status(f"正在查询域名 {domain} 的DNS记录...")
            else:
                self.print_status("正在查询所有DNS记录...")
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if not result.get("success", False):
                error_msg = result.get('errors', [{'message': '未知错误'}])[0].get('message', '未知错误')
                self.print_status(f"获取DNS记录失败: {error_msg}", "error")
                return []
                
            records = result.get("result", [])
            
            if domain:
                # 过滤指定域名的记录
                filtered_records = [record for record in records if record.get('name') == domain or record.get('name').endswith('.' + domain)]
                self.print_status(f"找到 {len(filtered_records)} 条域名 {domain} 的DNS记录", "success")
                return filtered_records
            else:
                self.print_status(f"找到 {len(records)} 条DNS记录", "success")
                return records
            
        except requests.exceptions.RequestException as e:
            self.print_status(f"网络错误: {str(e)}", "error")
            return []
        except Exception as e:
            self.print_status(f"未知错误: {str(e)}", "error")
            return []
    
    def display_records_table(self, records: List[Dict[str, Any]]):
        """
        以表格形式显示DNS记录
        
        Args:
            records: DNS记录列表
        """
        if not records:
            self.print_status("没有找到DNS记录", "warning")
            return
        
        print("\n📋 DNS记录列表:")
        print("-" * 100)
        print(f"{'序号':<4} {'类型':<6} {'名称':<30} {'内容':<20} {'TTL':<6} {'ID':<30}")
        print("-" * 100)
        
        for i, record in enumerate(records, 1):
            record_type = record.get('type', 'N/A')
            record_name = record.get('name', 'N/A')
            record_content = record.get('content', 'N/A')
            record_ttl = record.get('ttl', 'N/A')
            record_id = record.get('id', 'N/A')
            
            # 截断过长的内容以便显示
            if len(record_name) > 28:
                record_name = record_name[:25] + "..."
            if len(record_content) > 18:
                record_content = record_content[:15] + "..."
            if len(record_id) > 27:
                record_id = record_id[:24] + "..."
            
            print(f"{i:<4} {record_type:<6} {record_name:<30} {record_content:<20} {record_ttl:<6} {record_id:<30}")
        
        print("-" * 100)
    
    def delete_dns_record_by_ip(self, ip: str, domain: str = None) -> int:
        """
        根据IP地址删除DNS记录
        
        Args:
            ip: 要删除的IP地址
            domain: 限制删除的域名（可选）
            
        Returns:
            删除的记录数量
        """
        self.print_section(f"删除IP为 {ip} 的DNS记录")
        
        # 获取所有记录
        all_records = self.get_all_dns_records(domain)
        if not all_records:
            return 0
        
        # 筛选匹配IP的记录
        matching_records = []
        for record in all_records:
            if (record.get('type') in ['A', 'AAAA'] and 
                record.get('content') == ip and
                (domain is None or record.get('name') == domain or record.get('name').endswith('.' + domain))):
                matching_records.append(record)
        
        if not matching_records:
            self.print_status(f"没有找到IP为 {ip} 的DNS记录", "warning")
            return 0
        
        # 显示匹配的记录
        print(f"\n🔍 找到 {len(matching_records)} 条IP为 {ip} 的DNS记录:")
        self.display_records_table(matching_records)
        
        # 确认删除
        confirm = input(f"\n⚠️  确定要删除这 {len(matching_records)} 条记录吗？(y/N): ").strip().lower()
        if confirm != 'y':
            self.print_status("取消删除操作", "info")
            return 0
        
        # 执行删除
        deleted_count = 0
        for record in matching_records:
            record_id = record.get('id')
            record_name = record.get('name')
            record_content = record.get('content')
            
            if self._delete_single_record(record_id, record_content):
                deleted_count += 1
                self.print_status(f"已删除记录: {record_name} -> {record_content}", "success")
            else:
                self.print_status(f"删除记录失败: {record_name} -> {record_content}", "error")
            
            # 短暂延迟避免API限制
            import time
            time.sleep(0.5)
        
        self.print_status(f"删除完成，共删除 {deleted_count} 条记录", "success")
        return deleted_count
    
    def _delete_single_record(self, record_id: str, ip: str) -> bool:
        """
        删除单个DNS记录
        
        Args:
            record_id: 要删除的记录ID
            ip: 对应的IP地址(用于日志)
            
        Returns:
            bool: 删除是否成功
        """
        try:
            url = f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}"
            
            response = requests.delete(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("success", False):
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

    def add_dns_record(self, domain: str, ip: str, record_type: str = "A", ttl: int = 1, proxied: bool = False) -> bool:
        """
        添加DNS记录
        
        Args:
            domain: 域名
            ip: IP地址
            record_type: 记录类型，默认为A记录
            ttl: TTL值，默认为1（自动）
            proxied: 是否通过Cloudflare代理，默认为False
            
        Returns:
            bool: 添加是否成功
        """
        self.print_section("添加DNS记录")
        self.print_status(f"正在添加记录: {domain} -> {ip} (类型: {record_type})")
        
        # 验证IP地址格式
        if record_type == "A" and not self._is_valid_ipv4(ip):
            self.print_status(f"IPv4地址格式无效: {ip}", "error")
            return False
        elif record_type == "AAAA" and not self._is_valid_ipv6(ip):
            self.print_status(f"IPv6地址格式无效: {ip}", "error")
            return False
        
        try:
            url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
            
            data = {
                "type": record_type,
                "name": domain,
                "content": ip,
                "ttl": ttl,
                "proxied": proxied
            }
            
            response = requests.post(url, headers=self.headers, data=json.dumps(data), timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("success", False):
                record_id = result.get('result', {}).get('id', '未知')
                self.print_status(f"成功创建DNS记录: {domain} -> {ip}", "success")
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
    
    def _is_valid_ipv4(self, ip: str) -> bool:
        """
        验证IPv4地址格式
        
        Args:
            ip: IP地址字符串
            
        Returns:
            bool: 是否为有效IPv4地址
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
    
    def _is_valid_ipv6(self, ip: str) -> bool:
        """
        简单验证IPv6地址格式
        
        Args:
            ip: IP地址字符串
            
        Returns:
            bool: 是否为有效IPv6地址格式
        """
        # 简化的IPv6验证，实际使用中可能需要更复杂的验证
        ipv6_pattern = r'^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::1$|^::$'
        return bool(re.match(ipv6_pattern, ip))

def clear_screen():
    """清空终端屏幕"""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_menu():
    """打印主菜单"""
    print("\n" + "=" * 60)
    print("🌐 Cloudflare DNS记录管理工具")
    print("=" * 60)
    print("1. 📋 查询域名DNS记录")
    print("2. 🗑️  根据IP删除DNS记录")
    print("3. ➕ 添加DNS记录")
    print("4. 🚪 退出")
    print("=" * 60)

def get_user_input(prompt: str, default: str = "") -> str:
    """获取用户输入，支持默认值"""
    if default:
        user_input = input(f"{prompt} (默认: {default}): ").strip()
        return user_input if user_input else default
    else:
        return input(f"{prompt}: ").strip()

def main():
    """
    主函数 - 交互式DNS记录管理
    """
    clear_screen()
    
    # 加载配置
    config_manager = ConfigManager()
    config = config_manager.load_config()
    
    # 检查必要配置
    required_configs = ['ZONE_ID', 'AUTH_EMAIL', 'AUTH_KEY']
    missing_configs = [key for key in required_configs if not config.get(key)]
    
    if missing_configs:
        print("❌ 配置缺失")
        print(f"缺少以下必要配置: {', '.join(missing_configs)}")
        print(f"\n💡 请确保已设置环境变量或编辑配置文件: {config_manager.config_file}")
        print("\n环境变量设置示例:")
        print("  export CLOUDFLARE_ZONE_ID=\"您的区域ID\"")
        print("  export CLOUDFLARE_AUTH_EMAIL=\"您的邮箱\"")
        print("  export CLOUDFLARE_AUTH_KEY=\"您的API密钥\"")
        return
    
    # 使用配置
    ZONE_ID = config['ZONE_ID']
    AUTH_EMAIL = config['AUTH_EMAIL']
    AUTH_KEY = config['AUTH_KEY']
    DEFAULT_DOMAIN = config.get('DOMAIN', '')
    
    # 创建管理器实例
    manager = DNSManager(ZONE_ID, AUTH_EMAIL, AUTH_KEY)
    
    while True:
        print_menu()
        choice = input("\n请选择操作 (1-4): ").strip()
        
        if choice == '1':
            clear_screen()
            manager.print_banner("查询域名DNS记录")
            
            if DEFAULT_DOMAIN:
                use_default = input(f"使用默认域名 {DEFAULT_DOMAIN}？(Y/n): ").strip().lower()
                if use_default in ['', 'y', 'yes']:
                    domain = DEFAULT_DOMAIN
                else:
                    domain = input("请输入要查询的域名: ").strip()
            else:
                domain = input("请输入要查询的域名: ").strip()
            
            if not domain:
                manager.print_status("域名不能为空", "error")
                input("\n按回车键继续...")
                continue
            
            records = manager.get_all_dns_records(domain)
            manager.display_records_table(records)
            
            input("\n按回车键继续...")
            clear_screen()
            
        elif choice == '2':
            clear_screen()
            manager.print_banner("根据IP删除DNS记录")
            
            ip = input("请输入要删除的IP地址: ").strip()
            if not ip:
                manager.print_status("IP地址不能为空", "error")
                input("\n按回车键继续...")
                continue
            
            if DEFAULT_DOMAIN:
                use_domain = input(f"是否限制在域名 {DEFAULT_DOMAIN} 中删除？(Y/n): ").strip().lower()
                if use_domain in ['', 'y', 'yes']:
                    domain = DEFAULT_DOMAIN
                else:
                    domain = None
            else:
                domain_choice = input("是否限制在特定域名中删除？(y/N): ").strip().lower()
                if domain_choice == 'y':
                    domain = input("请输入域名: ").strip()
                else:
                    domain = None
            
            manager.delete_dns_record_by_ip(ip, domain)
            
            input("\n按回车键继续...")
            clear_screen()
            
        elif choice == '3':
            clear_screen()
            manager.print_banner("添加DNS记录")
            
            # 获取域名
            if DEFAULT_DOMAIN:
                use_default = input(f"使用默认域名 {DEFAULT_DOMAIN}？(Y/n): ").strip().lower()
                if use_default in ['', 'y', 'yes']:
                    domain = DEFAULT_DOMAIN
                else:
                    domain = input("请输入要添加记录的域名: ").strip()
            else:
                domain = input("请输入要添加记录的域名: ").strip()
            
            if not domain:
                manager.print_status("域名不能为空", "error")
                input("\n按回车键继续...")
                continue
            
            # 获取IP地址
            ip = input("请输入IP地址: ").strip()
            if not ip:
                manager.print_status("IP地址不能为空", "error")
                input("\n按回车键继续...")
                continue
            
            # 选择记录类型
            record_type = input("请输入记录类型 (默认: A): ").strip().upper()
            if not record_type:
                record_type = "A"
            
            # 选择TTL
            ttl_input = input("请输入TTL值 (默认: 1-自动): ").strip()
            if ttl_input:
                try:
                    ttl = int(ttl_input)
                except ValueError:
                    manager.print_status("TTL必须是数字，使用默认值1", "warning")
                    ttl = 1
            else:
                ttl = 1
            
            # 选择代理状态
            proxied_input = input("是否通过Cloudflare代理？(y/N): ").strip().lower()
            proxied = proxied_input in ['y', 'yes']
            
            # 确认添加
            print(f"\n📋 将要添加的记录:")
            print(f"   域名: {domain}")
            print(f"   IP地址: {ip}")
            print(f"   记录类型: {record_type}")
            print(f"   TTL: {ttl}")
            print(f"   代理状态: {'是' if proxied else '否'}")
            
            confirm = input("\n确认添加此记录？(y/N): ").strip().lower()
            if confirm != 'y':
                manager.print_status("取消添加操作", "info")
                input("\n按回车键继续...")
                clear_screen()
                continue
            
            # 执行添加
            success = manager.add_dns_record(domain, ip, record_type, ttl, proxied)
            
            if success:
                manager.print_status("记录添加成功", "success")
            else:
                manager.print_status("记录添加失败", "error")
            
            input("\n按回车键继续...")
            clear_screen()
            
        elif choice == '4':
            print("\n👋 感谢使用，再见！")
            break
            
        else:
            print("\n❌ 无效选择，请重新输入")
            input("\n按回车键继续...")
            clear_screen()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断执行")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 程序执行时发生错误: {str(e)}")
        sys.exit(1)