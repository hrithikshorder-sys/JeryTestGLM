import json
import logging
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
import webbrowser

import requests

from reverse_proxy_server import ReverseProxyServer


LOCAL_AUTH_CONFIG = "auth_config.local.json"
PROFILE_CONFIG = "profile_config.local.json"


def _read_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def load_local_auth_config():
    return _read_json(os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCAL_AUTH_CONFIG))


def load_profile_config():
    return _read_json(os.path.join(os.path.dirname(os.path.abspath(__file__)), PROFILE_CONFIG))


class ProxyGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Reverse Proxy Controller")
        self.root.geometry("980x860")
        self.root.minsize(900, 780)

        self.proxy_server = ReverseProxyServer()
        self.auth_config = load_local_auth_config()
        self.profile_config = load_profile_config()

        self.create_widgets()
        self.refresh_profile_combo()
        self.update_status()
        self.root.after(300, self.auto_start_debug)

    def create_widgets(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)

        title_label = ttk.Label(main_frame, text="Reverse Proxy Controller", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=10)

        target_frame = ttk.LabelFrame(main_frame, text="Target", padding="5")
        target_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.target_url_var = tk.StringVar(value=self.proxy_server.target_url)
        self.target_entry = ttk.Entry(target_frame, textvariable=self.target_url_var)
        self.target_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        target_frame.columnconfigure(0, weight=1)

        proxy_frame = ttk.LabelFrame(main_frame, text="Proxy", padding="5")
        proxy_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.proxy_address_var = tk.StringVar(value=self.proxy_server.get_proxy_address())
        ttk.Label(proxy_frame, textvariable=self.proxy_address_var, font=("Arial", 10)).grid(
            row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5
        )

        profile_frame = ttk.LabelFrame(main_frame, text="Profile", padding="5")
        profile_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        ttk.Label(profile_frame, text="Active Profile:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.profile_name_var = tk.StringVar(value="")
        self.profile_combo = ttk.Combobox(
            profile_frame, textvariable=self.profile_name_var, width=32, state="readonly"
        )
        self.profile_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.profile_combo.bind("<<ComboboxSelected>>", self.on_profile_selected)
        ttk.Button(profile_frame, text="Create JSON", command=self.create_profile_template).grid(
            row=0, column=2, padx=4
        )
        ttk.Button(profile_frame, text="Reload JSON", command=self.reload_profile_config).grid(
            row=0, column=3, padx=4
        )
        profile_frame.columnconfigure(1, weight=1)

        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=4, column=0, columnspan=2, pady=10)
        self.start_button = ttk.Button(control_frame, text="Start", command=self.start_proxy)
        self.start_button.grid(row=0, column=0, padx=5)
        self.stop_button = ttk.Button(control_frame, text="Stop", command=self.stop_proxy, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5)
        self.update_button = ttk.Button(control_frame, text="Update", command=self.update_settings)
        self.update_button.grid(row=0, column=2, padx=5)

        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="5")
        status_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(status_frame, textvariable=self.status_var).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)

        test_frame = ttk.LabelFrame(main_frame, text="Test", padding="5")
        test_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(test_frame, text="Test /health", command=self.test_proxy).grid(row=0, column=0, padx=5, pady=5)

        self.auth_frame = ttk.LabelFrame(main_frame, text="Credentials", padding="5")
        self.auth_frame.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(self.auth_frame, text="Authorization Token:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.auth_token_entry = ttk.Entry(self.auth_frame, width=60, show="*")
        self.auth_token_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.auth_token_entry.insert(0, self.auth_config.get("authorization", os.environ.get("BIGMODEL_AUTH", "")))

        ttk.Label(self.auth_frame, text="Model ID:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.model_id_entry = ttk.Entry(self.auth_frame, width=60)
        self.model_id_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.model_id_entry.insert(0, self.auth_config.get("model_id", os.environ.get("BIGMODEL_MODEL_ID", "11989")))

        ttk.Label(self.auth_frame, text="Organization:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.org_entry = ttk.Entry(self.auth_frame, width=60)
        self.org_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.org_entry.insert(0, self.auth_config.get("organization", os.environ.get("BIGMODEL_ORG", "")))

        ttk.Label(self.auth_frame, text="Project:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.project_entry = ttk.Entry(self.auth_frame, width=60)
        self.project_entry.grid(row=3, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.project_entry.insert(0, self.auth_config.get("project", os.environ.get("BIGMODEL_PROJECT", "")))

        auth_buttons = ttk.Frame(self.auth_frame)
        auth_buttons.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=4)
        ttk.Button(auth_buttons, text="OPEN", command=self.open_bigmodel_devtools).grid(row=0, column=0, padx=4)
        ttk.Button(auth_buttons, text="Open BigModel", command=self.open_bigmodel_page).grid(row=0, column=1, padx=4)
        ttk.Button(auth_buttons, text="Network SOP", command=self.show_auth_sop).grid(row=0, column=2, padx=4)
        ttk.Button(auth_buttons, text="Create JSON", command=self.create_local_auth_template).grid(row=0, column=3, padx=4)
        ttk.Button(auth_buttons, text="Reload JSON", command=self.reload_local_auth_config).grid(row=0, column=4, padx=4)

        self.claude_frame = ttk.LabelFrame(main_frame, text="ClaudeAI", padding="5")
        self.claude_frame.grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        ttk.Label(self.claude_frame, text="Base URL:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.claude_base_url_entry = ttk.Entry(self.claude_frame, width=60)
        self.claude_base_url_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.claude_base_url_entry.insert(0, "https://claude.ai")

        ttk.Label(self.claude_frame, text="Organization ID:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.claude_org_entry = ttk.Entry(self.claude_frame, width=60)
        self.claude_org_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)

        ttk.Label(self.claude_frame, text="Conversation ID:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.claude_conversation_entry = ttk.Entry(self.claude_frame, width=60)
        self.claude_conversation_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)

        ttk.Label(self.claude_frame, text="Cookie:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.claude_cookie_text = scrolledtext.ScrolledText(self.claude_frame, height=3, width=80)
        self.claude_cookie_text.grid(row=3, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)

        ttk.Label(self.claude_frame, text="Anthropic Device ID:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
        self.claude_device_entry = ttk.Entry(self.claude_frame, width=60)
        self.claude_device_entry.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)

        ttk.Label(self.claude_frame, text="User-Agent:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=2)
        self.claude_user_agent_entry = ttk.Entry(self.claude_frame, width=60)
        self.claude_user_agent_entry.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)

        ttk.Label(self.claude_frame, text="Payload Template:").grid(row=6, column=0, sticky=tk.W, padx=5, pady=2)
        self.claude_payload_text = scrolledtext.ScrolledText(self.claude_frame, height=6, width=80)
        self.claude_payload_text.grid(row=6, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.claude_payload_text.insert(
            tk.END,
            json.dumps({"prompt": "HI", "attachments": [], "files": []}, ensure_ascii=False, indent=2),
        )

        claude_buttons = ttk.Frame(self.claude_frame)
        claude_buttons.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=4)
        ttk.Button(claude_buttons, text="Send ClaudeAI", command=self.send_claude_message).grid(row=0, column=0, padx=4)
        ttk.Button(claude_buttons, text="Create JSON", command=self.create_claude_profile_template).grid(
            row=0, column=1, padx=4
        )
        ttk.Button(claude_buttons, text="Record", command=self.record_claude_profile).grid(row=0, column=2, padx=4)
        ttk.Button(claude_buttons, text="Reload JSON", command=self.reload_profile_config).grid(row=0, column=3, padx=4)
        self.claude_frame.columnconfigure(1, weight=1)
        self.claude_frame.grid_remove()

        message_frame = ttk.LabelFrame(main_frame, text="Message", padding="5")
        message_frame.grid(row=9, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        ttk.Label(message_frame, text="Input:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.message_entry = ttk.Entry(message_frame, width=60)
        self.message_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.message_entry.insert(0, "HI")

        self.use_chatbox_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(message_frame, text="Use CHATBOX", variable=self.use_chatbox_var).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2
        )
        ttk.Button(message_frame, text="Send", command=self.send_message).grid(row=2, column=0, columnspan=2, pady=5)
        ttk.Label(message_frame, text="Response:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.response_text = scrolledtext.ScrolledText(message_frame, height=7, width=80)
        self.response_text.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=2)
        message_frame.columnconfigure(1, weight=1)
        message_frame.rowconfigure(4, weight=1)

        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="5")
        log_frame.grid(row=10, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=7, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        main_frame.rowconfigure(10, weight=1)

    def refresh_profile_combo(self):
        profiles = self.profile_config.get("profiles", {})
        names = sorted(profiles.keys())
        self.profile_combo["values"] = names
        active = self.profile_config.get("active_profile", names[0] if names else "")
        if active:
            self.profile_name_var.set(active)
            self.proxy_server.set_active_profile(active)
        self.toggle_profile_sections()

    def create_profile_template(self):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), PROFILE_CONFIG)
        if os.path.exists(config_path):
            messagebox.showinfo("Info", f"{PROFILE_CONFIG} already exists")
            return
        template = {
            "active_profile": "bigmodel",
            "profiles": {
                "bigmodel": {
                    "provider": "bigmodel",
                    "base_url": "https://bigmodel.cn",
                    "target_url": "https://bigmodel.cn/trialcenter/modeltrial/text?modelCode=glm-5.1",
                },
                "claude_web": {
                    "provider": "claude_web",
                    "base_url": "https://claude.ai",
                    "organization_id": "",
                    "conversation_id": "",
                    "cookie": "",
                    "device_id": "",
                    "user_agent": "",
                    "payload_template": {
                        "prompt": "HI",
                        "attachments": [],
                        "files": [],
                    },
                },
            },
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        self.profile_config = load_profile_config()
        self.refresh_profile_combo()
        self.log_message(f"Created {PROFILE_CONFIG}")

    def create_claude_profile_template(self):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), PROFILE_CONFIG)
        current = load_profile_config() or {
            "active_profile": "bigmodel",
            "profiles": {
                "bigmodel": {
                    "provider": "bigmodel",
                    "base_url": "https://bigmodel.cn",
                    "target_url": "https://bigmodel.cn/trialcenter/modeltrial/text?modelCode=glm-5.1",
                }
            },
        }
        profiles = current.setdefault("profiles", {})
        profiles["claude_web"] = {
            "provider": "claude_web",
            "base_url": "https://claude.ai",
            "organization_id": "",
            "conversation_id": "",
            "cookie": "",
            "device_id": "",
            "user_agent": "",
            "payload_template": {
                "prompt": "HI",
                "attachments": [],
                "files": [],
            },
        }
        current["active_profile"] = "claude_web"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        self.profile_config = load_profile_config()
        self.refresh_profile_combo()
        self.log_message(f"Created claude_web in {PROFILE_CONFIG}")

    def record_claude_profile(self):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), PROFILE_CONFIG)
        current = load_profile_config() or {
            "active_profile": "claude_web",
            "profiles": {},
        }
        profiles = current.setdefault("profiles", {})
        profiles["claude_web"] = {
            "provider": "claude_web",
            "base_url": self.claude_base_url_entry.get().strip() or "https://claude.ai",
            "organization_id": self.claude_org_entry.get().strip(),
            "conversation_id": self.claude_conversation_entry.get().strip(),
            "cookie": self.claude_cookie_text.get(1.0, tk.END).strip(),
            "device_id": self.claude_device_entry.get().strip(),
            "user_agent": self.claude_user_agent_entry.get().strip(),
            "payload_template": self._parse_claude_payload_template(),
        }
        current["active_profile"] = "claude_web"
        if "bigmodel" not in profiles:
            profiles["bigmodel"] = {
                "provider": "bigmodel",
                "base_url": "https://bigmodel.cn",
                "target_url": "https://bigmodel.cn/trialcenter/modeltrial/text?modelCode=glm-5.1",
            }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        self.profile_config = load_profile_config()
        self.refresh_profile_combo()
        self.log_message(f"Recorded claude_web into {PROFILE_CONFIG}")

    def _parse_claude_payload_template(self):
        payload_text = self.claude_payload_text.get(1.0, tk.END).strip()
        if not payload_text:
            return {"prompt": "HI", "attachments": [], "files": []}
        try:
            return json.loads(payload_text)
        except json.JSONDecodeError:
            return {"prompt": payload_text, "attachments": [], "files": []}

    def reload_profile_config(self):
        self.profile_config = load_profile_config()
        self.refresh_profile_combo()
        self.log_message(f"Reloaded {PROFILE_CONFIG}")

    def on_profile_selected(self, event=None):
        profile = self.profile_name_var.get().strip()
        if profile:
            self.proxy_server.set_active_profile(profile)
            self.profile_config["active_profile"] = profile
            self.log_message(f"Active profile: {profile}")
            self.toggle_profile_sections()

    def toggle_profile_sections(self):
        profile = self.profile_name_var.get().strip() or self.profile_config.get("active_profile", "")
        if profile == "claude_web":
            self.auth_frame.grid_remove()
            self.claude_frame.grid()
        else:
            self.claude_frame.grid_remove()
            self.auth_frame.grid()

    def log_message(self, message):
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)

    def auto_start_debug(self):
        try:
            if not self.proxy_server.is_running:
                self.start_proxy()
            self.root.after(1200, self.auto_health_check)
        except Exception as e:
            self.log_message(f"Auto start error: {e}")

    def auto_health_check(self):
        try:
            response = requests.get(f"{self.proxy_server.get_proxy_address()}/health", timeout=10)
            self.log_message(f"health: {response.status_code}")
        except Exception as e:
            self.log_message(f"health error: {e}")

    def open_bigmodel_page(self):
        webbrowser.open("https://bigmodel.cn/trialcenter/modeltrial/text?modelCode=glm-5.1")

    def open_bigmodel_devtools(self):
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "open_bigmodel_devtools.py")
        subprocess.Popen([sys.executable, script_path], cwd=os.path.dirname(script_path))

    def show_auth_sop(self):
        sop = (
            "1. Open BigModel in Chrome.\n"
            "2. Open DevTools -> Network.\n"
            "3. Send HI.\n"
            "4. Copy Authorization, Organization, Project, Model ID.\n"
        )
        self.response_text.delete(1.0, tk.END)
        self.response_text.insert(tk.END, sop)

    def create_local_auth_template(self):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCAL_AUTH_CONFIG)
        if os.path.exists(config_path):
            messagebox.showinfo("Info", f"{LOCAL_AUTH_CONFIG} already exists")
            return
        template = {
            "authorization": "header.payload.signature",
            "model_id": "11989",
            "organization": "org_xxx",
            "project": "proj_xxx",
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        self.auth_config = load_local_auth_config()
        self.reload_local_auth_config()

    def reload_local_auth_config(self):
        self.auth_config = load_local_auth_config()
        self.auth_token_entry.delete(0, tk.END)
        self.auth_token_entry.insert(0, self.auth_config.get("authorization", ""))
        self.model_id_entry.delete(0, tk.END)
        self.model_id_entry.insert(0, self.auth_config.get("model_id", ""))
        self.org_entry.delete(0, tk.END)
        self.org_entry.insert(0, self.auth_config.get("organization", ""))
        self.project_entry.delete(0, tk.END)
        self.project_entry.insert(0, self.auth_config.get("project", ""))
        self.log_message(f"Reloaded {LOCAL_AUTH_CONFIG}")

    def send_message(self):
        try:
            message = self.message_entry.get().strip()
            if not message:
                return

            proxy_address = self.proxy_server.get_proxy_address()
            auth_token = self.auth_token_entry.get().strip() or os.environ.get("BIGMODEL_AUTH", "").strip()
            model_id = self.model_id_entry.get().strip() or os.environ.get("BIGMODEL_MODEL_ID", "11989")
            model_code = os.environ.get("BIGMODEL_MODEL_CODE", "glm-5.1")
            org_id = self.org_entry.get().strip() or os.environ.get("BIGMODEL_ORG", "").strip()
            project_id = self.project_entry.get().strip() or os.environ.get("BIGMODEL_PROJECT", "").strip()
            active_profile = self.profile_name_var.get().strip() or "bigmodel"

            if active_profile == "claude_web":
                self.send_claude_message()
                return

            use_chatbox = self.use_chatbox_var.get()

            if use_chatbox:
                api_json_data = {
                    "model": model_code.replace(".", "-"),
                    "messages": [{"role": "user", "content": message}],
                    "temperature": 1,
                    "top_p": 0.95,
                    "max_tokens": 1000,
                    "provider": active_profile,
                }
            else:
                api_json_data = {
                    "model": model_code,
                    "prompt": [{"role": "user", "content": message, "fileContentList": []}],
                    "modelId": int(model_id) if model_id.isdigit() else model_id,
                    "stream": True,
                    "thinking": {"type": "enabled"},
                    "max_tokens": 65536,
                    "temperature": 1,
                    "top_p": 0.95,
                    "provider": active_profile,
                    "tools": [
                        {
                            "type": "web_search",
                            "web_search": {
                                "search_engine": "search_std",
                                "search_recency_filter": "noLimit",
                                "count": 10,
                                "search_intent": False,
                                "search_domain_filter": "",
                                "content_size": "medium",
                            },
                            "extraMcpData": [],
                        }
                    ],
                }

            headers = {
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                "Set-Language": "zh",
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            if auth_token:
                headers["Authorization"] = auth_token
            if org_id:
                headers["Bigmodel-Organization"] = org_id
            if project_id:
                headers["Bigmodel-Project"] = project_id

            if use_chatbox:
                api_url = f"{proxy_address}/api/biz/trial/response/v4/sse/glm-5-1"
            else:
                api_url = f"{proxy_address}/api/biz/trial/response/v4/sse/{model_id}"

            response = requests.post(api_url, json=api_json_data, headers=headers, timeout=30)
            self.response_text.delete(1.0, tk.END)
            self.response_text.insert(tk.END, response.text[:8000])
            self.log_message(f"POST {api_url} -> {response.status_code}")
        except Exception as e:
            self.response_text.delete(1.0, tk.END)
            self.response_text.insert(tk.END, f"Error: {e}")
            self.log_message(f"send error: {e}")

    def send_claude_message(self):
        try:
            org_id = self.claude_org_entry.get().strip()
            conversation_id = self.claude_conversation_entry.get().strip()
            cookie = self.claude_cookie_text.get(1.0, tk.END).strip()
            if not org_id or not conversation_id or not cookie:
                messagebox.showwarning("Missing fields", "ClaudeAI requires Organization ID, Conversation ID and Cookie")
                return

            payload_template = self.claude_payload_text.get(1.0, tk.END).strip()
            try:
                parsed_template = json.loads(payload_template) if payload_template else {}
            except json.JSONDecodeError:
                parsed_template = {}

            request_body = {
                "provider": "claude_web",
                "messages": [{"role": "user", "content": self.message_entry.get().strip() or "HI"}],
                "claude": {
                    "base_url": self.claude_base_url_entry.get().strip() or "https://claude.ai",
                    "organization_id": org_id,
                    "conversation_id": conversation_id,
                    "cookie": cookie,
                    "device_id": self.claude_device_entry.get().strip(),
                    "user_agent": self.claude_user_agent_entry.get().strip(),
                    "payload_template": parsed_template,
                },
            }

            api_url = f"{self.proxy_server.get_proxy_address()}/claude-web/completion"
            response = requests.post(api_url, json=request_body, timeout=30)
            self.response_text.delete(1.0, tk.END)
            self.response_text.insert(tk.END, response.text[:8000])
            self.log_message(f"POST {api_url} -> {response.status_code}")
        except Exception as e:
            self.response_text.delete(1.0, tk.END)
            self.response_text.insert(tk.END, f"Error: {e}")
            self.log_message(f"ClaudeAI send error: {e}")

    def start_proxy(self):
        try:
            self.proxy_server.target_url = self.target_url_var.get()
            self.proxy_server.start_server()
            self.status_var.set("Running")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.update_proxy_address()
            self.log_message("Proxy started")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def stop_proxy(self):
        self.proxy_server.stop_server()
        self.status_var.set("Stopped")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.log_message("Proxy stopped")

    def update_settings(self):
        self.proxy_server.target_url = self.target_url_var.get()
        self.log_message(f"Target updated: {self.proxy_server.target_url}")

    def update_proxy_address(self):
        self.proxy_address_var.set(self.proxy_server.get_proxy_address())

    def test_proxy(self):
        try:
            response = requests.get(f"{self.proxy_server.get_proxy_address()}/health", timeout=10)
            messagebox.showinfo("Health", str(response.json()))
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def update_status(self):
        self.root.after(5000, self.update_status)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    root = tk.Tk()
    app = ProxyGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
