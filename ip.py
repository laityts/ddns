import glob
import os
import csv
import subprocess
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import threading  # 用于文件写入锁，确保线程安全

# 常量定义
FULL_RESPONSES_FILE = 'full_responses.txt'  # 完整响应保存文件
PROXY_FILE = 'ip.txt'  # 代理列表文件
SUCCESS_PROXY_FILE = 'proxyip.txt'  # 成功代理保存文件
STANDARD_PORTS_FILE = '标准端口.txt'  # CF标准端口代理保存文件
NON_STANDARD_FILE = '非标端口.txt'  # 非CF标准端口代理保存文件
CSV_FILE = 'data.csv'  # 重命名后的CSV文件

# CF标准端口列表（基于Cloudflare支持的HTTP/HTTPS端口）
STANDARD_PORTS = {
    '80', '443', '2052', '2053', '2082', '2083', '2086', '2087', 
    '2095', '2096', '8080', '8443', '8880'
}

# 文件写入锁，确保多线程追加文件时不混乱
file_lock = threading.Lock()

# 步骤1: 使用通配符查找并重命名 *.csv 为 data.csv
# 只处理第一个匹配的CSV文件，如果 ip.txt 不存在
try:
    csv_files = glob.glob('*.csv')
    ip_txt_exists = os.path.exists(PROXY_FILE)
    if not ip_txt_exists and csv_files:
        old_name = csv_files[0]
        os.rename(old_name, CSV_FILE)
        print(f"已将 {old_name} 重命名为 {CSV_FILE}")
    elif not csv_files and not ip_txt_exists:
        print("未找到CSV文件且无 ip.txt，将退出。")
        exit(1)
    else:
        print("检测到现有 ip.txt 文件，将直接使用。")
except Exception as e:
    print(f"重命名CSV文件时发生异常: {str(e)}")
    exit(1)

# 步骤2: 从 data.csv 提取 ip 和 port 并保存到 ip.txt（如果 ip.txt 不存在）
if not ip_txt_exists:
    try:
        if not os.path.exists(CSV_FILE):
            print(f"{CSV_FILE} 不存在，无法提取代理。")
            exit(1)
        
        with open(CSV_FILE, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            headers = next(reader, None)  # 读取表头行
            if headers is None:
                print("CSV文件为空。")
                exit(1)
            
            # 查找列索引，支持忽略大小写
            ip_col_idx = next((i for i, h in enumerate(headers) if h.lower() == 'ip'), -1)
            port_col_idx = next((i for i, h in enumerate(headers) if h.lower() == 'port'), -1)
            if ip_col_idx == -1 or port_col_idx == -1:
                print("CSV中未找到 'ip' 和 'port' 列（忽略大小写）。")
                exit(1)
            
            # 读取数据行并写入 ip.txt，跳过空行和无效行
            valid_count = 0
            with open(PROXY_FILE, 'w', encoding='utf-8') as f:
                for row in reader:
                    if len(row) > max(ip_col_idx, port_col_idx):
                        ip = row[ip_col_idx].strip()
                        port = row[port_col_idx].strip()
                        if ip and port and port.isdigit():  # 优化：确保端口是数字
                            f.write(f"{ip} {port}\n")
                            valid_count += 1
            if valid_count == 0:
                print("CSV中无有效IP和端口。")
                exit(1)
            print(f"已将 {valid_count} 个有效IPs和ports提取到 {PROXY_FILE}")
    except FileNotFoundError:
        print(f"文件 {CSV_FILE} 不存在。")
        exit(1)
    except csv.Error as e:
        print(f"读取CSV文件时发生错误: {str(e)}")
        exit(1)
    except Exception as e:
        print(f"提取代理时发生异常: {str(e)}")
        exit(1)

# 步骤3: 读取 ip.txt 中的代理列表
proxies = []
try:
    if os.path.exists(PROXY_FILE):
        with open(PROXY_FILE, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip() and len(line.split()) == 2]
    if not proxies:
        print(f"{PROXY_FILE} 中无有效代理，将退出。")
        exit(1)
except FileNotFoundError:
    print(f"文件 {PROXY_FILE} 不存在。")
    exit(1)
except Exception as e:
    print(f"读取 {PROXY_FILE} 时发生异常: {str(e)}")
    exit(1)

# 清空完整响应文件（开始新检查）
try:
    with open(FULL_RESPONSES_FILE, 'w', encoding='utf-8'):
        pass
except Exception as e:
    print(f"清空 {FULL_RESPONSES_FILE} 时发生异常: {str(e)}")
    exit(1)

# 步骤4: 定义检查单个代理的函数
def check_proxy(ip_port):
    """
    检查单个代理的有效性，并保存完整响应信息
    """
    try:
        ip, port = ip_port.split()  # 假设格式正确，否则跳过
        if not port.isdigit():  # 优化：再次验证端口
            raise ValueError("端口不是有效数字")
    except ValueError as e:
        with file_lock:
            try:
                with open(FULL_RESPONSES_FILE, 'a', encoding='utf-8') as full_file:
                    full_file.write(f"\n--- 代理: {ip_port} ---\n")
                    full_file.write(f"无效代理格式: {str(e)}\n\n")
            except Exception as write_e:
                print(f"写入 {FULL_RESPONSES_FILE} 时发生异常: {str(write_e)}")
        return None
    
    url = f"https://check.proxyip.eytan.qzz.io/check?proxyip={ip}:{port}"
    header = f"{ip}:{port}"
    stdout = ""
    stderr = ""
    returncode = 1
    
    try:
        # 使用subprocess运行curl，设置超时10秒
        result = subprocess.run(['curl', '-s', url], capture_output=True, text=True, timeout=10)
        returncode = result.returncode
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        # 尝试解析JSON，更新header
        if stdout:
            data = json.loads(stdout)
            header_ip = data.get('proxyIP', ip)
            header_port = str(data.get('portRemote', port))
            header = f"{header_ip}:{header_port}"
    except subprocess.TimeoutExpired:
        stderr = "请求超时"
    except json.JSONDecodeError:
        stderr = "JSON解析失败"
    except subprocess.CalledProcessError as e:
        stderr = f"subprocess调用错误: {str(e)}"
    except Exception as e:
        stderr = f"异常: {str(e)}"
    
    # 使用锁安全追加到完整响应文件
    with file_lock:
        try:
            with open(FULL_RESPONSES_FILE, 'a', encoding='utf-8') as full_file:
                full_file.write(f"\n--- 代理: {header} ---\n")
                full_file.write("检查结果:\n")
                full_file.write(f"STDOUT: {stdout}\n")
                full_file.write(f"STDERR: {stderr}\n")
                full_file.write(f"Return Code: {returncode}\n\n")
        except Exception as write_e:
            print(f"写入 {FULL_RESPONSES_FILE} 时发生异常: {str(write_e)}")
    
    # 检查是否成功
    success = False
    response_time = -1
    if returncode == 0 and stdout:
        try:
            data = json.loads(stdout)
            success = data.get('success', False)
            response_time = data.get('responseTime', -1)
        except json.JSONDecodeError:
            pass
    
    if success and response_time != -1:
        proxy_entry = f"{header}#{response_time}ms"
        return (response_time, proxy_entry)
    
    return None

# 步骤5: 使用 ThreadPoolExecutor 进行并发检查
try:
    max_workers = min(50, len(proxies))  # 限制最大线程数，避免资源耗尽
    successful_proxies = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_proxy = {executor.submit(check_proxy, proxy): proxy for proxy in proxies}
        with tqdm(total=len(proxies), desc="正在检查代理", unit="个") as pbar:
            for future in as_completed(future_to_proxy):
                try:
                    result = future.result()
                    if result:
                        successful_proxies.append(result)
                except Exception as e:
                    print(f"处理代理 {future_to_proxy[future]} 时发生异常: {str(e)}")
                pbar.update(1)
except Exception as e:
    print(f"并发检查代理时发生异常: {str(e)}")
    exit(1)

# 按 responseTime 排序（从小到大）
successful_proxies.sort(key=lambda x: x[0])

# 步骤6: 保存成功代理到 proxyip.txt
try:
    with open(SUCCESS_PROXY_FILE, 'w', encoding='utf-8') as f:
        for _, proxy in successful_proxies:
            f.write(f"{proxy}\n")
    print(f"提取了 {len(successful_proxies)} 个有效代理到 {SUCCESS_PROXY_FILE}")
except Exception as e:
    print(f"保存 {SUCCESS_PROXY_FILE} 时发生异常: {str(e)}")
    exit(1)

# 步骤7: 从 proxyip.txt 分离标准端口和非标准端口代理
try:
    standard_proxies = []
    non_standard_proxies = []
    
    if os.path.exists(SUCCESS_PROXY_FILE):
        with open(SUCCESS_PROXY_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ip_port_part = line.split('#')[0]
                    _, port = ip_port_part.rsplit(':', 1)
                    if port in STANDARD_PORTS:
                        standard_proxies.append(line)
                    else:
                        non_standard_proxies.append(line)
                except ValueError:
                    print(f"无效行格式: {line}")
                    continue
    
    # 保存标准端口代理
    if standard_proxies:
        with open(STANDARD_PORTS_FILE, 'w', encoding='utf-8') as f:
            for proxy in standard_proxies:
                f.write(f"{proxy}\n")
        print(f"提取了 {len(standard_proxies)} 个CF标准端口代理到 {STANDARD_PORTS_FILE}")
    else:
        print(f"无CF标准端口代理。")
    
    # 保存非标准端口代理
    if non_standard_proxies:
        with open(NON_STANDARD_FILE, 'w', encoding='utf-8') as f:
            for proxy in non_standard_proxies:
                f.write(f"{proxy}\n")
        print(f"提取了 {len(non_standard_proxies)} 个非CF标准端口代理到 {NON_STANDARD_FILE}")
    else:
        print(f"无非CF标准端口代理。")
        
except FileNotFoundError:
    print(f"文件 {SUCCESS_PROXY_FILE} 不存在。")
except Exception as e:
    print(f"分离端口类型代理时发生异常: {str(e)}")

# 美化输出：显示成功代理列表
print("\n" + "="*80)
print("代理检查完成！以下是成功代理：")
print("="*80)

# 分别显示标准端口和非标准端口代理
if standard_proxies:
    print("\nCF标准端口代理:")
    for proxy in standard_proxies:
        parts = proxy.split('#')
        if len(parts) >= 2:
            ip_port = parts[0]
            status = parts[1]
            display_proxy = f"{ip_port} ({status})"
        else:
            display_proxy = proxy
        print(f"  ✓ {display_proxy}")

if non_standard_proxies:
    print("\n非CF标准端口代理:")
    for proxy in non_standard_proxies:
        parts = proxy.split('#')
        if len(parts) >= 2:
            ip_port = parts[0]
            status = parts[1]
            display_proxy = f"{ip_port} ({status})"
        else:
            display_proxy = proxy
        print(f"  ⚠ {display_proxy}")

print("="*80)
print(f"总共保存 {len(successful_proxies)} 个成功代理到 {SUCCESS_PROXY_FILE}")
print(f"CF标准端口代理: {len(standard_proxies)} 个 -> {STANDARD_PORTS_FILE}")
print(f"非CF标准端口代理: {len(non_standard_proxies)} 个 -> {NON_STANDARD_FILE}")
print(f"完整curl响应（所有代理）已保存到 {FULL_RESPONSES_FILE}")
print("="*80)