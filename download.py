import streamlit as st
import requests
import re
import time
import hashlib
from bs4 import BeautifulSoup
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
    expires: Optional[str] = "7d",  # 默认7天过期（符合临时音频使用场景）
    max_downloads: Optional[int] = 5,  # 默认最多5次下载（避免链接泄露后滥用）
    auto_delete: bool = True,
    retry_count: int = 2
) -> Optional[str]:
    """
    终极适配版 file.io API 上传函数：确保请求被识别为API调用，而非浏览器访问
    
    核心改进：
    1. 增加API专用请求头（X-Requested-With、Referer）
    2. 固定multipart/form-data参数顺序（file字段必须第一个）
    3. 规范User-Agent为API调用标识
    4. 强制校验请求格式，避免服务端误判
    """
    # 1. 前置校验：排除明显无效请求
    if not audio_data:
        st.error("❌ 音频数据为空，无法上传")
        return None
    file_size_mb = len(audio_data) / (1024 * 1024)
    if file_size_mb > 512:  # 参考file.io免费版常见限制（512MB，避免返回网页提示“文件过大”）
        st.error(f"❌ 文件超过512MB限制（当前{file_size_mb:.1f}MB），请压缩后上传")
        return None

    # 2. 配置 file.io API 核心参数（严格遵循官方规范）
    API_URL = "https://file.io"
    # 关键：API专用请求头（让服务端识别为API调用，而非浏览器访问）
    headers = {
        "User-Agent": "FileIO-API-Client/1.0 (Python; AudioUploadScenario)",  # 明确API客户端标识
        "Accept": "application/json",  # 强制要求JSON响应
        "X-Requested-With": "XMLHttpRequest",  # 模拟AJAX请求（file.io API关键识别头）
        "Referer": "https://file.io/developers",  # 关联API文档页，提升请求合法性
        "DNT": "1"  # 可选：减少服务端跟踪，降低拦截概率
    }

    # 3. 构造请求体：固定参数顺序（file字段必须第一个，否则可能被解析为网页上传）
    # 注意：requests库的files参数会按字典顺序传递，需用OrderedDict保证顺序（Python 3.7+字典默认有序，仍显式声明更安全）
    from collections import OrderedDict
    files = OrderedDict()
    # 第一个参数必须是file：符合file.io API参数顺序要求
    files["file"] = (audio_filename, audio_data, audio_mime_type)
    
    # 构造data参数（仅传递有效值，且顺序固定）
    data = OrderedDict()
    if expires:
        # 校验expires格式（避免因格式错误返回网页）
        valid_units = {"y", "Q", "M", "w", "d", "h", "m", "s"}
        if not (expires[:-1].isdigit() and expires[-1] in valid_units):
            st.error(f"❌ 过期时间格式错误（{expires}），需为「数字+单位」（如7d=7天、12h=12小时）")
            return None
        data["expires"] = expires
    if max_downloads is not None and isinstance(max_downloads, int) and max_downloads > 0:
        data["maxDownloads"] = max_downloads
    data["autoDelete"] = auto_delete

    # 4. 带重试的请求逻辑（针对临时网络/服务端波动）
    for attempt in range(retry_count + 1):
        try:
            st.info(f"🔄 第{attempt+1}/{retry_count+1}次上传...")
            response = requests.post(
                url=API_URL,
                files=files,
                data=data,
                headers=headers,
                timeout=30,
                verify=True,  # 启用SSL校验（避免被劫持至虚假网页）
                allow_redirects=False  # 禁止重定向（若被重定向到登录页，直接判定为请求无效）
            )

            # 5. 响应处理：分场景精准判断
            # 场景1：请求被识别为API（状态码200且响应为JSON）
            if response.status_code == 200:
                try:
                    resp_json = response.json()
                    # API成功响应
                    if resp_json.get("success"):
                        file_link = resp_json["link"]
                        st.success(f"✅ 上传成功！\n📎 链接：{file_link}\n⏳ 过期时间：{resp_json.get('expires', '无限制')}\n📥 最大下载：{resp_json.get('maxDownloads', '无限制')}次")
                        return file_link
                    # API失败响应（返回JSON格式错误）
                    else:
                        error_msg = resp_json.get("message", "未知错误")
                        st.error(f"❌ API拒绝上传：{error_msg}")
                        break  # 客户端参数错误，无需重试

                # 场景2：仍返回网页（最后尝试提取网页中的错误原因）
                except ValueError:
                    soup = BeautifulSoup(response.text, "html.parser")
                    # 提取file.io网页中的错误提示（如“文件过大”“格式不支持”）
                    error_elem = soup.find("div", class_="alert-error") or soup.find("div", role="alert")
                    if error_elem:
                        error_text = error_elem.get_text(strip=True)
                        st.error(f"❌ 服务端网页提示错误：{error_text}")
                    else:
                        st.error(f"❌ 仍返回网页界面（非API响应），请检查请求头配置")
                    # 仅当是临时错误（如服务端负载高）才重试
                    if attempt < retry_count:
                        st.info(f"⌛ 10秒后重试（服务端临时误判）...")
                        time.sleep(10)
                    else:
                        break

            # 场景3：请求被重定向（通常是引导到登录/注册页，判定为请求无效）
            elif response.status_code in [301, 302, 307]:
                st.error(f"❌ 请求被重定向（{response.status_code}），可能因请求头不规范被判定为浏览器访问")
                st.info(f"🔍 重定向目标：{response.headers.get('Location', '未知')}")
                break

            # 场景4：其他HTTP错误（如429限流、413文件过大）
            else:
                st.error(f"❌ HTTP错误 {response.status_code}")
                # 尝试提取错误信息（无论JSON还是HTML）
                try:
                    resp_json = response.json()
                    st.error(f"📝 API错误详情：{resp_json.get('message')}")
                except ValueError:
                    soup = BeautifulSoup(response.text, "html.parser")
                    error_text = soup.get_text(strip=True)[:150]
                    st.error(f"📝 网页错误详情：{error_text}...")
                # 仅限流（429）和服务端错误（5xx）重试
                if response.status_code in [429, 500, 502, 503] and attempt < retry_count:
                    wait_time = 5 * (attempt + 1)
                    st.info(f"⌛ {wait_time}秒后重试（{response.status_code}临时错误）...")
                    time.sleep(wait_time)
                else:
                    break

        # 场景5：网络异常（超时、连接失败）
        except requests.exceptions.RequestException as e:
            st.error(f"❌ 网络异常：{str(e)}")
            if attempt < retry_count:
                wait_time = 5 * (attempt + 1)
                st.info(f"⌛ {wait_time}秒后重试（网络波动）...")
                time.sleep(wait_time)
            else:
                st.error(f"❌ 所有重试均失败，网络问题未解决")
                break

    st.error("💥 文件上传最终失败，请参考上述错误提示调整参数")
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
