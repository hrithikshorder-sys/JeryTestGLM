import threading
import requests
from flask import Flask, request, jsonify, Response
from urllib.parse import urljoin
import logging
import json
import os
import sys


LOCAL_AUTH_CONFIG = "auth_config.local.json"
PROFILE_CONFIG = "profile_config.local.json"

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


def load_profile_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), PROFILE_CONFIG)
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


def extract_last_user_message(messages):
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            return extract_text_content(message.get("content", ""))
    return ""


def set_nested_text(payload, text):
    changed = False
    if isinstance(payload, dict):
        for key in ("prompt", "text", "content", "message"):
            if isinstance(payload.get(key), str):
                payload[key] = text
                changed = True
        for value in payload.values():
            if isinstance(value, (dict, list)):
                changed = set_nested_text(value, text) or changed
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, (dict, list)):
                changed = set_nested_text(item, text) or changed
    return changed


def build_claude_web_payload(body):
    claude_config = body.get("claude", {}) if isinstance(body.get("claude"), dict) else {}
    template = claude_config.get("payload_template") or body.get("payload_template") or {}
    message_text = extract_last_user_message(body.get("messages", []))

    if isinstance(template, str):
        try:
            payload = json.loads(template) if template.strip() else {}
        except json.JSONDecodeError:
            payload = {}
    elif isinstance(template, dict):
        payload = json.loads(json.dumps(template))
    else:
        payload = {}

    if not payload:
        payload = {
            "prompt": message_text,
            "attachments": [],
            "files": [],
        }
    elif message_text and not set_nested_text(payload, message_text):
        payload["prompt"] = message_text

    return payload


def claude_web_headers(claude_config):
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Origin": "https://claude.ai",
        "Referer": "https://claude.ai/new",
        "Anthropic-Client-Platform": "web_claude_ai",
    }
    cookie = str(claude_config.get("cookie", "")).strip()
    device_id = str(claude_config.get("device_id", "")).strip()
    user_agent = str(claude_config.get("user_agent", "")).strip()

    if cookie:
        headers["Cookie"] = cookie
    if device_id:
        headers["Anthropic-Device-Id"] = device_id
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers


def extract_claude_web_text(payload):
    if not isinstance(payload, dict):
        return ""
    for key in ("completion", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    for value in payload.values():
        if isinstance(value, dict):
            text = extract_claude_web_text(value)
            if text:
                return text
        elif isinstance(value, list):
            for item in value:
                text = extract_claude_web_text(item)
                if text:
                    return text
    return ""


def convert_claude_web_sse_to_openai_sse(content):
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
        text = extract_claude_web_text(payload)
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
        self.profile_config = load_profile_config()
        self.active_profile_name = self.profile_config.get("active_profile", "bigmodel")
        self.active_profile = self.profile_config.get("profiles", {}).get(self.active_profile_name, {})
        self.setup_routes()

    def set_active_profile(self, profile_name):
        self.profile_config = load_profile_config()
        profiles = self.profile_config.get("profiles", {})
        self.active_profile_name = profile_name
        self.active_profile = profiles.get(profile_name, {})

    def get_active_profile(self):
        return {
            "name": self.active_profile_name,
            **self.active_profile,
        }
        
    def setup_routes(self):
        @self.app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
        @self.app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
        def proxy(path):
            # 隤輯岫?亥?
            logging.info(f"?嗅隢?: {request.method} {path}")
            logging.info(f"隢??寞?: {request.method}")
            logging.info(f"隢?頝臬?: {path}")
            logging.info(f"隢??? {sanitize_headers(dict(request.headers))}")
            profile = self.get_active_profile()
            
            # 瑽遣?格?URL - ?垢?頝臬???API 頝臬?雿輻銝?閬?
            base_url = str(profile.get("base_url", "https://bigmodel.cn")).rstrip("/")
            default_target = profile.get(
                "target_url",
                f"{base_url}/trialcenter/modeltrial/text?modelCode=glm-5.1",
            )
            if path == '':
                # 憒?頝臬??箇征嚗蝙?典?祉垢暺?
                target_url = default_target
            elif path.startswith('api/') or path.startswith('biz/'):
                target_url = urljoin(f"{base_url}/", path)
            else:
                # ?血?嚗蝙?灸ase URL + 頝臬?
                target_url = urljoin(f"{base_url}/", path)
                
                # 蝣箔?modelCode?摮
                if 'modelCode=glm-5.1' not in target_url:
                    if '?' in target_url:
                        target_url += '&modelCode=glm-5.1'
                    else:
                        target_url += '?modelCode=glm-5.1'
            
            logging.info(f"?格?URL: {target_url}")
            
            # ?脣?隢??豢?
            data = request.get_data()
            headers = dict(request.headers)
            
            # 蝘駁銝鈭??閬??潛??剝
            headers.pop('Host', None)
            headers.pop('Content-Length', None)
            headers = apply_env_auth_headers(headers)
            openai_response_mode = ""
            
            try:
                # ?寞?隢??寞?頧
                if request.method == 'GET':
                    response = requests.get(target_url, headers=headers, params=request.args, data=data, timeout=30)
                elif request.method == 'POST':
                    json_data = request.get_json(silent=True)
                    if isinstance(json_data, dict) and json_data.get("provider"):
                        requested_provider = str(json_data.get("provider"))
                        self.set_active_profile(requested_provider)
                        profile = self.get_active_profile()
                        base_url = str(profile.get("base_url", base_url)).rstrip("/")
                        default_target = profile.get(
                            "target_url",
                            f"{base_url}/trialcenter/modeltrial/text?modelCode=glm-5.1",
                        )
                        target_url = profile.get("target_url", target_url)
                    if isinstance(json_data, dict) and "messages" in json_data:
                        json_data, model_id = convert_messages_to_bigmodel(json_data)
                        target_url = f"{base_url}/api/biz/trial/response/v4/sse/{model_id}"
                        data = None
                        openai_response_mode = "bigmodel"
                        logging.info("Detected Chatbox/OpenAI messages payload; converted to BigModel prompt payload")
                    logging.info(f"POST?豢?: {json_data}")
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
                    return jsonify({'error': '銝??隢??寞?'}), 405
                
                logging.info(f"?踵???? {response.status_code}")
                if response.status_code == 401:
                    logging.warning(
                        "?格? API ? 401: Authorization ?⊥??歇??嚗?蝻箏? Bigmodel-Organization/Bigmodel-Project"
                    )
                
                # 頧?踵?
                excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
                headers = [(name, value) for (name, value) in response.headers.items() if name.lower() not in excluded_headers]
                if openai_response_mode and response.status_code == 200:
                    if openai_response_mode == "claude_web":
                        converted_content = convert_claude_web_sse_to_openai_sse(response.content)
                        logging.info("Converted Claude Web SSE response to OpenAI-compatible SSE chunks")
                    else:
                        converted_content = convert_bigmodel_sse_to_openai_sse(response.content)
                        logging.info("Converted BigModel SSE response to OpenAI-compatible SSE chunks")
                    return Response(converted_content, response.status_code, headers)

                return Response(response.content, response.status_code, headers)
                
            except requests.exceptions.RequestException as e:
                logging.error(f"隞??隢?憭望?: {e}")
                return jsonify({'error': f'隞??隢?憭望?: {str(e)}'}), 500

        @self.app.route('/claude-web/completion', methods=['POST'])
        def claude_web_completion():
            json_data = request.get_json(silent=True) or {}
            if not isinstance(json_data, dict):
                return jsonify({"error": "Invalid JSON payload"}), 400
            json_data["provider"] = "claude_web"
            profile = json_data.get("claude", {}) if isinstance(json_data.get("claude"), dict) else {}
            base_url = str(profile.get("base_url", "https://claude.ai")).rstrip("/")
            org_id = str(profile.get("organization_id", "")).strip()
            conversation_id = str(profile.get("conversation_id", "")).strip()
            if not org_id or not conversation_id:
                return jsonify({"error": "Claude Web requires organization_id and conversation_id"}), 400

            target_url = f"{base_url}/api/organizations/{org_id}/chat_conversations/{conversation_id}/completion"
            headers = claude_web_headers(profile)
            headers = apply_env_auth_headers(headers)
            payload = build_claude_web_payload(json_data)

            try:
                response = requests.post(target_url, headers=headers, json=payload, timeout=30)
                response_headers = [
                    (name, value)
                    for (name, value) in response.headers.items()
                    if name.lower() not in ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
                ]
                if response.status_code == 200:
                    converted_content = convert_claude_web_sse_to_openai_sse(response.content)
                    response_headers = [(n, v) for (n, v) in response_headers if n.lower() != 'content-type']
                    response_headers.append(('Content-Type', 'text/event-stream; charset=utf-8'))
                    return Response(converted_content, response.status_code, response_headers)
                return Response(response.content, response.status_code, response_headers)
            except requests.exceptions.RequestException as e:
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            return jsonify({'status': 'ok', 'target_url': self.target_url})
    
    def start_server(self):
        if not self.is_running:
            self.is_running = True
            self.server_thread = threading.Thread(target=self.run_server)
            self.server_thread.daemon = True
            self.server_thread.start()
            logging.info(f"??隞??隡箸??典歇??嚗?賜垢?? {self.proxy_port}")
    
    def stop_server(self):
        if self.is_running:
            self.is_running = False
            # Flask隡箸??券?閬???甇ｇ??ㄐ蝪∪???
            logging.info("??隞??隡箸??典歇?迫")
    
    def run_server(self):
        try:
            self.app.run(host='0.0.0.0', port=self.proxy_port, debug=False, use_reloader=False)
        except Exception as e:
            logging.error(f"隡箸??券?銵隤? {e}")
    
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
