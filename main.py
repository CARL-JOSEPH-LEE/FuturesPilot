from __future__ import annotations

import io
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path


def _force_utf8_io() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                buffer = getattr(stream, "buffer", None)
                if buffer is not None:
                    wrapped = io.TextIOWrapper(
                        buffer, encoding="utf-8", errors="replace", line_buffering=True
                    )
                    setattr(sys, stream_name, wrapped)
        except Exception:
            pass
    if sys.platform == "win32":
        try:
            os.system("chcp 65001 >nul")
        except Exception:
            pass


_force_utf8_io()


from trader import (
    BinanceFuturesTrader,
    ConfigError,
    OrderError,
    PrecheckError,
    TraderConfig,
    TraderError,
)


def _setup_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"trade_{datetime.now():%Y%m%d_%H%M%S}.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(logging.INFO)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return log_path


def main() -> int:
    root = Path(__file__).parent
    log_path = _setup_logging(root / "logs")
    log = logging.getLogger("main")
    log.info("日志写入: %s", log_path)

    try:
        config = TraderConfig.load(root / "config.json")
    except ConfigError as exc:
        log.error("配置错误: %s", exc)
        return 2

    try:
        result = BinanceFuturesTrader(config).execute()
    except PrecheckError as exc:
        log.error("前置检查失败: %s", exc)
        return 3
    except OrderError as exc:
        log.error("下单失败: %s", exc)
        return 4
    except TraderError as exc:
        log.error("交易错误: %s", exc)
        return 5
    except KeyboardInterrupt:
        log.warning("被用户中断")
        return 130
    except Exception as exc:
        log.exception("未预期错误: %s", exc)
        return 1

    print()
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
