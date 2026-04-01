import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    AI_API_KEY = os.getenv('AI_API_KEY')
    AI_BASE_URL = os.getenv('AI_BASE_URL', 'https://ai.100969.xyz/v1')
    AI_MODEL = os.getenv('AI_MODEL', 'mimo-v2-omni')
    
    OKX_API_KEY = os.getenv('OKX_API_KEY')
    OKX_SECRET = os.getenv('OKX_SECRET')
    OKX_PASSWORD = os.getenv('OKX_PASSWORD')
    
    TRADE_SYMBOL = os.getenv('TRADE_SYMBOL', 'BTC/USDT:USDT')
    TRADE_AMOUNT = float(os.getenv('TRADE_AMOUNT', '0.01'))
    TRADE_LEVERAGE = int(os.getenv('TRADE_LEVERAGE', '10'))
    TRADE_TIMEFRAME = os.getenv('TRADE_TIMEFRAME', '15m')
    TEST_MODE = os.getenv('TEST_MODE', 'true').lower() == 'true'
    
    MAX_POSITIONS = int(os.getenv('MAX_POSITIONS', '3'))
    STOP_LOSS_PERCENT = float(os.getenv('STOP_LOSS_PERCENT', '1.5'))
    TAKE_PROFIT_PERCENT = float(os.getenv('TAKE_PROFIT_PERCENT', '3.0'))
    
    KLINE_DATA_POINTS = int(os.getenv('KLINE_DATA_POINTS', '96'))
    KLINE_FOR_AI = int(os.getenv('KLINE_FOR_AI', '8'))
    RECENT_TRADES_COUNT = int(os.getenv('RECENT_TRADES_COUNT', '10'))
    TRADE_HISTORY_LIMIT = int(os.getenv('TRADE_HISTORY_LIMIT', '200'))
    
    # 决策间隔配置（分钟）
    DECISION_INTERVAL = int(os.getenv('DECISION_INTERVAL', '2'))
    
    # RSI阈值配置
    RSI_OVERSOLD_THRESHOLD = int(os.getenv('RSI_OVERSOLD_THRESHOLD', '35'))
    RSI_OVERBOUGHT_THRESHOLD = int(os.getenv('RSI_OVERBOUGHT_THRESHOLD', '65'))
    
    # 同方向最大持仓数配置
    MAX_SAME_DIRECTION_POSITIONS = int(os.getenv('MAX_SAME_DIRECTION_POSITIONS', '2'))
    
    # 策略模式配置
    STRATEGY_MODE = os.getenv('STRATEGY_MODE', 'standard')
    
    # 不同策略模式的RSI阈值配置
    AGGRESSIVE_RSI_OVERSOLD = int(os.getenv('AGGRESSIVE_RSI_OVERSOLD', '25'))
    AGGRESSIVE_RSI_OVERBOUGHT = int(os.getenv('AGGRESSIVE_RSI_OVERBOUGHT', '75'))
    STANDARD_RSI_OVERSOLD = int(os.getenv('STANDARD_RSI_OVERSOLD', '35'))
    STANDARD_RSI_OVERBOUGHT = int(os.getenv('STANDARD_RSI_OVERBOUGHT', '65'))
    CONSERVATIVE_RSI_OVERSOLD = int(os.getenv('CONSERVATIVE_RSI_OVERSOLD', '45'))
    CONSERVATIVE_RSI_OVERBOUGHT = int(os.getenv('CONSERVATIVE_RSI_OVERBOUGHT', '55'))
    
    # 不同策略模式的止损止盈配置
    AGGRESSIVE_STOP_LOSS = float(os.getenv('AGGRESSIVE_STOP_LOSS', '2.0'))
    AGGRESSIVE_TAKE_PROFIT = float(os.getenv('AGGRESSIVE_TAKE_PROFIT', '4.0'))
    AGGRESSIVE_DECISION_INTERVAL = int(os.getenv('AGGRESSIVE_DECISION_INTERVAL', '10'))
    STANDARD_STOP_LOSS = float(os.getenv('STANDARD_STOP_LOSS', '1.5'))
    STANDARD_TAKE_PROFIT = float(os.getenv('STANDARD_TAKE_PROFIT', '3.0'))
    STANDARD_DECISION_INTERVAL = int(os.getenv('STANDARD_DECISION_INTERVAL', '15'))
    CONSERVATIVE_STOP_LOSS = float(os.getenv('CONSERVATIVE_STOP_LOSS', '1.0'))
    CONSERVATIVE_TAKE_PROFIT = float(os.getenv('CONSERVATIVE_TAKE_PROFIT', '2.0'))
    CONSERVATIVE_DECISION_INTERVAL = int(os.getenv('CONSERVATIVE_DECISION_INTERVAL', '20'))
    
    WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
    WEB_PORT = int(os.getenv('WEB_PORT', '5000'))
    WEB_SECRET_KEY = os.getenv('WEB_SECRET_KEY', 'dev-secret-key')
    
    @classmethod
    def get_rsi_thresholds(cls):
        """根据策略模式获取RSI阈值"""
        if cls.STRATEGY_MODE == 'aggressive':
            return cls.AGGRESSIVE_RSI_OVERSOLD, cls.AGGRESSIVE_RSI_OVERBOUGHT
        elif cls.STRATEGY_MODE == 'conservative':
            return cls.CONSERVATIVE_RSI_OVERSOLD, cls.CONSERVATIVE_RSI_OVERBOUGHT
        else:  # standard
            return cls.STANDARD_RSI_OVERSOLD, cls.STANDARD_RSI_OVERBOUGHT
    
    @classmethod
    def get_stop_loss_take_profit(cls):
        """根据策略模式获取止损止盈参数"""
        if cls.STRATEGY_MODE == 'aggressive':
            return cls.AGGRESSIVE_STOP_LOSS, cls.AGGRESSIVE_TAKE_PROFIT
        elif cls.STRATEGY_MODE == 'conservative':
            return cls.CONSERVATIVE_STOP_LOSS, cls.CONSERVATIVE_TAKE_PROFIT
        else:  # standard
            return cls.STANDARD_STOP_LOSS, cls.STANDARD_TAKE_PROFIT
    
    @classmethod
    def get_decision_interval(cls):
        """根据策略模式获取决策间隔时间"""
        if cls.STRATEGY_MODE == 'aggressive':
            return cls.AGGRESSIVE_DECISION_INTERVAL
        elif cls.STRATEGY_MODE == 'conservative':
            return cls.CONSERVATIVE_DECISION_INTERVAL
        else:  # standard
            return cls.STANDARD_DECISION_INTERVAL
    
    @classmethod
    def get_strategy_description(cls):
        """获取策略模式描述"""
        descriptions = {
            'aggressive': '激进模式 - 高风险高收益，更频繁的交易信号',
            'standard': '标准模式 - 平衡风险收益，适中的交易频率',
            'conservative': '保守模式 - 低风险稳健，更少的交易信号'
        }
        return descriptions.get(cls.STRATEGY_MODE, '未知模式')
    
    @classmethod
    def display(cls):
        print("=" * 60)
        print("交易机器人配置")
        print("=" * 60)
        print(f"AI模型: {cls.AI_MODEL}")
        print(f"交易对: {cls.TRADE_SYMBOL}")
        print(f"交易数量: {cls.TRADE_AMOUNT} BTC")
        print(f"杠杆倍数: {cls.TRADE_LEVERAGE}x")
        print(f"时间周期: {cls.TRADE_TIMEFRAME}")
        print(f"测试模式: {cls.TEST_MODE}")
        print(f"最大持仓数: {cls.MAX_POSITIONS}")
        print(f"止损比例: {cls.STOP_LOSS_PERCENT}%")
        print(f"止盈比例: {cls.TAKE_PROFIT_PERCENT}%")
        print(f"K线数据点: {cls.KLINE_DATA_POINTS}")
        print(f"AI分析K线数: {cls.KLINE_FOR_AI}")
        print(f"最近交易记录: {cls.RECENT_TRADES_COUNT}")
        print(f"RSI超卖阈值: {cls.RSI_OVERSOLD_THRESHOLD}")
        print(f"RSI超买阈值: {cls.RSI_OVERBOUGHT_THRESHOLD}")
        print(f"同方向最大持仓数: {cls.MAX_SAME_DIRECTION_POSITIONS}")
        print(f"决策间隔: {cls.DECISION_INTERVAL}分钟")
        print(f"策略模式: {cls.STRATEGY_MODE}")
        print(f"策略描述: {cls.get_strategy_description()}")
        rsi_oversold, rsi_overbought = cls.get_rsi_thresholds()
        stop_loss, take_profit = cls.get_stop_loss_take_profit()
        decision_interval = cls.get_decision_interval()
        print(f"当前RSI阈值: 超卖={rsi_oversold}, 超买={rsi_overbought}")
        print(f"当前止损止盈: 止损={stop_loss}%, 止盈={take_profit}%")
        print(f"当前决策间隔: {decision_interval}分钟")
        print("=" * 60)
