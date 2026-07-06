from __future__ import annotations

import re
from typing import NamedTuple


class MatchFlag(NamedTuple):
    match: str
    category: str
    span_start: int
    span_end: int


class CommandDetector:
    """M278 Layer A — output-scan: recall-biased command detector.

    Scans LLM output text for trading commands. Recall-biased:
    FN = M278 violation (unsafe), FP = operator adhudicates.

    Category taxonomy:
      - command_verb_en     English imperative verb
      - command_verb_ru     Russian imperative verb
      - direction_word      long/short (standalone)
      - numeric_direction   amount + ticker + direction pattern
      - leverage            Nx leverage pattern
    """

    _COMMAND_VERBS_EN: frozenset[str] = frozenset(
        {
            "buy",
            "sell",
            "close",
            "exit",
            "enter",
            "cancel",
            "order",
            "set",
            "place",
            "submit",
            "reduce",
            "cut",
            "trim",
            "add",
            "increase",
            "scale",
            "move",
            "trail",
            "replace",
            "amend",
            "open",
            "go",
            "take",
        }
    )

    _COMMAND_VERBS_RU: frozenset[str] = frozenset(
        {
            "купи",
            "купить",
            "продай",
            "продать",
            "закрой",
            "закрыть",
            "отмени",
            "отменить",
            "выставь",
            "выставить",
            "поставь",
            "поставить",
            "сократи",
            "уменьши",
            "увеличь",
            "добавь",
            "передвинь",
            "подтяни",
            "хеджируй",
            "захеджируй",
            "открой",
            "открыть",
        }
    )

    _DIRECTION_WORDS: frozenset[str] = frozenset({"long", "short"})

    _EXCLUDED_COMPOUNDS: frozenset[str] = frozenset(
        {
            "shortlist",
            "short-term",
            "shorting",
            "shortcut",
            "shortest",
            "shorter",
            "long-term",
            "longonly",
            "longest",
            "longitude",
            "longing",
            "longtime",
            "orderbook",
            "orderflow",
            "order-type",
            "order_type",
            "buyback",
            "buyout",
            "buyer",
            "buyers",
            "buying",
            "seller",
            "sellers",
            "selloff",
            "sellside",
            "selling",
            "setup",
            "setups",
            "set-up",
            "stop-loss",
            "stoplimit",
            "stopword",
        }
    )

    _TOKEN_RE: re.Pattern = re.compile(r"[a-zA-Zа-яА-ЯёЁ]+(?:[-][a-zA-Zа-яА-ЯёЁ]+)*")

    _NUMERIC_DIRECTION_RE: re.Pattern = re.compile(
        r"(?i)"
        r"(?:(?:\d+[.]?\d*)\s+[A-Z]{2,10}(?:-[A-Z]{2,6})?\s+(?:long|short))"
        r"|"
        r"(?:(?:long|short)\s+(?:\d+[.]?\d*)\s+[A-Z]{2,10}(?:-[A-Z]{2,6})?)"
    )

    _LEVERAGE_RE: re.Pattern = re.compile(
        r"(?i)"
        r"(?:\b\d+\s*x\s+(?:leverage|плеч[оаеу]|плечи)\b)"
        r"|"
        r"(?:\b\d+x(?!\w))"
    )

    def scan(self, text: str) -> list[MatchFlag]:
        flags: list[MatchFlag] = []

        # 1. Token-level: verbs + direction words
        for m in self._TOKEN_RE.finditer(text):
            token = m.group()
            token_lower = token.lower()
            span = (m.start(), m.end())

            if token_lower in self._EXCLUDED_COMPOUNDS:
                continue

            if token_lower in self._COMMAND_VERBS_EN:
                cat = "command_verb_en"
            elif token_lower in self._COMMAND_VERBS_RU:
                cat = "command_verb_ru"
            elif token_lower in self._DIRECTION_WORDS:
                cat = "direction_word"
            else:
                continue

            flags.append(
                MatchFlag(
                    match=token_lower,
                    category=cat,
                    span_start=span[0],
                    span_end=span[1],
                )
            )

        # 2. Numeric direction: "0.5 BTC long", "short 100 SOL"
        for m in self._NUMERIC_DIRECTION_RE.finditer(text):
            flags.append(
                MatchFlag(
                    match=m.group().strip(),
                    category="numeric_direction",
                    span_start=m.start(),
                    span_end=m.end(),
                )
            )

        # 3. Leverage: "2x ETH", "3x leverage"
        for m in self._LEVERAGE_RE.finditer(text):
            flags.append(
                MatchFlag(
                    match=m.group().strip(),
                    category="leverage",
                    span_start=m.start(),
                    span_end=m.end(),
                )
            )

        return flags
