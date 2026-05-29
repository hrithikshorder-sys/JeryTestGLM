# 反向代理控制器

一個用於代理AI網頁的Python應用程序，提供圖形化界面來控制反向代理服務。

## 功能特點

- 🌐 **反向代理**: 將請求轉發到指定的AI網頁
- 🎛️ **圖形化界面**: 使用tkinter提供直觀的控制界面
- 💬 **消息傳遞**: 支持直接在APP中輸入訊息並獲取AI回應
- 📡 **GET/POST支持**: 支持多種HTTP請求方法
- 🔧 **可配置**: 可以自定義目標網址和代理端口
- 📊 **實時狀態**: 顯示代理服務的運行狀態
- 🧪 **測試功能**: 內置測試工具驗證代理服務
- 📝 **日誌記錄**: 詳細的操作日誌
- 🔌 **API客戶端**: 提供Python客戶端庫，可在代碼中直接使用

## 系統要求

- Python 3.7+
- 操作系統: Windows/Linux/macOS

## 安裝說明

1. 克隆或下載項目文件
2. 安裝依賴包：

```bash
pip install -r requirements.txt
```

## 使用方法

### 啟動應用程序

```bash
python main.py
```

### 操作步驟

1. **啟動應用**：運行`main.py`，會打開圖形化界面
2. **設置目標網址**：在"目標網址"欄位輸入要代理的網址（預設為GLM-5.1）
3. **啟動代理**：點擊"開始代理"按鈕
4. **查看代理位址**：代理位址會顯示在界面上（預設為`http://localhost:8080`）
5. **測試代理**：點擊"測試代理"按鈕驗證服務是否正常
6. **消息傳遞**：在"消息傳遞"區塊輸入訊息，點擊"發送訊息"獲取AI回應
7. **停止代理**：點擊"停止代理"按鈕關閉服務

### 功能說明

#### 控制按鈕
- **開始代理**: 啟動反向代理服務
- **停止代理**: 停止反向代理服務
- **更新設定**: 更新目標網址設定
- **測試代理**: 測試代理服務是否正常運行

#### 狀態顯示
- **目標網址**: 顯示當前代理的目標網址
- **代理位址**: 顯示代理服務的訪問地址
- **狀態**: 顯示代理服務的當前狀態（未啟動/運行中/已停止）
- **日誌**: 顯示操作日誌和錯誤信息

### 測試工具

使用測試腳本驗證代理服務：

```bash
python test_proxy.py
```

測試腳本會執行以下檢查：
1. 自動啟動代理服務
2. 目標頁面 GET 測試
3. 代理 `/health` 健康檢查
4. 自動送出訊息 `HI`
5. 若收到 `405`，確認錯誤來源是否為目標站
6. 若提供授權資訊，模擬前端 SSE API 呼叫

模擬前端 SSE 呼叫需要先設定登入後的授權資訊：

```powershell
$env:BIGMODEL_AUTH="你的登入 Authorization token"
$env:BIGMODEL_MODEL_ID="模型 ID"
$env:BIGMODEL_MODEL_CODE="glm-5.1"
python test_proxy.py
```

可選設定：

```powershell
$env:BIGMODEL_ORG="你的 organization id"
$env:BIGMODEL_PROJECT="你的 project id"
```

目前已知 `https://bigmodel.cn/trialcenter/modeltrial/text?modelCode=glm-5.1` 是前端頁面，GET 可正常開啟，但不接受 POST 聊天訊息。前端實際聊天 API 為 `/api/biz/trial/response/v4/sse/{modelId}`，需要 `Authorization`。

若前端 SSE 呼叫回 `401`，請重新從瀏覽器 Network 複製 `Authorization` 原值，並確認 `BIGMODEL_ORG`、`BIGMODEL_PROJECT`、`BIGMODEL_MODEL_ID` 與該請求一致。不要自行加上 `Bearer`，除非瀏覽器請求裡本來就有。

## 配置說明

### 預設配置

- **目標網址**: `https://bigmodel.cn/trialcenter/modeltrial/text?modelCode=glm-5.1`
- **代理端口**: `8080`
- **監聽地址**: `0.0.0.0`（所有接口）

### 自定義配置

可以修改`reverse_proxy_server.py`中的以下參數：

```python
# 修改目標網址
self.target_url = "https://your-target-url.com"

# 修改代理端口
self.proxy_port = 8080
```

## 技術架構

### 核心組件

1. **ReverseProxyServer** (`reverse_proxy_server.py`)
   - Flask Web框架
   - 請求轉發邏輯
   - 線程管理

2. **ProxyGUI** (`proxy_gui.py`)
   - tkinter圖形界面
   - 用戶交互控制
   - 狀態監控

3. **主程序** (`main.py`)
   - 程序入口
   - 日誌配置
   - 錯誤處理
   
4. **AI代理客戶端** (`ai_proxy_client.py`)
   - Python客戶端庫
   - 封裝AI交互功能
   - 支持代碼中直接調用

### 工作流程

```
用戶請求 → GUI界面 → 反向代理 → 目標網站 → 返回響應
```

## 注意事項

1. **防火牆設置**: 確保代理端口（預設8080）未被防火牆阻擋
2. **網路連接**: 確保能夠訪問目標網站
3. **權限**: 某些系統可能需要管理員權限才能綁定特定端口
4. **資源使用**: 代理服務會占用一定的CPU和內存資源

## 故障排除

### 常見問題

1. **端口被占用**
   - 修改`proxy_port`變數
   - 或停止占用該端口的程序

2. **無法連接到目標網站**
   - 檢查網路連接
   - 確認目標網址正確
   - 檢查防火牆設置

3. **GUI無法啟動**
   - 確保安裝了tkinter
   - 檢查Python版本兼容性

### 日誌查看

應用程序會生成`proxy_app.log`文件，包含詳細的運行日誌。

## 開發說明

### 完整專案紀錄

詳細流程、設計理念、除錯過程、啟動 SOP、困難與 checkpoint 請見：

```text
PROJECT_CHECKPOINTS.md
```

### 擴展功能

可以根據需要添加以下功能：
- 支持HTTPS代理
- 添加用戶認證
- 實現請求/響應過濾
- 添加性能監控

### 代碼結構

```
├── main.py              # 主程序入口
├── reverse_proxy_server.py  # 反向代理核心
├── proxy_gui.py        # 圖形界面
├── test_proxy.py       # 測試腳本
├── requirements.txt    # 依賴包列表
└── README.md           # 說明文檔
```

## API客戶端使用

### 基本使用

```python
from ai_proxy_client import AIProxyClient

# 創建客戶端
client = AIProxyClient(proxy_url="http://localhost:8080")

# 問AI問題
response = client.ask_ai("你好，請介紹一下你自己")
print(response)

# 檢查服務狀態
health = client.get_health_check()
print(health)
```

### 高級使用

```python
# 自定義參數
response = client.ask_ai(
    prompt="寫一首關於春天的詩",
    model_code="glm-5.1",
    temperature=0.8,
    max_tokens=500
)

# 自定義請求
custom_response = client.custom_request(
    endpoint="/some/endpoint",
    method="POST",
    data={"key": "value"}
)
```

## 版本歷史

- v1.1.0: 添加消息傳遞功能和API客戶端
- v1.0.0: 初始版本，支持基本反向代理功能

## 許可證

此項目僅用於學習和研究目的。

## 聯繫方式

如有問題或建議，請通過以下方式聯繫：
- 創建Issue
- 發送郵件

---

**注意**: 此應用程序僅用於合法用途，請遵守相關法律法規和服務條款。

## Chatbox Mode

The app includes a checkbox:

```text
[ ] 是否使用 CHATBOX
```

When disabled, the GUI sends the native BigModel trial payload:

```json
{
  "model": "glm-5.1",
  "prompt": [
    {
      "role": "user",
      "content": "HI",
      "fileContentList": []
    }
  ],
  "modelId": 11989,
  "stream": true
}
```

When enabled, the GUI simulates Chatbox/OpenAI request format:

```json
{
  "model": "glm-5-1",
  "messages": [
    {
      "role": "user",
      "content": "HI"
    }
  ]
}
```

The proxy then works as an API adapter:

```text
OpenAI messages request -> BigModel prompt request
BigModel SSE response -> OpenAI-compatible SSE response
```

This is required because Chatbox validates streamed `data:` objects. BigModel may return internal chunks such as:

```text
data: {"think":"1"}
```

Chatbox rejects that shape because it expects:

```json
{
  "choices": [
    {
      "delta": {
        "content": "..."
      }
    }
  ]
}
```

In Chatbox mode, the proxy filters non-display BigModel events and returns OpenAI-compatible chunks ending with:

```text
data: [DONE]
```

## Chatbox Debug SOP

1. Start the app:

```powershell
python main.py
```

2. Confirm the proxy is running:

```text
http://localhost:8080/health
```

3. Fill or reload local credentials:

```text
Authorization Token
Model ID
Organization
Project
```

4. Enable:

```text
[x] 是否使用 CHATBOX
```

5. Send default message:

```text
HI
```

6. Expected behavior:

- The request body contains `messages`.
- The proxy logs request conversion to BigModel `prompt`.
- The response body contains OpenAI `choices`.
- Chatbox should not show `Invalid input: expected array choices`.

## Latest Checkpoint

```text
ae7416b Convert BigModel SSE to OpenAI stream
```

Validation command:

```powershell
python -m py_compile reverse_proxy_server.py proxy_gui.py main.py
```

## Chatbox Exclusion Checklist

When `是否使用 CHATBOX` is enabled, the proxy must exclude BigModel-native SSE details from the final response.

Do not send these raw chunks to Chatbox:

```text
data: {"think":"1"}
data: [{"title":"...","link":"..."}]
event:webSearch
event:add
id:...
```

These are BigModel/internal SSE details. Chatbox expects OpenAI-compatible chunks only.

Valid Chatbox stream chunk:

```text
data: {"choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}
```

Valid stream ending:

```text
data: [DONE]
```

If Chatbox shows:

```text
Type validation failed
Invalid input: expected array at path ["choices"]
```

Check these items:

- The request body sent to the proxy has `messages`.
- The proxy log says it converted OpenAI messages to BigModel prompt.
- The response does not include raw `think`, `webSearch`, `event`, or `id` lines.
- Every JSON `data:` line has `choices` or `error`.
- Response content type is `text/event-stream; charset=utf-8`.

## Profile Save

The app stores provider settings in `profile_config.local.json`.

Current profile behavior:

- `bigmodel` shows `Credentials`.
- `claude_web` shows `ClaudeAI`.
- Switching profiles does not restart the proxy.
- The `Record` button on the `ClaudeAI` section writes the current Claude fields back into `profile_config.local.json`.

Claude fields saved by `Record`:

```text
base_url
organization_id
conversation_id
cookie
device_id
user_agent
payload_template
```

If `claude_web` is selected, the main `Send` button routes through the Claude path instead of the BigModel path.
