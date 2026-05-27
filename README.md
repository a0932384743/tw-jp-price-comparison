# 台日商品比價 AI 顧問系統
**Taiwan–Japan Commodity Price Comparison & AI Advisory System**

輸入商品名稱或上傳商品圖片，系統自動識別商品、翻譯關鍵字、同步抓取台日電商價格，並透過 AI 分析匯率、退稅與運費，給出最佳購買建議。

---

## 系統架構

```
使用者輸入（文字 or 圖片）
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  POST /api/search                                       │
│                                                         │
│  1. AI Agent (Claude)                                   │
│     └─ 視覺辨識 / 語意分析                               │
│        → 台灣關鍵字、日本關鍵字、商品分類                 │
│                                                         │
│  2. 價格快取檢查（同關鍵字 + 當日）                       │
│     ├─ 命中 → 直接回傳 DB 資料                           │
│     └─ 未命中 → 並發抓取：                               │
│         fetch_tw_prices()  ─┐                           │
│         fetch_jp_prices()  ─┘  asyncio.gather           │
│                                                         │
│  3. AI 顧問 (Claude)                                    │
│     └─ 匯率換算 + 日本退稅 10%                           │
│        → 比價摘要、最佳地點、優缺點、結論                 │
│                                                         │
│  4. 寫入 PostgreSQL（搜尋紀錄 + 價格快取）               │
│  5. 回傳 JSON                                           │
└─────────────────────────────────────────────────────────┘
```

---

## 技術棧

| 層級 | 技術 |
|---|---|
| **後端框架** | Python 3.10+ / FastAPI (非同步) |
| **AI 核心** | Anthropic Claude Sonnet（視覺辨識、多語關鍵字映射、購買建議） |
| **爬蟲結構** | httpx + BeautifulSoup（開發期使用 Mock 資料） |
| **資料庫** | PostgreSQL + SQLAlchemy 2 Async + Alembic |
| **資料驗證** | Pydantic v2 |
| **韌性機制** | tenacity（自動重試，指數退避） |

---

## 專案結構

```
tw-jp-price-comparison/
├── main.py                    # FastAPI app 進入點
├── requirements.txt
├── .env.example               # 環境變數範本
├── alembic.ini
├── alembic/
│   └── env.py                 # 非同步 Alembic 設定
├── app/
│   ├── core/
│   │   ├── config.py          # Pydantic-Settings（讀取 .env）
│   │   └── db.py              # 非同步 SQLAlchemy 引擎與 Session
│   ├── api/
│   │   └── routes.py          # POST /api/search
│   ├── services/
│   │   ├── ai_agent.py        # Claude 商品識別 & 關鍵字映射
│   │   ├── scraper.py         # 台日電商爬蟲（含 Mock 層）
│   │   └── advisor.py         # Claude 購買建議生成
│   ├── models/
│   │   └── database.py        # ORM：SearchHistory、PriceCache
│   └── schemas/
│       └── product.py         # Pydantic 請求/回應 Schema
└── tests/
    └── test_pipeline.py       # 8 項單元 & 整合測試
```

---

## 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 填入以下必要值：
# ANTHROPIC_API_KEY=sk-ant-...
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/twjp_prices
```

### 3. 資料庫初始化（需有 PostgreSQL）

```bash
alembic revision --autogenerate -m "init"
alembic upgrade head
```

> 若在開發模式（`APP_ENV=development`）且無 DB，系統仍可正常啟動，DB 步驟會自動略過。

### 4. 啟動伺服器

```bash
uvicorn main:app --reload
```

互動文件：`http://localhost:8000/docs`

### 5. 執行測試

```bash
pytest tests/ -v --asyncio-mode=auto
```

---

## API 說明

### `POST /api/search`

| 欄位 | 類型 | 說明 |
|---|---|---|
| `query` | `string` (Form) | 商品名稱（文字輸入） |
| `image` | `file` (Multipart) | 商品圖片（jpg / png / webp） |

`query` 與 `image` 擇一提供即可。

#### 回應範例

```json
{
  "keyword_mapping": {
    "refined_tw_keyword": "Sony WH-1000XM5 無線降噪耳機",
    "refined_jp_keyword": "ソニー WH-1000XM5 ワイヤレスノイズキャンセリングヘッドホン",
    "category": "電子產品"
  },
  "tw_listings": [
    { "platform": "momo購物網", "title": "...", "price": 9900, "currency": "TWD", "url": "..." }
  ],
  "jp_listings": [
    { "platform": "Amazon Japan", "title": "...", "price": 41800, "currency": "JPY", "url": "..." }
  ],
  "exchange_rate_jpy_twd": 0.218,
  "advice": {
    "price_comparison_summary": "台灣平均售價約 NT$9,900，日本含稅換算約 NT$9,112，退稅後約 NT$8,201。",
    "best_deal_location": "Japan",
    "tw_average_price_twd": 9900.0,
    "jp_average_price_twd": 9112.4,
    "jp_tax_free_price_twd": 8201.16,
    "pros_cons": {
      "pros": ["退稅後省約 NT$1,700", "日本定價較低"],
      "cons": ["需加計國際運費 NT$300–800", "平行輸入保固限制"]
    },
    "verdict": "建議赴日時在實體門市退稅購買，可省約 NT$1,700；若不去日本，momo 有官方保固較安心。"
  }
}
```

---

## 資料庫 Schema

### `search_history`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | UUID | 主鍵 |
| `created_at` | timestamptz | 搜尋時間 |
| `input_type` | varchar(10) | `"text"` 或 `"image"` |
| `raw_query` | text | 原始文字查詢 |
| `image_filename` | varchar | 上傳圖片檔名 |
| `refined_tw_keyword` | varchar | AI 優化後台灣關鍵字 |
| `refined_jp_keyword` | varchar | AI 優化後日本關鍵字 |
| `category` | varchar | 商品分類 |
| `exchange_rate_jpy_twd` | float | 搜尋當下匯率 |
| `best_deal_location` | varchar | 最佳購買地點 |
| `verdict` | text | AI 結論 |

### `price_cache`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | bigserial | 主鍵 |
| `keyword` | varchar | 搜尋關鍵字（indexed） |
| `market` | varchar(5) | `"TW"` 或 `"JP"` |
| `platform` | varchar | 平台名稱 |
| `title` | text | 商品標題 |
| `price` | float | 商品價格（當地幣別） |
| `currency` | varchar(5) | `"TWD"` 或 `"JPY"` |
| `url` | text | 商品連結 |
| `cache_date` | date | 快取日期（每日更新） |

唯一約束：`(keyword, platform, cache_date)` — 同一關鍵字在同一天對同一平台只抓取一次。

---

## 環境變數一覽

| 變數 | 預設值 | 說明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **必填**，Anthropic API 金鑰 |
| `DATABASE_URL` | — | PostgreSQL 連線字串 |
| `APP_ENV` | `development` | `development` 使用 Mock 資料；`production` 啟動真實爬蟲 |
| `APP_PORT` | `8000` | 伺服器埠號 |
| `JPY_TO_TWD_RATE` | `0.218` | 日圓兌台幣匯率（可串接即時 API 覆蓋） |
| `SCRAPER_REQUEST_DELAY` | `1.5` | 爬蟲請求間隔（秒），避免被封鎖 |
