import streamlit as st
import requests
import re
import time
import hashlib
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from aliyunsdkcore.auth.credentials import AccessKeyCredential
import os
import json
import datetime



# 配置阿里云Access Key ID和Secret
os.environ['ALIBABA_CLOUD_ACCESS_KEY_ID'] = ''
os.environ['ALIBABA_CLOUD_ACCESS_KEY_SECRET'] = '

# 新增函数：创建阿里听悟任务
def create_tingwu_task(file_url):
    credentials = AccessKeyCredential(os.environ['ALIBABA_CLOUD_ACCESS_KEY_ID'], os.environ['ALIBABA_CLOUD_ACCESS_KEY_SECRET'])
    client = AcsClient(region_id='cn-beijing', credential=credentials)
    
    body = {
        "AppKey": "",
        "Input": {
            "SourceLanguage": "cn",  # 根据实际情况调整
            "TaskKey": "task" + datetime.datetime.now().strftime('%Y%m%d%H%M%S'),
            "FileUrl": file_url,
        },
        "Parameters": {
            "SummarizationEnabled": True,
            "Summarization": {
                "Types": ["MindMap"]
            }
        }
    }

    request = CommonRequest()
    request.set_accept_format('json')
    request.set_domain('tingwu.cn-beijing.aliyuncs.com')
    request.set_version('2023-09-30')
    request.set_protocol_type('https')
    request.set_method('PUT')
    request.set_uri_pattern('/openapi/tingwu/v2/tasks')
    request.add_query_param('type', 'offline')
    request.set_content(json.dumps(body).encode('utf-8'))
    
    response = client.do_action_with_exception(request)
    return json.loads(response)

# 新增函数：查询任务状态
def check_tingwu_task(task_id):
    credentials = AccessKeyCredential(os.environ['ALIBABA_CLOUD_ACCESS_KEY_ID'], os.environ['ALIBABA_CLOUD_ACCESS_KEY_SECRET'])
    client = AcsClient(region_id='cn-beijing', credential=credentials)
    
    request = CommonRequest()
    request.set_accept_format('json')
    request.set_domain('tingwu.cn-beijing.aliyuncs.com')
    request.set_version('2023-09-30')
    request.set_protocol_type('https')
    request.set_method('GET')
    request.set_uri_pattern(f'/openapi/tingwu/v2/tasks/{task_id}')
    
    response = client.do_action_with_exception(request)
    return json.loads(response)


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

def upload_to_catbox(audio_data):
    url = "https://catbox.moe/user/api.php"
    files = {
        "fileToUpload": ("bilibili_audio.m4a", audio_data, "audio/m4a")
    }
    data = {
        "reqtype": "fileupload",
        "userhash": ""  # 可留空，除非你有注册 userhash
    }
    try:
        response = requests.post(url, data=data, files=files, timeout=30)
        # catbox 返回的是纯文本 URL，不是 JSON！
        if response.status_code == 200 and response.text.strip():
            return response.text.strip()  # 直接返回 URL 字符串
        else:
            st.error(f"上传失败：HTTP {response.status_code}")
            st.debug(response.text)
    except Exception as e:
        st.error(f"网络错误：{str(e)}")
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
                        # 原调用部分修改如下：
                        with st.spinner("正在下载并上传音频..."):
                            audio_data = download_audio(audio_url, video_url)
                            if not audio_data:
                                st.error("音频下载失败，请重试")
                            else:
                                st.info("音频已下载，正在上传到 catbox.moe...")
                                file_link = upload_to_catbox(audio_data)
                                if file_link:
                                    st.success("✅ 音频已上传！")
                                    st.markdown(f"### 🔗 可访问的音频链接：\n\n{file_link}")
                                    st.markdown(f"[点击下载音频]({file_link})")
                                    st.caption("注意：此链接由 catbox.moe 提供，长期有效（除非被举报删除）。")
                                    st.info("音频已上传，正在提交阿里听悟任务...")
                                    task_response = create_tingwu_task(file_link)
                                    task_id = task_response.get('Data', {}).get('TaskId')
                                    
                                    if task_id:
                                        with st.spinner("等待阿里听悟任务完成..."):
                                            while True:
                                                time.sleep(60)  # 每分钟检查一次任务状态
                                                task_status_response = check_tingwu_task(task_id)
                                                task_status = task_status_response.get('Data', {}).get('TaskStatus')
                                                
                                                if task_status == 'COMPLETED':
                                                    result_urls = task_status_response.get('Data', {}).get('Result', {})
                                                    mindmap_url = result_urls.get('Summarization') if isinstance(result_urls, dict) else None
                                                    
                                                    if mindmap_url:
                                                        st.success("✅ 思维导图已生成！")
                                                        st.markdown(f"### 🔗 可访问的思维导图链接：\n\n{mindmap_url}")
                                                    break
                                                elif task_status == 'FAILED':
                                                    st.error("阿里听悟任务失败，请重试。")
                                                    break
                                else:
                                    st.error("文件上传失败，请稍后重试。")
