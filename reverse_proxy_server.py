import threading
import requests
from flask import Flask, request, jsonify, Response
from urllib.parse import urljoin
import logging
import json
import os
import sys


LOCAL_AUTH_CONFIG = "auth_config.local.json"

SENSITIVE_HEADERS = {
    'authorization',
    'cookie',
    'set-cookie',
    'x-token',
}


def load_local_auth_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCAL_AUTH_CONFIG)
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            return json.load(config_file)
    except (OSError, json.JSONDecodeError):
        return {}


def config_value(config_key, env_key, default=""):
    config = load_local_auth_config()
    value = str(config.get(config_key, "")).strip()
    if value:
        return value
    return os.environ.get(env_key, default).strip()


def has_header(headers, header_name):
    return any(name.lower() == header_name.lower() for name in headers)


def set_header_if_missing(headers, header_name, value):
    if value and not has_header(headers, header_name):
        headers[header_name] = value


def sanitize_headers(headers):
    safe_headers = {}
    for name, value in headers.items():
        if name.lower() in SENSITIVE_HEADERS:
            safe_headers[name] = '***'
        else:
            safe_headers[name] = value
    return safe_headers


def apply_env_auth_headers(headers):
    auth = config_value('authorization', 'BIGMODEL_AUTH')
    org_id = config_value('organization', 'BIGMODEL_ORG')
    project_id = config_value('project', 'BIGMODEL_PROJECT')

    set_header_if_missing(headers, 'Authorization', auth)
    set_header_if_missing(headers, 'Bigmodel-Organization', org_id)
    set_header_if_missing(headers, 'Bigmodel-Project', project_id)
    set_header_if_missing(headers, 'Set-Language', 'zh')
    set_header_if_missing(headers, 'Accept', 'text/event-stream')
    set_header_if_missing(headers, 'Content-Type', 'application/json')
    return headers


def extract_text_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(part for part in parts if part).strip()
    if content is None:
        return ""
    return str(content)


def convert_messages_to_bigmodel(body):
    model_id = config_value('model_id', 'BIGMODEL_MODEL_ID', '11989')
    model_code = os.environ.get('BIGMODEL_MODEL_CODE', 'glm-5.1').strip() or 'glm-5.1'
    requested_model = body.get("model", model_code)
    if requested_model == "glm-5-1":
        requested_model = "glm-5.1"
    prompt = []

    for msg in body.get("messages", []):
        if not isinstance(msg, dict):
            continue
        prompt.append({
            "role": msg.get("role", "user"),
            "content": extract_text_content(msg.get("content", "")),
            "fileContentList": [],
        })

    payload = {
        "model": requested_model,
        "prompt": prompt,
        "modelId": int(model_id) if model_id.isdigit() else model_id,
        "stream": True,
        "thinking": {"type": "enabled"},
        "max_tokens": body.get("max_tokens", 65536),
        "temperature": body.get("temperature", 1),
        "top_p": body.get("top_p", 0.95),
    }

    return payload, model_id


def extract_bigmodel_answer_text(payload):
    if not isinstance(payload, dict):
        return ""
    for key in ("text", "content", "answer", "output"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            delta = first.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                return delta["content"]
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    return ""


def openai_stream_chunk(content="", role=None, finish_reason=None):
    delta = {}
    if role:
        delta["role"] = role
    if content:
        delta["content"] = content
    chunk = {
        "id": "chatcmpl-bigmodel-proxy",
        "object": "chat.completion.chunk",
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")


def convert_bigmodel_sse_to_openai_sse(content):
    output = [openai_stream_chunk(role="assistant")]
    for raw_line in content.decode("utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data_text = line[5:].strip()
        if not data_text or data_text == "[DONE]":
            continue
        try:
            payload = json.loads(data_text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            continue
        text = extract_bigmodel_answer_text(payload)
        if text:
            output.append(openai_stream_chunk(content=text))
    output.append(openai_stream_chunk(finish_reason="stop"))
    output.append(b"data: [DONE]\n\n")
    return b"".join(output)

class ReverseProxyServer:
    def __init__(self):
        self.app = Flask(__name__)
        self.target_url = "https://bigmodel.cn/trialcenter/modeltrial/text?modelCode=glm-5.1"
        self.proxy_port = 8080
        self.server_thread = None
        self.is_running = False
        self.setup_routes()
        
    def setup_routes(self):
        @self.app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
        @self.app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
        def proxy(path):
            # 調試日誌
            logging.info(f"收到請求: {request.method} {path}")
            logging.info(f"請求方法: {request.method}")
            logging.info(f"請求路徑: {path}")
            logging.info(f"請求頭: {sanitize_headers(dict(request.headers))}")
            
            # 構建目標URL - 前端頁面路徑與 API 路徑使用不同規則
            base_url = "https://bigmodel.cn"
            if path == '':
                # 如果路徑為空，使用基本端點
                target_url = f"{base_url}/trialcenter/modeltrial/text?modelCode=glm-5.1"
            elif path.startswith('api/') or path.startswith('biz/'):
                target_url = urljoin(f"{base_url}/", path)
            else:
                # 否則，使用base URL + 路徑
                target_url = urljoin(f"{base_url}/", path)
                
                # 確保modelCode參數存在
                if 'modelCode=glm-5.1' not in target_url:
                    if '?' in target_url:
                        target_url += '&modelCode=glm-5.1'
                    else:
                        target_url += '?modelCode=glm-5.1'
            
            logging.info(f"目標URL: {target_url}")
            
            # 獲取請求數據
            data = request.get_data()
            headers = dict(request.headers)
            
            # 移除一些不需要轉發的頭部
            headers.pop('Host', None)
            headers.pop('Content-Length', None)
            headers = apply_env_auth_headers(headers)
            openai_response_mode = False
            
            try:
                # 根據請求方法轉發
                if request.method == 'GET':
                    response = requests.get(target_url, headers=headers, params=request.args, data=data, timeout=30)
                elif request.method == 'POST':
                    json_data = request.get_json(silent=True)
                    if isinstance(json_data, dict) and "messages" in json_data:
                        json_data, model_id = convert_messages_to_bigmodel(json_data)
                        target_url = f"{base_url}/api/biz/trial/response/v4/sse/{model_id}"
                        data = None
                        openai_response_mode = True
                        logging.info("Detected Chatbox/OpenAI messages payload; converted to BigModel prompt payload")
                    logging.info(f"POST數據: {json_data}")
                    if json_data is not None:
                        response = requests.post(target_url, headers=headers, json=json_data, timeout=30)
                    else:
                        response = requests.post(target_url, headers=headers, data=data, timeout=30)
                elif request.method == 'PUT':
                    response = requests.put(target_url, headers=headers, json=request.get_json(), data=data, timeout=30)
                elif request.method == 'DELETE':
                    response = requests.delete(target_url, headers=headers, data=data, timeout=30)
                elif request.method == 'PATCH':
                    response = requests.patch(target_url, headers=headers, json=request.get_json(), data=data, timeout=30)
                elif request.method == 'HEAD':
                    response = requests.head(target_url, headers=headers, timeout=30)
                elif request.method == 'OPTIONS':
                    response = requests.options(target_url, headers=headers, timeout=30)
                else:
                    return jsonify({'error': '不支持的請求方法'}), 405
                
                logging.info(f"響應狀態: {response.status_code}")
                if response.status_code == 401:
                    logging.warning(
                        "目標 API 回傳 401: Authorization 無效、已過期，或缺少 Bigmodel-Organization/Bigmodel-Project"
                    )
                
                # 轉發響應
                excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
                headers = [(name, value) for (name, value) in response.headers.items() if name.lower() not in excluded_headers]
                if openai_response_mode and response.status_code == 200:
                    converted_content = convert_bigmodel_sse_to_openai_sse(response.content)
                    headers = [(name, value) for (name, value) in headers if name.lower() != 'content-type']
                    headers.append(('Content-Type', 'text/event-stream; charset=utf-8'))
                    logging.info("Converted BigModel SSE response to OpenAI-compatible SSE chunks")
                    return Response(converted_content, response.status_code, headers)

                return Response(response.content, response.status_code, headers)
                
            except requests.exceptions.RequestException as e:
                logging.error(f"代理請求失敗: {e}")
                return jsonify({'error': f'代理請求失敗: {str(e)}'}), 500
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            return jsonify({'status': 'ok', 'target_url': self.target_url})
    
    def start_server(self):
        if not self.is_running:
            self.is_running = True
            self.server_thread = threading.Thread(target=self.run_server)
            self.server_thread.daemon = True
            self.server_thread.start()
            logging.info(f"反向代理伺服器已啟動，監聽端口: {self.proxy_port}")
    
    def stop_server(self):
        if self.is_running:
            self.is_running = False
            # Flask伺服器需要手動停止，這裡簡化處理
            logging.info("反向代理伺服器已停止")
    
    def run_server(self):
        try:
            self.app.run(host='0.0.0.0', port=self.proxy_port, debug=False, use_reloader=False)
        except Exception as e:
            logging.error(f"伺服器運行錯誤: {e}")
    
    def get_proxy_address(self):
        return f"http://localhost:{self.proxy_port}"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    proxy_server = ReverseProxyServer()
    proxy_server.start_server()
    
    try:
        while True:
            pass
    except KeyboardInterrupt:
        proxy_server.stop_server()
