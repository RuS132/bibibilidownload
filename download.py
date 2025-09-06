import streamlit as st
import requests
import time
from typing import Optional, Tuple  # 用于类型提示，提升代码可读性

def upload_to_transfersh(audio_data: bytes, filename: str = "bilibili_audio.m4a", mime_type: str = "audio/m4a") -> Optional[str]:
    """适配 transfer.sh 的上传函数，无需注册，支持大文件"""
    API_URL = "https://transfer.sh"
    files = {"file": (filename, audio_data, mime_type)}
    
    try:
        st.info(f"正在上传音频到 transfer.sh（文件名：{filename}）...")
        # transfer.sh 需在 URL 后拼接文件名（否则默认生成随机名）
        response = requests.post(
            url=f"{API_URL}/{filename}",
            files=files,
            timeout=60,  # 适配大文件，延长超时时间
            headers={"User-Agent": "BilibiliAudioUploader/1.0"}
        )
        
        if response.status_code == 200:
            file_link = response.text.strip()
            # transfer.sh 链接格式为 "https://transfer.sh/xxx/filename"
            if file_link.startswith("https://transfer.sh/"):
                st.success(f"✅ 上传成功！\n访问链接：{file_link}")
                return file_link
            else:
                st.error(f"❌ 返回无效链接：{file_link[:50]}...")
        else:
            st.error(f"❌ 上传失败（HTTP {response.status_code}）：{response.text.strip()}")
    
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
                                st.info(f"音频已下载（大小：{len(audio_data)/1024/1024:.1f}MB），正在上传到 0x0.st...")
                                # 调用重写后的 0x0.st 上传函数
                                # 调用 transfer.sh 上传函数（无需过期时间/秘密URL参数，服务默认保留14天）
                                file_link = upload_to_transfersh(audio_data=audio_data)
                                if file_link:
                                    st.success("✅ 音频处理完成！")
                                    # 展示结果（补充 0x0.st 专属提示）
                                    st.markdown(f"### 🔗 可访问的音频链接：\n\n{file_link}")
                                    st.markdown(f"[点击下载音频]({file_link})")
                                    # 显示管理令牌（便于用户后续删除文件）
                                    if manage_token:
                                        st.markdown(f"### 🔑 文件管理令牌（请保存）：\n\n`{manage_token}`")
                                        st.caption("提示：使用令牌可通过 0x0.st API 删除文件或修改过期时间")
                                    # 计算并显示过期时间（提升用户感知）
                                    expire_time = time.strftime("%Y-%m-%d %H:%M:%S", 
                                                              time.localtime(time.time() + expires_hours * 3600))
                                    st.caption(f"⚠️ 注意：此链接将在 {expire_time} 过期（{expires_hours} 小时后），过期后文件自动删除")
                                else:
                                    st.error("文件上传失败，请稍后重试。")
