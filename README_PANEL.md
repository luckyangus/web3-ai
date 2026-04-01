# BTC交易机器人监控面板

## 快速开始

### 1. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
copy .env.example .env
```

编辑 `.env` 文件，填写以下配置：

```env
# AI模型配置（已预填）
AI_API_KEY=sk-jE8zn4GmSbLwMefSMQz4j86n9xbXRMmf3K0Yo8PyV0virCAs
AI_BASE_URL=https://ai.100969.xyz/v1
AI_MODEL=mimo-v2-omni

# OKX交易所配置（需填写）
OKX_API_KEY=your_okx_api_key
OKX_SECRET=your_okx_secret
OKX_PASSWORD=your_okx_password

# 交易配置
TRADE_SYMBOL=BTC/USDT:USDT
TRADE_AMOUNT=0.01
TRADE_LEVERAGE=10
TRADE_TIMEFRAME=15m
TEST_MODE=true

# Web面板配置
WEB_HOST=0.0.0.0
WEB_PORT=5000
WEB_SECRET_KEY=your_secret_key_here
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动程序

**Windows:**
```bash
start.bat
```

**Linux/Mac:**
```bash
python web_app.py
```

### 4. 访问面板

打开浏览器访问：http://localhost:5000

## 功能特性

- ✅ 现代化Web监控面板
- ✅ 实时价格和技术指标显示
- ✅ 交易信号历史记录
- ✅ 持仓和盈亏监控
- ✅ 一键启动/停止机器人
- ✅ 模拟交易模式（默认开启）
- ✅ 支持OpenAI兼容API

## API接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/status` | GET | 获取机器人状态 |
| `/api/market` | GET | 获取市场数据 |
| `/api/position` | GET | 获取持仓信息 |
| `/api/signals` | GET | 获取信号历史 |
| `/api/start` | POST | 启动机器人 |
| `/api/stop` | POST | 停止机器人 |
| `/api/config` | GET | 获取配置信息 |

## 模拟交易说明

默认配置为模拟交易模式（TEST_MODE=true），不会真实下单。  
如需实盘交易，请将 `.env` 中的 `TEST_MODE` 改为 `false`（谨慎操作！）

## 技术栈

- **后端**: Flask + Python
- **前端**: TailwindCSS + Chart.js
- **交易所**: OKX (via CCXT)
- **AI**: mimo-v2-omni (OpenAI兼容格式)