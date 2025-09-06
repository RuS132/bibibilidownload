import streamlit as st
import requests
import time
from typing import Optional, Tuple  # 用于类型提示，提升代码可读性

import requests
import streamlit as st

def upload_to_tmpfiles(audio_data: bytes, filename: str = "bilibili_audio.m4a", mime_type: str = "audio/m4a") -> Optional[str]:
    """
    上传音频到 tmpfiles.org（Streamlit Cloud 兼容）
    返回：成功则为文件访问链接，失败则为 None
    """
    # tmpfiles.org 官方 API 端点（支持 multipart/form-data 上传）
    API_URL = "https://tmpfiles.org/api/v1/upload"
    
    # 构造请求体（严格遵循 tmpfiles.org API 要求）
    files = {
        "file": (filename, audio_data, mime_type)  # 必选字段：文件二进制数据
    }
    # 可选参数：设置文件保留时间（默认 24 小时，支持 1h/6h/12h/24h/7d）
    data = {"expiry": "7d"}  # 此处设置保留 7 天，可根据需求调整
    
    try:
        st.info(f"正在上传音频到 tmpfiles.org（大小：{len(audio_data)/1024/1024:.1f}MB）...")
        response = requests.post(
            url=API_URL,
            files=files,
            data=data,
            timeout=60,  # 延长超时，适配大文件
            headers={"User-Agent": "BilibiliAudioUploader/1.0"}
        )
        
        # 解析 tmpfiles.org 的 JSON 响应（规范且易处理）
        if response.status_code == 200:
            resp_json = response.json()
            # 成功响应包含 "status": "success" 和 "data" 字段
            if resp_json.get("status") == "success":
                file_info = resp_json.get("data", {})
                file_link = file_info.get("url")  # 提取直接访问链接
                if file_link and file_link.startswith("https://"):
                    st.success(f"✅ 上传成功！文件将保留 7 天")
                    return file_link
                else:
                    st.error(f"❌ 未获取到有效链接：{file_info}")
            else:
                st.error(f"❌ 服务端拒绝：{resp_json.get('message', '未知错误')}")
        else:
            st.error(f"❌ HTTP 错误 {response.status_code}：{response.text[:100]}...")
    
    except Exception as e:
        st.error(f"❌ 上传异常：{str(e)}")
    return None


# ------------------- 以下为原代码适配修改（替换原 upload_to_fileio 调用逻辑） -------------------
def extract_bvid(url):
    import re
    match = re.search(r'(BV[\w]+)', url)
    return match.group(1) if match else None

def get_cid(bvid):
    import requests
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if response.status_code == 200:
        return response.json()["data"]["cid"]
    return None

def get_wbi_keys():
    import requests
    nav_url = "https://api.bilibili.com/x/web-interface/nav"
    response = requests.get(nav_url, headers={"User-Agent": "Mozilla/5.0"})
    if response.status_code == 200:
        wbi_img = response.json()["data"]["wbi_img"]
        img_key = wbi_img["img_url"].split("/")[-1].split(".")[0]
        sub_key = wbi_img["sub_url"].split("/")[-1].split(".")[0]
        return img_key, sub_key
    return None, None

def generate_wbi_sign(params, img_key, sub_key):
    import hashlib
    mix_key = img_key + sub_key
    params = dict(sorted(params.items()))
    params_str = "&".join([f"{k}={v}" for k, v in params.items()])
    sign_str = params_str + mix_key
    return hashlib.md5(sign_str.encode()).hexdigest()

def get_audio_url(bvid, cid):
    import requests
    import time
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
    import requests
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Referer": referer
    }
    response = requests.get(url, headers=headers, stream=True)
    if response.status_code == 200:
        return response.content
    return None


# Streamlit UI（仅修改上传函数调用部分，保持原交互逻辑）
st.title("B站音频下载工具 🎵")
st.write("输入B站视频链接，获取音频文件的可访问链接")

video_url = st.text_input("视频链接：", placeholder="https://www.bilibili.com/video/BV...")

# 新增：0x0.st 自定义配置选项（可选，提升用户灵活性）
with st.expander("📌 高级配置（可选）"):
    expires_hours = st.number_input("文件过期时间（小时，默认720小时=30天）", min_value=1, max_value=8760, value=720)
    use_secret_url = st.checkbox("生成秘密URL（防他人猜测）", value=False)

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
                                st.info(f"音频已下载（大小：{len(audio_data)/1024/1024:.1f}MB），正在上传...")
                                # 调用 tmpfiles.org 上传函数
                                file_link = upload_to_tmpfiles(audio_data=audio_data)
                                if file_link:
                                    st.success("✅ 音频处理完成！")
                                    st.markdown(f"### 🔗 可访问的音频链接：\n\n{file_link}")
                                    st.markdown(f"[点击下载音频]({file_link})")
                                    st.caption("⚠️ 注意：文件保留 7 天，过期后自动删除。")
                                else:
                                    st.error("文件上传失败，请稍后重试。")
