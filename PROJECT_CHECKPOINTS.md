# 反向代理控制器專案完整紀錄

日期：2026-05-28

## 1. 專案目標

本專案目標是建立一個 Python 桌面工具，用 GUI 控制本機反向代理，並透過模擬 BigModel 前端 SSE API 的方式送出訊息、接收模型串流回應。

目前重點不是呼叫官方公開 API，而是重現 BigModel 網頁前端的請求格式：

```text
POST /api/biz/trial/response/v4/sse/{modelId}
```

## 2. 目前架構

```text
myapp/
├── main.py                       # GUI 入口
├── proxy_gui.py                  # tkinter GUI、授權欄位、SSE 請求
├── reverse_proxy_server.py       # Flask 反向代理
├── test_proxy.py                 # 自動化測試與除錯腳本
├── ai_proxy_client.py            # 舊版 API client
├── open_bigmodel_devtools.py     # Selenium 開 Chrome + DevTools
├── auth_config.local.example.json# 本機授權設定範本
├── auth_config.local.json        # 本機私有授權設定，需自行建立，不提交
├── frontend_sse_debug.md         # SSE 除錯紀錄
├── debug_report.md               # 歷史除錯報告
├── README.md                     # 使用說明
└── requirements.txt              # 依賴
```

## 3. 設計理念

### 3.1 安全邊界

`Authorization` 和 `Cookie` 屬於登入憑證，因此不硬編碼進程式碼，也不自動讀取瀏覽器 Network/Cookie。

目前採用安全替代方案：

- 使用者手動從瀏覽器 DevTools 複製必要欄位
- APP 可從本機私有檔 `auth_config.local.json` 自動預填
- `.gitignore` 排除 `auth_config.local.json` 與 log
- 代理日誌遮蔽 `Authorization`、`Cookie` 等敏感 header

### 3.2 前端模擬而非頁面 POST

BigModel 頁面：

```text
https://bigmodel.cn/trialcenter/modeltrial/text?modelCode=glm-5.1
```

只是一個 HTML 頁面。直接 POST 到：

```text
/trialcenter/modeltrial/text
```

會得到：

```text
405 Method Not Allowed
```

真正可用的聊天 API 是前端 SSE API：

```text
/api/biz/trial/response/v4/sse/{modelId}
```

### 3.3 GUI 優先

使用者主要透過 `proxy_gui.py` 操作：

- 自動啟動代理
- 預設訊息 `HI`
- 預填 Model ID
- 可讀取本機 JSON 設定
- 可一鍵開 Chrome + DevTools
- 可顯示欄位取得 SOP

## 4. 啟動 SOP

### 4.1 安裝依賴

```powershell
cd C:\Users\BIOS\Documents\myapp
pip install -r requirements.txt
```

### 4.2 建立本機授權設定

方法一：在 APP 裡按：

```text
建立本機設定範本
```

方法二：手動複製範本：

```powershell
Copy-Item .\auth_config.local.example.json .\auth_config.local.json
```

填入：

```json
{
  "authorization": "瀏覽器 Network 複製的 Authorization 原值",
  "model_id": "11989",
  "organization": "Bigmodel-Organization",
  "project": "Bigmodel-Project"
}
```

### 4.3 啟動 APP

```powershell
python main.py
```

APP 啟動後會：

1. 自動啟動代理
2. 自動測 `/health`
3. 從 `auth_config.local.json` 預填四個欄位
4. 訊息欄預設 `HI`

### 4.4 更新授權欄位

若修改 `auth_config.local.json`，不必重啟 APP。按：

```text
RELOAD JSON
```

即可重新讀取：

- Authorization Token
- Model ID
- Organization
- Project

## 5. 取得欄位 SOP

1. 按 APP 的 `OPEN`，或按 `開啟 BigModel`
2. 登入 BigModel
3. 按 `F12`
4. 切到 `Network`
5. 勾選 `Preserve log`
6. 在 BigModel 頁面送出 `HI`
7. 找到：

```text
/api/biz/trial/response/v4/sse/11989
```

8. 複製下列欄位：

```text
Authorization
Bigmodel-Organization
Bigmodel-Project
```

9. URL 最後一段就是：

```text
model_id = 11989
```

## 6. 目前 GUI 按鈕功能

### OPEN

使用 Selenium 啟動 Chrome，並自動開啟 DevTools。

特性：

- 只開 Chrome
- 只導向 BigModel
- 不點擊網頁
- 不讀 Cookie
- 不讀 Network
- 等使用者手動操作

### 開啟 BigModel

用系統預設瀏覽器開 BigModel 頁面，不開 DevTools。

### Network/Cookie 欄位指引

在 APP 回應區顯示手動取得欄位的 SOP。

### 建立本機設定範本

建立 `auth_config.local.json`，讓使用者填入本機授權值。

### RELOAD JSON

重新讀取 `auth_config.local.json`，即時更新 GUI 欄位。

### 發送訊息

使用前端 SSE 格式送出目前訊息欄內容。

## 7. SSE 請求格式

目前 GUI 發送的 payload：

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
  "stream": true,
  "thinking": {
    "type": "disabled"
  },
  "max_tokens": 65536,
  "temperature": 1,
  "top_p": 0.95
}
```

目前 headers：

```text
Accept: text/event-stream
Content-Type: application/json
Set-Language: zh
Accept-Language: zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7
Authorization: 使用者填入
Bigmodel-Organization: 使用者填入
Bigmodel-Project: 使用者填入
```

## 8. 回應處理策略

BigModel SSE 回應包含：

```text
event:
id:
data:
```

早期版本直接顯示完整 SSE，會看到大量：

- `event:webSearch`
- `event:add`
- `id:...`
- `data:{"think":"..."}`
- 搜尋參考資料

目前策略：

- 關閉 `thinking`
- 不送 `web_search tools`
- 解析 `data:` JSON
- 過濾 list 型態的搜尋資料
- 過濾含 `think` 的思考串流
- 只收集這些欄位：
  - `text`
  - `content`
  - `answer`
  - `output`

若解析不到內容，顯示：

```text
未解析到回答內容。請查看 proxy_app.log 或暫時改用完整 SSE 除錯。
```

## 9. 除錯過程

### 9.1 問題：POST 頁面回 405

現象：

```text
POST /trialcenter/modeltrial/text -> 405
```

判斷：

該路徑是 HTML 頁面，不是 API。

修正：

改用前端 SSE API：

```text
/api/biz/trial/response/v4/sse/{modelId}
```

### 9.2 問題：SSE 回 401

現象：

```json
{"error":{"code":"1001","message":"Header中未收到Authorization参数，无法进行身份验证。"}}
```

原因：

- 未帶 Authorization
- GUI 欄位空白
- 或 APP 啟動環境沒有 `BIGMODEL_AUTH`

修正：

- 加入 GUI 欄位檢查
- 若缺 token 則阻止送出
- 加入 JSON 預填

### 9.3 問題：SSE 回 500

現象：

```text
POST /api/biz/trial/response/v4/sse/11989 -> 500
```

原因：

payload 太簡化，與前端實際請求不一致。

修正：

補上：

- `prompt[].fileContentList`
- `thinking`
- `max_tokens`
- `temperature`
- `top_p`
- `tools.web_search`

結果：

```text
HTTP 200
Content-Type: text/event-stream;charset=UTF-8
```

### 9.4 問題：回應內容太雜

現象：

SSE 回應包含搜尋資料、思考串流、event/id。

修正：

- 關閉 `thinking`
- 移除 `web_search tools`
- 只解析 `data:` 中的回答欄位

## 10. 遇到的困難

1. BigModel 目標頁是 SPA HTML，不是聊天 API
2. 前端 API 需要登入態 headers
3. `Authorization`、`Cookie` 不能硬編碼或自動擷取
4. SSE payload 必須接近前端實際格式
5. SSE 回應不是一般 JSON，而是事件流
6. 回應中含搜尋資料、思考資料、答案資料，需要解析
7. tkinter 預設視窗高度不足，認證欄位曾經被擠到下方
8. APP 重啟與 JSON reload 需要區分

## 11. 任務清單

已完成：

- 建立 Flask 反向代理
- 建立 tkinter GUI
- 自動啟動代理
- 預設訊息 `HI`
- 前端 SSE API 模擬
- 支援 Authorization / Organization / Project
- 支援 `auth_config.local.json`
- 支援 `RELOAD JSON`
- 加入 Selenium `OPEN`
- 加入 Network 欄位 SOP
- 遮蔽敏感 header log
- 過濾 SSE 回應中的多餘內容

待觀察：

- `thinking: disabled` 下不同模型是否仍會回 `think`
- 移除 `web_search tools` 後是否所有問題都能穩定回答
- SSE 回答欄位是否固定為 `text/content/answer/output`

可選後續：

- 加入「完整 SSE 除錯模式」切換
- 加入「只顯示 data 原文」切換
- 加入「只顯示最終回答」切換
- 加入更完整的 SSE parser
- 改用官方 API Key，避免依賴前端私有 API

## 12. Checkpoints

### Checkpoint 1：基本代理可啟動

驗證：

```text
GET /health -> 200
```

狀態：完成

### Checkpoint 2：確認 405 來源

驗證：

```text
GET 目標頁 -> 200
POST 目標頁 -> 405
```

狀態：完成

### Checkpoint 3：取得前端 SSE 端點

確認端點：

```text
/api/biz/trial/response/v4/sse/11989
```

狀態：完成

### Checkpoint 4：補齊授權 headers

需要：

```text
Authorization
Bigmodel-Organization
Bigmodel-Project
```

狀態：完成

### Checkpoint 5：補齊前端 payload

需要：

```text
prompt
modelId
thinking
max_tokens
temperature
top_p
tools
```

狀態：完成

### Checkpoint 6：SSE 成功

驗證：

```text
HTTP 200
Content-Type: text/event-stream;charset=UTF-8
```

狀態：完成

### Checkpoint 7：GUI 可用

功能：

- 自動代理
- JSON 預填
- RELOAD JSON
- 發送 SSE
- 顯示回應

狀態：完成

### Checkpoint 8：回應內容過濾

目標：

只顯示可辨識的回答內容，不顯示 `event/id/webSearch/think`。

狀態：已實作，需持續觀察 API 回傳格式。

## 13. 測試指令

語法檢查：

```powershell
python -m py_compile main.py proxy_gui.py reverse_proxy_server.py test_proxy.py open_bigmodel_devtools.py
```

啟動 APP：

```powershell
python main.py
```

測試代理與 SSE：

```powershell
python test_proxy.py
```

## 14. 安全注意事項

不要提交：

```text
auth_config.local.json
proxy_app.log
```

不要在聊天或文件中貼：

```text
Authorization
Cookie
Set-Cookie
bigmodel_token_production
```

若 token 曾貼出，建議重新登入 BigModel，讓舊 token 失效。

## 15. Chatbox Adapter Checkpoint

Date: 2026-05-28

### Problem

Chatbox sends an OpenAI-compatible request body:

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

BigModel trial SSE does not accept this shape directly. It expects:

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

The root cause was not the URL alone. The proxy was forwarding requests without translating the API contract.

### Design Decision

The local service now behaves as an API Adapter / API Translator:

- If the incoming JSON contains `messages`, it is treated as Chatbox/OpenAI format.
- The proxy converts `messages` into BigModel `prompt`.
- The proxy replaces the upstream URL with `/api/biz/trial/response/v4/sse/{model_id}`.
- The proxy fills required BigModel headers from `auth_config.local.json` or environment variables.
- If the incoming JSON already contains BigModel `prompt`, it is forwarded as before.

### Header Rules

The adapter fills these headers when missing:

```text
Authorization
Bigmodel-Organization
Bigmodel-Project
Set-Language: zh
Accept: text/event-stream
Content-Type: application/json
```

Credential priority:

```text
incoming request headers -> auth_config.local.json -> environment variables
```

### GUI Change

Added checkbox:

```text
[ ] 是否使用 CHATBOX
```

Behavior:

- Unchecked: GUI sends native BigModel `prompt` payload.
- Checked: GUI sends Chatbox/OpenAI `messages` payload and lets the proxy convert it.

### Checkpoint

Run:

```powershell
python -m py_compile reverse_proxy_server.py proxy_gui.py main.py
python main.py
```

Expected:

- App opens normally.
- Proxy starts automatically.
- Default message is `HI`.
- Unchecked mode sends BigModel `prompt`.
- Checked Chatbox mode sends `messages`, proxy logs conversion, then BigModel receives `prompt`.

## 16. Chatbox Response Adapter Checkpoint

Date: 2026-05-28

### Problem

After request-body conversion was added, Chatbox still failed with:

```text
Type validation failed: Value: {"think":"1"}.
Invalid input: expected array at path ["choices"]
```

This means the request adapter was working, but the response was still BigModel-native SSE.

BigModel may return SSE lines like:

```text
event:add
data:{"think":"1"}
```

Chatbox expects OpenAI-compatible streaming chunks:

```text
data: {"choices":[{"delta":{"content":"..."}}]}
```

So the missing layer was:

```text
BigModel SSE response -> OpenAI-compatible SSE response
```

### Root Cause

The previous proxy only translated the incoming request:

```text
OpenAI messages -> BigModel prompt
```

But it returned the upstream response unchanged:

```text
BigModel data:{"think":"1"} -> Chatbox
```

Chatbox validates each `data:` JSON object. If the object does not contain either `choices` or `error`, validation fails.

### Design Decision

Only Chatbox/OpenAI mode should receive translated response chunks.

Rules:

- If request JSON contains `messages`, enable OpenAI response mode.
- Convert request body to BigModel `prompt`.
- Send request to BigModel trial SSE endpoint.
- Convert BigModel SSE response to OpenAI-compatible SSE before returning to Chatbox.
- Ignore non-display BigModel events such as `think` and `webSearch`.
- Extract visible text from common fields: `text`, `content`, `answer`, `output`.
- Wrap visible text into `choices[0].delta.content`.
- End the stream with `data: [DONE]`.

### Output Format

The adapter emits:

```text
data: {"id":"chatcmpl-bigmodel-proxy","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-bigmodel-proxy","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-bigmodel-proxy","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## 18. ClaudeAI Web Reverse Proxy Page

Date: 2026-05-29

### Goal

Add a second GUI page named `ClaudeAI` with the same local-proxy testing concept as the original page, but targeting Claude Web frontend reverse proxy behavior.

This is not the official Anthropic API mode. It is a manual frontend-simulation mode:

```text
User logs in to Claude Web
User manually copies Network fields
App stores nothing automatically
Proxy only formats requests and responses
```

### GUI Page

Added a `ttk.Notebook` with two tabs:

```text
BigModel
ClaudeAI
```

The ClaudeAI tab includes:

```text
Base URL
Organization ID
Conversation ID
Cookie
Anthropic Device ID
User-Agent
Payload Template
Message
Response
ClaudeAI Log
```

### Claude Web Completion Endpoint

The proxy builds:

```text
POST https://claude.ai/api/organizations/{organization_id}/chat_conversations/{conversation_id}/completion
```

Required manual fields:

```text
organization_id
conversation_id
cookie
```

Optional but recommended:

```text
anthropic-device-id
user-agent
payload_template
```

### Local Proxy Request

The GUI sends this local request:

```text
POST http://localhost:8080/claude-web/completion
```

Payload shape:

```json
{
  "provider": "claude_web",
  "messages": [
    {
      "role": "user",
      "content": "HI"
    }
  ],
  "stream": true,
  "claude": {
    "base_url": "https://claude.ai",
    "organization_id": "...",
    "conversation_id": "...",
    "cookie": "...",
    "device_id": "...",
    "user_agent": "...",
    "payload_template": "{\"prompt\":\"HI\",\"attachments\":[],\"files\":[]}"
  }
}
```

### Adapter Flow

```text
OpenAI messages
-> Claude Web payload template
-> Claude Web completion endpoint
-> Claude Web SSE
-> OpenAI-compatible SSE choices
```

### Security Rule

Do not commit these values:

```text
Cookie
sessionKey
routingHint
cf_clearance
__cf_bm
Anthropic session cookies
```

The app only provides manual input fields. It does not read browser cookies or browser network traffic automatically.

### Verification

Syntax check:

```powershell
python -m py_compile reverse_proxy_server.py proxy_gui.py main.py
```

Local mocked proxy test confirmed:

```text
POST /claude-web/completion
-> https://claude.ai/api/organizations/org-test/chat_conversations/conv-test/completion
-> {"prompt": "HI", "attachments": [], "files": []}
-> data: {"choices":[...]}
-> data: [DONE]
```

### Verification

Run:

```powershell
python -m py_compile reverse_proxy_server.py proxy_gui.py main.py
```

Local conversion test:

```python
from reverse_proxy_server import convert_bigmodel_sse_to_openai_sse

sample = b'event:add\ndata:{"think":"1"}\n\nevent:add\ndata:{"content":"Hello"}\n\n'
print(convert_bigmodel_sse_to_openai_sse(sample).decode("utf-8"))
```

Expected:

- No raw `data:{"think":"1"}` is returned.
- Every JSON `data:` line has `choices`.
- Final line is `data: [DONE]`.

### Current Status

Implemented in:

```text
reverse_proxy_server.py
```

Git commit:

```text
ae7416b Convert BigModel SSE to OpenAI stream
```

## 17. Chatbox Exclusion Rules

Date: 2026-05-28

### Purpose

Chatbox mode must not pass BigModel-native events directly to the client. Chatbox validates the streamed response against an OpenAI-compatible shape. Any non-OpenAI object in a `data:` line can break rendering.

### Must Exclude From Chatbox Output

The following BigModel SSE payloads should not be returned directly to Chatbox:

```text
data: {"think":"..."}
data: {"search":"..."}
data: {"webSearch":"..."}
data: [{"title":"...","link":"..."}]
event:webSearch
event:add
id:...
```

Reason:

- `think` is internal reasoning/debug text.
- `webSearch` and search result arrays are tool metadata, not assistant text.
- `event:` and `id:` are SSE metadata lines, not OpenAI JSON chunks.
- Raw arrays do not contain `choices`.

### Must Not Return

Do not return these shapes in Chatbox mode:

```text
data: {"think":"1"}
data: [{"content":"search result"}]
data: {"content":"Hello"}
```

Even `{"content":"Hello"}` is invalid for Chatbox unless wrapped as OpenAI stream format.

### Required Chatbox Shape

Every JSON `data:` line returned to Chatbox must contain either:

```json
{
  "choices": [
    {
      "index": 0,
      "delta": {
        "content": "Hello"
      },
      "finish_reason": null
    }
  ]
}
```

or an OpenAI-compatible error object:

```json
{
  "error": {
    "message": "error message",
    "type": "proxy_error"
  }
}
```

The stream should end with:

```text
data: [DONE]
```

### Current Implementation Rule

In `reverse_proxy_server.py`:

- `openai_response_mode = True` only when incoming JSON has `messages`.
- `convert_bigmodel_sse_to_openai_sse()` filters BigModel-only events.
- `extract_bigmodel_answer_text()` only extracts display text from known text fields.
- Non-display chunks are skipped.

### Debug Checklist

If Chatbox fails with type validation:

1. Check whether the request body contains `messages`.
2. Confirm proxy log contains request conversion message.
3. Inspect response body.
4. If any raw `data: {"think": ...}` appears, response conversion is not active.
5. If any JSON `data:` line lacks `choices` or `error`, Chatbox will reject it.
6. Confirm response content type is:

```text
text/event-stream; charset=utf-8
```

### Checkpoint Result

Expected Chatbox response example:

```text
data: {"id":"chatcmpl-bigmodel-proxy","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-bigmodel-proxy","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-bigmodel-proxy","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```
