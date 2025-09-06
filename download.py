import streamlit as st
import requests
import re
import time
import hashlib

# --- 核心功能函数 ---

def extract_bvid(url):
    """从B站链接中提取BV号"""
    match = re.search(r'(BV[\w]+)', url)
    return match.group(1) if match else None

def get_cid(bvid):
    """通过bvid获取cid"""
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data["code"] == 0:
                return data["data"]["cid"]
    except Exception as e:
        st.warning(f"获取CID时出错: {e}")
    return None

def get_wbi_keys():
    """获取WBI签名所需的img_key和sub_key"""
    nav_url = "https://api.bilibili.com/x/web-interface/nav"
    try:
        response = requests.get(nav_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data["code"] == 0:
                wbi_img = data["data"]["wbi_img"]
                img_key = wbi_img["img_url"].split("/")[-1].split(".")[0]
                sub_key = wbi_img["sub_url"].split("/")[-1].split(".")[0]
                return img_key, sub_key
    except Exception as e:
        st.warning(f"获取WBI密钥失败: {e}")
    return None, None

def generate_wbi_sign(params, img_key, sub_key):
    """生成WBI签名"""
    mix_key = img_key + sub_key
    # 参数按字典序排序
    sorted_params = dict(sorted(params.items()))
    param_str = "&".join([f"{k}={v}" for k, v in sorted_params.items()])
    sign_content = param_str + mix_key
    return hashlib.md5(sign_content.encode()).hexdigest()

def get_audio_url(bvid, cid):
    """获取音频直链（带WBI签名）"""
    img_key, sub_key = get_wbi_keys()
    if not img_key or not sub_key:
        st.error("无法获取WBI密钥，请稍后重试。")
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

    # 生成 w_rid 签名
    params["w_rid"] = generate_wbi_sign(params, img_key, sub_key)

    url = "https://api.bilibili.com/x/player/wbi/playurl"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://www.bilibili.com/video/{bvid}"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data["code"] == 0:
                dash = data["data"]["dash"]
                audio_list = dash.get("audio")
                if audio_list:
                    return audio_list[0]["baseUrl"]
    except Exception as e:
        st.warning(f"获取音频地址失败: {e}")
    return None

def download_audio(audio_url, referer):
    """下载音频数据"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": referer
    }
    try:
        response = requests.get(audio_url, headers=headers, stream=True, timeout=30)
        if response.status_code == 200:
            # 读取前 10KB 检查是否为有效音频（防止防盗链返回HTML）
            chunk = next(iter(response.iter_content(10240)))
            if chunk.startswith(b"<html") or b"403" in chunk or b"error" in chunk.lower():
                st.error("音频请求被拒绝（可能防盗链或权限问题）")
                return None
            return response.content
    except Exception as e:
        st.error(f"下载音频时出错: {str(e)}")
    return None

def upload_to_tmpfiles(audio_data):
    """上传音频到 tmpfiles.org"""
    url = "https://tmpfiles.org/api/v1/upload"
    files = {
        "file": ("bilibili_audio.m4a", audio_data, "audio/m4a")
    }
    try:
        response = requests.post(url, files=files, timeout=30)
        if response.status_code == 200:
            try:
                result = response.json()
                if result.get("success"):
                    return result["data"]["url"]
                else:
                    st.error("上传失败：" + str(result))
            except requests.exceptions.JSONDecodeError:
                st.error("上传失败：服务器返回非JSON内容（可能是服务不可用或被屏蔽）")
                st.text(f"原始响应内容：\n{response.text}")
        else:
            st.error(f"上传失败，HTTP状态码: {response.status_code}")
    except requests.exceptions.RequestException as e:
        st.error(f"网络请求错误: {str(e)}")
    except Exception as e:
        st.error(f"未知错误: {str(e)}")
    return None


# --- Streamlit UI 主界面 ---

st.title("B站音频提取工具 🎧")
st.markdown("输入B站视频链接，自动提取音频并生成可分享的 **HTTPS 下载链接**")

video_url = st.text_input(
    "请输入B站视频链接：",
    placeholder="https://www.bilibili.com/video/BV1xx411c7..."
)

if st.button("🚀 提取音频并生成链接"):
    if not video_url.strip():
        st.error("请先输入有效的B站视频链接！")
    else:
        with st.spinner("🔍 正在解析视频信息..."):
            bvid = extract_bvid(video_url)
            if not bvid:
                st.error("❌ 无法识别BV号，请确认链接是否为B站视频页。")
            else:
                cid = get_cid(bvid)
                if not cid:
                    st.error("❌ 无法获取视频信息，请检查链接是否正确或稍后重试。")
                else:
                    with st.spinner("🎧 正在获取音频地址..."):
                        audio_url = get_audio_url(bvid, cid)
                        if not audio_url:
                            st.error("❌ 无法获取音频下载地址，可能该视频无音频或受权限限制。")
                        else:
                            referer = f"https://www.bilibili.com/video/{bvid}"
                            with st.spinner("⏬ 正在下载音频数据..."):
                                audio_data = download_audio(audio_url, referer)
                                if not audio_data:
                                    st.error("❌ 音频下载失败。")
                                else:
                                    st.info("📤 正在上传到 tmpfiles.org...")
                                    file_link = upload_to_tmpfiles(audio_data)
                                    if file_link:
                                        st.success("✅ 上传成功！")
                                        st.markdown("### 🔗 音频下载链接")
                                        st.markdown(f"[📥 点击下载音频]({file_link})")
                                        st.code(file_link, language="text")
                                        st.caption("提示：链接由 tmpfiles.org 提供，通常保留30天。")
                                    else:
                                        st.error("❌ 文件上传失败，请稍后重试。")
