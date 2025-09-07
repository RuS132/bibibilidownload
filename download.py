# -*- coding: utf-8 -*-
"""
B站音视频下载合并工具 - Streamlit Web 版（已修复 FFmpeg 问题）
"""

import os
import re
import json
import requests
import logging
import streamlit as st
import ffmpeg-python as ffmpeg # 使用 ffmpeg-python + Streamlit Cloud 预装 ffmpeg

# ================ 配置区 =================
VIDEO_DIR = os.path.join(os.getcwd(), "Bilibili")
os.makedirs(VIDEO_DIR, exist_ok=True)

# 🔴 请务必在部署后通过 Streamlit Secrets 替换以下 Cookie
# 获取方式：登录B站后，在浏览器开发者工具中复制 Cookie 字符串
COOKIE = "buvid3=xxx; LIVE_BUVID=xxx; SESSDATA=xxx; bili_jct=xxx; DedeUserID=xxx"

HEADERS = {
    'Referer': 'https://www.bilibili.com/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Cookie': COOKIE
}

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ================ 工具函数 =================
@st.cache_data
def get_bilibili_video_info(url):
    """解析B站视频信息，返回标题、视频链接、音频链接"""
    try:
        st.info("正在请求视频信息...")
        response = requests.get(url, headers={**HEADERS, 'Referer': url}, timeout=10)
        response.raise_for_status()
        html = response.text

        # 提取标题
        title_match = re.search(r'<title data-vue-meta="true">(.*?)_哔哩哔哩_bilibili</title>', html, re.S)
        title = title_match.group(1) if title_match else "未命名视频"
        title = re.sub(r'[\/\\\:\*\?\"\<\>\|]', '_', title).strip()

        # 提取 __playinfo__
        playinfo_match = re.search(r'__playinfo__=(.*?)</script>', html, re.S)
        if not playinfo_match:
            st.error("无法提取视频信息，请检查URL或Cookie权限。")
            return None, None, None

        data = json.loads(playinfo_match.group(1))
        dash = data['data']['dash']
        video_url = dash['video'][2]['base_url']  # 选清晰度较高的
        audio_url = dash['audio'][2]['base_url']

        return title, video_url, audio_url

    except Exception as e:
        logging.error(f"解析失败: {e}")
        st.error(f"解析失败: {e}")
        return None, None, None


def download_file(url, filename, desc="下载中"):
    try:
        st.info(f"📥 正在下载 {desc}...")
        with requests.get(url, headers=HEADERS, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
        st.success(f"✅ {desc}完成！")
        return True
    except Exception as e:
        st.error(f"❌ 下载失败: {e}")
        return False


def merge_video_audio(video_path, audio_path, output_path):
    """使用 ffmpeg 快速合并视频与音频"""
    try:
        st.info("⚡ 正在使用 FFmpeg 高速合并音视频...")
        (
            ffmpeg
            .input(video_path)
            .input(audio_path)
            .output(
                output_path,
                vcodec='libx264',
                acodec='aac',
                loglevel='quiet'
            )
            .run(overwrite_output=True)  # ✅ 移除了 timeout 参数
        )
        st.success("✅ 合并完成！")
        return True
    except Exception as e:
        logging.error(f"合并失败: {e}")
        st.error(f"❌ 合并失败: {e}")
        return False


# ================ Streamlit 主界面 =================
st.set_page_config(page_title="B站视频下载器", page_icon="🎬", layout="centered")
st.title("🎬 B站音视频下载合并工具")

st.markdown("""
> 输入 B站视频链接（如 `https://www.bilibili.com/video/BVxxxx`），自动下载并合并高清音视频。
>
> ⚠️ **注意**：
> - 需要登录 Cookie 才能访问高清资源，请确保 `COOKIE` 已正确配置。
> - 请勿用于商业或批量下载，遵守 B站 用户协议。
""")

url = st.text_input("请输入B站视频链接：", placeholder="https://www.bilibili.com/video/BV1nb421B7Y5")

if st.button("🔍 解析视频信息") and url:
    with st.spinner("正在解析..."):
        title, video_url, audio_url = get_bilibili_video_info(url)
        if title and video_url and audio_url:
            st.session_state.title = title
            st.session_state.video_url = video_url
            st.session_state.audio_url = audio_url
            st.success(f"✅ 解析成功！标题：《{title}》")

if hasattr(st.session_state, 'title'):
    st.write(f"**标题**：{st.session_state.title}")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 开始下载并合并"):
            tmp_video = "tmp_video.mp4"
            tmp_audio = "tmp_audio.mp3"
            output_path = os.path.join(VIDEO_DIR, f"{st.session_state.title}.mp4")

            success = True
            if success:
                success = download_file(st.session_state.video_url, tmp_video, "视频下载")
            if success:
                success = download_file(st.session_state.audio_url, tmp_audio, "音频下载")
            if success:
                if merge_video_audio(tmp_video, tmp_audio, output_path):
                    st.session_state.output_file = output_path
                    st.success(f"✅ 合并完成！文件已保存至：{output_path}")
                else:
                    success = False

            # 清理临时文件
            for tmp_file in [tmp_video, tmp_audio]:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)

            if not success:
                st.error("❌ 下载或合并失败，请查看日志。")

    with col2:
        if hasattr(st.session_state, 'output_file') and os.path.exists(st.session_state.output_file):
            with open(st.session_state.output_file, 'rb') as f:
                st.download_button(
                    label="📥 下载到本地",
                    data=f.read(),
                    file_name=f"{st.session_state.title}.mp4",
                    mime="video/mp4"
                )

# 显示已下载文件
if st.checkbox("查看已下载的视频文件"):
    files = [f for f in os.listdir(VIDEO_DIR) if f.endswith('.mp4')]
    if files:
        selected = st.selectbox("选择文件下载", files)
        file_path = os.path.join(VIDEO_DIR, selected)
        with open(file_path, 'rb') as f:
            st.download_button("📥 下载", f.read(), selected, "video/mp4")
    else:
        st.info("暂无已下载的视频文件。")


if st.button("🔍 检查 ffmpeg 包"):
    try:
        import ffmpeg
        st.write("📁 路径:", ffmpeg.__file__)
        st.write("🔧 类型:", type(ffmpeg))
        
        # 尝试创建 input
        try:
            stream = ffmpeg.input("test.mp4")
            st.success("✅ ffmpeg.input() 可用！包正确。")
        except Exception as e:
            st.error(f"❌ ffmpeg.input() 失败: {e}")
            
    except Exception as e:
        st.error(f"❌ 无法导入 ffmpeg: {e}")
