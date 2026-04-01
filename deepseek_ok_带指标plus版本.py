import os
import time
import schedule
from openai import OpenAI
import ccxt
import pandas as pd
from datetime import datetime
import json
import re
from dotenv import load_dotenv
import logging

load_dotenv()

# 配置AI日志
ai_logger = logging.getLogger('ai')
ai_logger.setLevel(logging.INFO)
ai_handler = logging.FileHandler('logs/ai.log', mode='a', encoding='utf-8')
ai_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
ai_logger.addHandler(ai_handler)

# 初始化AI客户端（OpenAI兼容格式）
ai_client = OpenAI(
    api_key=os.getenv('AI_API_KEY'),
    base_url=os.getenv('AI_BASE_URL', 'https://ai.100969.xyz/v1')
)

# 初始化OKX交易所
exchange = ccxt.okx({
    'options': {
        'defaultType': 'swap',  # OKX使用swap表示永续合约
    },
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSWORD'),  # OKX需要交易密码
})

# 交易参数配置 - 结合两个版本的优点
TRADE_CONFIG = {
    'symbol': os.getenv('TRADE_SYMBOL') or 'BTC/USDT:USDT',
    'amount': float(os.getenv('TRADE_AMOUNT') or '0.01'),
    'leverage': int(os.getenv('TRADE_LEVERAGE') or '10'),
    'timeframe': os.getenv('TRADE_TIMEFRAME') or '15m',
    'test_mode': os.getenv('TEST_MODE', 'true').lower() == 'true',
    'data_points': 96,
    'analysis_periods': {
        'short_term': 20,
        'medium_term': 50,
        'long_term': 96
    }
}

# 全局变量存储历史数据
price_history = []
signal_history = []
position = None


def setup_exchange():
    """设置交易所参数"""
    try:
        # OKX设置杠杆
        exchange.set_leverage(
            TRADE_CONFIG['leverage'],
            TRADE_CONFIG['symbol'],
            {'mgnMode': 'cross'}  # 全仓模式
        )
        print(f"设置杠杆倍数: {TRADE_CONFIG['leverage']}x")

        # 获取余额
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        print(f"当前USDT余额: {usdt_balance:.2f}")

        return True
    except Exception as e:
        print(f"交易所设置失败: {e}")
        return False


def calculate_technical_indicators(df):
    """计算技术指标 - 来自第一个策略"""
    try:
        # 移动平均线
        df['sma_5'] = df['close'].rolling(window=5, min_periods=1).mean()
        df['sma_20'] = df['close'].rolling(window=20, min_periods=1).mean()
        df['sma_50'] = df['close'].rolling(window=50, min_periods=1).mean()

        # 指数移动平均线
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']

        # 相对强弱指数 (RSI)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # 布林带
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # 成交量均线
        df['volume_ma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']

        # 支撑阻力位
        df['resistance'] = df['high'].rolling(20).max()
        df['support'] = df['low'].rolling(20).min()

        # 填充NaN值
        df = df.bfill().ffill()

        return df
    except Exception as e:
        print(f"技术指标计算失败: {e}")
        return df


def get_support_resistance_levels(df, lookback=20):
    """计算支撑阻力位"""
    try:
        recent_high = df['high'].tail(lookback).max()
        recent_low = df['low'].tail(lookback).min()
        current_price = df['close'].iloc[-1]

        resistance_level = recent_high
        support_level = recent_low

        # 动态支撑阻力（基于布林带）
        bb_upper = df['bb_upper'].iloc[-1]
        bb_lower = df['bb_lower'].iloc[-1]

        return {
            'static_resistance': resistance_level,
            'static_support': support_level,
            'dynamic_resistance': bb_upper,
            'dynamic_support': bb_lower,
            'price_vs_resistance': ((resistance_level - current_price) / current_price) * 100,
            'price_vs_support': ((current_price - support_level) / support_level) * 100
        }
    except Exception as e:
        print(f"支撑阻力计算失败: {e}")
        return {}


def get_market_trend(df):
    """判断市场趋势"""
    try:
        current_price = df['close'].iloc[-1]

        # 多时间框架趋势分析
        trend_short = "上涨" if current_price > df['sma_20'].iloc[-1] else "下跌"
        trend_medium = "上涨" if current_price > df['sma_50'].iloc[-1] else "下跌"

        # MACD趋势
        macd_trend = "bullish" if df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] else "bearish"

        # 综合趋势判断
        if trend_short == "上涨" and trend_medium == "上涨":
            overall_trend = "强势上涨"
        elif trend_short == "下跌" and trend_medium == "下跌":
            overall_trend = "强势下跌"
        else:
            overall_trend = "震荡整理"

        return {
            'short_term': trend_short,
            'medium_term': trend_medium,
            'macd': macd_trend,
            'overall': overall_trend,
            'rsi_level': df['rsi'].iloc[-1]
        }
    except Exception as e:
        print(f"趋势分析失败: {e}")
        return {}


def get_btc_ohlcv_enhanced():
    """增强版：获取BTC K线数据并计算技术指标"""
    try:
        # 获取K线数据
        ohlcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], TRADE_CONFIG['timeframe'],
                                     limit=TRADE_CONFIG['data_points'])

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # 计算技术指标
        df = calculate_technical_indicators(df)

        current_data = df.iloc[-1]
        previous_data = df.iloc[-2]

        # 获取技术分析数据
        trend_analysis = get_market_trend(df)
        levels_analysis = get_support_resistance_levels(df)

        return {
            'price': current_data['close'],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'high': current_data['high'],
            'low': current_data['low'],
            'volume': current_data['volume'],
            'timeframe': TRADE_CONFIG['timeframe'],
            'price_change': ((current_data['close'] - previous_data['close']) / previous_data['close']) * 100,
            'kline_data': df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].tail(60).to_dict('records'),
            'technical_data': {
                'sma_5': current_data.get('sma_5', 0),
                'sma_20': current_data.get('sma_20', 0),
                'sma_50': current_data.get('sma_50', 0),
                'rsi': current_data.get('rsi', 0),
                'macd': current_data.get('macd', 0),
                'macd_signal': current_data.get('macd_signal', 0),
                'macd_histogram': current_data.get('macd_histogram', 0),
                'bb_upper': current_data.get('bb_upper', 0),
                'bb_lower': current_data.get('bb_lower', 0),
                'bb_position': current_data.get('bb_position', 0),
                'volume_ratio': current_data.get('volume_ratio', 0)
            },
            'trend_analysis': trend_analysis,
            'levels_analysis': levels_analysis,
            'full_data': df
        }
    except Exception as e:
        print(f"获取增强K线数据失败: {e}")
        return None


def generate_technical_analysis_text(price_data):
    """生成技术分析文本"""
    if 'technical_data' not in price_data:
        return "技术指标数据不可用"

    tech = price_data['technical_data']
    trend = price_data.get('trend_analysis', {})
    levels = price_data.get('levels_analysis', {})

    # 检查数据有效性
    def safe_float(value, default=0):
        return float(value) if value and pd.notna(value) else default

    analysis_text = f"""
    【技术指标分析】
    📈 移动平均线:
    - 5周期: {safe_float(tech['sma_5']):.2f} | 价格相对: {(price_data['price'] - safe_float(tech['sma_5'])) / safe_float(tech['sma_5']) * 100:+.2f}%
    - 20周期: {safe_float(tech['sma_20']):.2f} | 价格相对: {(price_data['price'] - safe_float(tech['sma_20'])) / safe_float(tech['sma_20']) * 100:+.2f}%
    - 50周期: {safe_float(tech['sma_50']):.2f} | 价格相对: {(price_data['price'] - safe_float(tech['sma_50'])) / safe_float(tech['sma_50']) * 100:+.2f}%

    🎯 趋势分析:
    - 短期趋势: {trend.get('short_term', 'N/A')}
    - 中期趋势: {trend.get('medium_term', 'N/A')}
    - 整体趋势: {trend.get('overall', 'N/A')}
    - MACD方向: {trend.get('macd', 'N/A')}

    📊 动量指标:
    - RSI: {safe_float(tech['rsi']):.2f} ({'超买' if safe_float(tech['rsi']) > 70 else '超卖' if safe_float(tech['rsi']) < 30 else '中性'})
    - MACD: {safe_float(tech['macd']):.4f}
    - 信号线: {safe_float(tech['macd_signal']):.4f}

    🎚️ 布林带位置: {safe_float(tech['bb_position']):.2%} ({'上部' if safe_float(tech['bb_position']) > 0.7 else '下部' if safe_float(tech['bb_position']) < 0.3 else '中部'})

    💰 关键水平:
    - 静态阻力: {safe_float(levels.get('static_resistance', 0)):.2f}
    - 静态支撑: {safe_float(levels.get('static_support', 0)):.2f}
    """
    return analysis_text


def get_current_position():
    """获取当前持仓情况 - OKX版本"""
    try:
        positions = exchange.fetch_positions([TRADE_CONFIG['symbol']])

        for pos in positions:
            if pos['symbol'] == TRADE_CONFIG['symbol']:
                contracts = float(pos['contracts']) if pos['contracts'] else 0

                if contracts > 0:
                    return {
                        'side': pos['side'],  # 'long' or 'short'
                        'size': contracts,
                        'entry_price': float(pos['entryPrice']) if pos['entryPrice'] else 0,
                        'unrealized_pnl': float(pos['unrealizedPnl']) if pos['unrealizedPnl'] else 0,
                        'leverage': float(pos['leverage']) if pos['leverage'] else TRADE_CONFIG['leverage'],
                        'symbol': pos['symbol']
                    }

        return None

    except Exception as e:
        print(f"获取持仓失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def safe_json_parse(json_str):
    """安全解析JSON，处理格式不规范的情况"""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        try:
            # 修复常见的JSON格式问题
            json_str = json_str.replace("'", '"')
            json_str = re.sub(r'(\w+):', r'"\1":', json_str)
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"JSON解析失败，原始内容: {json_str}")
            print(f"错误详情: {e}")
            return None


def create_fallback_signal(price_data):
    """创建备用交易信号"""
    return {
        "signal": "HOLD",
        "reason": "因技术分析暂时不可用，采取保守策略",
        "stop_loss": price_data['price'] * 0.98,  # -2%
        "take_profit": price_data['price'] * 1.02,  # +2%
        "confidence": "LOW",
        "is_fallback": True
    }


def analyze_with_deepseek(price_data):
    """使用AI分析市场并生成交易信号（完整版）"""
    
    # 构建完整的K线数据
    klines = price_data['kline_data'][-8:]
    kline_text = "【最近8根K线数据】\n"
    kline_text += "时间\t\t开盘\t\t最高\t\t最低\t\t收盘\t\t涨跌幅\t\t成交量\n"
    for kline in klines:
        change = ((kline['close'] - kline['open']) / kline['open']) * 100
        time_str = kline['timestamp'].strftime('%m-%d %H:%M') if hasattr(kline['timestamp'], 'strftime') else str(kline['timestamp'])
        kline_text += f"{time_str}\t${kline['open']:,.0f}\t${kline['high']:,.0f}\t${kline['low']:,.0f}\t${kline['close']:,.0f}\t{change:+.2f}%\t{kline['volume']:.2f}\n"
    
    # 详细技术指标
    tech = price_data['technical_data']
    trend = price_data['trend_analysis']
    levels = price_data.get('levels_analysis', {})
    
    tech_text = f"""【技术指标详情】

📊 移动平均线:
- MA5: ${tech.get('sma_5', 0):,.2f} (价格相对: {((price_data['price'] - tech.get('sma_5', 0)) / tech.get('sma_5', 1) * 100):+.2f}%)
- MA20: ${tech.get('sma_20', 0):,.2f} (价格相对: {((price_data['price'] - tech.get('sma_20', 0)) / tech.get('sma_20', 1) * 100):+.2f}%)
- MA50: ${tech.get('sma_50', 0):,.2f} (价格相对: {((price_data['price'] - tech.get('sma_50', 0)) / tech.get('sma_50', 1) * 100):+.2f}%)

🎯 趋势分析:
- 短期趋势: {trend.get('short_term', 'N/A')}
- 中期趋势: {trend.get('medium_term', 'N/A')}
- 整体趋势: {trend.get('overall', 'N/A')}
- MACD方向: {trend.get('macd', 'N/A')}

📈 动量指标:
- RSI(14): {tech.get('rsi', 0):.2f} {'⚠️超买' if tech.get('rsi', 0) > 70 else '⚠️超卖' if tech.get('rsi', 0) < 30 else '✅正常'}
- MACD: {tech.get('macd', 0):.4f}
- 信号线: {tech.get('macd_signal', 0):.4f}
- 柱状图: {tech.get('macd_histogram', 0):.4f} {'✅多头' if tech.get('macd_histogram', 0) > 0 else '❌空头'}

🎚️ 布林带:
- 上轨: ${tech.get('bb_upper', 0):,.2f}
- 中轨: ${tech.get('bb_middle', price_data['price']):,.2f}
- 下轨: ${tech.get('bb_lower', 0):,.2f}
- 当前位置: {tech.get('bb_position', 0)*100:.1f}% {'⚠️上部' if tech.get('bb_position', 0) > 0.7 else '⚠️下部' if tech.get('bb_position', 0) < 0.3 else '✅中部'}

💰 支撑阻力位:
- 阻力位: ${levels.get('static_resistance', 0):,.2f} (距离: {levels.get('price_vs_resistance', 0):+.2f}%)
- 支撑位: ${levels.get('static_support', 0):,.2f} (距离: {levels.get('price_vs_support', 0):+.2f}%)

📊 成交量:
- 当前量: {price_data['volume']:.2f} BTC
- 均量: {tech.get('volume_ma', price_data['volume']):.2f} BTC
- 量比: {tech.get('volume_ratio', 1):.2f}x {'📈放量' if tech.get('volume_ratio', 1) > 1.5 else '📉缩量' if tech.get('volume_ratio', 1) < 0.7 else '✅正常'}"""
    
    # 持仓信息
    current_pos = get_current_position()
    pos_text = "无持仓"
    if current_pos:
        pnl = current_pos['unrealized_pnl']
        pos_text = f"{current_pos['side']}仓 | 数量: {current_pos['size']} BTC | 入场价: ${current_pos['entry_price']:,.2f} | 盈亏: ${pnl:,.2f}"
    
    # 上次信号
    last_signal_text = ""
    if signal_history:
        last = signal_history[-1]
        last_signal_text = f"\n【上次交易信号】\n信号: {last.get('signal')} | 信心: {last.get('confidence')} | 时间: {last.get('timestamp')}"
    
    prompt = f"""你是专业的BTC量化交易分析师。请基于以下完整数据进行深度分析：

{kline_text}

{tech_text}

【当前市场状态】
- 当前价格: ${price_data['price']:,.2f}
- 时间: {price_data['timestamp']}
- 本K线: 最高 ${price_data['high']:,.2f} | 最低 ${price_data['low']:,.2f} | 收盘 ${price_data['price']:,.2f}
- 价格变化: {price_data['price_change']:+.2f}%
- 成交量: {price_data['volume']:.2f} BTC
- 当前持仓: {pos_text}
{last_signal_text}

【交易决策规则】
1. ✅ 趋势跟随: 顺势交易，避免逆势
2. ✅ 多指标共振: 至少2-3个指标同向确认
3. ✅ 风险管理: 
   - RSI > 70 谨慎做多
   - RSI < 30 谨慎做空
   - 价格触及布林带上轨慎买，下轨慎卖
4. ✅ 成交量确认: 放量突破可信度高
5. ✅ BTC特性: 长期看涨，做多机会可适当放宽
6. ✅ 持仓控制: 
   - 有持仓时需更强信号才反向
   - 避免频繁开平仓

【分析要求】
请综合以上所有数据进行全面分析，给出明确的交易信号和详细的理由说明。

请严格按以下JSON格式回复（不要有任何多余文字）:
{{
    "signal": "BUY或SELL或HOLD",
    "reason": "详细分析理由（包含：趋势判断、技术指标依据、支撑阻力分析、成交量情况）",
    "stop_loss": 具体止损价格,
    "take_profit": 具体止盈价格,
    "confidence": "HIGH或MEDIUM或LOW"
}}"""

    try:
        response = ai_client.chat.completions.create(
            model=os.getenv('AI_MODEL', 'mimo-v2-omni'),
            messages=[
                {"role": "system",
                 "content": f"您是一位专业的交易员，专注于{TRADE_CONFIG['timeframe']}周期趋势分析。请结合K线形态和技术指标做出判断，并严格遵循JSON格式要求。"},
                {"role": "user", "content": prompt}
            ],
            stream=False,
            temperature=0.1
        )

        # 安全解析JSON
        result = response.choices[0].message.content
        if not result:
            ai_logger.warning("AI返回空内容，使用备用信号")
            return create_fallback_signal(price_data)
        
        ai_logger.info(f"AI原始回复: {result}")

        # 提取JSON部分
        start_idx = result.find('{')
        end_idx = result.rfind('}') + 1

        if start_idx != -1 and end_idx != 0:
            json_str = result[start_idx:end_idx]
            signal_data = safe_json_parse(json_str)

            if signal_data is None:
                signal_data = create_fallback_signal(price_data)
        else:
            signal_data = create_fallback_signal(price_data)

        # 验证必需字段
        required_fields = ['signal', 'reason', 'stop_loss', 'take_profit', 'confidence']
        if not all(field in signal_data for field in required_fields):
            signal_data = create_fallback_signal(price_data)

        # 保存信号到历史记录
        signal_data['timestamp'] = price_data['timestamp']
        signal_history.append(signal_data)
        if len(signal_history) > 30:
            signal_history.pop(0)

        # 记录AI决策详情
        ai_logger.info(f"{'='*60}")
        ai_logger.info(f"[AI决策] 信号: {signal_data['signal']}, 信心: {signal_data['confidence']}")
        ai_logger.info(f"[价格] ${price_data['price']:,.2f}")
        ai_logger.info(f"[理由] {signal_data.get('reason', 'N/A')}")
        ai_logger.info(f"[止损] ${signal_data.get('stop_loss', 0):,.2f}")
        ai_logger.info(f"[止盈] ${signal_data.get('take_profit', 0):,.2f}")

        # 信号统计
        signal_count = len([s for s in signal_history if s.get('signal') == signal_data['signal']])
        total_signals = len(signal_history)
        ai_logger.info(f"信号统计: {signal_data['signal']} (最近{total_signals}次中出现{signal_count}次)")

        # 信号连续性检查
        if len(signal_history) >= 3:
            last_three = [s['signal'] for s in signal_history[-3:]]
            if len(set(last_three)) == 1:
                ai_logger.info(f"⚠️ 注意：连续3次{signal_data['signal']}信号")

        return signal_data

    except Exception as e:
        ai_logger.error(f"DeepSeek分析失败: {e}")
        return create_fallback_signal(price_data)


def execute_trade(signal_data, price_data):
    """执行交易 - OKX版本（修复保证金检查）"""
    global position

    current_position = get_current_position()

    # 🔴 紧急修复：防止频繁反转
    if current_position and signal_data['signal'] != 'HOLD':
        current_side = current_position['side']
        # 修正：正确处理HOLD情况
        if signal_data['signal'] == 'BUY':
            new_side = 'long'
        elif signal_data['signal'] == 'SELL':
            new_side = 'short'
        else:  # HOLD
            new_side = None

        # 如果只是方向反转，需要高信心才执行
        if new_side != current_side:
            if signal_data['confidence'] != 'HIGH':
                print(f"🔒 非高信心反转信号，保持现有{current_side}仓")
                return

            # 检查最近信号历史，避免频繁反转
            if len(signal_history) >= 2:
                last_signals = [s['signal'] for s in signal_history[-2:]]
                if signal_data['signal'] in last_signals:
                    print(f"🔒 近期已出现{signal_data['signal']}信号，避免频繁反转")
                    return

    print(f"交易信号: {signal_data['signal']}")
    print(f"信心程度: {signal_data['confidence']}")
    print(f"理由: {signal_data['reason']}")
    print(f"止损: ${signal_data['stop_loss']:,.2f}")
    print(f"止盈: ${signal_data['take_profit']:,.2f}")
    print(f"当前持仓: {current_position}")

    # 风险管理：低信心信号不执行
    if signal_data['confidence'] == 'LOW' and not TRADE_CONFIG['test_mode']:
        print("⚠️ 低信心信号，跳过执行")
        return

    if TRADE_CONFIG['test_mode']:
        print("测试模式 - 仅模拟交易")
        return

    try:
        # 获取账户余额
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        required_margin = price_data['price'] * TRADE_CONFIG['amount'] / TRADE_CONFIG['leverage']

        if required_margin > usdt_balance * 0.8:  # 使用不超过80%的余额
            print(f"⚠️ 保证金不足，跳过交易。需要: {required_margin:.2f} USDT, 可用: {usdt_balance:.2f} USDT")
            return

        # 执行交易逻辑   tag 是我的经纪商api（不拿白不拿），不会影响大家返佣，介意可以删除
        if signal_data['signal'] == 'BUY':
            if current_position and current_position['side'] == 'short':
                print("平空仓并开多仓...")
                # 平空仓
                exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'buy',
                    current_position['size'],
                    params={'reduceOnly': True, 'tag': '60bb4a8d3416BCDE'}
                )
                time.sleep(1)
                # 开多仓
                exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'buy',
                    TRADE_CONFIG['amount'],
                    params={'tag': 'f1ee03b510d5SUDE'}
                )
            elif current_position and current_position['side'] == 'long':
                print("已有多头持仓，保持现状")
            else:
                # 无持仓时开多仓
                print("开多仓...")
                exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'buy',
                    TRADE_CONFIG['amount'],
                    params={'tag': 'f1ee03b510d5SUDE'}
                )

        elif signal_data['signal'] == 'SELL':
            if current_position and current_position['side'] == 'long':
                print("平多仓并开空仓...")
                # 平多仓
                exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'sell',
                    current_position['size'],
                    params={'reduceOnly': True, 'tag': 'f1ee03b510d5SUDE'}
                )
                time.sleep(1)
                # 开空仓
                exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'sell',
                    TRADE_CONFIG['amount'],
                    params={'tag': 'f1ee03b510d5SUDE'}
                )
            elif current_position and current_position['side'] == 'short':
                print("已有空头持仓，保持现状")
            else:
                # 无持仓时开空仓
                print("开空仓...")
                exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'sell',
                    TRADE_CONFIG['amount'],
                    params={'tag': 'f1ee03b510d5SUDE'}
                )

        print("订单执行成功")
        time.sleep(2)
        position = get_current_position()
        print(f"更新后持仓: {position}")

    except Exception as e:
        print(f"订单执行失败: {e}")
        import traceback
        traceback.print_exc()


def analyze_with_deepseek_with_retry(price_data, max_retries=2):
    """带重试的DeepSeek分析"""
    for attempt in range(max_retries):
        try:
            signal_data = analyze_with_deepseek(price_data)
            if signal_data and not signal_data.get('is_fallback', False):
                return signal_data

            print(f"第{attempt + 1}次尝试失败，进行重试...")
            time.sleep(1)

        except Exception as e:
            print(f"第{attempt + 1}次尝试异常: {e}")
            if attempt == max_retries - 1:
                return create_fallback_signal(price_data)
            time.sleep(1)

    return create_fallback_signal(price_data)


def wait_for_next_period():
    """等待到下一个整点时间（根据TIMEFRAME配置）"""
    timeframe = TRADE_CONFIG['timeframe']
    
    # 解析时间周期
    timeframe_minutes = {'1m': 1, '5m': 5, '12m': 12, '15m': 15, '30m': 30, '1h': 60}
    period_minutes = timeframe_minutes.get(timeframe, 1)
    
    now = datetime.now()
    current_minute = now.minute
    current_second = now.second

    # 计算下一个整点时间
    next_period_minute = ((current_minute // period_minutes) + 1) * period_minutes
    if next_period_minute >= 60:
        next_period_minute = 0

    # 计算需要等待的总秒数
    if next_period_minute > current_minute:
        minutes_to_wait = next_period_minute - current_minute
    else:
        minutes_to_wait = 60 - current_minute + next_period_minute

    seconds_to_wait = minutes_to_wait * 60 - current_second

    # 显示友好的等待时间
    display_minutes = minutes_to_wait - 1 if current_second > 0 else minutes_to_wait
    display_seconds = 60 - current_second if current_second > 0 else 0

    if display_minutes > 0:
        print(f"🕒 等待 {display_minutes} 分 {display_seconds} 秒到整点...")
    else:
        print(f"🕒 等待 {display_seconds} 秒到整点...")

    return seconds_to_wait


def trading_bot():
    # 等待到整点再执行
    wait_seconds = wait_for_next_period()
    if wait_seconds > 0:
        time.sleep(wait_seconds)

    """主交易机器人函数"""
    print("\n" + "=" * 60)
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取增强版K线数据
    price_data = get_btc_ohlcv_enhanced()
    if not price_data:
        return

    print(f"BTC当前价格: ${price_data['price']:,.2f}")
    print(f"数据周期: {TRADE_CONFIG['timeframe']}")
    print(f"价格变化: {price_data['price_change']:+.2f}%")

    # 2. 使用DeepSeek分析（带重试）
    signal_data = analyze_with_deepseek_with_retry(price_data)

    if signal_data.get('is_fallback', False):
        print("⚠️ 使用备用交易信号")

    # 3. 执行交易
    execute_trade(signal_data, price_data)


def main():
    """主函数"""
    print("BTC/USDT OKX自动交易机器人启动成功！")
    print("融合技术指标策略 + OKX实盘接口")

    if TRADE_CONFIG['test_mode']:
        print("当前为模拟模式，不会真实下单")
    else:
        print("实盘交易模式，请谨慎操作！")

    print(f"交易周期: {TRADE_CONFIG['timeframe']}")
    print("已启用完整技术指标分析和持仓跟踪功能")

    # 设置交易所
    if not setup_exchange():
        print("交易所初始化失败，程序退出")
        return

    print(f"执行频率: 每{TRADE_CONFIG['timeframe']}整点执行")

    # 循环执行（不使用schedule）
    while True:
        trading_bot()  # 函数内部会自己等待整点

        # 执行完后等待一段时间再检查（避免频繁循环）
        time.sleep(60)  # 每分钟检查一次


if __name__ == "__main__":
    main()