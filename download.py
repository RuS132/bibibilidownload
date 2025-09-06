import streamlit as st
import requests
import re
import time
import hashlib

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

def upload_to_fileio(audio_data, expires=None, max_downloads=None, auto_delete=True):
    """
    上传音频数据到 file.io 并返回文件访问链接
    
    参数说明：
    - audio_data: 音频二进制数据（如文件读取后的bytes对象）
    - expires: 可选，文件过期时间（格式：符合file.io TimePeriod规范，如"7d"表示7天、"12h"表示12小时，默认无过期限制）
    - max_downloads: 可选，文件最大下载次数（整数，默认无限制）
    - auto_delete: 可选，是否在达到最大下载次数/过期后自动删除（布尔值，默认True）
    
    返回值：
    - 成功：file.io 生成的文件访问链接（string）
    - 失败：None
    """
    # 1. 配置 file.io 核心参数（参考API文档：https://www.file.io/developers）
    FILE_IO_API_URL = "https://file.io"  # file.io 主服务地址
    audio_filename = "bilibili_audio.m4a"  # 音频文件名（保持原函数命名逻辑）
    audio_mime_type = "audio/m4a"  # 音频MIME类型
    
    # 2. 构造 multipart/form-data 请求体（file.io 要求的格式）
    # 核心参数：file（二进制文件）、expires（过期时间）、maxDownloads（最大下载次数）、autoDelete（自动删除）
    files = {
        "file": (audio_filename, audio_data, audio_mime_type)  # 必选：音频文件数据
    }
    # 可选参数：仅在传入有效值时添加（避免传递默认空值导致接口重置）
    data = {}
    if expires:
        data["expires"] = expires  # 示例："7d"（7天过期）、"24h"（24小时过期）
    if max_downloads is not None and isinstance(max_downloads, int) and max_downloads > 0:
        data["maxDownloads"] = max_downloads  # 示例：5（最多下载5次）
    data["autoDelete"] = auto_delete  # 默认为True，符合file.io自动清理逻辑

    try:
        # 3. 发送POST请求（file.io 仅支持POST上传，超时时间保留原函数30秒）
        response = requests.post(
            url=FILE_IO_API_URL,
            files=files,
            data=data,  # 传递可选参数（过期时间、下载次数等）
            timeout=30,
            headers={"Accept": "application/json"}  # 明确要求返回JSON格式响应
        )
        
        # 4. 解析响应（file.io 返回JSON格式，包含success状态和fileDetails信息）
        # 参考file.io API响应示例：{"success":true,"id":"xxx","key":"xxx","link":"https://file.io/xxx"...}
        if response.status_code == 200:
            try:
                response_json = response.json()
                # 检查上传是否成功（file.io 用success字段标识）
                if response_json.get("success"):
                    file_link = response_json.get("link")
                    # 验证链接有效性（确保是file.io生成的HTTPS链接）
                    if file_link and file_link.startswith("https://file.io/"):
                        st.success(f"文件上传成功！访问链接：{file_link}")
                        # 可选：返回链接时附带过期时间/下载次数信息（便于后续管理）
                        return file_link
                    else:
                        st.error(f"file.io 返回无效链接：{file_link}")
                else:
                    # 上传失败：提取错误信息（file.io 可能返回status和message字段）
                    error_msg = response_json.get("message", "未知错误")
                    st.error(f"file.io 上传失败：{error_msg}（状态码：{response_json.get('status')}）")
            
            except ValueError:
                # 异常情况：响应不是JSON格式（file.io 标准接口不会出现，仅做容错）
                st.error(f"file.io 响应格式异常，非JSON数据：{response.text[:100]}...")
        
        else:
            # HTTP状态码非200：返回状态码和响应内容（便于排查问题）
            st.error(
                f"file.io 上传请求失败\n"
                f"HTTP状态码：{response.status_code}\n"
                f"响应内容：{response.text[:200]}..."  # 限制内容长度，避免日志过长
            )
    
    except requests.exceptions.RequestException as e:
        # 网络异常：如超时、连接失败等（保留原函数的异常捕获逻辑）
        st.error(f"file.io 上传请求异常：{str(e)}")
    
    # 所有失败场景均返回None
    return None


# Streamlit UI
st.title("B站音频下载工具 🎵")
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
