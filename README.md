# FuturesPilot

FuturesPilot is a small Windows-friendly Binance USDⓈ-M Futures trading tool with a Tkinter GUI. It places a maker limit entry order and then submits reduce-only stop-loss and take-profit orders based on the configured symbol, side, leverage, and percentage offsets.

> Risk warning: this project can place real futures orders. Use it only after reading the code, testing with small size, and understanding Binance Futures liquidation and API risks. Never commit real API keys.

## Features

- One-click long or short entry for Binance USDⓈ-M Futures.
- Maker-only limit entry using `GTX` time-in-force.
- Automatic leverage setup, symbol precision loading, and available balance check.
- Reduce-only stop-loss and take-profit order placement.
- Simple Tkinter desktop UI for API credentials and trading parameters.
- PyInstaller build script for a standalone Windows executable.

## Requirements

- Windows 10 or later.
- Python 3.10 or later.
- A Binance account with Futures enabled.
- Binance API key with Futures trading permission. Withdrawal permission is not needed and should stay disabled.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Create your local config from the example:

```powershell
copy config.example.json config.json
```

Then either edit `config.json` manually or fill the fields in the GUI. `config.json` is ignored by Git because it may contain plaintext API credentials.

Configuration fields:

- `api_key`: Binance API key.
- `api_secret`: Binance API secret.
- `symbol`: Futures symbol, for example `BTCUSDT`.
- `side`: Default side, `BUY` or `SELL`.
- `leverage`: Futures leverage from `1` to `125`.
- `entry_offset_pct`: Distance from the current bid/ask midpoint for the maker entry.
- `take_profit_pct`: Take-profit distance from the entry price.
- `stop_loss_pct`: Stop-loss distance from the entry price.

## Usage

Start the GUI:

```powershell
python gui.py
```

Recommended workflow:

1. Enter API credentials and trading parameters.
2. Click `Initialize` to set leverage, load symbol filters, and cache available balance.
3. Click `BUY` for a long setup or `SELL` for a short setup.
4. Check the status message for the submitted entry, stop-loss, and take-profit result.

The command-line entry point in `main.py` is kept for logging-oriented execution, but the GUI is the primary supported workflow because it performs the required initialization step before order placement.

## Build

Install PyInstaller if it is not already available in your virtual environment:

```powershell
pip install pyinstaller
```

Build the standalone Windows executable:

```powershell
.\build.bat
```

The executable is written to `dist\quant_trader.exe`. Build output under `build\` and `dist\` is ignored by Git.

## Project Structure

- `gui.py`: Tkinter desktop interface and user workflow.
- `trader.py`: Binance Futures trading logic, validation, precision handling, retries, and order placement.
- `main.py`: Logging-oriented script entry point.
- `config.example.json`: Safe example configuration for GitHub.
- `build.bat`: Windows PyInstaller build helper.
- `quant_trader.spec`: PyInstaller spec generated for the GUI app.

## Security Notes

- Do not commit `config.json`, `.env`, logs, or build artifacts.
- Store API keys with the minimum required permissions.
- Disable withdrawal permission on Binance API keys.
- Test carefully before using meaningful account size.

## 中文说明

FuturesPilot 是一个面向 Windows 的 Binance USDⓈ-M 永续合约一键交易工具，提供 Tkinter 图形界面。它会根据配置的交易对、方向、杠杆和百分比参数提交 Maker 限价开仓单，并在开仓单提交后继续提交 reduce-only 止损和止盈订单。

风险提示：本项目可以提交真实合约订单。请先阅读代码、用小资金测试，并充分理解 Binance 合约、爆仓和 API 风险。不要把真实 API Key 提交到 GitHub。

## 功能

- 支持 Binance USDⓈ-M 永续合约一键做多或做空。
- 使用 `GTX` 提交 Maker-only 限价开仓单。
- 自动设置杠杆、读取交易对精度、检查可用保证金。
- 自动提交 reduce-only 止损和止盈订单。
- 使用 Tkinter 提供简单桌面界面。
- 提供 PyInstaller 打包脚本，可生成 Windows 单文件程序。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 配置

复制示例配置：

```powershell
copy config.example.json config.json
```

然后手动编辑 `config.json`，或在 GUI 中填写并保存。`config.json` 已加入 `.gitignore`，因为它可能包含明文 API Key 和 Secret。

## 使用

启动 GUI：

```powershell
python gui.py
```

建议流程：

1. 填写 API 凭证和交易参数。
2. 点击 `初始化`，程序会设置杠杆、读取精度并缓存可用余额。
3. 点击 `BUY` 做多，或点击 `SELL` 做空。
4. 根据界面底部状态信息确认订单提交结果。

## 打包

如果虚拟环境里还没有 PyInstaller：

```powershell
pip install pyinstaller
```

运行打包脚本：

```powershell
.\build.bat
```

生成的程序位于 `dist\quant_trader.exe`，`build\` 和 `dist\` 不会提交到 Git。

## 项目名

我建议项目名使用 **FuturesPilot**。它比 “quant trader” 更具体，能表达这是一个面向合约交易执行的轻量工具，也适合作为 GitHub 仓库名：`futures-pilot`。
