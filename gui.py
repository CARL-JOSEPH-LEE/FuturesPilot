from __future__ import annotations

import json
import logging
import sys
import threading
import tkinter as tk
from decimal import Decimal
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk
from typing import Optional

from binance.client import Client


from trader import BinanceFuturesTrader, SymbolFilters, TraderConfig


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = _app_dir()
CONFIG_PATH = APP_DIR / "config.json"

UI_FONT_FAMILY = "Microsoft YaHei UI"
MONO_FONT_FAMILY = "Consolas"

COLOR_BUY = "#00B14F"
COLOR_BUY_ACTIVE = "#008C3D"
COLOR_SELL = "#E03131"
COLOR_SELL_ACTIVE = "#B12626"
COLOR_DISABLED_FG = "#cccccc"
COLOR_SUCCESS = "#2BA84A"
COLOR_WARN = "#F08C00"
COLOR_ERROR = "#E03131"
COLOR_BUSY = "#1971C2"
COLOR_IDLE = "#333333"


class TraderGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Binance USDT 永续 · 一键下单")
        root.geometry("620x560")
        root.minsize(560, 520)

        self._trading_lock = threading.Lock()
        self._cached_symbol: Optional[str] = None
        self._cached_filters: Optional[SymbolFilters] = None
        self._cached_balance: Optional[Decimal] = None
        self._cached_client: Optional[Client] = None

        self._silence_loggers()
        self._build_ui()
        self._load_inputs_from_config()

    @staticmethod
    def _silence_loggers() -> None:
        logging.disable(logging.CRITICAL)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.CRITICAL + 1)
        for h in list(root_logger.handlers):
            root_logger.removeHandler(h)
        root_logger.addHandler(logging.NullHandler())

    def _font(self, size: int, weight: str = "normal", family: str = UI_FONT_FAMILY) -> tkfont.Font:
        return tkfont.Font(family=family, size=size, weight=weight)

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        for theme in ("vista", "winnative", "clam", "default"):
            try:
                style.theme_use(theme)
                break
            except Exception:
                continue

        font_label = self._font(11)
        font_entry = self._font(12, family=MONO_FONT_FAMILY)
        font_button = self._font(16, "bold")
        font_status = self._font(10)

        fr_api = ttk.LabelFrame(self.root, text="API 凭证（明文存于 config.json）")
        fr_api.pack(fill="x", padx=12, pady=(12, 4))
        fr_api.columnconfigure(1, weight=1)

        self.v_api_key = tk.StringVar()
        self.v_api_secret = tk.StringVar()
        self.v_show_api = tk.BooleanVar(value=False)

        ttk.Label(fr_api, text="API Key", font=font_label).grid(
            row=0, column=0, sticky="e", padx=(16, 10), pady=6
        )
        self.ent_api_key = ttk.Entry(
            fr_api, textvariable=self.v_api_key, font=font_entry, show="*"
        )
        self.ent_api_key.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=6)

        ttk.Label(fr_api, text="API Secret", font=font_label).grid(
            row=1, column=0, sticky="e", padx=(16, 10), pady=6
        )
        self.ent_api_secret = ttk.Entry(
            fr_api, textvariable=self.v_api_secret, font=font_entry, show="*"
        )
        self.ent_api_secret.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=6)

        self.chk_show_api = ttk.Checkbutton(
            fr_api,
            text="显示明文",
            variable=self.v_show_api,
            command=self._on_toggle_show_api,
        )
        self.chk_show_api.grid(row=0, column=2, rowspan=2, sticky="ns", padx=(0, 16), pady=6)

        fr_params = ttk.LabelFrame(self.root, text="交易参数")
        fr_params.pack(fill="x", padx=12, pady=(4, 4))
        fr_params.columnconfigure(1, weight=1)

        def add_row(row: int, label: str, var: tk.StringVar) -> ttk.Entry:
            ttk.Label(fr_params, text=label, font=font_label).grid(
                row=row, column=0, sticky="e", padx=(16, 10), pady=6
            )
            entry = ttk.Entry(fr_params, textvariable=var, font=font_entry)
            entry.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=6)
            return entry

        self.v_symbol = tk.StringVar()
        self.v_leverage = tk.StringVar()
        self.v_entry_offset = tk.StringVar()
        self.v_tp = tk.StringVar()
        self.v_sl = tk.StringVar()

        add_row(0, "币种 Symbol", self.v_symbol)
        add_row(1, "杠杆 Leverage", self.v_leverage)
        add_row(2, "建仓偏移 Entry (%, 距 mid)", self.v_entry_offset)
        add_row(3, "止盈 TP (%)", self.v_tp)
        add_row(4, "止损 SL (%)", self.v_sl)

        self.btn_init = tk.Button(
            self.root,
            text="初始化  Initialize",
            bg="#1971C2",
            fg="white",
            activebackground="#155A9B",
            activeforeground="white",
            disabledforeground=COLOR_DISABLED_FG,
            font=self._font(12, "bold"),
            relief="flat",
            bd=0,
            cursor="hand2",
            height=2,
            command=self._on_init,
        )
        self.btn_init.pack(fill="x", padx=12, pady=(4, 4))

        fr_btn = tk.Frame(self.root, bd=0)
        fr_btn.pack(fill="x", padx=12, pady=(4, 4))
        fr_btn.columnconfigure(0, weight=1)
        fr_btn.columnconfigure(1, weight=1)

        self.btn_buy = tk.Button(
            fr_btn,
            text="做多  BUY",
            bg=COLOR_BUY,
            fg="white",
            activebackground=COLOR_BUY_ACTIVE,
            activeforeground="white",
            disabledforeground=COLOR_DISABLED_FG,
            font=font_button,
            relief="flat",
            bd=0,
            cursor="hand2",
            height=2,
            command=lambda: self._on_click("BUY"),
        )
        self.btn_buy.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.btn_sell = tk.Button(
            fr_btn,
            text="做空  SELL",
            bg=COLOR_SELL,
            fg="white",
            activebackground=COLOR_SELL_ACTIVE,
            activeforeground="white",
            disabledforeground=COLOR_DISABLED_FG,
            font=font_button,
            relief="flat",
            bd=0,
            cursor="hand2",
            height=2,
            command=lambda: self._on_click("SELL"),
        )
        self.btn_sell.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.v_status = tk.StringVar(value="就绪 · 请先点击「初始化」")
        self.lbl_status = tk.Label(
            self.root,
            textvariable=self.v_status,
            font=font_status,
            anchor="w",
            padx=12,
            pady=8,
            fg=COLOR_IDLE,
            justify="left",
            wraplength=590,
        )
        self.lbl_status.pack(fill="x", padx=12, pady=(4, 12))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_config_data(self) -> dict:
        if not CONFIG_PATH.exists():
            return {}
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config_data(self, data: dict) -> None:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def _load_inputs_from_config(self) -> None:
        d = self._load_config_data()
        self.v_api_key.set(str(d.get("api_key", "")))
        self.v_api_secret.set(str(d.get("api_secret", "")))
        self.v_symbol.set(str(d.get("symbol", "BTCUSDT")))
        self.v_leverage.set(str(d.get("leverage", 10)))
        self.v_entry_offset.set(str(d.get("entry_offset_pct", "0.05")))
        self.v_tp.set(str(d.get("take_profit_pct", "0.3")))
        self.v_sl.set(str(d.get("stop_loss_pct", "0.3")))

    def _on_toggle_show_api(self) -> None:
        show = "" if self.v_show_api.get() else "*"
        self.ent_api_key.config(show=show)
        self.ent_api_secret.config(show=show)

    def _validate_inputs(self) -> tuple[str, str, str, int, str, str, str]:
        api_key = self.v_api_key.get().strip()
        api_secret = self.v_api_secret.get().strip()
        if not api_key or not api_secret:
            raise ValueError("API Key / Secret 不能为空")
        symbol = self.v_symbol.get().strip().upper()
        if not symbol:
            raise ValueError("symbol 不能为空")
        lev_str = self.v_leverage.get().strip()
        try:
            leverage = int(lev_str)
        except ValueError:
            raise ValueError(f"leverage 必须是整数: {lev_str!r}")
        entry = self.v_entry_offset.get().strip()
        tp = self.v_tp.get().strip()
        sl = self.v_sl.get().strip()
        try:
            Decimal(entry)
            Decimal(tp)
            Decimal(sl)
        except Exception:
            raise ValueError(f"百分比必须是数字: entry={entry!r} tp={tp!r} sl={sl!r}")
        return api_key, api_secret, symbol, leverage, entry, tp, sl

    def _on_click(self, side: str) -> None:
        if not self._trading_lock.acquire(blocking=False):
            return

        try:
            api_key, api_secret, symbol, leverage, entry, tp, sl = self._validate_inputs()
        except Exception as exc:
            self._set_status(f"参数错误: {exc}", COLOR_ERROR)
            self._trading_lock.release()
            return

        if (
            self._cached_symbol != symbol
            or self._cached_filters is None
            or self._cached_balance is None
            or self._cached_client is None
        ):
            self._set_status(
                f"未初始化或 symbol 已改变；请先点击「初始化」"
                f"  (cached={self._cached_symbol!r}  current={symbol!r})",
                COLOR_ERROR,
            )
            self._trading_lock.release()
            return

        try:
            data = self._load_config_data()
            data.update(
                {
                    "api_key": api_key,
                    "api_secret": api_secret,
                    "symbol": symbol,
                    "side": side,
                    "leverage": leverage,
                    "entry_offset_pct": entry,
                    "take_profit_pct": tp,
                    "stop_loss_pct": sl,
                }
            )
            self._save_config_data(data)
        except Exception as exc:
            self._set_status(f"配置保存失败: {exc}", COLOR_ERROR)
            self._trading_lock.release()
            return

        self._set_buttons_state(False)
        self._set_status(
            f"下单中…  {side}  {symbol}  {leverage}x  "
            f"entry={entry}%  TP={tp}%  SL={sl}%",
            COLOR_BUSY,
        )
        threading.Thread(target=self._do_trade, daemon=True).start()

    def _do_trade(self) -> None:
        try:
            config = TraderConfig.load(CONFIG_PATH)
            trader = BinanceFuturesTrader(config, client=self._cached_client)
            trader.inject_filters(self._cached_filters)
            trader.inject_balance(self._cached_balance)
            result = trader.execute()
            self.root.after(0, self._on_done, result, None)
        except Exception as exc:
            self.root.after(0, self._on_done, None, exc)

    def _on_done(self, result, exc) -> None:
        if exc is None and result is not None:
            d = result.to_dict()
            msg = (
                f"成功 · mid={d['latest_mid_price']}  entry={d['entry_price']}  "
                f"qty={d['filled_quantity']}  SL={d['stop_loss_price']}  "
                f"TP={d['take_profit_price']}  status={d['entry_order_status']}"
            )
            color = COLOR_SUCCESS
            if d.get("warnings"):
                msg = "部分成功 · " + msg + " · warnings=" + str(d.get("warnings"))
                color = COLOR_WARN
            self._set_status(msg, color)
        else:
            self._set_status(f"失败: {exc}", COLOR_ERROR)

        self._set_buttons_state(True)
        try:
            self._trading_lock.release()
        except RuntimeError:
            pass

    def _set_buttons_state(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.btn_buy.config(state=state)
        self.btn_sell.config(state=state)
        self.btn_init.config(state=state)

    def _set_status(self, text: str, fg: str = COLOR_IDLE) -> None:
        self.v_status.set(text)
        self.lbl_status.config(fg=fg)

    def _on_init(self) -> None:
        if not self._trading_lock.acquire(blocking=False):
            return

        try:
            api_key, api_secret, symbol, leverage, entry, tp, sl = self._validate_inputs()
        except Exception as exc:
            self._set_status(f"参数错误: {exc}", COLOR_ERROR)
            self._trading_lock.release()
            return

        try:
            data = self._load_config_data()
            data.update(
                {
                    "api_key": api_key,
                    "api_secret": api_secret,
                    "symbol": symbol,
                    "side": data.get("side", "BUY"),
                    "leverage": leverage,
                    "entry_offset_pct": entry,
                    "take_profit_pct": tp,
                    "stop_loss_pct": sl,
                }
            )
            self._save_config_data(data)
        except Exception as exc:
            self._set_status(f"配置保存失败: {exc}", COLOR_ERROR)
            self._trading_lock.release()
            return

        self._cached_symbol = None
        self._cached_filters = None
        self._cached_balance = None
        self._cached_client = None

        self._set_buttons_state(False)
        self._set_status(f"初始化中…  {symbol}  {leverage}x", COLOR_BUSY)
        threading.Thread(
            target=self._do_init, args=(symbol,), daemon=True
        ).start()

    def _do_init(self, symbol: str) -> None:
        try:
            config = TraderConfig.load(CONFIG_PATH)
            trader = BinanceFuturesTrader(config)
            filters, balance, lev_resp = trader.init_session()
            self.root.after(
                0,
                self._on_init_done,
                symbol,
                filters,
                balance,
                lev_resp,
                trader.client,
                None,
            )
        except Exception as exc:
            self.root.after(
                0, self._on_init_done, symbol, None, None, None, None, exc
            )

    def _on_init_done(self, symbol, filters, balance, lev_resp, client, exc) -> None:
        if exc is None and filters is not None and balance is not None:
            self._cached_symbol = symbol
            self._cached_filters = filters
            self._cached_balance = balance
            self._cached_client = client
            self._set_status(
                f"已初始化 · {symbol}  杠杆={lev_resp.get('leverage')}x  "
                f"balance={balance} USD  tick={filters.tick_size}  "
                f"step={filters.step_size}  minNotional={filters.min_notional}",
                COLOR_SUCCESS,
            )
        else:
            self._set_status(f"初始化失败: {exc}", COLOR_ERROR)
        self._set_buttons_state(True)
        try:
            self._trading_lock.release()
        except RuntimeError:
            pass

    def _on_close(self) -> None:
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except Exception:
        pass
    TraderGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
