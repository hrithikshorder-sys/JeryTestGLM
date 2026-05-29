import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import requests
import logging
import json
import os
import subprocess
import sys
import webbrowser
from reverse_proxy_server import ReverseProxyServer


LOCAL_AUTH_CONFIG = "auth_config.local.json"


def load_local_auth_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCAL_AUTH_CONFIG)
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            return json.load(config_file)
    except (OSError, json.JSONDecodeError):
        return {}


class ProxyGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("反向代理控制器")
        self.root.geometry("900x820")
        self.root.minsize(820, 760)
        
        # 初始化反向代理伺服器
        self.proxy_server = ReverseProxyServer()
        self.auth_config = load_local_auth_config()
        
        # 創建UI組件
        self.create_widgets()
        
        # 更新狀態
        self.update_status()

        # 開啟 GUI 後自動啟動代理並做一次健康檢查
        self.root.after(300, self.auto_start_debug)
        
    def create_widgets(self):
        # 創建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 標題
        title_label = ttk.Label(main_frame, text="反向代理控制器", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=10)
        
        # 目標網址框架
        target_frame = ttk.LabelFrame(main_frame, text="目標網址", padding="5")
        target_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.target_url_var = tk.StringVar(value=self.proxy_server.target_url)
        self.target_entry = ttk.Entry(target_frame, textvariable=self.target_url_var, width=60)
        self.target_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 代理位址框架
        proxy_frame = ttk.LabelFrame(main_frame, text="代理位址", padding="5")
        proxy_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.proxy_address_var = tk.StringVar(value=self.proxy_server.get_proxy_address())
        self.proxy_label = ttk.Label(proxy_frame, textvariable=self.proxy_address_var, font=("Arial", 10))
        self.proxy_label.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 控制按鈕框架
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        self.start_button = ttk.Button(control_frame, text="開始代理", command=self.start_proxy)
        self.start_button.grid(row=0, column=0, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="停止代理", command=self.stop_proxy, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5)
        
        self.update_button = ttk.Button(control_frame, text="更新設定", command=self.update_settings)
        self.update_button.grid(row=0, column=2, padx=5)
        
        # 狀態框架
        status_frame = ttk.LabelFrame(main_frame, text="狀態", padding="5")
        status_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.status_var = tk.StringVar(value="未啟動")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, font=("Arial", 10))
        self.status_label.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 測試框架
        test_frame = ttk.LabelFrame(main_frame, text="測試", padding="5")
        test_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.test_button = ttk.Button(test_frame, text="測試代理", command=self.test_proxy)
        self.test_button.grid(row=0, column=0, padx=5, pady=5)
        
        # 認證配置
        auth_frame = ttk.LabelFrame(main_frame, text="認證配置", padding="5")
        auth_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(auth_frame, text="Authorization Token:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.auth_token_entry = ttk.Entry(auth_frame, width=50, show="*")
        self.auth_token_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.auth_token_entry.insert(0, self.auth_config.get("authorization", os.environ.get("BIGMODEL_AUTH", "")))
        ttk.Label(
            auth_frame,
            text="格式: JWT 三段，以 . 分隔，例如 header.payload.signature；請填入瀏覽器 Network 的 Authorization 原值。",
            foreground="#555555",
        ).grid(row=1, column=1, sticky=tk.W, padx=5, pady=1)
        
        ttk.Label(auth_frame, text="Model ID:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.model_id_entry = ttk.Entry(auth_frame, width=50)
        self.model_id_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.model_id_entry.insert(0, self.auth_config.get("model_id", os.environ.get("BIGMODEL_MODEL_ID", "11989")))

        ttk.Label(auth_frame, text="Organization:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.org_entry = ttk.Entry(auth_frame, width=50)
        self.org_entry.grid(row=3, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.org_entry.insert(0, self.auth_config.get("organization", os.environ.get("BIGMODEL_ORG", "")))

        ttk.Label(auth_frame, text="Project:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
        self.project_entry = ttk.Entry(auth_frame, width=50)
        self.project_entry.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.project_entry.insert(0, self.auth_config.get("project", os.environ.get("BIGMODEL_PROJECT", "")))

        auth_buttons = ttk.Frame(auth_frame)
        auth_buttons.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=4)
        ttk.Button(auth_buttons, text="OPEN", command=self.open_bigmodel_devtools).grid(row=0, column=0, padx=4)
        ttk.Button(auth_buttons, text="開啟 BigModel", command=self.open_bigmodel_page).grid(row=0, column=1, padx=4)
        ttk.Button(auth_buttons, text="Network/Cookie 欄位指引", command=self.show_auth_sop).grid(row=0, column=2, padx=4)
        ttk.Button(auth_buttons, text="建立本機設定範本", command=self.create_local_auth_template).grid(row=0, column=3, padx=4)
        ttk.Button(auth_buttons, text="RELOAD JSON", command=self.reload_local_auth_config).grid(row=0, column=4, padx=4)

        # 消息框架
        message_frame = ttk.LabelFrame(main_frame, text="消息傳遞", padding="5")
        message_frame.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # 訊息輸入
        ttk.Label(message_frame, text="輸入訊息:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.message_entry = ttk.Entry(message_frame, width=50)
        self.message_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.message_entry.insert(0, "HI")

        self.use_chatbox_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            message_frame,
            text="是否使用 CHATBOX",
            variable=self.use_chatbox_var,
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        # 發送按鈕
        send_button = ttk.Button(message_frame, text="發送訊息", command=self.send_message)
        send_button.grid(row=2, column=0, columnspan=2, pady=5)
        
        # 響應顯示
        ttk.Label(message_frame, text="AI回應:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.response_text = scrolledtext.ScrolledText(message_frame, height=6, width=70)
        self.response_text.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=2)

        # 日誌框架
        log_frame = ttk.LabelFrame(main_frame, text="日誌", padding="5")
        log_frame.grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, width=70)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置權重
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(8, weight=1)
        auth_frame.columnconfigure(1, weight=1)
        message_frame.columnconfigure(1, weight=1)
        message_frame.rowconfigure(4, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
    def log_message(self, message):
        """添加日誌消息"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)

    def auto_start_debug(self):
        """開啟時自動啟動代理並執行基本除錯"""
        try:
            if not self.proxy_server.is_running:
                self.start_proxy()
            self.root.after(1200, self.auto_health_check)
        except Exception as e:
            self.log_message(f"自動啟動除錯失敗: {str(e)}")

    def auto_health_check(self):
        """自動健康檢查，不跳出對話框"""
        try:
            proxy_address = self.proxy_server.get_proxy_address()
            response = requests.get(f"{proxy_address}/health", timeout=10)
            if response.status_code == 200:
                self.log_message(f"自動除錯成功: /health {response.json()}")
            else:
                self.log_message(f"自動除錯失敗: /health {response.status_code}")
        except requests.exceptions.RequestException as e:
            self.log_message(f"自動除錯連線失敗: {str(e)}")
        except Exception as e:
            self.log_message(f"自動除錯發生錯誤: {str(e)}")

    def open_bigmodel_page(self):
        """開啟 BigModel 體驗中心，由使用者自行複製授權欄位"""
        url = "https://bigmodel.cn/trialcenter/modeltrial/text?modelCode=glm-5.1"
        webbrowser.open(url)
        self.log_message("已開啟 BigModel，請在瀏覽器 DevTools Network 內手動複製授權欄位")

    def open_bigmodel_devtools(self):
        """使用 Selenium 開啟 Chrome 和 DevTools，等待使用者手動操作"""
        try:
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "open_bigmodel_devtools.py")
            subprocess.Popen([sys.executable, script_path], cwd=os.path.dirname(script_path))
            self.log_message("已啟動 Selenium Chrome + DevTools。請在新開啟的瀏覽器中手動操作。")
        except FileNotFoundError:
            self.log_message("啟動失敗: 找不到 Python 或 open_bigmodel_devtools.py")
            messagebox.showerror("錯誤", "啟動失敗: 找不到 Python 或 open_bigmodel_devtools.py")
        except Exception as e:
            self.log_message(f"啟動 Selenium Chrome 失敗: {str(e)}")
            messagebox.showerror("錯誤", f"啟動 Selenium Chrome 失敗: {str(e)}")

    def show_auth_sop(self):
        """顯示取得授權欄位的安全 SOP"""
        sop = (
            "取得欄位 SOP:\n"
            "1. 按「開啟 BigModel」並登入。\n"
            "2. 按 F12，切到 Network，勾選 Preserve log。\n"
            "3. 在 BigModel 頁面送出 HI。\n"
            "4. 找到 /api/biz/trial/response/v4/sse/11989。\n"
            "5. 複製 Request Headers 的 Authorization 到 Authorization Token。\n"
            "6. 複製 Bigmodel-Organization 到 Organization。\n"
            "7. 複製 Bigmodel-Project 到 Project。\n"
            "8. Request URL 最後一段填入 Model ID，例如 11989。\n\n"
            "Cookie 欄位僅用於判斷前端請求是否帶 session；目前 APP 不需要填 Cookie。\n"
            "注意: APP 不會讀取 Cookie 或 Network 內容，請你手動查看並填入上方欄位。"
        )
        self.response_text.delete(1.0, tk.END)
        self.response_text.insert(tk.END, sop)
        self.log_message("已顯示取得授權欄位 SOP")

    def create_local_auth_template(self):
        """建立本機授權設定檔範本"""
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCAL_AUTH_CONFIG)
        if os.path.exists(config_path):
            self.log_message(f"{LOCAL_AUTH_CONFIG} 已存在，不覆蓋")
            messagebox.showinfo("已存在", f"{LOCAL_AUTH_CONFIG} 已存在")
            return
        template = {
            "authorization": "header.payload.signature",
            "model_id": "11989",
            "organization": "org_xxx",
            "project": "proj_xxx",
        }
        with open(config_path, "w", encoding="utf-8") as config_file:
            json.dump(template, config_file, ensure_ascii=False, indent=2)
        self.log_message(f"已建立 {LOCAL_AUTH_CONFIG}，請在檔案中填入本機授權值後重啟 APP")
        messagebox.showinfo("完成", f"已建立 {LOCAL_AUTH_CONFIG}，填入授權值後重啟 APP")

    def reload_local_auth_config(self):
        """重新讀取本機授權設定並更新 GUI 欄位"""
        self.auth_config = load_local_auth_config()
        if not self.auth_config:
            self.log_message(f"未讀取到 {LOCAL_AUTH_CONFIG}，請確認檔案存在且 JSON 格式正確")
            messagebox.showwarning("讀取失敗", f"未讀取到 {LOCAL_AUTH_CONFIG}")
            return

        field_map = [
            (self.auth_token_entry, self.auth_config.get("authorization", "")),
            (self.model_id_entry, self.auth_config.get("model_id", "")),
            (self.org_entry, self.auth_config.get("organization", "")),
            (self.project_entry, self.auth_config.get("project", "")),
        ]
        for entry, value in field_map:
            entry.delete(0, tk.END)
            entry.insert(0, value)

        self.log_message(f"已重新讀取 {LOCAL_AUTH_CONFIG} 並更新欄位")
    
    def send_message(self):
        """發送消息到AI網頁"""
        try:
            message = self.message_entry.get().strip()
            if not message:
                messagebox.showwarning("警告", "請輸入要發送的訊息")
                return
            
            proxy_address = self.proxy_server.get_proxy_address()
            auth_token = self.auth_token_entry.get().strip() or os.environ.get("BIGMODEL_AUTH", "").strip()
            model_id = self.model_id_entry.get().strip() or os.environ.get("BIGMODEL_MODEL_ID", "11989")
            model_code = os.environ.get("BIGMODEL_MODEL_CODE", "glm-5.1")
            org_id = self.org_entry.get().strip() or os.environ.get("BIGMODEL_ORG", "").strip()
            project_id = self.project_entry.get().strip() or os.environ.get("BIGMODEL_PROJECT", "").strip()

            if not auth_token:
                self.log_message("缺少 Authorization Token，請先填入登入後的 Authorization")
                messagebox.showwarning("缺少認證", "請先填入 Authorization Token")
                return
            if auth_token.count(".") != 2:
                self.log_message("Authorization Token 格式看起來不正確，應為 header.payload.signature")
                messagebox.showwarning("格式錯誤", "Authorization Token 應為 JWT 三段格式：header.payload.signature")
                return
            if not org_id or not project_id:
                self.log_message("缺少 Organization 或 Project，請填入 Bigmodel-Organization / Bigmodel-Project")
                messagebox.showwarning("缺少認證", "請填入 Organization 和 Project")
                return
            
            use_chatbox = self.use_chatbox_var.get()
            if use_chatbox:
                api_json_data = {
                    "model": model_code.replace(".", "-"),
                    "messages": [{"role": "user", "content": message}],
                    "temperature": 1,
                    "top_p": 0.95,
                    "max_tokens": 1000,
                }
            else:
                # 構建前端 SSE API 請求格式
                api_json_data = {
                    "model": model_code,
                    "prompt": [{"role": "user", "content": message, "fileContentList": []}],
                    "modelId": int(model_id) if model_id.isdigit() else model_id,
                    "stream": True,
                    "thinking": {"type": "enabled"},
                    "max_tokens": 65536,
                    "temperature": 1,
                    "top_p": 0.95,
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
            
            # 構建headers
            headers = {
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                "Set-Language": "zh",
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            
            # 如果有認證token，添加到headers
            if auth_token:
                headers["Authorization"] = auth_token
                self.log_message("已添加認證token")
            if org_id:
                headers["Bigmodel-Organization"] = org_id
            if project_id:
                headers["Bigmodel-Project"] = project_id
            
            # 發送API請求
            if use_chatbox:
                api_url = f"{proxy_address}/api/biz/trial/response/v4/sse/glm-5-1"
                self.log_message("使用 CHATBOX 模式：送出 OpenAI messages，由 proxy 轉成 BigModel prompt")
            else:
                api_url = f"{proxy_address}/api/biz/trial/response/v4/sse/{model_id}"
            self.log_message(f"發送請求到: {api_url}")
            
            api_response = requests.post(
                api_url,
                json=api_json_data,
                headers=headers,
                timeout=30
            )
            
            if api_response.status_code == 200:
                api_response_data = api_response.text
                self.response_text.delete(1.0, tk.END)
                self.response_text.insert(tk.END, api_response_data[:8000])
                self.log_message(f"API端點訊息發送成功: {message}")
                self.log_message("已收到 SSE 串流回應")
            else:
                self.response_text.delete(1.0, tk.END)
                self.response_text.insert(tk.END, f"API端點請求失敗: {api_response.status_code}")
                self.log_message(f"API端點訊息發送失敗: {api_response.status_code}")
                self.log_message(f"錯誤信息: {api_response.text}")
                
                # 如果是401錯誤，提示認證問題
                if api_response.status_code == 401:
                    messagebox.showwarning(
                        "認證錯誤",
                        "API 未收到或不接受 Authorization。請確認 Token、Organization、Project 都已填入。"
                    )
                
        except requests.exceptions.RequestException as e:
            self.response_text.delete(1.0, tk.END)
            self.response_text.insert(tk.END, f"網路錯誤: {str(e)}")
            self.log_message(f"網路錯誤: {str(e)}")
        except Exception as e:
            self.response_text.delete(1.0, tk.END)
            self.response_text.insert(tk.END, f"錯誤: {str(e)}")
            self.log_message(f"發送訊息時發生錯誤: {str(e)}")
        
    def start_proxy(self):
        """啟動代理服務"""
        try:
            # 更新目標網址
            self.proxy_server.target_url = self.target_url_var.get()
            
            # 啟動伺服器
            self.proxy_server.start_server()
            
            # 更新UI
            self.status_var.set("運行中")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.update_proxy_address()
            
            self.log_message("代理服務已啟動")
            
        except Exception as e:
            messagebox.showerror("錯誤", f"啟動代理服務失敗: {str(e)}")
            self.log_message(f"啟動失敗: {str(e)}")
    
    def stop_proxy(self):
        """停止代理服務"""
        try:
            self.proxy_server.stop_server()
            
            # 更新UI
            self.status_var.set("已停止")
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            
            self.log_message("代理服務已停止")
            
        except Exception as e:
            messagebox.showerror("錯誤", f"停止代理服務失敗: {str(e)}")
            self.log_message(f"停止失敗: {str(e)}")
    
    def update_settings(self):
        """更新設定"""
        try:
            old_url = self.proxy_server.target_url
            new_url = self.target_url_var.get()
            
            if old_url != new_url:
                self.proxy_server.target_url = new_url
                self.log_message(f"目標網址已更新為: {new_url}")
            else:
                self.log_message("目標網址未變更")
                
        except Exception as e:
            messagebox.showerror("錯誤", f"更新設定失敗: {str(e)}")
            self.log_message(f"更新設定失敗: {str(e)}")
    
    def update_proxy_address(self):
        """更新代理位址顯示"""
        self.proxy_address_var.set(self.proxy_server.get_proxy_address())
    
    def test_proxy(self):
        """測試代理服務"""
        try:
            proxy_address = self.proxy_server.get_proxy_address()
            
            # 測試GET請求
            response = requests.get(f"{proxy_address}/health", timeout=10)
            
            if response.status_code == 200:
                self.log_message(f"代理服務測試成功: {response.json()}")
                messagebox.showinfo("成功", "代理服務測試成功！")
            else:
                self.log_message(f"代理服務測試失敗: {response.status_code}")
                messagebox.showwarning("警告", f"代理服務測試失敗: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.log_message(f"代理服務測試失敗: {str(e)}")
            messagebox.showerror("錯誤", f"無法連接到代理服務: {str(e)}")
        except Exception as e:
            self.log_message(f"測試過程中發生錯誤: {str(e)}")
            messagebox.showerror("錯誤", f"測試過程中發生錯誤: {str(e)}")
    
    def update_status(self):
        """定期更新狀態"""
        try:
            # 這裡可以添加更多的狀態檢查邏輯
            pass
        except Exception as e:
            self.log_message(f"狀態更新失敗: {str(e)}")
        
        # 每5秒更新一次
        self.root.after(5000, self.update_status)

def main():
    # 設置日誌
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # 創建主窗口
    root = tk.Tk()
    app = ProxyGUI(root)
    
    # 運行應用程序
    root.mainloop()

if __name__ == "__main__":
    main()
