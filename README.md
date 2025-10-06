Cloudflare 反代IP优选与 DDNS 健康检查工具

项目概述

本项目包含两个核心脚本，用于自动化管理 Cloudflare 反代 IP 和 DNS 记录：

· ip.py - 反代 IP 检查与优选工具
· ddns.py - DDNS 健康检查与自动管理工具

功能特点

ip.py - 反代 IP 管理器

· ✅ 多源代理提取（CSV 文件 + iptest 工具）
· ✅ 多线程并发代理检查
· ✅ 智能代理分类（标准端口/非标准端口）
· ✅ 优选代理筛选（响应时间 + 国家过滤）
· ✅ 完整响应日志记录
· ✅ 实时进度显示

ddns.py - DDNS 健康检查器

· ✅ 自动 DNS 记录健康检查
· ✅ 失效 IP 自动替换
· ✅ 优选 IP 智能补充
· ✅ Telegram 通知集成
· ✅ 配置自动管理
· ✅ 空记录自动初始化

快速开始

环境要求

· Python 3.6+
· 以下系统包：
  ```bash
  # Ubuntu/Debian
  sudo apt update
  sudo apt install curl
  
  # CentOS/RHEL
  sudo yum install curl
  ```

安装步骤

1. 克隆或下载项目文件
   ```bash
   # 确保有以下文件：
   # - ip.py
   # - ddns.py
   # - iptest (可执行文件，用于代理测试)
   ```
2. 设置执行权限
   ```bash
   chmod +x ip.py ddns.py iptest
   ```
3. 准备数据源
   · 将代理 CSV 文件放在同一目录，或
   · 确保 iptest 可正常生成 ip.csv

使用指南

1. 反代 IP 管理 (ip.py)

基本用法：

```bash
python3 ip.py
```

配置选项（编辑 ip.py 中的配置变量）：

```python
# 优选国家设置
PREFERRED_COUNTRY = '新加坡'  # 留空则使用所有国家

# 响应时间阈值（毫秒）
PREFERRED_MAX_RESPONSE_TIME = 350

# 优选端口设置
PREFERRED_PROXY_PORT = '443'  # 支持多端口: '80,443,2053'
```

生成的文件：

· proxyip.txt - 所有成功代理
· 优选反代.txt - 优选代理（响应时间 < 阈值）
· 标准端口.txt - CF 标准端口代理
· 非标端口.txt - 非标准端口代理
· full_responses.txt - 完整检查日志

2. DDNS 健康检查 (ddns.py)

首次配置：

```bash
python3 ddns.py
```

首次运行会自动创建配置文件模板。

配置方法（二选一）：

方法1：环境变量

```bash
export CLOUDFLARE_ZONE_ID="您的区域ID"
export CLOUDFLARE_AUTH_EMAIL="您的邮箱"
export CLOUDFLARE_AUTH_KEY="您的API密钥"
export CLOUDFLARE_DOMAIN="您的域名"
export CLOUDFLARE_CHECK_PORT="443"  # 必需：健康检查端口
export TELEGRAM_BOT_TOKEN="您的机器人令牌"  # 可选
export TELEGRAM_CHAT_ID="您的聊天ID"  # 可选
```

方法2：配置文件
编辑自动生成的.cloudflare_ddns_config 文件：

```ini
ZONE_ID=your_zone_id_here
AUTH_EMAIL=your_email@example.com
AUTH_KEY=your_global_api_key_here
DOMAIN=your_domain_here
CHECK_PORT=443  # 必需：健康检查端口
BOT_TOKEN=your_bot_token_here  # 可选
CHAT_ID=your_chat_id_here  # 可选
```

运行管理：

```bash
python3 ddns.py
```

文件说明

输入文件

· *.csv / data.csv - 代理 IP 数据源
· ip.txt - 代理列表（自动生成）
· 优选反代.txt - 优选代理列表（由 ip.py 生成）

输出文件

· proxyip.txt - 所有有效代理
· 标准端口.txt - Cloudflare 标准端口代理
· 非标端口.txt - 非标准端口代理
· full_responses.txt - 完整检查日志

配置文件

· .cloudflare_ddns_config - DDNS 配置文件（自动生成）

Cloudflare 标准端口

支持的 HTTP/HTTPS 端口：

```
80, 443, 2052, 2053, 2082, 2083, 2086, 2087, 
2095, 2096, 8080, 8443, 8880
```

API 密钥获取

1. 登录 Cloudflare 控制台
2. 进入「我的个人资料」→「API 令牌」
3. 获取「区域资源」的「编辑」权限令牌，或使用全局 API 密钥

Telegram 通知设置

1. 创建 Telegram Bot：联系 @BotFather
2. 获取 Bot Token
3. 获取 Chat ID：向 @userinfobot 发送消息
4. 在配置中填入相应信息

自动化部署

定时任务（Crontab）

```bash
# 每6小时检查一次代理
0 */6 * * * /usr/bin/python3 /path/to/ip.py

# 每30分钟检查DNS健康
*/30 * * * * /usr/bin/python3 /path/to/ddns.py
```

Docker 部署（可选）

```dockerfile
FROM python:3.9-slim
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
COPY ip.py ddns.py iptest /app/
WORKDIR /app
CMD ["python3", "ddns.py"]
```

故障排除

常见问题

1. 代理检查失败
   · 检查网络连接
   · 验证 iptest 工具权限
   · 查看 full_responses.txt 日志
2. Cloudflare API 错误
   · 验证 API 密钥权限
   · 检查区域 ID 和域名匹配
   · 确认账户有足够权限
3. Telegram 通知失败
   · 验证 Bot Token 和 Chat ID
   · 检查网络连接
   · 查看脚本日志输出

日志查看

```bash
# 查看详细执行日志
tail -f full_responses.txt

# 查看脚本输出
python3 ddns.py 2>&1 | tee ddns.log
```