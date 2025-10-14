#!/usr/bin/env python3
"""
Fanable Referral Bot with Proxy Support
Python version converted from index.deobfuscated.js
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import aiohttp
from eth_account import Account
from eth_account.messages import encode_defunct

# Enable unaudited HD wallet features
Account.enable_unaudited_hdwallet_features()


# API Endpoints
SIGN_URL = "https://bqe6ojyqj7.execute-api.eu-central-1.amazonaws.com/wallet/signature"
REFERRAL_URL = "https://bqe6ojyqj7.execute-api.eu-central-1.amazonaws.com/wallet/referral"
SOCIAL_URL = "https://bqe6ojyqj7.execute-api.eu-central-1.amazonaws.com/wallet/social"
WALLET_DETAILS_BASE = "https://bqe6ojyqj7.execute-api.eu-central-1.amazonaws.com/wallet/"

# Configuration
PROXY_FILE = "config/proxy.txt"
ADDRESSES_FILE = "config/addresses.txt"
PRIVATE_KEYS_FILE = "config/private_keys.txt"
ITERATION_DELAY_MS = 5000  # milliseconds
MAX_TIMESTAMP_RETRIES = 5
TIMESTAMP_RETRY_DELAY_MS = 1500  # milliseconds
DEBUG_MODE = False  # 设置为 False 可关闭调试输出

# Common HTTP Headers
COMMON_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://points.fanable.io",
    "referer": "https://points.fanable.io/",
    "sec-ch-ua": '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"
}



class Colors:
    """ANSI 颜色代码"""
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    BLUE = "\033[34m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def styled_log(message: str, color: str = Colors.CYAN):
    """打印彩色日志"""
    print(f"{color}{message}{Colors.RESET}")


def success(message: str):
    """成功消息（绿色）"""
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")


def error(message: str):
    """错误消息（红色）"""
    print(f"{Colors.RED}✗ {message}{Colors.RESET}")


def warning(message: str):
    """警告消息（黄色）"""
    print(f"{Colors.YELLOW}⚠ {message}{Colors.RESET}")


def info(message: str):
    """信息消息（蓝色）"""
    print(f"{Colors.BLUE}ℹ {message}{Colors.RESET}")


def parse_response(data: Any) -> str:
    """解析响应数据为可读文本"""
    if isinstance(data, dict):
        if "message" in data:
            return data["message"]
        if "error" in data:
            return data["error"]
        if "status" in data:
            return f"状态: {data['status']}"
        if "success" in data:
            return f"成功: {data['success']}"
        if "points" in data:
            return f"获得积分: {data['points']}"
        # 简化显示关键信息
        key_fields = ["points", "referrals", "tasks", "success", "code"]
        result = []
        for field in key_fields:
            if field in data:
                result.append(f"{field}: {data[field]}")
        return ", ".join(result) if result else "操作完成"
    return str(data)


def debug_response(data: Any, context: str = ""):
    """调试响应数据"""
    if not DEBUG_MODE:
        return
    
    if isinstance(data, dict):
        print(f"  [DEBUG {context}] 完整响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
    else:
        print(f"  [DEBUG {context}] 原始响应: {data}")


async def load_proxies() -> List[str]:
    """加载代理列表"""
    try:
        proxy_path = Path(PROXY_FILE)
        if not proxy_path.exists():
            warning(f"未找到代理文件 {PROXY_FILE}，将不使用代理运行")
            return []
        
        content = proxy_path.read_text(encoding="utf-8")
        proxies = [line.strip() for line in content.split("\n") if line.strip()]
        
        if not proxies:
            return []
        
        info(f"已加载 {len(proxies)} 个代理")
        return proxies
    except Exception as e:
        warning(f"读取代理文件失败：{e}")
        return []


def save_wallet_info(address: str, private_key: str):
    """保存钱包地址和私钥到文件"""
    try:
        # 保存地址
        with open(ADDRESSES_FILE, "a", encoding="utf-8") as f:
            f.write(f"{address}\n")
        
        # 保存私钥
        with open(PRIVATE_KEYS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{private_key}\n")
        
        success(f"钱包信息已保存")
    except Exception as e:
        error(f"保存钱包信息失败：{e}")


def create_wallet() -> tuple[str, str]:
    """Create a random Ethereum wallet
    
    Returns:
        Tuple of (address, private_key)
    """
    account = Account.create()
    return account.address, account.key.hex()


def sign_message(private_key: str, message: str) -> str:
    """Sign a message with private key
    
    Args:
        private_key: Hex string of private key
        message: Message to sign
        
    Returns:
        Signature as hex string with 0x prefix
    """
    account = Account.from_key(private_key)
    message_hash = encode_defunct(text=message)
    signed_message = account.sign_message(message_hash)
    # Add 0x prefix to match JavaScript ethers.js format
    signature_hex = signed_message.signature.hex()
    if not signature_hex.startswith('0x'):
        signature_hex = '0x' + signature_hex
    return signature_hex


async def fetch_with_proxy(
    session: aiohttp.ClientSession,
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict] = None,
    proxy: Optional[str] = None
) -> tuple[int, str]:
    """Fetch with optional proxy
    
    Returns:
        Tuple of (status_code, response_text)
    """
    try:
        async with session.request(
            method,
            url,
            headers=headers,
            json=json_data,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            text = await response.text()
            return response.status, text
    except Exception as e:
        raise Exception(f"Request failed: {e}")


async def sign_and_get_token_with_retries(
    session: aiohttp.ClientSession,
    address: str,
    private_key: str,
    proxy: Optional[str] = None
) -> str:
    """签名并获取认证令牌（支持重试）"""
    
    for attempt in range(1, MAX_TIMESTAMP_RETRIES + 1):
        timestamp = int(time.time() * 1000)  # 毫秒
        message_to_sign = f"Fanable Rewards {timestamp}"
        
        if attempt > 1:
            info(f"  正在重试签名... (第 {attempt} 次)")
        
        # 签名消息
        signature = sign_message(private_key, message_to_sign)
        
        payload = {
            "signature": signature,
            "timestamp": timestamp,
            "address": address.lower()
        }
        
        # 发送签名请求
        status, response_text = await fetch_with_proxy(
            session,
            SIGN_URL,
            method="POST",
            headers=COMMON_HEADERS,
            json_data=payload,
            proxy=proxy
        )
        
        # 解析响应
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError:
            error(f"  服务器返回非JSON格式数据")
            raise Exception("签名端点返回非JSON格式")
        
        # 检查是否获取到token
        if response_data.get("token"):
            return response_data["token"]
        
        # 检查时间戳错误
        code = response_data.get("code", "")
        message = response_data.get("message", "").lower()
        
        if code == "INVALID_TIMESTAMP" or "timestamp" in message:
            if attempt < MAX_TIMESTAMP_RETRIES:
                warning(f"  时间戳无效，{TIMESTAMP_RETRY_DELAY_MS/1000}秒后重试...")
                await asyncio.sleep(TIMESTAMP_RETRY_DELAY_MS / 1000)
                continue
            else:
                raise Exception("已达到最大重试次数（时间戳无效）")
        
        raise Exception(f"签名失败：{parse_response(response_data)}")
    
    raise Exception("签名流程异常结束")


async def call_referral(
    session: aiohttp.ClientSession,
    token: str,
    referral_code: str,
    proxy: Optional[str] = None
) -> dict:
    """调用推荐接口"""
    
    payload = {"referralCode": referral_code}
    headers = {**COMMON_HEADERS, "authorization": f"Bearer {token}"}
    
    status, response_text = await fetch_with_proxy(
        session,
        REFERRAL_URL,
        method="POST",
        headers=headers,
        json_data=payload,
        proxy=proxy
    )
    
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return {"raw": response_text}


async def call_social(
    session: aiohttp.ClientSession,
    token: str,
    task_data: Dict[str, str],
    proxy: Optional[str] = None
) -> dict:
    """调用社交任务接口"""
    
    headers = {**COMMON_HEADERS, "authorization": f"Bearer {token}"}
    
    status, response_text = await fetch_with_proxy(
        session,
        SOCIAL_URL,
        method="POST",
        headers=headers,
        json_data=task_data,
        proxy=proxy
    )
    
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return {"raw": response_text}


async def get_wallet_details(
    session: aiohttp.ClientSession,
    token: str,
    address: str,
    proxy: Optional[str] = None
) -> dict:
    """获取钱包详情"""
    
    url = WALLET_DETAILS_BASE + address
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {token}"
    }
    
    status, response_text = await fetch_with_proxy(
        session,
        url,
        method="GET",
        headers=headers,
        proxy=proxy
    )
    
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return {"raw": response_text}


def display_banner():
    """显示横幅"""
    styled_log("Fanable Bot v1.0", Colors.CYAN + Colors.BOLD)
    print()


async def main():
    """Main execution"""
    
    try:
        # Display banner
        display_banner()
        
        # Load proxies
        proxies = await load_proxies()
        
        # 获取推荐数量
        count_input = input(f"{Colors.YELLOW}请输入要发送的推荐数量: {Colors.RESET}").strip()
        try:
            referral_count = int(count_input)
            if referral_count <= 0:
                raise ValueError
        except ValueError:
            error("无效的数字，程序退出")
            return
        
        # 获取推荐码
        referral_code = input(f"{Colors.YELLOW}请输入推荐码: {Colors.RESET}").strip()
        if not referral_code:
            error("推荐码为空，程序退出")
            return
        
        print()
        info(f"开始执行任务，共 {referral_count} 次迭代")
        if DEBUG_MODE:
            warning("调试模式已开启，将显示详细的API响应信息")
        print()
        
        # Create aiohttp session
        async with aiohttp.ClientSession() as session:
            # 主循环 - 创建钱包并发送推荐
            for iteration in range(1, referral_count + 1):
                styled_log(f"\n{'='*60}", Colors.CYAN)
                styled_log(f"  第 {iteration} / {referral_count} 次迭代", Colors.BOLD + Colors.MAGENTA)
                styled_log(f"{'='*60}", Colors.CYAN)
                
                # 选择代理（轮询）
                proxy = None
                if proxies:
                    proxy_string = proxies[(iteration - 1) % len(proxies)]
                    proxy = f"http://{proxy_string}" if not proxy_string.startswith("http") else proxy_string
                    info(f"使用代理: {proxy_string}")
                else:
                    warning("未使用代理")
                
                # 生成随机钱包
                address, private_key = create_wallet()
                styled_log("\n🔐 钱包已生成", Colors.CYAN)
                print(f"   地址: {Colors.GREEN}{address}{Colors.RESET}")
                print(f"   私钥: {Colors.YELLOW}{private_key}{Colors.RESET}")
                
                # 保存钱包信息
                save_wallet_info(address, private_key)
                
                await asyncio.sleep(0.3)
                
                # 签名并获取 token
                print()
                info("正在签名并获取认证令牌...")
                try:
                    token = await sign_and_get_token_with_retries(
                        session, address, private_key, proxy
                    )
                    success("认证令牌获取成功")
                except Exception as e:
                    error(f"获取令牌失败: {e}")
                    
                    if iteration < referral_count:
                        warning(f"等待 {ITERATION_DELAY_MS/1000} 秒后继续下一次...")
                        await asyncio.sleep(ITERATION_DELAY_MS / 1000)
                    continue
                
                # 发送推荐
                print()
                info(f'正在发送推荐码: {Colors.YELLOW}{referral_code}{Colors.RESET}')
                try:
                    referral_response = await call_referral(
                        session, token, referral_code, proxy
                    )
                    result_msg = parse_response(referral_response)
                    success(f"推荐发送成功 - {result_msg}")
                    # 调试输出完整响应
                    debug_response(referral_response, "推荐")
                except Exception as e:
                    error(f"推荐发送失败: {e}")
                
                # 完成社交任务
                print()
                styled_log("📱 开始执行社交任务", Colors.CYAN)
                wallet_address = address.lower()
                
                task_names = {
                    "TWITTER_FOLLOW": "Twitter 关注",
                    "FACEBOOK_FOLLOW": "Facebook 关注",
                    "INSTAGRAM_FOLLOW": "Instagram 关注",
                    "DISCROD_JOIN": "Discord 加入",
                    "YOUTUBE_SUBSCRIBE": "YouTube 订阅"
                }
                
                social_tasks = [
                    {"address": wallet_address, "type": "TWITTER_FOLLOW"},
                    {"address": wallet_address, "type": "FACEBOOK_FOLLOW"},
                    {"address": wallet_address, "type": "INSTAGRAM_FOLLOW"},
                    {"address": wallet_address, "type": "DISCROD_JOIN"},
                    {"address": wallet_address, "type": "YOUTUBE_SUBSCRIBE"}
                ]
                
                for i, task in enumerate(social_tasks, 1):
                    task_type = task['type']
                    task_name = task_names.get(task_type, task_type)
                    print(f"   [{i}/5] {task_name}...", end=" ")
                    
                    try:
                        social_response = await call_social(session, token, task, proxy)
                        result_msg = parse_response(social_response)
                        success(result_msg)
                        # 调试输出完整响应
                        debug_response(social_response, f"社交任务-{task_type}")
                    except Exception as e:
                        error(str(e))
                    
                    await asyncio.sleep(0.7)
                
                # 获取钱包详情
                print()
                info("正在获取钱包详情...")
                try:
                    details = await get_wallet_details(
                        session, token, wallet_address, proxy
                    )
                    if isinstance(details, dict):
                        points = details.get("points", "未知")
                        referrals = details.get("referralCount", "未知")
                        success(f"积分: {points}, 推荐数: {referrals}")
                        # 调试输出完整响应
                        debug_response(details, "钱包详情")
                    else:
                        success("钱包详情获取成功")
                        debug_response(details, "钱包详情")
                except Exception as e:
                    error(f"获取详情失败: {e}")
                
                # 等待下次迭代
                if iteration < referral_count:
                    print()
                    warning(f"等待 {ITERATION_DELAY_MS/1000} 秒后进行下一次迭代...")
                    await asyncio.sleep(ITERATION_DELAY_MS / 1000)
            
            # 完成所有任务
            print()
            styled_log("="*60, Colors.GREEN)
            styled_log("✅  所有任务已完成！", Colors.GREEN + Colors.BOLD)
            styled_log("="*60, Colors.GREEN)
            info(f"钱包信息已保存到 {ADDRESSES_FILE} 和 {PRIVATE_KEYS_FILE}")
    
    except KeyboardInterrupt:
        print()
        warning("程序被用户中断")
    except Exception as e:
        print()
        error(f"发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

