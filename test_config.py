#!/usr/bin/env python
import os
import sys

print("=" * 60)
print("测试配置加载")
print("=" * 60)

print(f"Python版本: {sys.version}")
print(f"当前工作目录: {os.getcwd()}")
print(f".env文件路径: {os.path.abspath('.env')}")
print(f".env文件存在: {os.path.exists('.env')}")

if os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            if 'TRADE_TIMEFRAME' in line:
                print(f".env文件内容: {line.strip()}")

print("\n加载dotenv...")
from dotenv import load_dotenv
load_dotenv()

print(f"os.getenv('TRADE_TIMEFRAME'): {os.getenv('TRADE_TIMEFRAME')}")

print("\n导入模块...")
from deepseek_ok_带指标plus版本 import TRADE_CONFIG
print(f"TRADE_CONFIG['timeframe']: {TRADE_CONFIG['timeframe']}")

print("\n测试API调用...")
from deepseek_ok_带指标plus版本 import get_btc_ohlcv_enhanced
result = get_btc_ohlcv_enhanced()
if result:
    print(f"SUCCESS! 价格: {result['price']}")
else:
    print("FAILED!")