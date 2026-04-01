import os
import json
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import threading
import logging

load_dotenv()

# 配置程序日志
program_logger = logging.getLogger('program')
program_logger.setLevel(logging.INFO)
program_handler = logging.FileHandler('logs/program.log', mode='a', encoding='utf-8')
program_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
program_logger.addHandler(program_handler)

# 关闭Flask的HTTP请求日志
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('WEB_SECRET_KEY', 'dev-secret-key')
CORS(app)

price_history = []

simulated_account = {
    'balance': 10000,
    'position': None,
    'trades': [],
    'total_pnl': 0,
    'win_count': 0,
    'loss_count': 0
}

bot_data = {
    'status': 'stopped',
    'last_update': None,
    'current_price': 0,
    'price_change': 0,
    'position': None,
    'latest_signal': None,
    'signal_history': [],
    'trade_history': [],
    'technical_indicators': {},
    'balance': 10000,
    'pnl': 0,
    'unrealized_pnl': 0
}

bot_thread = None
bot_running = False
trade_counter = 0  # 交易计数器


def simulate_trade(signal_data, price_data):
    global simulated_account, bot_data
    
    current_price = price_data['price']
    signal = signal_data.get('signal', 'HOLD')
    
    if signal == 'HOLD':
        return
    
    amount = float(os.getenv('TRADE_AMOUNT', '0.01'))
    leverage = float(os.getenv('TRADE_LEVERAGE', '10'))
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    program_logger.info(f"\n{'='*60}")
    program_logger.info(f"[模拟交易] 信号: {signal}, 价格: ${current_price:.2f}")
    program_logger.info(f"[账户状态] 余额: ${simulated_account['balance']:.2f}, 持仓: {simulated_account['position']}")
    
    if signal == 'BUY':
        if simulated_account['position']:
            pos = simulated_account['position']
            
            if pos['side'] == 'long':
                program_logger.info(f"[模拟] 已有多头持仓，跳过开仓")
                program_logger.info(f"{'='*60}")
                return
            
            if pos['side'] == 'short':
                # 平空仓
                close_pnl = (pos['entry_price'] - current_price) * pos['amount']
                simulated_account['balance'] += pos['margin'] + close_pnl
                simulated_account['total_pnl'] += close_pnl
                
                if close_pnl > 0:
                    simulated_account['win_count'] += 1
                else:
                    simulated_account['loss_count'] += 1
                
                close_trade = {
                    'timestamp': timestamp,
                    'type': 'CLOSE_SHORT',
                    'side': 'short',
                    'entry_price': pos['entry_price'],
                    'exit_price': current_price,
                    'amount': pos['amount'],
                    'pnl': close_pnl,
                    'balance': simulated_account['balance'],
                    'margin': pos['margin']
                }
                simulated_account['trades'].append(close_trade)
                program_logger.info(f"[模拟] 平空仓: 入场={pos['entry_price']:.2f}, 出场={current_price:.2f}, 盈亏={close_pnl:.2f}, 返还保证金={pos['margin']:.2f}")
                program_logger.info(f"[模拟] 平仓后余额: ${simulated_account['balance']:.2f}")
                
                simulated_account['position'] = None
        
        # 开多仓
        margin = current_price * amount / leverage
        if simulated_account['balance'] < margin:
            program_logger.info(f"[模拟] 余额不足! 需要${margin:.2f}, 可用${simulated_account['balance']:.2f}")
            program_logger.info(f"{'='*60}")
            return
        
        simulated_account['balance'] -= margin
        simulated_account['position'] = {
            'side': 'long',
            'entry_price': current_price,
            'amount': amount,
            'margin': margin,
            'timestamp': timestamp
        }
        
        open_trade = {
            'timestamp': timestamp,
            'type': 'OPEN_LONG',
            'side': 'long',
            'price': current_price,
            'amount': amount,
            'margin': margin,
            'balance': simulated_account['balance']
        }
        simulated_account['trades'].append(open_trade)
        program_logger.info(f"[模拟] 开多仓: 价格={current_price:.2f}, 数量={amount}, 保证金={margin:.2f}")
        program_logger.info(f"[模拟] 开仓后余额: ${simulated_account['balance']:.2f}")
    
    elif signal == 'SELL':
        if simulated_account['position']:
            pos = simulated_account['position']
            
            if pos['side'] == 'short':
                program_logger.info(f"[模拟] 已有空头持仓，跳过开仓")
                program_logger.info(f"{'='*60}")
                return
            
            if pos['side'] == 'long':
                # 平多仓
                close_pnl = (current_price - pos['entry_price']) * pos['amount']
                simulated_account['balance'] += pos['margin'] + close_pnl
                simulated_account['total_pnl'] += close_pnl
                
                if close_pnl > 0:
                    simulated_account['win_count'] += 1
                else:
                    simulated_account['loss_count'] += 1
                
                close_trade = {
                    'timestamp': timestamp,
                    'type': 'CLOSE_LONG',
                    'side': 'long',
                    'entry_price': pos['entry_price'],
                    'exit_price': current_price,
                    'amount': pos['amount'],
                    'pnl': close_pnl,
                    'balance': simulated_account['balance'],
                    'margin': pos['margin']
                }
                simulated_account['trades'].append(close_trade)
                program_logger.info(f"[模拟] 平多仓: 入场={pos['entry_price']:.2f}, 出场={current_price:.2f}, 盈亏={close_pnl:.2f}, 返还保证金={pos['margin']:.2f}")
                program_logger.info(f"[模拟] 平仓后余额: ${simulated_account['balance']:.2f}")
                
                simulated_account['position'] = None
        
        # 开空仓
        margin = current_price * amount / leverage
        if simulated_account['balance'] < margin:
            print(f"[模拟] 余额不足! 需要${margin:.2f}, 可用${simulated_account['balance']:.2f}")
            print(f"{'='*60}\n")
            return
        
        simulated_account['balance'] -= margin
        simulated_account['position'] = {
            'side': 'short',
            'entry_price': current_price,
            'amount': amount,
            'margin': margin,
            'timestamp': timestamp
        }
        
        open_trade = {
            'timestamp': timestamp,
            'type': 'OPEN_SHORT',
            'side': 'short',
            'price': current_price,
            'amount': amount,
            'margin': margin,
            'balance': simulated_account['balance']
        }
        simulated_account['trades'].append(open_trade)
        program_logger.info(f"[模拟] 开空仓: 价格={current_price:.2f}, 数量={amount}, 保证金={margin:.2f}")
        program_logger.info(f"[模拟] 开仓后余额: ${simulated_account['balance']:.2f}")
    
    program_logger.info(f"{'='*60}")
    
    if len(simulated_account['trades']) > 200:
        simulated_account['trades'] = simulated_account['trades'][-200:]
    
    update_bot_data(current_price)


def update_bot_data(current_price):
    global bot_data
    
    bot_data['trade_history'] = simulated_account['trades']
    bot_data['balance'] = simulated_account['balance']
    bot_data['pnl'] = simulated_account['total_pnl']
    
    total_closed = simulated_account['win_count'] + simulated_account['loss_count']
    if total_closed > 0:
        bot_data['win_rate'] = (simulated_account['win_count'] / total_closed) * 100
    else:
        bot_data['win_rate'] = 0
    
    if simulated_account['position']:
        pos = simulated_account['position']
        if pos['side'] == 'long':
            unrealized_pnl = (current_price - pos['entry_price']) * pos['amount']
        else:
            unrealized_pnl = (pos['entry_price'] - current_price) * pos['amount']
        
        bot_data['position'] = {
            'side': pos['side'],
            'size': pos['amount'],
            'entry_price': pos['entry_price'],
            'unrealized_pnl': unrealized_pnl,
            'margin': pos['margin'],
            'timestamp': pos['timestamp']
        }
        bot_data['unrealized_pnl'] = unrealized_pnl
    else:
        bot_data['position'] = None
        bot_data['unrealized_pnl'] = 0


def run_trading_bot():
    global bot_running, bot_data, price_history, trade_counter
    
    trade_counter = 0  # 初始化交易计数器
    
    try:
        from deepseek_ok_带指标plus版本 import (
            get_btc_ohlcv_enhanced,
            analyze_with_deepseek_with_retry,
            setup_exchange
        )
        
        bot_running = True
        bot_data['status'] = 'running'
        
        if not setup_exchange():
            bot_data['status'] = 'error'
            bot_running = False
            return
        
        while bot_running:
            try:
                price_data = get_btc_ohlcv_enhanced()
                if price_data:
                    current_price = price_data['price']
                    
                    # 直接使用API返回的K线数据
                    kline_data_full = price_data.get('kline_data', [])
                    if kline_data_full:
                        # 转换为标准格式
                        price_history.clear()
                        for kline in kline_data_full:
                            price_history.append({
                                'timestamp': kline['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(kline['timestamp'], 'strftime') else str(kline['timestamp']),
                                'open': float(kline['open']),
                                'high': float(kline['high']),
                                'low': float(kline['low']),
                                'close': float(kline['close']),
                                'volume': float(kline['volume'])
                            })
                    
                    bot_data['current_price'] = current_price
                    bot_data['price_change'] = price_data['price_change']
                    bot_data['technical_indicators'] = price_data.get('technical_data', {})
                    bot_data['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    update_bot_data(current_price)
                    
                    # 交易计数器递增
                    trade_counter += 1
                    
                    # 根据TIMEFRAME计算交易间隔（秒）
                    timeframe = os.getenv('TRADE_TIMEFRAME', '1m')
                    timeframe_map = {'1m': 60, '5m': 300, '12m': 720, '15m': 900, '30m': 1800, '1h': 3600}
                    trade_interval = timeframe_map.get(timeframe, 60)
                    
                    # 按配置的交易间隔执行
                    if trade_counter % trade_interval == 0:
                        program_logger.info(f"{'='*60}")
                        program_logger.info(f"[交易时间] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        program_logger.info(f"[价格] ${current_price:,.2f}")
                        program_logger.info(f"[账户] 余额: ${simulated_account['balance']:.2f}, 持仓: {simulated_account['position']}")
                        program_logger.info(f"[调用AI分析...]")
                        
                        signal_data = analyze_with_deepseek_with_retry(price_data)
                        bot_data['latest_signal'] = signal_data
                        
                        program_logger.info(f"[AI信号] {signal_data.get('signal')} (信心: {signal_data.get('confidence')})")
                        program_logger.info(f"[理由] {signal_data.get('reason', 'N/A')[:100]}...")
                        
                        if len(bot_data['signal_history']) >= 100:
                            bot_data['signal_history'].pop(0)
                        bot_data['signal_history'].append({
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'signal': signal_data.get('signal'),
                            'confidence': signal_data.get('confidence'),
                            'reason': signal_data.get('reason')
                        })
                        
                        simulate_trade(signal_data, price_data)
                
                time.sleep(1)
                
            except Exception as e:
                program_logger.error(f"Bot error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(10)
                
    except Exception as e:
        program_logger.error(f"Failed to start bot: {e}")
        import traceback
        traceback.print_exc()
        bot_data['status'] = 'error'
        bot_running = False


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    return jsonify({
        'status': bot_data['status'],
        'last_update': bot_data['last_update'],
        'test_mode': os.getenv('TEST_MODE', 'true').lower() == 'true'
    })


@app.route('/api/market')
def get_market():
    return jsonify({
        'current_price': bot_data['current_price'],
        'price_change': bot_data['price_change'],
        'technical_indicators': bot_data['technical_indicators'],
        'kline_data': price_history
    })


@app.route('/api/position')
def get_position():
    return jsonify({
        'position': bot_data['position'],
        'pnl': bot_data.get('pnl', 0),
        'unrealized_pnl': bot_data.get('unrealized_pnl', 0),
        'balance': bot_data.get('balance', 10000)
    })


@app.route('/api/signals')
def get_signals():
    limit = request.args.get('limit', 20, type=int)
    return jsonify({
        'latest_signal': bot_data['latest_signal'],
        'signal_history': bot_data['signal_history'][-limit:]
    })


@app.route('/api/trades')
def get_trades():
    limit = request.args.get('limit', 100, type=int)
    trades = simulated_account['trades'][-limit:]
    
    return jsonify({
        'trade_history': trades,
        'total_trades': simulated_account['win_count'] + simulated_account['loss_count'],
        'win_rate': bot_data.get('win_rate', 0),
        'total_pnl': simulated_account['total_pnl'],
        'win_count': simulated_account['win_count'],
        'loss_count': simulated_account['loss_count']
    })


@app.route('/api/start', methods=['POST'])
def start_bot():
    global bot_thread, bot_running, simulated_account, price_history
    
    data = request.get_json() or {}
    password = data.get('password', '')
    correct_password = os.getenv('OKX_PASSWORD', '')
    
    if not correct_password or password != correct_password:
        return jsonify({'success': False, 'message': '密码错误'})
    
    if bot_running:
        return jsonify({'success': False, 'message': 'Bot is already running'})
    
    simulated_account = {
        'balance': 10000,
        'position': None,
        'trades': [],
        'total_pnl': 0,
        'win_count': 0,
        'loss_count': 0
    }
    
    price_history = []
    
    bot_data['balance'] = 10000
    bot_data['pnl'] = 0
    bot_data['unrealized_pnl'] = 0
    bot_data['position'] = None
    bot_data['trade_history'] = []
    bot_data['signal_history'] = []
    
    bot_thread = threading.Thread(target=run_trading_bot, daemon=True)
    bot_thread.start()
    
    return jsonify({'success': True, 'message': 'Bot started successfully'})


@app.route('/api/stop', methods=['POST'])
def stop_bot():
    global bot_running
    
    data = request.get_json() or {}
    password = data.get('password', '')
    correct_password = os.getenv('OKX_PASSWORD', '')
    
    if not correct_password or password != correct_password:
        return jsonify({'success': False, 'message': '密码错误'})
    
    bot_running = False
    bot_data['status'] = 'stopped'
    return jsonify({'success': True, 'message': 'Bot stopped successfully'})


@app.route('/api/config')
def get_config():
    from deepseek_ok_带指标plus版本 import TRADE_CONFIG
    return jsonify({
        'symbol': TRADE_CONFIG.get('symbol'),
        'amount': TRADE_CONFIG.get('amount'),
        'leverage': TRADE_CONFIG.get('leverage'),
        'timeframe': TRADE_CONFIG.get('timeframe'),
        'test_mode': TRADE_CONFIG.get('test_mode'),
        'model': os.getenv('AI_MODEL', 'unknown')
    })


if __name__ == '__main__':
    host = os.getenv('WEB_HOST', '0.0.0.0')
    port = int(os.getenv('WEB_PORT', 5000))
    app.run(host=host, port=port, debug=False)