import os
import json
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import threading
import logging
from config import Config

load_dotenv()

Config.display()

program_logger = logging.getLogger('program')
program_logger.setLevel(logging.INFO)
program_handler = logging.FileHandler('logs/program.log', mode='a', encoding='utf-8')
program_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
program_logger.addHandler(program_handler)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.WEB_SECRET_KEY
CORS(app)

price_history = []

simulated_account = {
    'balance': 10000,
    'positions': [],
    'trades': [],
    'total_pnl': 0,
    'win_count': 0,
    'loss_count': 0,
    'max_positions': Config.MAX_POSITIONS
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


def check_stop_loss_take_profit(current_price):
    """检查所有仓位的止损止盈"""
    global simulated_account
    
    positions_to_close = []
    
    for i, pos in enumerate(simulated_account['positions']):
        if pos['side'] == 'long':
            pnl_percent = (current_price - pos['entry_price']) / pos['entry_price'] * 100
        else:
            pnl_percent = (pos['entry_price'] - current_price) / pos['entry_price'] * 100
        
        # 止损检查 -1.5%
        if pnl_percent <= -1.5:
            positions_to_close.append((i, 'stop_loss', pnl_percent))
        # 止盈检查 +3%
        elif pnl_percent >= 3:
            positions_to_close.append((i, 'take_profit', pnl_percent))
    
    # 执行平仓
    for i, reason, pnl_percent in sorted(positions_to_close, reverse=True):
        pos = simulated_account['positions'][i]
        
        if pos['side'] == 'long':
            close_pnl = (current_price - pos['entry_price']) * pos['amount']
        else:
            close_pnl = (pos['entry_price'] - current_price) * pos['amount']
        
        simulated_account['balance'] += pos['margin'] + close_pnl
        simulated_account['total_pnl'] += close_pnl
        
        if close_pnl > 0:
            simulated_account['win_count'] += 1
        else:
            simulated_account['loss_count'] += 1
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # 交易类型中文映射
        side_text = '多仓' if pos['side'] == 'long' else '空仓'
        reason_text = {'stop_loss': '止损', 'take_profit': '止盈'}
        type_text = f'平{side_text}-{reason_text.get(reason, reason)}'
        
        close_trade = {
            'timestamp': timestamp,
            'type': type_text,
            'side': pos['side'],
            'entry_price': pos['entry_price'],
            'exit_price': current_price,
            'amount': pos['amount'],
            'pnl': close_pnl,
            'pnl_percent': pnl_percent,
            'balance': simulated_account['balance'],
            'margin': pos['margin'],
            'reason': reason,
            'strategy_mode': Config.STRATEGY_MODE
        }
        simulated_account['trades'].append(close_trade)
        
        reason_text = {'stop_loss': '止损', 'take_profit': '止盈'}
        side_text = '多仓' if pos['side'] == 'long' else '空仓'
        program_logger.info(f"[自动{reason_text.get(reason, reason)}] 平{side_text}: 入场={pos['entry_price']:.2f}, 出场={current_price:.2f}, 盈亏={close_pnl:.2f} ({pnl_percent:.2f}%)")
        
        # 记录到AI日志
        ai_logger = logging.getLogger('ai')
        ai_logger.info(f"{'='*60}")
        ai_logger.info(f"[平仓记录] 类型: 平{side_text}-{reason_text.get(reason, reason)}")
        ai_logger.info(f"[平仓详情] 方向: {side_text}")
        ai_logger.info(f"[平仓价格] 入场: ${pos['entry_price']:,.2f} | 出场: ${current_price:,.2f}")
        ai_logger.info(f"[平仓盈亏] ${close_pnl:,.2f} ({pnl_percent:+.2f}%)")
        ai_logger.info(f"[平仓原因] {reason_text.get(reason, reason)}")
        ai_logger.info(f"[账户余额] ${simulated_account['balance']:,.2f}")
        
        simulated_account['positions'].pop(i)


def simulate_trade(signal_data, price_data):
    global simulated_account, bot_data
    
    current_price = price_data['price']
    signal = signal_data.get('signal', 'HOLD')
    
    # 先检查止损止盈
    check_stop_loss_take_profit(current_price)
    
    if signal == 'HOLD':
        return
    
    # 风险管理：根据策略模式调整信心等级要求
    confidence = signal_data.get('confidence', 'LOW')
    strategy_mode = os.getenv('STRATEGY_MODE', 'standard')
    
    # 激进模式允许MEDIUM信心交易，标准和保守模式需要HIGH信心
    if strategy_mode == 'aggressive':
        if confidence not in ['HIGH', 'MEDIUM']:
            confidence_text = {'HIGH': '高', 'MEDIUM': '中', 'LOW': '低'}
            program_logger.info(f"⚠️ {confidence_text.get(confidence, confidence)}信心信号，跳过执行（激进模式需要中等或高信心）")
            return
    else:
        if confidence != 'HIGH':
            confidence_text = {'HIGH': '高', 'MEDIUM': '中', 'LOW': '低'}
            program_logger.info(f"⚠️ {confidence_text.get(confidence, confidence)}信心信号，跳过执行（标准/保守模式需要高信心）")
            return
    
    # 检查是否有持仓，避免频繁操作
    if simulated_account['positions']:
        for pos in simulated_account['positions']:
            if pos['side'] == 'long':
                pnl_percent = (current_price - pos['entry_price']) / pos['entry_price'] * 100
            else:
                pnl_percent = (pos['entry_price'] - current_price) / pos['entry_price'] * 100
            
            # 如果当前持仓盈利超过1%，保持持仓不动
            if pnl_percent > 1.0:
                program_logger.info(f"🔒 当前持仓盈利{pnl_percent:.2f}%，保持持仓")
                return
            
            # 如果当前持仓亏损但未到止损，需要更强信号才反向
            if pnl_percent < -0.5 and confidence != 'HIGH':
                program_logger.info(f"🔒 当前持仓亏损{pnl_percent:.2f}%，需要HIGH信心才反向操作")
                return
    
    amount = float(os.getenv('TRADE_AMOUNT', '0.01'))
    leverage = float(os.getenv('TRADE_LEVERAGE', '10'))
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    signal_text = {'BUY': '买入', 'SELL': '卖出', 'HOLD': '持有'}
    program_logger.info(f"\n{'='*60}")
    program_logger.info(f"[模拟交易] 信号: {signal_text.get(signal, signal)}, 价格: ${current_price:.2f}")
    program_logger.info(f"[账户状态] 余额: ${simulated_account['balance']:.2f}, 持仓数: {len(simulated_account['positions'])}")
    
    # 显示当前持仓详情
    if simulated_account['positions']:
        for i, pos in enumerate(simulated_account['positions']):
            if pos['side'] == 'long':
                pnl = (current_price - pos['entry_price']) * pos['amount']
            else:
                pnl = (pos['entry_price'] - current_price) * pos['amount']
            side_text = '多仓' if pos['side'] == 'long' else '空仓'
            program_logger.info(f"  [{i+1}] {side_text}: 入场=${pos['entry_price']:.2f}, 盈亏=${pnl:.2f}")
    
    # 多仓交易逻辑
    if signal == 'BUY':
        # 先平掉所有空仓
        short_positions = [i for i, pos in enumerate(simulated_account['positions']) if pos['side'] == 'short']
        
        if short_positions:
            program_logger.info(f"[模拟] 发现{len(short_positions)}个空仓，先平仓...")
            for i in sorted(short_positions, reverse=True):
                pos = simulated_account['positions'][i]
                close_pnl = (pos['entry_price'] - current_price) * pos['amount']
                pnl_percent = (pos['entry_price'] - current_price) / pos['entry_price'] * 100
                
                simulated_account['balance'] += pos['margin'] + close_pnl
                simulated_account['total_pnl'] += close_pnl
                
                if close_pnl > 0:
                    simulated_account['win_count'] += 1
                else:
                    simulated_account['loss_count'] += 1
                
                close_trade = {
                    'timestamp': timestamp,
                    'type': '平空仓-买入信号',
                    'side': 'short',
                    'entry_price': pos['entry_price'],
                    'exit_price': current_price,
                    'amount': pos['amount'],
                    'pnl': close_pnl,
                    'pnl_percent': pnl_percent,
                    'balance': simulated_account['balance'],
                    'margin': pos['margin'],
                    'reason': '买入信号平空仓',
                    'strategy_mode': Config.STRATEGY_MODE
                }
                simulated_account['trades'].append(close_trade)
                program_logger.info(f"[模拟] 平空仓#{i+1}: 入场={pos['entry_price']:.2f}, 出场={current_price:.2f}, 盈亏={close_pnl:.2f}")
                
                # 记录到AI日志
                ai_logger = logging.getLogger('ai')
                ai_logger.info(f"{'='*60}")
                ai_logger.info(f"[平仓记录] 类型: 平空仓-买入信号")
                ai_logger.info(f"[平仓详情] 方向: 空仓")
                ai_logger.info(f"[平仓价格] 入场: ${pos['entry_price']:,.2f} | 出场: ${current_price:,.2f}")
                ai_logger.info(f"[平仓盈亏] ${close_pnl:,.2f} ({pnl_percent:+.2f}%)")
                ai_logger.info(f"[平仓原因] 买入信号触发，平掉所有空仓")
                ai_logger.info(f"[账户余额] ${simulated_account['balance']:,.2f}")
                
                simulated_account['positions'].pop(i)
        
        # 检查是否还能开多仓
        if len(simulated_account['positions']) >= simulated_account['max_positions']:
            program_logger.info(f"[模拟] 已达最大持仓数 {simulated_account['max_positions']}，无法开多仓")
            program_logger.info(f"{'='*60}")
            return
        
        # 检查是否已有同方向仓位，避免过度加仓
        long_positions = [p for p in simulated_account['positions'] if p['side'] == 'long']
        if len(long_positions) >= 2:
            program_logger.info(f"[模拟] 已有{len(long_positions)}个多仓，避免过度加仓（同方向最大2个）")
            program_logger.info(f"{'='*60}")
            return
        
        # 检查是否有空仓，需要先平仓再开多仓
        short_positions = [p for p in simulated_account['positions'] if p['side'] == 'short']
        if short_positions:
            program_logger.info(f"[模拟] 有{len(short_positions)}个空仓，需要先平仓再开多仓")
            program_logger.info(f"{'='*60}")
            return
        
        # 计算保证金
        margin = current_price * amount / leverage
        if simulated_account['balance'] < margin:
            program_logger.info(f"[模拟] 余额不足! 需要${margin:.2f}, 可用${simulated_account['balance']:.2f}")
            program_logger.info(f"{'='*60}")
            return
        
        # 开多仓
        simulated_account['balance'] -= margin
        new_position = {
            'side': 'long',
            'entry_price': current_price,
            'amount': amount,
            'margin': margin,
            'timestamp': timestamp,
            'stop_loss': signal_data.get('stop_loss', current_price * 0.985),
            'take_profit': signal_data.get('take_profit', current_price * 1.03)
        }
        simulated_account['positions'].append(new_position)
        
        open_trade = {
            'timestamp': timestamp,
            'type': '开多仓',
            'side': 'long',
            'price': current_price,
            'amount': amount,
            'margin': margin,
            'balance': simulated_account['balance'],
            'strategy_mode': Config.STRATEGY_MODE
        }
        simulated_account['trades'].append(open_trade)
        program_logger.info(f"[模拟] 开多仓: 价格={current_price:.2f}, 数量={amount}, 保证金={margin:.2f}")
        program_logger.info(f"[模拟] 当前持仓数: {len(simulated_account['positions'])} (多仓{len([p for p in simulated_account['positions'] if p['side']=='long'])}个)")
    
    elif signal == 'SELL':
        # 先平掉所有多仓
        long_positions = [i for i, pos in enumerate(simulated_account['positions']) if pos['side'] == 'long']
        
        if long_positions:
            program_logger.info(f"[模拟] 发现{len(long_positions)}个多仓，先平仓...")
            for i in sorted(long_positions, reverse=True):
                pos = simulated_account['positions'][i]
                close_pnl = (current_price - pos['entry_price']) * pos['amount']
                pnl_percent = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                
                simulated_account['balance'] += pos['margin'] + close_pnl
                simulated_account['total_pnl'] += close_pnl
                
                if close_pnl > 0:
                    simulated_account['win_count'] += 1
                else:
                    simulated_account['loss_count'] += 1
                
                close_trade = {
                    'timestamp': timestamp,
                    'type': '平多仓-卖出信号',
                    'side': 'long',
                    'entry_price': pos['entry_price'],
                    'exit_price': current_price,
                    'amount': pos['amount'],
                    'pnl': close_pnl,
                    'pnl_percent': pnl_percent,
                    'balance': simulated_account['balance'],
                    'margin': pos['margin'],
                    'reason': '卖出信号平多仓',
                    'strategy_mode': Config.STRATEGY_MODE
                }
                simulated_account['trades'].append(close_trade)
                program_logger.info(f"[模拟] 平多仓#{i+1}: 入场={pos['entry_price']:.2f}, 出场={current_price:.2f}, 盈亏={close_pnl:.2f}")
                
                # 记录到AI日志
                ai_logger = logging.getLogger('ai')
                ai_logger.info(f"{'='*60}")
                ai_logger.info(f"[平仓记录] 类型: 平多仓-卖出信号")
                ai_logger.info(f"[平仓详情] 方向: 多仓")
                ai_logger.info(f"[平仓价格] 入场: ${pos['entry_price']:,.2f} | 出场: ${current_price:,.2f}")
                ai_logger.info(f"[平仓盈亏] ${close_pnl:,.2f} ({pnl_percent:+.2f}%)")
                ai_logger.info(f"[平仓原因] 卖出信号触发，平掉所有多仓")
                ai_logger.info(f"[账户余额] ${simulated_account['balance']:,.2f}")
                
                simulated_account['positions'].pop(i)
        
        # 检查是否还能开空仓
        if len(simulated_account['positions']) >= simulated_account['max_positions']:
            program_logger.info(f"[模拟] 已达最大持仓数 {simulated_account['max_positions']}，无法开空仓")
            program_logger.info(f"{'='*60}")
            return
        
        # 检查是否已有同方向仓位，避免过度加仓
        short_positions = [p for p in simulated_account['positions'] if p['side'] == 'short']
        if len(short_positions) >= 2:
            program_logger.info(f"[模拟] 已有{len(short_positions)}个空仓，避免过度加仓（同方向最大2个）")
            program_logger.info(f"{'='*60}")
            return
        
        # 检查是否有多仓，需要先平仓再开空仓
        long_positions = [p for p in simulated_account['positions'] if p['side'] == 'long']
        if long_positions:
            program_logger.info(f"[模拟] 有{len(long_positions)}个多仓，需要先平仓再开空仓")
            program_logger.info(f"{'='*60}")
            return
        
        # 计算保证金
        margin = current_price * amount / leverage
        if simulated_account['balance'] < margin:
            program_logger.info(f"[模拟] 余额不足! 需要${margin:.2f}, 可用${simulated_account['balance']:.2f}")
            program_logger.info(f"{'='*60}")
            return
        
        # 开空仓
        simulated_account['balance'] -= margin
        new_position = {
            'side': 'short',
            'entry_price': current_price,
            'amount': amount,
            'margin': margin,
            'timestamp': timestamp,
            'stop_loss': signal_data.get('stop_loss', current_price * 1.015),
            'take_profit': signal_data.get('take_profit', current_price * 0.97)
        }
        simulated_account['positions'].append(new_position)
        
        open_trade = {
            'timestamp': timestamp,
            'type': '开空仓',
            'side': 'short',
            'price': current_price,
            'amount': amount,
            'margin': margin,
            'balance': simulated_account['balance'],
            'strategy_mode': Config.STRATEGY_MODE
        }
        simulated_account['trades'].append(open_trade)
        program_logger.info(f"[模拟] 开空仓: 价格={current_price:.2f}, 数量={amount}, 保证金={margin:.2f}")
        program_logger.info(f"[模拟] 当前持仓数: {len(simulated_account['positions'])} (空仓{len([p for p in simulated_account['positions'] if p['side']=='short'])}个)")
    
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
    
    # 多仓位数据
    if simulated_account['positions']:
        total_unrealized_pnl = 0
        positions_data = []
        
        for pos in simulated_account['positions']:
            if pos['side'] == 'long':
                unrealized_pnl = (current_price - pos['entry_price']) * pos['amount']
            else:
                unrealized_pnl = (pos['entry_price'] - current_price) * pos['amount']
            
            total_unrealized_pnl += unrealized_pnl
            
            positions_data.append({
                'side': pos['side'],
                'size': pos['amount'],
                'entry_price': pos['entry_price'],
                'unrealized_pnl': unrealized_pnl,
                'margin': pos['margin'],
                'timestamp': pos['timestamp']
            })
        
        bot_data['positions'] = positions_data
        bot_data['unrealized_pnl'] = total_unrealized_pnl
        bot_data['position_count'] = len(simulated_account['positions'])
        
        # 调试日志
        program_logger.info(f"[数据更新] 持仓数: {len(positions_data)}, 未实现盈亏: ${total_unrealized_pnl:.2f}")
    else:
        bot_data['positions'] = []
        bot_data['unrealized_pnl'] = 0
        bot_data['position_count'] = 0


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
                    
                    # 实时更新持仓数据（每秒更新）
                    update_bot_data(current_price)
                    
                    # 根据配置的间隔时间执行交易分析
                    decision_interval = Config.DECISION_INTERVAL
                    current_minute = datetime.now().minute
                    if current_minute % decision_interval == 0 and datetime.now().second < 5:
                        program_logger.info(f"{'='*60}")
                        program_logger.info(f"[交易时间] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        program_logger.info(f"[价格] ${current_price:,.2f}")
                        program_logger.info(f"[账户] 余额: ${simulated_account['balance']:.2f}, 持仓数: {len(simulated_account['positions'])}")
                        kline_for_ai = Config.KLINE_FOR_AI
                        timeframe = Config.TRADE_TIMEFRAME
                        timeframe_minutes = int(timeframe.replace('m', '')) if 'm' in timeframe else 15
                        total_minutes = kline_for_ai * timeframe_minutes
                        program_logger.info(f"[AI分析] 发送最近{total_minutes}分钟K线数据 ({kline_for_ai}根 × {timeframe})")
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
                        
                        time.sleep(5)
                
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
        'positions': bot_data.get('positions', []),
        'position_count': bot_data.get('position_count', 0),
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
        'positions': [],  # 支持多个仓位
        'trades': [],
        'total_pnl': 0,
        'win_count': 0,
        'loss_count': 0,
        'max_positions': int(os.getenv('MAX_POSITIONS', '3'))  # 从.env读取最大持仓数
    }
    
    price_history = []
    
    bot_data['balance'] = 10000
    bot_data['pnl'] = 0
    bot_data['unrealized_pnl'] = 0
    bot_data['positions'] = []
    bot_data['position_count'] = 0
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
    rsi_oversold, rsi_overbought = Config.get_rsi_thresholds()
    return jsonify({
        'symbol': TRADE_CONFIG.get('symbol'),
        'amount': TRADE_CONFIG.get('amount'),
        'leverage': TRADE_CONFIG.get('leverage'),
        'timeframe': TRADE_CONFIG.get('timeframe'),
        'test_mode': TRADE_CONFIG.get('test_mode'),
        'model': os.getenv('AI_MODEL', 'unknown'),
        'max_positions': int(os.getenv('MAX_POSITIONS', '3')),
        'max_same_direction_positions': int(os.getenv('MAX_SAME_DIRECTION_POSITIONS', '2')),
        'stop_loss_percent': float(os.getenv('STOP_LOSS_PERCENT', '1.5')),
        'take_profit_percent': float(os.getenv('TAKE_PROFIT_PERCENT', '3.0')),
        'strategy_mode': Config.STRATEGY_MODE,
        'strategy_description': Config.get_strategy_description(),
        'rsi_oversold_threshold': rsi_oversold,
        'rsi_overbought_threshold': rsi_overbought,
        'decision_interval': Config.DECISION_INTERVAL,
        'kline_for_ai': Config.KLINE_FOR_AI
    })


@app.route('/api/strategy', methods=['POST'])
def update_strategy():
    """更新策略模式"""
    data = request.get_json() or {}
    password = data.get('password', '')
    correct_password = os.getenv('OKX_PASSWORD', '')
    
    if not correct_password or password != correct_password:
        return jsonify({'success': False, 'message': '密码错误'})
    
    new_mode = data.get('mode', '')
    if new_mode not in ['aggressive', 'standard', 'conservative']:
        return jsonify({'success': False, 'message': '无效的策略模式，支持: aggressive, standard, conservative'})
    
    # 更新环境变量
    os.environ['STRATEGY_MODE'] = new_mode
    
    # 持久化保存到.env文件
    try:
        env_path = '.env'
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 查找并更新STRATEGY_MODE行
        updated = False
        for i, line in enumerate(lines):
            if line.startswith('STRATEGY_MODE='):
                lines[i] = f'STRATEGY_MODE={new_mode}\n'
                updated = True
                break
        
        # 如果没找到，添加到策略模式配置部分
        if not updated:
            # 查找策略模式配置部分
            for i, line in enumerate(lines):
                if '策略模式配置' in line:
                    # 在注释后添加
                    lines.insert(i + 2, f'STRATEGY_MODE={new_mode}\n')
                    updated = True
                    break
        
        # 如果还是没找到，在文件末尾添加
        if not updated:
            lines.append(f'\n# 策略模式配置\nSTRATEGY_MODE={new_mode}\n')
        
        # 写入文件
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        program_logger.info(f"[配置保存] 策略模式已保存到.env文件: {new_mode}")
        
    except Exception as e:
        program_logger.error(f"[配置保存] 保存策略模式失败: {e}")
        return jsonify({'success': False, 'message': f'保存配置失败: {str(e)}'})
    
    # 重新加载配置
    try:
        # 重新加载环境变量
        load_dotenv(override=True)
        
        # 更新Config类的属性
        Config.STRATEGY_MODE = os.getenv('STRATEGY_MODE', 'standard')
        Config.AGGRESSIVE_RSI_OVERSOLD = int(os.getenv('AGGRESSIVE_RSI_OVERSOLD', '25'))
        Config.AGGRESSIVE_RSI_OVERBOUGHT = int(os.getenv('AGGRESSIVE_RSI_OVERBOUGHT', '75'))
        Config.STANDARD_RSI_OVERSOLD = int(os.getenv('STANDARD_RSI_OVERSOLD', '35'))
        Config.STANDARD_RSI_OVERBOUGHT = int(os.getenv('STANDARD_RSI_OVERBOUGHT', '65'))
        Config.CONSERVATIVE_RSI_OVERSOLD = int(os.getenv('CONSERVATIVE_RSI_OVERSOLD', '45'))
        Config.CONSERVATIVE_RSI_OVERBOUGHT = int(os.getenv('CONSERVATIVE_RSI_OVERBOUGHT', '55'))
        
        # 强制更新Config类的策略模式属性
        Config.STRATEGY_MODE = new_mode
        
        # 记录策略变更
        program_logger.info(f"{'='*60}")
        program_logger.info(f"[策略变更] 用户切换策略模式")
        program_logger.info(f"[新模式] {new_mode}")
        program_logger.info(f"[策略描述] {Config.get_strategy_description()}")
        rsi_oversold, rsi_overbought = Config.get_rsi_thresholds()
        program_logger.info(f"[RSI阈值] 超卖={rsi_oversold}, 超买={rsi_overbought}")
        program_logger.info(f"{'='*60}")
        
    except Exception as e:
        program_logger.error(f"[配置重载] 重新加载配置失败: {e}")
        return jsonify({'success': False, 'message': f'重新加载配置失败: {str(e)}'})
    
    return jsonify({
        'success': True, 
        'message': f'策略模式已切换为: {new_mode}',
        'strategy_mode': new_mode,
        'strategy_description': Config.get_strategy_description(),
        'rsi_oversold_threshold': rsi_oversold,
        'rsi_overbought_threshold': rsi_overbought
    })


if __name__ == '__main__':
    host = os.getenv('WEB_HOST', '0.0.0.0')
    port = int(os.getenv('WEB_PORT', 5000))
    app.run(host=host, port=port, debug=False)