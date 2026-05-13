# FuturesPilot

FuturesPilot is a small Windows-friendly Binance USDⓈ-M Futures trading tool with a Tkinter GUI. It places a maker limit entry order and then submits reduce-only stop-loss and take-profit orders based on the configured symbol, side, leverage, and percentage offsets.

## Features

- One-click long or short entry for Binance USDⓈ-M Futures.
- Maker-only limit entry using `GTX` time-in-force.
- Automatic leverage setup, symbol precision loading, and available balance check.
- Reduce-only stop-loss and take-profit order placement.
- Simple Tkinter desktop UI for API credentials and trading parameters.
- PyInstaller build script for a standalone Windows executable.

## Usage
Use the EXE directly.

Recommended workflow:

1. Enter API credentials and trading parameters.
2. Click `Initialize` to set leverage, load symbol filters, and cache available balance.
3. Click `BUY` for a long setup or `SELL` for a short setup.
4. Check the status message for the submitted entry, stop-loss, and take-profit result.

## 中文说明

FuturesPilot 是一个面向 Windows 的 Binance USDⓈ-M 永续合约一键交易工具，提供 Tkinter 图形界面。它会根据配置的交易对、方向、杠杆和百分比参数提交 Maker 限价开仓单，并在开仓单提交后继续提交 reduce-only 止损和止盈订单。

## 功能

- 支持 Binance USDⓈ-M 永续合约一键做多或做空。
- 使用 `GTX` 提交 Maker-only 限价开仓单。
- 自动设置杠杆、读取交易对精度、检查可用保证金。
- 自动提交 reduce-only 止损和止盈订单。
- 使用 Tkinter 提供简单桌面界面。
- 提供 PyInstaller 打包脚本，可生成 Windows 单文件程序。

## 使用
下载并点击exe即可

建议流程：

1. 填写 API 凭证和交易参数。
2. 点击 `初始化`，程序会设置杠杆、读取精度并缓存可用余额。
3. 点击 `BUY` 做多，或点击 `SELL` 做空。
4. 根据界面底部状态信息确认订单提交结果。
