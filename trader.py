from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_UP, Decimal, getcontext
from pathlib import Path
from typing import Optional

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

getcontext().prec = 50

logger = logging.getLogger("trader")


SUPPORTED_QUOTES: tuple[str, ...] = ("USDT", "USDC", "BUSD", "FDUSD")
ENTRY_SIDES: tuple[str, ...] = ("BUY", "SELL")

BALANCE_USAGE_PCT = Decimal("99")
BUFFER_PCT = Decimal("1")
WORKING_TYPE = "CONTRACT_PRICE"
TP_TRIGGER_OFFSET_FROM_LIMIT_PCT = Decimal("0.05")
ENTRY_TIME_IN_FORCE = "GTX"
RECV_WINDOW = 5000
REQUEST_TIMEOUT_SEC = 15
REQUEST_RETRY_ATTEMPTS = 3
REQUEST_RETRY_BASE_DELAY_SEC = 0.6

NON_RETRYABLE_API_CODES: frozenset[int] = frozenset(
    {
        -1013,
        -1102,
        -1111,
        -1116,
        -1117,
        -1130,
        -2010,
        -2013,
        -2014,
        -2015,
        -2018,
        -2019,
        -2021,
        -2022,
        -4046,
        -4061,
        -4131,
        -4164,
    }
)


class TraderError(RuntimeError):
    pass


class ConfigError(TraderError):
    pass


class PrecheckError(TraderError):
    pass


class OrderError(TraderError):
    pass


@dataclass(frozen=True)
class TraderConfig:
    api_key: str
    api_secret: str
    symbol: str
    side: str
    leverage: int
    entry_offset_pct: Decimal
    take_profit_pct: Decimal
    stop_loss_pct: Decimal

    @classmethod
    def load(cls, path: Path) -> "TraderConfig":
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc

        required = ("api_key", "api_secret", "symbol", "side", "leverage",
                    "entry_offset_pct", "take_profit_pct", "stop_loss_pct")
        for key in required:
            if key not in data:
                raise ConfigError(f"缺少必需配置项: {key}")

        cfg = cls(
            api_key=str(data["api_key"]).strip(),
            api_secret=str(data["api_secret"]).strip(),
            symbol=str(data["symbol"]).strip().upper(),
            side=str(data["side"]).strip().upper(),
            leverage=int(data["leverage"]),
            entry_offset_pct=Decimal(str(data["entry_offset_pct"])),
            take_profit_pct=Decimal(str(data["take_profit_pct"])),
            stop_loss_pct=Decimal(str(data["stop_loss_pct"])),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.api_key or not self.api_secret:
            raise ConfigError("api_key 与 api_secret 不能为空")
        if not self.symbol.endswith(SUPPORTED_QUOTES):
            raise ConfigError(
                f"symbol {self.symbol!r} 必须以 {SUPPORTED_QUOTES} 之一结尾"
            )
        if self.side not in ENTRY_SIDES:
            raise ConfigError(f"side 必须为 BUY 或 SELL，当前 {self.side!r}")
        if not 1 <= self.leverage <= 125:
            raise ConfigError(f"leverage 需在 1..125 之间，当前 {self.leverage}")
        if not (Decimal("0") < self.entry_offset_pct <= Decimal("100")):
            raise ConfigError(f"entry_offset_pct 非法：{self.entry_offset_pct}")
        if not (Decimal("0") < self.take_profit_pct <= Decimal("100")):
            raise ConfigError(f"take_profit_pct 非法：{self.take_profit_pct}")
        if not (Decimal("0") < self.stop_loss_pct <= Decimal("100")):
            raise ConfigError(f"stop_loss_pct 非法：{self.stop_loss_pct}")
        if self.take_profit_pct <= self.entry_offset_pct + TP_TRIGGER_OFFSET_FROM_LIMIT_PCT:
            raise ConfigError(
                f"take_profit_pct ({self.take_profit_pct}%) 必须大于 "
                f"entry_offset_pct ({self.entry_offset_pct}%) + "
                f"TP_TRIGGER_OFFSET_FROM_LIMIT_PCT ({TP_TRIGGER_OFFSET_FROM_LIMIT_PCT}%) "
                "否则止盈触发价会穿越当前价导致立即触发"
            )

    @property
    def close_side(self) -> str:
        return "SELL" if self.side == "BUY" else "BUY"


@dataclass(frozen=True)
class SymbolFilters:
    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    max_qty: Decimal
    min_notional: Decimal
    price_precision: int
    quantity_precision: int


@dataclass
class TradeResult:
    symbol: str
    side: str
    leverage: int
    available_balance: Decimal
    latest_mid_price: Decimal
    entry_price: Decimal
    filled_quantity: Decimal
    notional: Decimal
    stop_loss_price: Decimal
    take_profit_price: Decimal
    entry_order: dict
    stop_loss_order: dict
    take_profit_order: dict
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "leverage": self.leverage,
            "available_balance": str(self.available_balance),
            "latest_mid_price": str(self.latest_mid_price),
            "entry_price": str(self.entry_price),
            "filled_quantity": str(self.filled_quantity),
            "notional": str(self.notional),
            "stop_loss_price": str(self.stop_loss_price),
            "take_profit_price": str(self.take_profit_price),
            "entry_order_id": self.entry_order.get("orderId"),
            "entry_order_status": self.entry_order.get("status"),
            "stop_loss_order_id": (
                self.stop_loss_order.get("algoId") or self.stop_loss_order.get("orderId")
            ),
            "take_profit_order_id": (
                self.take_profit_order.get("algoId") or self.take_profit_order.get("orderId")
            ),
            "warnings": list(self.warnings),
        }


def _round_to_step(value: Decimal, step: Decimal, mode: str) -> Decimal:
    if step <= 0:
        return value
    quotient = (value / step).quantize(Decimal("1"), rounding=mode)
    return (quotient * step).quantize(step, rounding=mode)


def _format_decimal(value: Decimal, precision: int) -> str:
    if precision < 0:
        precision = 0
    quant = Decimal(1).scaleb(-precision) if precision > 0 else Decimal(1)
    return f"{value.quantize(quant, rounding=ROUND_DOWN):.{precision}f}"


class BinanceFuturesTrader:
    def __init__(
        self, config: TraderConfig, client: Optional[Client] = None
    ) -> None:
        self.config = config
        if client is not None:
            self.client = client
        else:
            self.client = Client(
                api_key=config.api_key,
                api_secret=config.api_secret,
                requests_params={"timeout": REQUEST_TIMEOUT_SEC},
                ping=False,
            )
            self.client.RECV_WINDOW = RECV_WINDOW
        self._symbol_filters: Optional[SymbolFilters] = None
        self._available_balance: Optional[Decimal] = None

    @property
    def filters(self) -> SymbolFilters:
        if self._symbol_filters is None:
            raise TraderError("Symbol filters not initialised yet")
        return self._symbol_filters

    @property
    def available_balance(self) -> Decimal:
        if self._available_balance is None:
            raise TraderError("Available balance not initialised yet")
        return self._available_balance

    def inject_filters(self, filters: SymbolFilters) -> None:
        self._symbol_filters = filters

    def inject_balance(self, balance: Decimal) -> None:
        self._available_balance = balance

    def execute(self) -> TradeResult:
        cfg = self.config

        logger.info("=" * 64)
        logger.info("Binance USDT 永续 · Maker 限价开仓 + 算法 SL/TP")
        logger.info(
            "symbol=%s side=%s leverage=%dx entry_offset=%s%% TP=%s%% SL=%s%%",
            cfg.symbol,
            cfg.side,
            cfg.leverage,
            cfg.entry_offset_pct,
            cfg.take_profit_pct,
            cfg.stop_loss_pct,
        )
        logger.info("=" * 64)

        if self._symbol_filters is None:
            raise PrecheckError("精度未注入；请先点击 GUI「初始化」")
        if self._available_balance is None:
            raise PrecheckError("可用保证金未注入；请先点击 GUI「初始化」")

        logger.info(
            "已注入 · balance=%s | tick=%s step=%s min_qty=%s min_notional=%s",
            self.available_balance,
            self.filters.tick_size,
            self.filters.step_size,
            self.filters.min_qty,
            self.filters.min_notional,
        )

        mid = self._fetch_latest_mid_price()
        entry_limit = self._compute_entry_limit_price(mid)
        quantity = self._compute_quantity(self.available_balance, entry_limit)
        sl_price = self._compute_sl_price(entry_limit)
        tp_price = self._compute_tp_price(entry_limit)
        tp_trigger = self._compute_tp_trigger_price(tp_price)

        logger.info(
            "最新价 mid=%s (买一卖一中点) | maker 挂单价=%s (距 mid %s%%) | 数量=%s (名义≈%s)",
            mid,
            entry_limit,
            cfg.entry_offset_pct,
            quantity,
            quantity * entry_limit,
        )
        logger.info(
            "止损触发=%s (距入场 %s%%) | 止盈挂单=%s (距入场 %s%%) | 止盈触发=%s (距挂单 %s%%)",
            sl_price,
            cfg.stop_loss_pct,
            tp_price,
            cfg.take_profit_pct,
            tp_trigger,
            TP_TRIGGER_OFFSET_FROM_LIMIT_PCT,
        )

        warnings: list[str] = []

        entry_order = self._place_maker_entry(entry_limit, quantity)
        entry_status = entry_order.get("status")
        logger.info(
            "Maker 入场单提交: orderId=%s status=%s",
            entry_order.get("orderId"),
            entry_status,
        )
        if entry_status == "EXPIRED":
            warnings.append(
                "Maker 入场单被 GTX 立即拒绝（挂单价会成为 taker）；"
                "未提交止损/止盈。请把 entry_offset_pct 调大或手动重试"
            )

        sl_order: dict
        tp_order: dict
        if entry_status == "EXPIRED":
            sl_order = {"algoId": None, "orderId": None, "skipped": True}
            tp_order = {"algoId": None, "orderId": None, "skipped": True}
        else:
            try:
                sl_order = self._place_stop_loss(sl_price, quantity)
            except Exception as exc:
                warnings.append(f"止损下单失败：{exc}")
                logger.error("止损下单失败: %s", exc, exc_info=True)
                sl_order = {"algoId": None, "orderId": None, "error": str(exc)}

            try:
                tp_order = self._place_take_profit(tp_trigger, tp_price, quantity)
            except Exception as exc:
                warnings.append(f"止盈下单失败：{exc}")
                logger.error("止盈下单失败: %s", exc, exc_info=True)
                tp_order = {"algoId": None, "orderId": None, "error": str(exc)}

        result = TradeResult(
            symbol=cfg.symbol,
            side=cfg.side,
            leverage=cfg.leverage,
            available_balance=self.available_balance,
            latest_mid_price=mid,
            entry_price=entry_limit,
            filled_quantity=quantity,
            notional=entry_limit * quantity,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            entry_order=entry_order,
            stop_loss_order=sl_order,
            take_profit_order=tp_order,
            warnings=warnings,
        )

        logger.info("=" * 64)
        logger.info("下单完成")
        for key, value in result.to_dict().items():
            logger.info("  %s = %s", key, value)
        logger.info("=" * 64)
        return result

    def _sync_time(self) -> None:
        try:
            server_time = int(self.client.futures_time()["serverTime"])
            local_time = int(time.time() * 1000)
            offset = server_time - local_time
            self.client.timestamp_offset = offset
            logger.debug("Time synced, offset=%dms", offset)
        except Exception as exc:
            logger.warning("时间同步失败（忽略）：%s", exc)

    def set_leverage(self) -> dict:
        result = self._retry(
            self.client.futures_change_leverage,
            symbol=self.config.symbol,
            leverage=self.config.leverage,
        )
        logger.info("杠杆已设置: %s", result)
        return result

    def init_session(self) -> tuple[SymbolFilters, Decimal, dict]:
        logger.info("初始化会话: %s", self.config.symbol)
        self._sync_time()
        leverage_resp = self.set_leverage()
        filters = self.fetch_symbol_filters()
        self.inject_filters(filters)
        logger.info(
            "精度已加载 · tick=%s step=%s min_qty=%s min_notional=%s "
            "price_prec=%d qty_prec=%d",
            filters.tick_size,
            filters.step_size,
            filters.min_qty,
            filters.min_notional,
            filters.price_precision,
            filters.quantity_precision,
        )
        balance = self._fetch_available_balance()
        self.inject_balance(balance)
        logger.info("可用保证金 · %s USD 等值", balance)
        return filters, balance, leverage_resp

    def fetch_symbol_filters(self) -> SymbolFilters:
        info = self._retry(self.client.futures_exchange_info)
        for sym in info.get("symbols", []):
            if sym.get("symbol") != self.config.symbol:
                continue
            tick_size = step_size = min_qty = max_qty = min_notional = None
            for flt in sym.get("filters", []):
                ftype = flt.get("filterType")
                if ftype == "PRICE_FILTER":
                    tick_size = Decimal(flt["tickSize"])
                elif ftype == "LOT_SIZE":
                    step_size = Decimal(flt["stepSize"])
                    min_qty = Decimal(flt["minQty"])
                    max_qty = Decimal(flt["maxQty"])
                elif ftype == "MARKET_LOT_SIZE":
                    if step_size is None:
                        step_size = Decimal(flt["stepSize"])
                    if min_qty is None:
                        min_qty = Decimal(flt["minQty"])
                    if max_qty is None:
                        max_qty = Decimal(flt["maxQty"])
                elif ftype == "MIN_NOTIONAL":
                    min_notional = Decimal(flt.get("notional", flt.get("minNotional", "0")))
            if tick_size is None or step_size is None:
                raise PrecheckError(f"{self.config.symbol} 缺少必要过滤器")
            return SymbolFilters(
                tick_size=tick_size,
                step_size=step_size,
                min_qty=min_qty or Decimal("0"),
                max_qty=max_qty or Decimal("0"),
                min_notional=min_notional or Decimal("0"),
                price_precision=int(sym.get("pricePrecision", 8)),
                quantity_precision=int(sym.get("quantityPrecision", 8)),
            )
        raise PrecheckError(f"未找到合约 {self.config.symbol}")

    def _fetch_available_balance(self) -> Decimal:
        info = self._retry(self.client.futures_account)
        avail = info.get("availableBalance")
        if avail is None:
            raise PrecheckError("API 未返回 availableBalance")
        return Decimal(str(avail))

    def _fetch_latest_mid_price(self) -> Decimal:
        data = self._retry(
            self.client.futures_orderbook_ticker, symbol=self.config.symbol
        )
        if isinstance(data, list):
            data = data[0] if data else {}
        bid = Decimal(str(data.get("bidPrice", "0")))
        ask = Decimal(str(data.get("askPrice", "0")))
        if bid <= 0 or ask <= 0 or ask < bid:
            raise PrecheckError(f"无效的 bookTicker 数据: {data}")
        return (bid + ask) / Decimal("2")

    def _compute_quantity(self, balance: Decimal, price: Decimal) -> Decimal:
        if balance <= 0:
            raise PrecheckError("可用余额为 0，无法下单")
        usable = balance * BALANCE_USAGE_PCT / Decimal("100")
        usable *= (Decimal("100") - BUFFER_PCT) / Decimal("100")
        notional = usable * Decimal(self.config.leverage)
        raw_qty = notional / price
        qty = _round_to_step(raw_qty, self.filters.step_size, ROUND_DOWN)

        if qty < self.filters.min_qty:
            raise PrecheckError(
                f"计算数量 {qty} 小于 minQty {self.filters.min_qty}，余额或杠杆不足"
            )
        if self.filters.max_qty > 0 and qty > self.filters.max_qty:
            qty = _round_to_step(self.filters.max_qty, self.filters.step_size, ROUND_DOWN)
            logger.warning("数量被 maxQty 限制为 %s", qty)
        if self.filters.min_notional > 0 and qty * price < self.filters.min_notional:
            raise PrecheckError(
                f"名义本金 {qty * price} 小于 minNotional {self.filters.min_notional}"
            )
        return qty

    def _compute_entry_limit_price(self, mark: Decimal) -> Decimal:
        ratio = self.config.entry_offset_pct / Decimal("100")
        if self.config.side == "BUY":
            raw = mark * (Decimal("1") - ratio)
            return _round_to_step(raw, self.filters.tick_size, ROUND_DOWN)
        raw = mark * (Decimal("1") + ratio)
        return _round_to_step(raw, self.filters.tick_size, ROUND_UP)

    def _place_maker_entry(self, price: Decimal, quantity: Decimal) -> dict:
        params = {
            "symbol": self.config.symbol,
            "side": self.config.side,
            "type": "LIMIT",
            "timeInForce": ENTRY_TIME_IN_FORCE,
            "price": _format_decimal(price, self.filters.price_precision),
            "quantity": _format_decimal(quantity, self.filters.quantity_precision),
            "newOrderRespType": "RESULT",
        }
        logger.info("提交 Maker LIMIT 入场单 (%s): %s", ENTRY_TIME_IN_FORCE, params)
        return self._retry(self.client.futures_create_order, **params)

    def _compute_sl_price(self, entry: Decimal) -> Decimal:
        ratio = self.config.stop_loss_pct / Decimal("100")
        if self.config.side == "BUY":
            raw = entry * (Decimal("1") - ratio)
            return _round_to_step(raw, self.filters.tick_size, ROUND_DOWN)
        raw = entry * (Decimal("1") + ratio)
        return _round_to_step(raw, self.filters.tick_size, ROUND_UP)

    def _compute_tp_price(self, entry: Decimal) -> Decimal:
        ratio = self.config.take_profit_pct / Decimal("100")
        if self.config.side == "BUY":
            raw = entry * (Decimal("1") + ratio)
            return _round_to_step(raw, self.filters.tick_size, ROUND_UP)
        raw = entry * (Decimal("1") - ratio)
        return _round_to_step(raw, self.filters.tick_size, ROUND_DOWN)

    def _compute_tp_trigger_price(self, tp_limit: Decimal) -> Decimal:
        ratio = TP_TRIGGER_OFFSET_FROM_LIMIT_PCT / Decimal("100")
        if self.config.side == "BUY":
            raw = tp_limit * (Decimal("1") - ratio)
            return _round_to_step(raw, self.filters.tick_size, ROUND_DOWN)
        raw = tp_limit * (Decimal("1") + ratio)
        return _round_to_step(raw, self.filters.tick_size, ROUND_UP)

    def _place_stop_loss(self, sl_price: Decimal, quantity: Decimal) -> dict:
        params = {
            "algoType": "CONDITIONAL",
            "symbol": self.config.symbol,
            "side": self.config.close_side,
            "type": "STOP_MARKET",
            "triggerPrice": _format_decimal(sl_price, self.filters.price_precision),
            "quantity": _format_decimal(quantity, self.filters.quantity_precision),
            "reduceOnly": "true",
            "workingType": WORKING_TYPE,
            "newOrderRespType": "RESULT",
        }
        logger.info("提交止损 algoOrder STOP_MARKET (reduceOnly): %s", params)
        return self._retry(self._create_algo_order, params)

    def _place_take_profit(
        self,
        trigger_price: Decimal,
        limit_price: Decimal,
        quantity: Decimal,
    ) -> dict:
        params = {
            "algoType": "CONDITIONAL",
            "symbol": self.config.symbol,
            "side": self.config.close_side,
            "type": "TAKE_PROFIT",
            "triggerPrice": _format_decimal(trigger_price, self.filters.price_precision),
            "price": _format_decimal(limit_price, self.filters.price_precision),
            "quantity": _format_decimal(quantity, self.filters.quantity_precision),
            "timeInForce": "GTC",
            "reduceOnly": "true",
            "workingType": WORKING_TYPE,
            "newOrderRespType": "RESULT",
        }
        logger.info("提交止盈 algoOrder TAKE_PROFIT: %s", params)
        return self._retry(self._create_algo_order, params)

    def _create_algo_order(self, params: dict) -> dict:
        return self.client._request_futures_api(
            "post", "algoOrder", True, data=dict(params)
        )

    def fetch_available_balance(self) -> Decimal:
        return self._fetch_available_balance()

    def _retry(self, fn, *args, **kwargs):
        last_exc: Optional[BaseException] = None
        for attempt in range(1, REQUEST_RETRY_ATTEMPTS + 1):
            try:
                return fn(*args, **kwargs)
            except BinanceAPIException as exc:
                last_exc = exc
                if exc.code == -1021:
                    logger.warning("时间戳错误，重新同步（attempt=%d）", attempt)
                    self._sync_time()
                    continue
                if exc.code in NON_RETRYABLE_API_CODES:
                    raise
                logger.warning(
                    "Binance API 错误 attempt=%d/%d code=%s msg=%s",
                    attempt,
                    REQUEST_RETRY_ATTEMPTS,
                    exc.code,
                    exc.message,
                )
            except BinanceRequestException as exc:
                last_exc = exc
                logger.warning(
                    "Binance 请求错误 attempt=%d/%d: %s",
                    attempt,
                    REQUEST_RETRY_ATTEMPTS,
                    exc,
                )
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "网络或未知错误 attempt=%d/%d: %s",
                    attempt,
                    REQUEST_RETRY_ATTEMPTS,
                    exc,
                )
            time.sleep(REQUEST_RETRY_BASE_DELAY_SEC * attempt)
        assert last_exc is not None
        raise last_exc
