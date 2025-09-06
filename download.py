import streamlit as st
import requests
import re
import time
import hashlib
from typing import Optional

def extract_bvid(url):
    match = re.search(r'(BV[\w]+)', url)
    return match.group(1) if match else None

def get_cid(bvid):
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if response.status_code == 200:
        return response.json()["data"]["cid"]
    return None

def get_wbi_keys():
    nav_url = "https://api.bilibili.com/x/web-interface/nav"
    response = requests.get(nav_url, headers={"User-Agent": "Mozilla/5.0"})
    if response.status_code == 200:
        wbi_img = response.json()["data"]["wbi_img"]
        img_key = wbi_img["img_url"].split("/")[-1].split(".")[0]
        sub_key = wbi_img["sub_url"].split("/")[-1].split(".")[0]
        return img_key, sub_key
    return None, None

def generate_wbi_sign(params, img_key, sub_key):
    mix_key = img_key + sub_key
    params = dict(sorted(params.items()))
    params_str = "&".join([f"{k}={v}" for k, v in params.items()])
    sign_str = params_str + mix_key
    return hashlib.md5(sign_str.encode()).hexdigest()

def get_audio_url(bvid, cid):
    img_key, sub_key = get_wbi_keys()
    if not img_key or not sub_key:
        return None

    wts = int(time.time())
    params = {
        "bvid": bvid,
        "cid": cid,
        "qn": 80,
        "fnver": 0,
        "fnval": 4048,
        "fourk": 1,
        "wts": wts
    }
    
    params["w_rid"] = generate_wbi_sign(params, img_key, sub_key)
    url = "https://api.bilibili.com/x/player/wbi/playurl"
    
    response = requests.get(
        url,
        params=params,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Referer": f"https://www.bilibili.com/video/{bvid}"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        return data["data"]["dash"]["audio"][0]["baseUrl"]
    return None

def download_audio(url, referer):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Referer": referer
    }
    response = requests.get(url, headers=headers, stream=True)
    if response.status_code == 200:
        return response.content
    return None

def upload_to_fileio(
    audio_data: bytes,
    audio_filename: str = "bilibili_audio.m4a",
    audio_mime_type: str = "audio/m4a",
    expires: Optional[str] = None,
    max_downloads: Optional[int] = None,
    auto_delete: bool = True,
    retry_count: int = 2  # 临时错误重试次数
) -> Optional[str]:
    """
    优化版 file.io 音频上传函数：补充参数校验、异常解析、重试机制
    
    参数说明：
    - audio_data: 音频二进制数据（必须非空）
    - audio_filename: 音频文件名（默认保留原命名）
    - audio_mime_type: 音频MIME类型（确保与文件格式匹配，如m4a对应audio/m4a）
    - expires: 文件过期时间（需符合file.io TimePeriod规范，如"7d"=7天、"12h"=12小时，None表示无限制）
    - max_downloads: 最大下载次数（正整数，None表示无限制）
    - auto_delete: 过期/达下载次数后自动删除（bool，默认True）
    - retry_count: 临时错误重试次数（默认2次，避免网络波动导致失败）
    
    返回值：
    - 成功：file.io 文件访问链接（str）
    - 失败：None
    """
    # 1. 前置参数校验（避免无效请求）
    if not audio_data:
        st.error("错误：音频数据为空，无法上传")
        return None
    if len(audio_data) > 5 * 1024 * 1024 * 1024:  # 临时限制：file.io 免费版通常≤5GB（需参考官方最新政策）
        st.error(f"错误：文件大小超过5GB（当前{len(audio_data)/1024/1024:.1f}MB），无法上传")
        return None
    
    # 2. 配置 file.io 基础信息
    FILE_IO_API_URL = "https://file.io"
    # 规范请求头：明确 User-Agent（避免被判定为非法请求）、Accept（要求JSON响应）
    headers = {
        "User-Agent": "AudioUploader/1.0 (https://your-app-url.com; contact@your-email.com)",  # 替换为你的应用标识
        "Accept": "application/json"  # 强制要求服务端返回JSON格式
    }
    
    # 3. 构造请求体（严格遵循file.io multipart/form-data格式）
    files = {
        "file": (audio_filename, audio_data, audio_mime_type)  # 必选：file字段（名称、数据、MIME类型）
    }
    data = {}
    # 可选参数：仅传递有效值（避免空值导致接口解析错误）
    if expires:
        # 校验 expires 格式（符合file.io TimePeriod规范：数字+单位，如1y/1Q/1M/1w/1d/1h/1m/1s）
        valid_units = {"y", "Q", "M", "w", "d", "h", "m", "s"}
        if not (expires[:-1].isdigit() and expires[-1] in valid_units):
            st.error(f"错误：expires格式无效（{expires}），需符合如'7d'（7天）、'12h'（12小时）的规范")
            return None
        data["expires"] = expires
    if max_downloads is not None:
        if isinstance(max_downloads, int) and max_downloads > 0:
            data["maxDownloads"] = max_downloads
        else:
            st.error(f"错误：max_downloads必须为正整数（当前{max_downloads}）")
            return None
    data["autoDelete"] = auto_delete  # 布尔值需正确传递（requests会自动处理格式）

    # 4. 发送请求（带重试机制）
    for attempt in range(retry_count + 1):
        try:
            st.info(f"正在上传（第{attempt+1}/{retry_count+1}次尝试）...")
            response = requests.post(
                url=FILE_IO_API_URL,
                files=files,
                data=data,
                headers=headers,
                timeout=30,  # 超时时间保留30秒，避免长期阻塞
                verify=True  # 启用SSL证书验证（防止中间人攻击，file.io支持HTTPS）
            )
            
            # 5. 响应解析（分场景处理：JSON正常响应、HTML错误响应、其他异常）
            # 场景1：HTTP状态码200（尝试解析JSON）
            if response.status_code == 200:
                # 优先尝试JSON解析（符合file.io标准接口）
                try:
                    resp_json = response.json()
                    if resp_json.get("success"):
                        file_link = resp_json.get("link")
                        if file_link and file_link.startswith("https://file.io/"):
                            st.success(f"上传成功！\n链接：{file_link}\n过期时间：{resp_json.get('expires', '无限制')}\n最大下载次数：{resp_json.get('maxDownloads', '无限制')}")
                            return file_link
                        else:
                            st.error(f"错误：file.io 返回无效链接：{file_link}")
                            break  # 链接无效，无需重试
                    else:
                        # JSON格式但上传失败（提取服务端错误信息）
                        error_msg = resp_json.get("message", "未知错误")
                        error_status = resp_json.get("status", "未知状态")
                        st.error(f"上传失败（服务端拒绝）：{error_msg}（状态码：{error_status}）")
                        # 判断是否需要重试：临时错误（如限流）可重试，永久错误（如参数无效）不重试
                        if error_status in [429]:  # 429通常为限流（Too Many Requests）
                            if attempt < retry_count:
                                st.info(f"将在5秒后重试（限流临时错误）...")
                                time.sleep(5)  # 等待5秒后重试，避免频繁请求
                            else:
                                st.error(f"已达最大重试次数（{retry_count+1}次），请稍后再试")
                                break
                        else:
                            break  # 永久错误（如参数无效），无需重试
                
                # 场景2：响应不是JSON（返回HTML，可能是服务端临时错误）
                except ValueError:
                    # 解析HTML中的错误提示（提取<body>内容，排除标签）
                    from bs4 import BeautifulSoup  # 需安装：pip install beautifulsoup4
                    soup = BeautifulSoup(response.text, "html.parser")
                    error_text = soup.get_text(strip=True)[:200]  # 提取纯文本并限制长度
                    st.error(f"响应格式异常（非JSON）：{error_text}...")
                    # 临时错误（如服务端维护）可重试，否则终止
                    if attempt < retry_count:
                        st.info(f"将在10秒后重试（服务端临时异常）...")
                        time.sleep(10)
                    else:
                        st.error(f"已达最大重试次数，仍无法获取有效响应")
                        break
            
            # 场景3：HTTP状态码非200（如400参数错误、413文件过大、429限流）
            else:
                st.error(f"请求失败（HTTP状态码：{response.status_code}）")
                # 解析非200状态码的响应内容（可能是HTML或纯文本）
                try:
                    # 尝试解析JSON错误（部分场景服务端会返回）
                    resp_json = response.json()
                    st.error(f"服务端错误信息：{resp_json.get('message', '无')}")
                except ValueError:
                    # 解析HTML错误文本
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, "html.parser")
                    error_text = soup.get_text(strip=True)[:200]
                    st.error(f"错误详情：{error_text}...")
                # 判断是否重试：429（限流）、5xx（服务端错误）可重试，4xx（客户端错误）不重试
                if response.status_code in [429, 500, 502, 503, 504] and attempt < retry_count:
                    wait_time = 5 * (attempt + 1)  # 重试间隔递增（5s、10s、15s...）
                    st.info(f"将在{wait_time}秒后重试（{response.status_code}临时错误）...")
                    time.sleep(wait_time)
                else:
                    break  # 客户端错误（如400、413）或无重试次数，终止
    
        # 场景4：网络异常（如超时、连接失败）
        except requests.exceptions.RequestException as e:
            st.error(f"请求异常：{str(e)}")
            if attempt < retry_count:
                wait_time = 5 * (attempt + 1)
                st.info(f"将在{wait_time}秒后重试（网络异常）...")
                time.sleep(wait_time)
            else:
                st.error(f"已达最大重试次数，网络异常仍未解决")
                break
    
    # 所有尝试失败后返回None
    st.error("文件上传最终失败，请检查参数或稍后重试")
    return None


# Streamlit UI
st.title("B站音频下载工具 1🎵")
st.write("输入B站视频链接，获取音频文件的可访问链接")

video_url = st.text_input("视频链接：", placeholder="https://www.bilibili.com/video/BV...")

if st.button("生成音频链接"):
    if not video_url:
        st.error("请输入有效的视频链接")
    else:
        bvid = extract_bvid(video_url)
        if not bvid:
            st.error("链接格式不正确，请确认是B站视频链接")
        else:
            with st.spinner("解析视频信息中..."):
                cid = get_cid(bvid)
                if not cid:
                    st.error("无法获取视频信息，请检查链接是否正确")
                else:
                    audio_url = get_audio_url(bvid, cid)
                    if not audio_url:
                        st.error("无法获取音频地址，可能视频不支持")
                    else:
                        with st.spinner("正在下载并上传音频..."):
                            audio_data = download_audio(audio_url, video_url)
                            if not audio_data:
                                st.error("音频下载失败，请重试")
                            else:
                                st.info("音频已下载，正在上传...")
                                file_link = upload_to_fileio(audio_data)
                                if file_link:
                                    st.success("✅ 音频已上传！")
                                    st.markdown(f"### 🔗 可访问的音频链接：\n\n{file_link}")
                                    st.markdown(f"[点击下载音频]({file_link})")
                                    st.caption("注意：此链接由 file.io 提供，默认14天后失效。")
                                else:
                                    st.error("文件上传失败，请稍后重试。")
