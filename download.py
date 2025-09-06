import streamlit as st
import requests
import time
from typing import Optional, Tuple  # 用于类型提示，提升代码可读性

def upload_to_0x0st(
    audio_data: bytes,
    filename: str = "bilibili_audio.m4a",
    mime_type: str = "audio/m4a",
    expires: Optional[str] = None,
    secret: bool = False,
    timeout: int = 30
) -> Tuple[Optional[str], Optional[str]]:
    """
    上传音频数据到 0x0.st，返回文件访问链接和管理令牌（用于后续删除/修改过期时间）
    
    参数说明（遵循 0x0.st API 规范）：
    - audio_data: 音频二进制数据（必填，如下载后的 bytes 对象）
    - filename: 音频文件名（默认保留原命名逻辑，0x0.st 会以此识别文件类型）
    - mime_type: 音频 MIME 类型（默认 "audio/m4a"，需与文件格式匹配）
    - expires: 可选，文件过期时间（格式：① 小时数，如 "24" 表示24小时；② UNIX毫秒时间戳，如 "1728000000000"；默认30天）
    - secret: 可选，是否生成“秘密URL”（True 则 URL 包含随机复杂字符串，防猜测；默认 False）
    - timeout: 可选，请求超时时间（默认30秒，适配大文件上传）
    
    返回值（元组）：
    - 成功：(文件访问链接 str, 文件管理令牌 str)
    - 失败：(None, None)
    """
    # 1. 0x0.st 核心配置（官方 API 端点）
    API_URL = "https://0x0.st"
    
    # 2. 构造请求体（multipart/form-data 格式，符合 0x0.st 要求）
    files = {
        "file": (filename, audio_data, mime_type)  # 必选字段：本地文件上传（与 "url" 字段互斥）
    }
    data = {}
    # 补充可选参数（仅传递有效值，避免触发 0x0.st 无效参数校验）
    if expires:
        # 校验 expires 格式（0x0.st 支持“小时数”或“UNIX毫秒时间戳”）
        if expires.isdigit():
            # 若为纯数字，判断是否为 UNIX 毫秒时间戳（长度13位），否则视为小时数
            if len(expires) == 13:
                data["expires"] = expires  # 格式2：UNIX毫秒时间戳
            else:
                # 限制小时数范围（0x0.st 最大支持 8760 小时 = 1年，避免参数无效）
                if 1 <= int(expires) <= 8760:
                    data["expires"] = expires  # 格式1：小时数
                else:
                    st.warning(f"过期时间超出范围（1-8760小时），将使用默认30天")
        else:
            st.warning(f"过期时间格式无效（仅支持小时数或UNIX毫秒时间戳），将使用默认30天")
    if secret:
        data["secret"] = "true"  # 0x0.st 要求此参数为字符串 "true" 才生效
    
    try:
        # 3. 发送 POST 请求（0x0.st 仅支持 POST 上传，且无需额外请求头）
        st.info(f"正在上传音频到 0x0.st（文件名：{filename}）...")
        response = requests.post(
            url=API_URL,
            files=files,
            data=data,
            timeout=timeout,
            headers={"User-Agent": "BilibiliAudioUploader/1.0"}  # 自定义 User-Agent，便于 0x0.st 识别合法请求
        )
        
        # 4. 响应解析（遵循 0x0.st 官方响应规则）
        if response.status_code == 200:
            # 4.1 提取文件访问链接（响应体为纯文本 URL，需去除首尾空格）
            file_link = response.text.strip()
            # 验证链接有效性（0x0.st 链接格式固定为 "https://0x0.st/xxx"）
            if file_link.startswith("https://0x0.st/"):
                # 4.2 提取文件管理令牌（从响应头 X-Token 获取，用于后续删除/修改过期时间）
                manage_token = response.headers.get("X-Token")
                st.success(f"✅ 上传成功！\n访问链接：{file_link}")
                if manage_token:
                    st.info(f"🔑 管理令牌（保存用于后续操作）：{manage_token}")
                return (file_link, manage_token)
            else:
                st.error(f"❌ 0x0.st 返回无效链接：{file_link[:50]}...")
        
        # 5. 处理非 200 状态码（0x0.st 错误场景）
        else:
            error_msg = response.text.strip() or f"HTTP状态码 {response.status_code}"
            # 常见错误场景提示（参考 0x0.st 官方文档）
            if response.status_code == 413:
                st.error(f"❌ 上传失败：文件超过 512MB 限制（0x0.st 免费版最大支持）")
            elif response.status_code == 400:
                st.error(f"❌ 上传失败：请求参数错误（{error_msg}）")
            elif response.status_code == 429:
                st.error(f"❌ 上传失败：请求频率过高（0x0.st 限制短时间内多次上传）")
            else:
                st.error(f"❌ 上传失败：{error_msg}")
    
    # 6. 捕获请求异常（网络问题、超时等）
    except requests.exceptions.Timeout:
        st.error(f"❌ 请求超时（超过 {timeout} 秒），请检查网络或减小文件大小后重试")
    except requests.exceptions.ConnectionError:
        st.error(f"❌ 网络连接失败，请检查是否能访问 https://0x0.st")
    except Exception as e:
        st.error(f"❌ 上传异常：{str(e)}")
    
    # 所有失败场景返回 (None, None)
    return (None, None)


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
                                file_link, manage_token = upload_to_0x0st(
                                    audio_data=audio_data,
                                    expires=str(expires_hours),  # 传递用户配置的过期时间（小时数）
                                    secret=use_secret_url       # 传递用户配置的秘密URL选项
                                )
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
