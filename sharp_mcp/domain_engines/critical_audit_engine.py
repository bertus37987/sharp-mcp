"""Adversarial, Tokenizer-Backed Critical Audit Engine for Sharp MCP."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .luau_audit_engine import LuauAuditSnapshotEngine


_AUDIT_HMAC_SECRET: bytes = secrets.token_bytes(32)


SEVERITIES: Tuple[str, ...] = ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO")
VERDICTS: Tuple[str, ...] = ("SHIP", "FIX_FIRST", "REJECT")

SEVERITY_PENALTIES: Dict[str, int] = {
    "BLOCKER": 30,
    "CRITICAL": 15,
    "MAJOR": 7,
    "MINOR": 2,
    "INFO": 0,
}

LUAU_KEYWORDS: Set[str] = {
    "and", "break", "do", "else", "elseif", "end", "false", "for", "function",
    "if", "in", "local", "nil", "not", "or", "repeat", "return", "then",
    "true", "until", "while",
}

DEPRECATED_SCHEDULER_CALLS: Dict[str, str] = {
    "wait": "task.wait",
    "spawn": "task.spawn",
    "delay": "task.delay",
}

DATASTORE_AND_MARKETPLACE_METHODS: Set[str] = {
    "GetAsync",
    "SetAsync",
    "UpdateAsync",
    "RemoveAsync",
    "IncrementAsync",
    "ListKeysAsync",
    "GetSortedAsync",
    "UserOwnsGamePassAsync",
    "GetProductInfoAsync",
    "GetProductInfo",
    "PlayerOwnsAssetAsync",
    "PromptProductPurchase",
    "PromptGamePassPurchase",
}

CLIENT_TRUSTED_PARAM_NAMES: Set[str] = {
    "damage", "dmg", "amount", "gold", "coins", "cash", "gems", "currency",
    "xp", "exp", "reward", "price", "cost", "isadmin", "admin", "role",
    "winner", "score", "health", "hp", "level", "userid", "ownerid",
}

VALIDATION_IDENTIFIERS: Set[str] = {
    "typeof", "type", "assert", "SafeRemoteGateway", "ValidateField",
    "ValidateArgs", "RegisterReliable", "RegisterUnreliable", "isfinite",
    "tonumber", "validate", "isValid", "Validate", "VerifyArgs", "VerifyPayload",
}

SERVER_CATALOG_TABLES: Set[str] = {
    "CATALOG", "Catalog", "PRICES", "Prices", "ITEMS", "Items",
    "WEAPONS", "Weapons", "SHOP_CATALOG", "SHOP_ITEMS", "SKILL_DATA",
}

RATE_LIMIT_IDENTIFIERS: Set[str] = {
    "ConsumeRateLimit", "rateLimit", "RateLimit", "RateLimiter", "cooldown",
    "Cooldown", "lastUsed", "lastRequest", "lastCall", "lastFire", "bucket",
    "tokens", "clock", "GetServerTimeNow", "tick", "debounce", "nextAllowed",
}

CONNECTION_LIFECYCLE_MARKERS: Set[str] = {
    "Disconnect", "Destroy", "GiveTask", "Add", "AddPromise", "LinkToInstance",
    "PlayerRemoving", "Destroying", "AncestryChanged", "Maid", "Janitor", "Trove",
}

EXPRESSION_PREFIX_VALUES: Set[str] = {
    "=", "(", "[", "{", ",", ";", ":", "return", "then", "else", "elseif",
    "and", "or", "not", "==", "~=", "<=", ">=", "<", ">", "+", "-", "*",
    "/", "//", "%", "^", "..", "#", "+=", "-=", "*=", "/=", "%=", "^=", "..=",
}

MULTI_CHAR_OPS: Tuple[str, ...] = (
    "...", "..=", "//=", "+=", "-=", "*=", "/=", "%=", "^=",
    "..", "::", "->", "==", "~=", "<=", ">=", "//",
)


@dataclass(frozen=True)
class LuauToken:
    kind: str  # KEYWORD, IDENT, NUMBER, STRING, OP
    value: str
    line: int
    col: int


@dataclass
class _BlockSpan:
    kind: str  # function, for, while, repeat
    start_idx: int
    end_idx: int
    header_end_idx: int


def _match_long_bracket(src: str, pos: int) -> Optional[Tuple[int, int]]:
    """Return (eq_count, content_start) if `src[pos:]` starts `[=*[`, else None."""
    n = len(src)
    if pos >= n or src[pos] != "[":
        return None
    j = pos + 1
    while j < n and src[j] == "=":
        j += 1
    if j < n and src[j] == "[":
        return (j - pos - 1, j + 1)
    return None


def _consume_long_bracket(src: str, eq_count: int, start_pos: int, line: int, col: int) -> Tuple[int, int, int]:
    """Consume until matching `]=*]` or EOF, returning (new_pos, new_line, new_col)."""
    n = len(src)
    closing = "]" + ("=" * eq_count) + "]"
    pos = start_pos
    while pos < n:
        if src.startswith(closing, pos):
            pos += len(closing)
            col += len(closing)
            return pos, line, col
        ch = src[pos]
        if ch == "\n":
            line += 1
            col = 1
        else:
            col += 1
        pos += 1
    return pos, line, col


def tokenize_luau(source: str) -> Tuple[List[LuauToken], List[str]]:
    """Lex Luau source into code tokens (ignoring comments/strings) plus leading directives.

    Handles:
    - Line comments `-- ...` and block comments `--[=*[ ... ]=*]`
    - Quoted strings `'...'`, `"..."` with escapes, and long strings `[=*[ ... ]=*]`
    - Luau interpolated backtick strings `` `...{expr}...` `` (literal text ignored; `{expr}` tokenized!)
    """
    tokens: List[LuauToken] = []
    directives: List[str] = []
    seen_code_token = False
    n = len(source)
    pos = 0
    line = 1
    col = 1

    # Stack for interpolated backtick string brace depth
    # Each entry tracks brace nesting inside a `{...}` interpolation slot.
    interp_brace_stack: List[int] = []

    def _lex_backtick_segment(p: int, ln: int, cl: int) -> Tuple[int, int, int, bool]:
        """Consume backtick string text until unescaped `{` (returns entered_interp=True) or closing `` ` ``."""
        start_ln, start_cl = ln, cl
        while p < n:
            ch = source[p]
            if ch == "\\":
                p += 1
                cl += 1
                if p < n:
                    if source[p] == "\n":
                        ln += 1
                        cl = 1
                    else:
                        cl += 1
                    p += 1
                continue
            if ch == "`":
                p += 1
                cl += 1
                tokens.append(LuauToken("STRING", "`...`", start_ln, start_cl))
                return p, ln, cl, False
            if ch == "{":
                p += 1
                cl += 1
                tokens.append(LuauToken("STRING", "`...`", start_ln, start_cl))
                return p, ln, cl, True
            if ch == "\n":
                ln += 1
                cl = 1
            else:
                cl += 1
            p += 1
        tokens.append(LuauToken("STRING", "`...`", start_ln, start_cl))
        return p, ln, cl, False

    while pos < n:
        ch = source[pos]

        # Track closing brace for active backtick interpolation expression
        if interp_brace_stack and ch == "}" and interp_brace_stack[-1] == 0:
            interp_brace_stack.pop()
            pos += 1
            col += 1
            pos, line, col, entered = _lex_backtick_segment(pos, line, col)
            if entered:
                interp_brace_stack.append(0)
            continue

        # Whitespace
        if ch in (" ", "\t", "\r"):
            pos += 1
            col += 1
            continue
        if ch == "\n":
            pos += 1
            line += 1
            col = 1
            continue

        # Comments (`--` or `--[=*[`)
        if ch == "-" and pos + 1 < n and source[pos + 1] == "-":
            long_hdr = _match_long_bracket(source, pos + 2)
            if long_hdr is not None:
                eq_cnt, content_start = long_hdr
                pos, line, col = _consume_long_bracket(
                    source, eq_cnt, content_start, line, col + 2 + (content_start - (pos + 2))
                )
            else:
                end_ln = source.find("\n", pos + 2)
                if end_ln == -1:
                    comment_text = source[pos + 2 :].strip()
                    pos = n
                else:
                    comment_text = source[pos + 2 : end_ln].strip()
                    col += (end_ln - pos)
                    pos = end_ln
                if not seen_code_token and comment_text.startswith("!"):
                    directives.append("--" + comment_text.strip())
            continue

        # Long string `[=*[`
        long_str = _match_long_bracket(source, pos)
        if long_str is not None:
            seen_code_token = True
            start_ln, start_cl = line, col
            eq_cnt, content_start = long_str
            col += content_start - pos
            pos, line, col = _consume_long_bracket(source, eq_cnt, content_start, line, col)
            tokens.append(LuauToken("STRING", "[...]", start_ln, start_cl))
            continue

        # Quoted strings `'...'` or `"..."`
        if ch in ('"', "'"):
            seen_code_token = True
            quote = ch
            start_ln, start_cl = line, col
            pos += 1
            col += 1
            while pos < n:
                sc = source[pos]
                if sc == "\\":
                    pos += 1
                    col += 1
                    if pos < n:
                        if source[pos] == "\n":
                            line += 1
                            col = 1
                        else:
                            col += 1
                        pos += 1
                    continue
                if sc == quote:
                    pos += 1
                    col += 1
                    break
                if sc == "\n":
                    line += 1
                    col = 1
                else:
                    col += 1
                pos += 1
            tokens.append(LuauToken("STRING", f"{quote}...{quote}", start_ln, start_cl))
            continue

        # Backtick interpolated string `` `...` ``
        if ch == "`":
            seen_code_token = True
            pos += 1
            col += 1
            pos, line, col, entered = _lex_backtick_segment(pos, line, col)
            if entered:
                interp_brace_stack.append(0)
            continue

        # Numbers (`0x`, `0b`, decimal/scientific with `_`)
        if ch.isdigit() or (ch == "." and pos + 1 < n and source[pos + 1].isdigit()):
            seen_code_token = True
            start_ln, start_cl = line, col
            start = pos
            if ch == "0" and pos + 1 < n and source[pos + 1] in ("x", "X", "b", "B"):
                pos += 2
                while pos < n and (source[pos].isalnum() or source[pos] == "_"):
                    pos += 1
            else:
                while pos < n and (source[pos].isdigit() or source[pos] == "_"):
                    pos += 1
                if pos < n and source[pos] == "." and (pos + 1 >= n or source[pos + 1] != "."):
                    pos += 1
                    while pos < n and (source[pos].isdigit() or source[pos] == "_"):
                        pos += 1
                if pos < n and source[pos] in ("e", "E"):
                    pos += 1
                    if pos < n and source[pos] in ("+", "-"):
                        pos += 1
                    while pos < n and (source[pos].isdigit() or source[pos] == "_"):
                        pos += 1
            val = source[start:pos]
            col += len(val)
            tokens.append(LuauToken("NUMBER", val, start_ln, start_cl))
            continue

        # Identifiers & Keywords
        if ch.isalpha() or ch == "_":
            seen_code_token = True
            start_ln, start_cl = line, col
            start = pos
            pos += 1
            while pos < n and (source[pos].isalnum() or source[pos] == "_"):
                pos += 1
            val = source[start:pos]
            col += len(val)
            kind = "KEYWORD" if val in LUAU_KEYWORDS else "IDENT"
            tokens.append(LuauToken(kind, val, start_ln, start_cl))
            continue

        # Track nested braces inside backtick interpolation
        if interp_brace_stack:
            if ch == "{":
                interp_brace_stack[-1] += 1
            elif ch == "}":
                interp_brace_stack[-1] = max(0, interp_brace_stack[-1] - 1)

        # Multi-char operators
        seen_code_token = True
        matched_op = None
        for op in MULTI_CHAR_OPS:
            if source.startswith(op, pos):
                matched_op = op
                break
        if matched_op:
            tokens.append(LuauToken("OP", matched_op, line, col))
            pos += len(matched_op)
            col += len(matched_op)
            continue

        tokens.append(LuauToken("OP", ch, line, col))
        pos += 1
        col += 1

    return tokens, directives


def _extract_paren_spans(tokens: Sequence[LuauToken]) -> Dict[int, int]:
    """Map every `(` token index to its matching `)` token index."""
    stack: List[int] = []
    pairs: Dict[int, int] = {}
    for i, tok in enumerate(tokens):
        if tok.value == "(":
            stack.append(i)
        elif tok.value == ")" and stack:
            pairs[stack.pop()] = i
    return pairs


def _extract_brace_spans(tokens: Sequence[LuauToken]) -> Dict[int, int]:
    """Map every `{` token index to its matching `}` token index."""
    stack: List[int] = []
    pairs: Dict[int, int] = {}
    for i, tok in enumerate(tokens):
        if tok.value == "{":
            stack.append(i)
        elif tok.value == "}" and stack:
            pairs[stack.pop()] = i
    return pairs


def _is_if_expression(tokens: Sequence[LuauToken], idx: int) -> bool:
    """Return True if `if` at `idx` is a Luau inline if-expression (no `end`)."""
    if idx == 0:
        return False
    prev = tokens[idx - 1]
    if prev.value in EXPRESSION_PREFIX_VALUES:
        return True
    # Note: after `IDENT` or `)` without semicolon/keyword could still be statement if prev is closing previous stmt,
    # whereas after `=`, `(`, `,`, `return`, operators, `{`, `[` it is definitely an if-expression.
    return False


def _extract_block_spans(tokens: Sequence[LuauToken], paren_pairs: Dict[int, int]) -> List[_BlockSpan]:
    """Extract matched `function`, `for`, `while`, `repeat` (and statement `if`/`do`) scopes."""
    blocks: List[_BlockSpan] = []
    # Stack entries: (kind, start_idx, header_end_idx)
    stack: List[Tuple[str, int, int]] = []
    n = len(tokens)
    i = 0
    while i < n:
        tok = tokens[i]
        val = tok.value
        if tok.kind == "KEYWORD":
            if val == "function":
                # Could be type annotation `(number) -> ...` vs function signature vs function body!
                # Inside type positions `::`, `:`, `type Foo = ...`, `->` may appear, check if there is a `)` followed by `->` (type syntax, no `end`)
                lp = i + 1
                while lp < n and tokens[lp].value not in ("(", "=", ";", "end") and lp - i < 8:
                    lp += 1
                header_end = i
                is_type_fn = False
                if lp < n and tokens[lp].value == "(" and lp in paren_pairs:
                    rp = paren_pairs[lp]
                    header_end = rp
                    if rp + 1 < n and tokens[rp + 1].value == "->":
                        is_type_fn = True
                if not is_type_fn:
                    stack.append(("function", i, header_end))
            elif val in ("for", "while"):
                # Find matching `do`
                j = i + 1
                while j < n and tokens[j].value != "do":
                    j += 1
                stack.append((val, i, min(j, n - 1)))
            elif val == "do":
                # Only push standalone `do` if not owned by top `for`/`while`
                if stack and stack[-1][0] in ("for", "while") and i == stack[-1][2]:
                    pass
                else:
                    stack.append(("do", i, i))
            elif val == "if":
                if not _is_if_expression(tokens, i):
                    stack.append(("if", i, i))
            elif val == "repeat":
                stack.append(("repeat", i, i))
            elif val == "until":
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k][0] == "repeat":
                        kind, s_idx, h_idx = stack.pop(k)
                        blocks.append(_BlockSpan(kind, s_idx, i, h_idx))
                        break
            elif val == "end":
                if stack:
                    # Pop closest non-repeat block
                    for k in range(len(stack) - 1, -1, -1):
                        if stack[k][0] != "repeat":
                            kind, s_idx, h_idx = stack.pop(k)
                            if kind in ("function", "for", "while", "do"):
                                blocks.append(_BlockSpan(kind, s_idx, i, h_idx))
                            break
        i += 1
    return blocks


def _make_finding(
    *,
    rule_id: str,
    severity: str,
    domain: str,
    evidence: str,
    why_it_matters: str,
    fix: str,
    auto_fixable: bool = False,
    file: Optional[str] = None,
    line: Optional[int] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": rule_id,
        "severity": severity if severity in SEVERITIES else "MAJOR",
        "domain": domain,
        "evidence": evidence,
        "why_it_matters": why_it_matters,
        "fix": fix,
        "auto_fixable": bool(auto_fixable),
    }
    if file is not None:
        out["file"] = file
    if line is not None:
        out["line"] = int(line)
    return out


def _score_and_verdict(findings: Sequence[Dict[str, Any]]) -> Tuple[int, str, Dict[str, int]]:
    counts = {"blocker": 0, "critical": 0, "major": 0, "minor": 0, "info": 0}
    score = 100
    for f in findings:
        sev = str(f.get("severity", "MAJOR")).upper()
        key = sev.lower()
        if key in counts:
            counts[key] += 1
        score -= SEVERITY_PENALTIES.get(sev, 5)

    score = max(0, min(100, score))
    if counts["blocker"] > 0:
        score = min(score, 49)
        verdict = "REJECT"
    elif counts["critical"] >= 3 or score < 50:
        verdict = "REJECT"
    elif counts["critical"] > 0 or counts["major"] > 0 or score < 85:
        verdict = "FIX_FIRST"
    else:
        verdict = "SHIP"
    return score, verdict, counts


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sign_audit_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Attach an unforgeable runtime HMAC-SHA256 attestation over the final report payload."""
    findings = list(report.get("findings") or [])
    findings_sha256 = hashlib.sha256(_canonical_json(findings).encode("utf-8")).hexdigest()
    summary_obj = dict(report.get("summary") or {})
    envelope = {
        "engine": "CriticalAuditEngine",
        "mode": str(report.get("mode", "")),
        "score": int(report.get("score", 0)),
        "verdict": str(report.get("verdict", "")),
        "summary": summary_obj,
        "findings_sha256": findings_sha256,
    }
    sig = hmac.new(_AUDIT_HMAC_SECRET, _canonical_json(envelope).encode("utf-8"), hashlib.sha256).hexdigest()
    out = dict(report)
    out["audit_attestation"] = {**envelope, "sig": sig}
    return out


def _has_remote_validation_call(tokens: Sequence[LuauToken]) -> bool:
    """Verify genuine validation calls rather than table field reads like `payload.type` or `math.clamp`."""
    n = len(tokens)
    builtin_calls = {"typeof", "type", "assert", "tonumber"}
    validator_methods = {
        "ValidateField", "ValidateArgs", "RegisterReliable", "RegisterUnreliable",
        "validate", "isValid", "Validate", "VerifyArgs", "VerifyPayload",
    }
    for idx, tok in enumerate(tokens):
        val = tok.value
        prev_val = tokens[idx - 1].value if idx > 0 else ""
        next_val = tokens[idx + 1].value if idx + 1 < n else ""
        if val in builtin_calls:
            if prev_val not in {".", ":"} and next_val == "(":
                return True
        elif val == "isfinite":
            if next_val == "(":
                return True
        elif val in validator_methods:
            if next_val == "(":
                return True
        elif val == "SafeRemoteGateway":
            if idx + 3 < n and next_val in {":", "."} and tokens[idx + 3].value == "(":
                return True
    return False


def _has_rate_limit_logic(tokens: Sequence[LuauToken], client_param_names: Sequence[str]) -> bool:
    """Check rate limiting markers while ignoring fields accessed on untrusted client payloads."""
    client_set = set(client_param_names)
    for idx, tok in enumerate(tokens):
        if tok.value in RATE_LIMIT_IDENTIFIERS:
            if idx >= 2 and tokens[idx - 1].value == "." and tokens[idx - 2].value in client_set:
                continue
            return True
    return False


def _has_server_catalog_lookup(tokens: Sequence[LuauToken]) -> bool:
    """Detect genuine server catalog table lookup (`CATALOG[id]` / `.` / `:`), never `math.clamp`."""
    n = len(tokens)
    for idx, tok in enumerate(tokens):
        if tok.value in SERVER_CATALOG_TABLES and idx + 1 < n and tokens[idx + 1].value in {"[", ".", ":"}:
            return True
    return False


def _collect_suspicious_client_refs(tokens: Sequence[LuauToken], extra_params: Sequence[str]) -> List[str]:
    """Find untrusted client parameters or payload fields whose names carry client-authority risks."""
    refs: List[str] = [p for p in extra_params if p.lower() in CLIENT_TRUSTED_PARAM_NAMES]
    extra_set = set(extra_params)
    n = len(tokens)
    for idx in range(n - 2):
        if (
            tokens[idx].value in extra_set
            and tokens[idx + 1].value == "."
            and tokens[idx + 2].kind == "IDENT"
            and tokens[idx + 2].value.lower() in CLIENT_TRUSTED_PARAM_NAMES
        ):
            dotted = f"{tokens[idx].value}.{tokens[idx + 2].value}"
            if dotted not in refs:
                refs.append(dotted)
    return refs


def _hex_to_rgb(hex_str: str) -> Optional[Tuple[int, int, int]]:
    if not isinstance(hex_str, str):
        return None
    s = hex_str.strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


def _rel_luminance(rgb: Tuple[int, int, int]) -> float:
    def _chan(v: int) -> float:
        x = v / 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = _chan(rgb[0]), _chan(rgb[1]), _chan(rgb[2])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _wcag_contrast(fg_hex: str, bg_hex: str) -> Optional[float]:
    fg = _hex_to_rgb(fg_hex)
    bg = _hex_to_rgb(bg_hex)
    if fg is None or bg is None:
        return None
    l1 = _rel_luminance(fg)
    l2 = _rel_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


class CriticalAuditEngine:
    """Adversarial, tokenizer-backed, multi-domain audit engine (`static`, `live`, `challenge`, `gate`)."""

    def __init__(
        self,
        luau_audit_engine: Optional[LuauAuditSnapshotEngine] = None,
        project_library: Optional[Any] = None,
    ) -> None:
        self.luau_audit_engine = luau_audit_engine
        self.project_library = project_library

    @staticmethod
    def verify_report_attestation(report: Any) -> Tuple[bool, str]:
        """Verify that an audit report carries an untampered CriticalAuditEngine HMAC attestation."""
        if not isinstance(report, dict):
            return False, "audit_report is not a dictionary."
        att = report.get("audit_attestation")
        if not isinstance(att, dict):
            return False, "audit_report lacks CriticalAuditEngine 'audit_attestation'."
        if att.get("engine") != "CriticalAuditEngine":
            return False, "audit_attestation engine mismatch."
        findings = report.get("findings")
        if not isinstance(findings, list):
            return False, "audit_report 'findings' must be a list."

        exp_score, exp_verdict, exp_counts = _score_and_verdict(findings)
        try:
            rep_score = int(report.get("score"))
        except (TypeError, ValueError):
            return False, "audit_report 'score' is missing or non-numeric."
        rep_verdict = str(report.get("verdict", "")).upper()
        if rep_score != exp_score or rep_verdict != exp_verdict:
            return False, "audit_report score/verdict inconsistent with findings."

        rep_summary = report.get("summary")
        if not isinstance(rep_summary, dict):
            return False, "audit_report 'summary' is missing."
        for k, v in exp_counts.items():
            if int(rep_summary.get(k, -1)) != v:
                return False, f"audit_report summary count mismatch for '{k}'."

        findings_sha256 = hashlib.sha256(_canonical_json(findings).encode("utf-8")).hexdigest()
        envelope = {
            "engine": "CriticalAuditEngine",
            "mode": str(report.get("mode", "")),
            "score": rep_score,
            "verdict": rep_verdict,
            "summary": dict(rep_summary),
            "findings_sha256": findings_sha256,
        }
        expected_sig = hmac.new(_AUDIT_HMAC_SECRET, _canonical_json(envelope).encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(att.get("sig", "")), expected_sig):
            return False, "audit_attestation HMAC signature failed verification."
        return True, "ok"

    # ------------------------------------------------------------------
    # Luau Static Analyzer (Token-Stream Based; ignores comments/strings)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_luau_sources(
        luau_sources: Optional[Dict[str, str] | List[Any] | str] = None,
        file_paths: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if isinstance(luau_sources, str):
            out["inline.luau"] = luau_sources
        elif isinstance(luau_sources, list):
            for idx, item in enumerate(luau_sources):
                if isinstance(item, dict):
                    name = str(item.get("path") or item.get("name") or f"script_{idx}.luau")
                    out[name] = str(item.get("source") or "")
                elif isinstance(item, str):
                    out[f"script_{idx}.luau"] = item
        elif isinstance(luau_sources, dict):
            for k, v in luau_sources.items():
                out[str(k)] = str(v)

        for fp in file_paths or []:
            p = Path(fp).expanduser()
            if p.is_file():
                out[str(p)] = p.read_text(encoding="utf-8", errors="replace")
        return out

    @staticmethod
    def _collect_named_functions(
        tokens: Sequence[LuauToken],
        blocks: Sequence[_BlockSpan],
        paren_pairs: Dict[int, int],
    ) -> Dict[str, Tuple[int, int, List[str]]]:
        """Map function name -> (start_tok_idx, end_tok_idx, param_names)."""
        fn_map: Dict[str, Tuple[int, int, List[str]]] = {}
        fn_blocks = {(b.start_idx, b.end_idx) for b in blocks if b.kind == "function"}
        block_by_start = {b.start_idx: b for b in blocks if b.kind == "function"}

        for start_idx, b in block_by_start.items():
            # Pattern 1: [local] function foo(a, b) or function Mod.foo(a, b)
            j = start_idx + 1
            fn_name: Optional[str] = None
            lp_idx: Optional[int] = None
            while j < len(tokens) and j <= b.header_end_idx:
                if tokens[j].value == "(":
                    lp_idx = j
                    break
                if tokens[j].kind == "IDENT":
                    fn_name = tokens[j].value
                j += 1

            # Pattern 2: local foo = function(a, b)
            if fn_name is None and start_idx >= 2 and tokens[start_idx - 1].value == "=" and tokens[start_idx - 2].kind == "IDENT":
                fn_name = tokens[start_idx - 2].value

            params: List[str] = []
            if lp_idx is not None and lp_idx in paren_pairs:
                rp = paren_pairs[lp_idx]
                k = lp_idx + 1
                while k < rp:
                    if tokens[k].kind == "IDENT":
                        params.append(tokens[k].value)
                        # Skip optional `: Type` annotation
                        if k + 1 < rp and tokens[k + 1].value == ":":
                            while k < rp and tokens[k].value != ",":
                                k += 1
                    k += 1
            if fn_name and (start_idx, b.end_idx) in fn_blocks:
                fn_map[fn_name] = (start_idx, b.end_idx, params)
        return fn_map

    @staticmethod
    def _extract_fn_params(tokens: Sequence[LuauToken], fn_start: int, paren_pairs: Dict[int, int]) -> List[str]:
        params: List[str] = []
        j = fn_start + 1
        while j < len(tokens) and tokens[j].value != "(":
            if tokens[j].value in ("=", "end"):
                return params
            j += 1
        if j < len(tokens) and tokens[j].value == "(" and j in paren_pairs:
            rp = paren_pairs[j]
            k = j + 1
            while k < rp:
                if tokens[k].kind == "IDENT":
                    params.append(tokens[k].value)
                    if k + 1 < rp and tokens[k + 1].value == ":":
                        while k < rp and tokens[k].value != ",":
                            k += 1
                k += 1
        return params

    @staticmethod
    def _tokens_text_slice(tokens: Sequence[LuauToken], start: int, end: int) -> str:
        return " ".join(t.value for t in tokens[max(0, start) : min(len(tokens), end + 1)])

    def _analyze_single_luau_file(
        self,
        path: str,
        source: str,
        *,
        shared_bind_to_close_present: bool = False,
    ) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        tokens, directives = tokenize_luau(source)
        lines_raw = source.splitlines()

        def line_snippet(ln: int) -> str:
            if 1 <= ln <= len(lines_raw):
                return f"L{ln}: {lines_raw[ln - 1].strip()[:140]}"
            return f"L{ln}"

        # 1. LUAU-TYPE-001: --!strict directive
        if "--!nocheck" in directives:
            findings.append(
                _make_finding(
                    rule_id="LUAU-TYPE-001",
                    severity="CRITICAL",
                    domain="luau",
                    file=path,
                    line=1,
                    evidence="--!nocheck disables type checking",
                    why_it_matters="Disabling Luau type checking hides nil dereferences, wrong Remote schemas, and table shape mismatches until runtime.",
                    fix="Replace `--!nocheck` on line 1 with `--!strict` and annotate function signatures.",
                    auto_fixable=True,
                )
            )
        elif "--!strict" not in directives:
            findings.append(
                _make_finding(
                    rule_id="LUAU-TYPE-001",
                    severity="MAJOR",
                    domain="luau",
                    file=path,
                    line=1,
                    evidence=f"Top directives: {directives or ['<none>']}",
                    why_it_matters="Without `--!strict`, Luau skips static type enforcement and misses nil/type bugs in production scripts.",
                    fix="Add `--!strict` on line 1 of the script.",
                    auto_fixable=True,
                )
            )

        if not tokens:
            return findings

        paren_pairs = _extract_paren_spans(tokens)
        blocks = _extract_block_spans(tokens, paren_pairs)
        fn_map = self._collect_named_functions(tokens, blocks, paren_pairs)

        loop_blocks = [b for b in blocks if b.kind in ("for", "while", "repeat")]
        fn_blocks = [b for b in blocks if b.kind == "function"]
        fn_by_start = {b.start_idx: b for b in fn_blocks}

        def in_any_loop(idx: int) -> bool:
            return any(b.start_idx < idx < b.end_idx for b in loop_blocks)

        def enclosing_loop(idx: int) -> Optional[_BlockSpan]:
            cands = [b for b in loop_blocks if b.start_idx < idx < b.end_idx]
            return max(cands, key=lambda b: b.start_idx) if cands else None

        # Identify `pcall` / `xpcall` spans and helper functions invoked inside `pcall(helper)`
        pcall_ranges: List[Tuple[int, int]] = []
        pcall_called_helpers: Set[str] = set()
        for i, tok in enumerate(tokens):
            if tok.kind == "IDENT" and tok.value in ("pcall", "xpcall"):
                if i + 1 < len(tokens) and tokens[i + 1].value == "(" and (i + 1) in paren_pairs:
                    rp = paren_pairs[i + 1]
                    pcall_ranges.append((i + 1, rp))
                    if i + 2 < rp and tokens[i + 2].kind == "IDENT" and tokens[i + 2].value != "function":
                        pcall_called_helpers.add(tokens[i + 2].value)

        def is_inside_pcall(idx: int) -> bool:
            if any(lo <= idx <= hi for lo, hi in pcall_ranges):
                return True
            for fn_name in pcall_called_helpers:
                if fn_name in fn_map:
                    fs, fe, _ = fn_map[fn_name]
                    if fs <= idx <= fe:
                        return True
            return False

        # Track per-frame callback spans (RunService hooks)
        per_frame_hooks = {"Heartbeat", "RenderStepped", "Stepped", "PreRender", "PreAnimation", "PreSimulation", "PostSimulation"}
        per_frame_spans: List[Tuple[int, int]] = []

        # Track `:Connect(` / `:Once(` callbacks
        connect_callbacks: List[Tuple[int, int, int, str, List[str]]] = []
        # tuple: (connect_tok_idx, body_start, body_end, signal_name, params)
        for i, tok in enumerate(tokens):
            if tok.value == ":" and i + 2 < len(tokens) and tokens[i + 1].value in ("Connect", "connect", "Once") and tokens[i + 2].value == "(":
                sig_name = tokens[i - 1].value if i >= 1 and tokens[i - 1].kind == "IDENT" else ""
                lp = i + 2
                rp = paren_pairs.get(lp)
                if rp is None:
                    continue
                if lp + 1 < rp and tokens[lp + 1].value == "function" and (lp + 1) in fn_by_start:
                    fb = fn_by_start[lp + 1]
                    params = self._extract_fn_params(tokens, fb.start_idx, paren_pairs)
                    connect_callbacks.append((i, fb.start_idx, fb.end_idx, sig_name, params))
                    if sig_name in per_frame_hooks:
                        per_frame_spans.append((fb.start_idx, fb.end_idx))
                elif lp + 1 < rp and tokens[lp + 1].kind == "IDENT":
                    cb_name = tokens[lp + 1].value
                    if cb_name in fn_map:
                        fs, fe, params = fn_map[cb_name]
                        connect_callbacks.append((i, fs, fe, sig_name, params))
                        if sig_name in per_frame_hooks:
                            per_frame_spans.append((fs, fe))
                    else:
                        connect_callbacks.append((i, lp, rp, sig_name, []))

        def in_per_frame_hook(idx: int) -> bool:
            return any(lo <= idx <= hi for lo, hi in per_frame_spans)

        # Resolve variables bound via `GetService(...)`, `GetDataStore(...)`, or Humanoid lookups
        service_vars: Dict[str, str] = {}
        humanoid_vars: Set[str] = set()
        for i, tok in enumerate(tokens):
            if (
                tok.value == "local"
                and i + 3 < len(tokens)
                and tokens[i + 1].kind == "IDENT"
                and tokens[i + 2].value == "="
            ):
                var_name = tokens[i + 1].value
                window = self._tokens_text_slice(tokens, i + 3, min(len(tokens) - 1, i + 12))
                ln_txt = lines_raw[tok.line - 1] if 1 <= tok.line <= len(lines_raw) else ""
                if "GetService" in window:
                    m_svc = re.search(r'GetService\(\s*["\']([A-Za-z0-9_]+)["\']\s*\)', ln_txt)
                    if m_svc:
                        service_vars[var_name] = m_svc.group(1)
                if "GetDataStore" in window or "GetOrderedDataStore" in window:
                    service_vars[var_name] = "DataStore"
                if re.search(r'(?:FindFirstChild(?:OfClass|WhichIsA)?|WaitForChild)\s*\(\s*["\']Humanoid["\']\s*\)|\.Humanoid\b', ln_txt):
                    if "Animator" not in ln_txt:
                        humanoid_vars.add(var_name)

        # 2. Scan token patterns
        n = len(tokens)
        has_datastore_usage = False
        has_bind_to_close = shared_bind_to_close_present
        has_text_scaled = False
        has_text_size_constraint = False

        for i, tok in enumerate(tokens):
            val = tok.value

            if val in ("DataStoreService", "GetDataStore", "GetOrderedDataStore"):
                has_datastore_usage = True
            if val == "BindToClose" and i >= 1 and tokens[i - 1].value == ":":
                has_bind_to_close = True
            if val == "TextScaled" and i + 2 < n and tokens[i + 1].value == "=" and tokens[i + 2].value == "true":
                has_text_scaled = True
            if val == "UITextSizeConstraint":
                has_text_size_constraint = True

            # LUAU-SEC-001: RemoteFunction:InvokeClient
            if val == ":" and i + 1 < n and tokens[i + 1].value == "InvokeClient":
                findings.append(
                    _make_finding(
                        rule_id="LUAU-SEC-001",
                        severity="BLOCKER",
                        domain="luau",
                        file=path,
                        line=tok.line,
                        evidence=line_snippet(tok.line),
                        why_it_matters="RemoteFunction:InvokeClient() lets an exploiter hang a server coroutine indefinitely or throw errors back to the server.",
                        fix="Replace InvokeClient with one-way RemoteEvent:FireClient() and a client intent RemoteEvent with server timeout.",
                    )
                )

            # LUAU-SEC-002: loadstring / getfenv / setfenv
            if (
                tok.kind == "IDENT"
                and val in ("loadstring", "getfenv", "setfenv")
                and i + 1 < n
                and tokens[i + 1].value == "("
                and (i == 0 or tokens[i - 1].value not in (".", ":", "function"))
            ):
                findings.append(
                    _make_finding(
                        rule_id="LUAU-SEC-002",
                        severity="BLOCKER",
                        domain="luau",
                        file=path,
                        line=tok.line,
                        evidence=line_snippet(tok.line),
                        why_it_matters=f"`{val}()` enables arbitrary runtime code execution / environment tampering and disables Luau optimizations.",
                        fix=f"Remove `{val}()` and use typed ModuleScript dispatch tables instead.",
                    )
                )

            # LUAU-PERF-001: deprecated wait() / spawn() / delay()
            if (
                tok.kind == "IDENT"
                and val in DEPRECATED_SCHEDULER_CALLS
                and i + 1 < n
                and tokens[i + 1].value == "("
                and (i == 0 or tokens[i - 1].value not in (".", ":", "function"))
            ):
                repl = DEPRECATED_SCHEDULER_CALLS[val]
                findings.append(
                    _make_finding(
                        rule_id="LUAU-PERF-001",
                        severity="CRITICAL",
                        domain="luau",
                        file=path,
                        line=tok.line,
                        evidence=line_snippet(tok.line),
                        why_it_matters=f"Global `{val}()` runs on the legacy 30Hz pipeline and throttles arbitrarily under load.",
                        fix=f"Replace `{val}(...)` with `{repl}(...)`.",
                        auto_fixable=True,
                    )
                )

            # LUAU-ANIM-001: Humanoid:LoadAnimation(...)
            if val == ":" and i + 2 < n and tokens[i + 1].value == "LoadAnimation" and tokens[i + 2].value == "(":
                recv_raw = tokens[i - 1].value if i >= 1 else ""
                recv = recv_raw.lower()
                raw_ln = lines_raw[tok.line - 1][: max(0, tok.col - 1)] if 1 <= tok.line <= len(lines_raw) else ""
                inline_hum_chain = bool(
                    re.search(
                        r'(?:FindFirstChild(?:OfClass|WhichIsA)?|WaitForChild)\s*\(\s*["\']Humanoid["\']\s*\)\s*$',
                        raw_ln,
                    )
                )
                if (
                    "humanoid" in recv
                    or recv in ("hum", "charhumanoid")
                    or recv_raw in humanoid_vars
                    or inline_hum_chain
                ):
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-ANIM-001",
                            severity="CRITICAL",
                            domain="animation",
                            file=path,
                            line=tok.line,
                            evidence=line_snippet(tok.line),
                            why_it_matters="Humanoid:LoadAnimation is deprecated and breaks when Animator replication isn't explicitly coordinated.",
                            fix="Resolve `local animator = humanoid:FindFirstChildOfClass('Animator')` and call `animator:LoadAnimation(anim)`.",
                            auto_fixable=True,
                        )
                    )

                # LUAU-ANIM-002: LoadAnimation inside loop or repeatable action callback without track caching
                in_action_cb = any(
                    sig in ("Activated", "Equipped", "Touched", "InputBegan", "OnServerEvent", "OnClientEvent", "Triggered")
                    and lo <= i <= hi
                    for _, lo, hi, sig, _ in connect_callbacks
                )
                if in_any_loop(i) or in_action_cb:
                    ctx_start = max(0, i - 30)
                    ctx_end = min(n, i + 25)
                    ctx_vals = {t.value for t in tokens[ctx_start:ctx_end]}
                    has_cache = any(
                        m in ctx_vals
                        for m in ("trackCache", "cachedTracks", "loadedTracks", "tracks", "animCache", "Stop", "Destroy")
                    ) or any(
                        tokens[k].value == "[" and k > 0 and "track" in tokens[k - 1].value.lower()
                        for k in range(ctx_start, ctx_end)
                    )
                    if not has_cache:
                        findings.append(
                            _make_finding(
                                rule_id="LUAU-ANIM-002",
                                severity="CRITICAL",
                                domain="animation",
                                file=path,
                                line=tok.line,
                                evidence=line_snippet(tok.line),
                                why_it_matters="Calling `:LoadAnimation()` repeatedly in a loop or input/equip callback leaks AnimationTracks and hits Roblox's active track cap.",
                                fix="Load and cache each AnimationTrack once per Animator/character, and call `:Stop()` / `:Destroy()` on cleanup.",
                            )
                        )

            # LUAU-PERF-003: Unbounded Instance.new in loops / per-frame hooks
            if (
                tok.kind == "IDENT"
                and val == "Instance"
                and i + 3 < n
                and tokens[i + 1].value == "."
                and tokens[i + 2].value == "new"
                and tokens[i + 3].value == "("
            ):
                loop = enclosing_loop(i)
                if loop is not None or in_per_frame_hook(i):
                    # Allow bounded pool pre-warming loops when explicit pool variables are populated
                    is_pool_warmup = False
                    if loop is not None and loop.kind == "for" and not in_per_frame_hook(i):
                        loop_vals = {t.value.lower() for t in tokens[loop.start_idx : loop.end_idx + 1]}
                        if any("pool" in v or "cache" in v for v in loop_vals):
                            is_pool_warmup = True
                    if not is_pool_warmup:
                        findings.append(
                            _make_finding(
                                rule_id="LUAU-PERF-003",
                                severity="CRITICAL",
                                domain="luau",
                                file=path,
                                line=tok.line,
                                evidence=line_snippet(tok.line),
                                why_it_matters="Creating Instances via `Instance.new()` inside loops or per-frame RunService callbacks causes GC spikes, memory churn, and frame drops.",
                                fix="Pre-allocate an object pool outside the loop and reuse instances via CFrame/Enabled toggles.",
                            )
                        )

            # LUAU-ECO-002: DataStore / Marketplace calls without pcall
            if val == ":" and i + 2 < n and tokens[i + 1].value in DATASTORE_AND_MARKETPLACE_METHODS and tokens[i + 2].value == "(":
                method_name = tokens[i + 1].value
                if method_name in ("GetAsync", "SetAsync", "UpdateAsync", "RemoveAsync", "IncrementAsync", "ListKeysAsync", "GetSortedAsync"):
                    has_datastore_usage = True
                if not is_inside_pcall(i):
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-ECO-002",
                            severity="CRITICAL",
                            domain="luau",
                            file=path,
                            line=tok.line,
                            evidence=line_snippet(tok.line),
                            why_it_matters=f"`{method_name}` performs a network yield that throws on Roblox outages, throttling, or HTTP errors; unhandled exceptions drop player saves or purchases.",
                            fix=f"Wrap `{method_name}` in `pcall(function() ... end)` with bounded exponential backoff retries.",
                        )
                    )

            # LUAU-PERF-005: Debris misuse
            if val == ":" and i + 2 < n and tokens[i + 1].value == "AddItem" and tokens[i + 2].value == "(":
                recv_name = tokens[i - 1].value if i >= 1 else ""
                is_debris = (
                    "debris" in recv_name.lower()
                    or service_vars.get(recv_name) == "Debris"
                    or "Debris" in self._tokens_text_slice(tokens, max(0, i - 6), i)
                )
                if is_debris:
                    sev = "CRITICAL" if (in_any_loop(i) or in_per_frame_hook(i)) else "MAJOR"
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-PERF-005",
                            severity=sev,
                            domain="luau",
                            file=path,
                            line=tok.line,
                            evidence=line_snippet(tok.line),
                            why_it_matters="Debris:AddItem uses legacy non-cancellable timers and hides pooling/lifecycle leaks when destroying ephemeral parts or VFX.",
                            fix="Use an object pool for projectiles/VFX or `task.delay(ttl, instance.Destroy, instance)` tracked by a Maid/Janitor.",
                        )
                    )

            # LUAU-ECO-001: ProcessReceipt assignment check
            if val == "ProcessReceipt" and i + 1 < n and tokens[i + 1].value == "=":
                cb_start, cb_end = i + 2, min(n - 1, i + 200)
                if i + 2 < n and tokens[i + 2].value == "function" and (i + 2) in fn_by_start:
                    fb = fn_by_start[i + 2]
                    cb_start, cb_end = fb.start_idx, fb.end_idx
                elif i + 2 < n and tokens[i + 2].kind == "IDENT" and tokens[i + 2].value in fn_map:
                    cb_start, cb_end, _ = fn_map[tokens[i + 2].value]
                cb_vals = {t.value for t in tokens[cb_start : cb_end + 1]}
                has_purchase_id = "PurchaseId" in cb_vals or "UpdateAsync" in cb_vals or "processedReceipts" in cb_vals
                has_not_processed = "NotProcessedYet" in cb_vals
                has_pcall_in_receipt = "pcall" in cb_vals or "xpcall" in cb_vals
                if not has_purchase_id or not (has_not_processed and has_pcall_in_receipt):
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-ECO-001",
                            severity="BLOCKER",
                            domain="luau",
                            file=path,
                            line=tok.line,
                            evidence=line_snippet(tok.line) + f" (idempotency={has_purchase_id}, safe_retry={has_not_processed and has_pcall_in_receipt})",
                            why_it_matters="A non-idempotent ProcessReceipt callback risks double-granting Robux purchases on DataStore retry or dropping paid receipts without refunding.",
                            fix="Deduplicate `receiptInfo.PurchaseId` via DataStore `UpdateAsync` inside `pcall`, and return `Enum.ProductPurchaseDecision.NotProcessedYet` on failure.",
                        )
                    )

            # LUAU-STREAM-001: Unbounded WaitForChild in OnClientEvent or ReplicatedFirst
            if val == "WaitForChild" and i + 1 < n and tokens[i + 1].value == "(" and (i + 1) in paren_pairs:
                rp = paren_pairs[i + 1]
                has_timeout = any(tokens[k].value == "," for k in range(i + 2, rp))
                in_client_cb = any(sig == "OnClientEvent" and lo <= i <= hi for _, lo, hi, sig, _ in connect_callbacks)
                is_rep_first = "replicatedfirst" in path.lower()
                if not has_timeout and (in_client_cb or is_rep_first):
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-STREAM-001",
                            severity="MAJOR",
                            domain="luau",
                            file=path,
                            line=tok.line,
                            evidence=line_snippet(tok.line),
                            why_it_matters="Infinite `WaitForChild(name)` without a timeout yields forever when StreamingEnabled streams targets out or during ReplicatedFirst startup.",
                            fix="Pass a bounded timeout `WaitForChild(name, 5)` and handle `nil`, or use `FindFirstChild`.",
                        )
                    )

        # 3. Inspect Loop Blocks for LUAU-PERF-002 (Polling / Infinite Non-Yielding Loops)
        for lb in loop_blocks:
            body_tokens = tokens[lb.start_idx : lb.end_idx + 1]
            body_vals = [t.value for t in body_tokens]
            start_line = tokens[lb.start_idx].line
            # Check for `while true do` without yield
            if lb.kind == "while":
                cond_tokens = tokens[lb.start_idx + 1 : lb.header_end_idx]
                is_while_true = len(cond_tokens) == 1 and cond_tokens[0].value == "true"
                has_yield = (
                    "wait" in body_vals
                    or "Wait" in body_vals
                    or ("task" in body_vals and any(
                        body_tokens[k].value == "task" and k + 2 < len(body_tokens) and body_tokens[k + 1].value == "." and body_tokens[k + 2].value == "wait"
                        for k in range(len(body_tokens))
                    ))
                )
                has_break_or_return = "break" in body_vals or "return" in body_vals
                if is_while_true and not has_yield and not has_break_or_return:
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-PERF-006",
                            severity="BLOCKER",
                            domain="luau",
                            file=path,
                            line=start_line,
                            evidence=line_snippet(start_line),
                            why_it_matters="An unbounded `while true do` loop without any yield or break freezes the Luau VM and triggers script timeout exhaustion.",
                            fix="Replace with event-driven `:Connect(...)` callbacks or add a valid exit condition / `task.wait(...)`.",
                        )
                    )
                    continue

            # Detect polling loops (`while true do task.wait(...)`, `while task.wait(...) do`, `repeat task.wait(...) until`)
            has_task_wait = any(
                body_tokens[k].value == "task" and k + 2 < len(body_tokens) and body_tokens[k + 1].value == "." and body_tokens[k + 2].value == "wait"
                for k in range(len(body_tokens))
            )
            has_bare_wait = any(
                body_tokens[k].value == "wait" and k + 1 < len(body_tokens) and body_tokens[k + 1].value == "("
                and (k == 0 or body_tokens[k - 1].value not in (".", ":"))
                for k in range(len(body_tokens))
            )
            if has_task_wait or has_bare_wait:
                is_bounded_for = lb.kind == "for"
                # Bounded `for attempt = 1, 3` retry loops are legitimate backoff, not polling loops
                if not is_bounded_for:
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-PERF-002",
                            severity="CRITICAL",
                            domain="luau",
                            file=path,
                            line=start_line,
                            evidence=line_snippet(start_line),
                            why_it_matters="Polling loops waste frame budget and add input/state latency across concurrent players.",
                            fix="Replace polling loops with `:GetPropertyChangedSignal`, `:GetAttributeChangedSignal`, `RBXScriptSignal:Wait()`, or a single RunService.Heartbeat accumulator.",
                        )
                    )

        # 4. Inspect Remote / Touched / Connection Lifecycle Callbacks
        file_has_player_removing = any(t.value == "PlayerRemoving" for t in tokens)
        file_has_cleanup = any(t.value in CONNECTION_LIFECYCLE_MARKERS for t in tokens)

        for conn_idx, cb_start, cb_end, sig_name, params in connect_callbacks:
            cb_line = tokens[conn_idx].line
            cb_tokens = tokens[cb_start : cb_end + 1]
            cb_vals = {t.value for t in cb_tokens}

            # Expand helper functions called from inside callback (1-hop)
            expanded_vals = set(cb_vals)
            expanded_tokens = list(cb_tokens)
            for t in cb_tokens:
                if t.kind == "IDENT" and t.value in fn_map:
                    hs, he, _ = fn_map[t.value]
                    expanded_tokens.extend(tokens[hs : he + 1])
                    expanded_vals.update(x.value for x in tokens[hs : he + 1])

            # LUAU-SEC-003 / 004 / 005: OnServerEvent checks
            if sig_name == "OnServerEvent":
                extra_params = [p for idx_p, p in enumerate(params) if idx_p > 0]
                has_validation = _has_remote_validation_call(expanded_tokens)
                has_rate_limit = _has_rate_limit_logic(expanded_tokens, extra_params)
                if not has_validation and extra_params:
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-SEC-003",
                            severity="BLOCKER",
                            domain="luau",
                            file=path,
                            line=cb_line,
                            evidence=line_snippet(cb_line) + f" (params={params}, has_rate_limit={has_rate_limit})",
                            why_it_matters="Unvalidated RemoteEvent.OnServerEvent accepts arbitrary exploiter payloads (NaN, huge numbers, wrong Instance types, mixed tables).",
                            fix="Route through SafeRemoteGateway or validate `typeof()`, finite numbers, bounds, and per-player token-bucket rate limits.",
                        )
                    )
                elif not has_rate_limit:
                    sev = "BLOCKER" if not has_validation else "CRITICAL"
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-SEC-004" if has_validation else "LUAU-SEC-003",
                            severity=sev,
                            domain="luau",
                            file=path,
                            line=cb_line,
                            evidence=line_snippet(cb_line),
                            why_it_matters="OnServerEvent without per-player rate limiting allows exploiters to flood the server with thousands of events per second.",
                            fix="Add a per-player token bucket (`SafeRemoteGateway:ConsumeRateLimit` or `os.clock()` cooldown) and prune on `PlayerRemoving`.",
                        )
                    )

                # LUAU-SEC-005: Client-trusted values in OnServerEvent
                suspicious_params = _collect_suspicious_client_refs(expanded_tokens, extra_params)
                has_server_lookup = _has_server_catalog_lookup(expanded_tokens)
                trusts_amount_directly = bool(suspicious_params) and not has_server_lookup
                # Direct TakeDamage inside OnServerEvent without distance check
                if "TakeDamage" in expanded_vals and "Magnitude" not in expanded_vals:
                    trusts_amount_directly = True
                if trusts_amount_directly:
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-SEC-005",
                            severity="BLOCKER",
                            domain="luau",
                            file=path,
                            line=cb_line,
                            evidence=line_snippet(cb_line) + f" (suspicious_params={suspicious_params})",
                            why_it_matters="Trusting client-supplied damage, currency, rewards, userId, or unverified hit targets allows instant economy/kill exploits.",
                            fix="Accept client intent IDs only; look up prices/damage from server-only tables in ServerScriptService and verify distance <= max range.",
                        )
                    )

            # LUAU-PERF-004: Touched-spam
            if sig_name == "Touched" and tokens[conn_idx + 1].value != "Once":
                has_debounce = any(
                    k in expanded_vals
                    for k in ("debounce", "Debounce", "cooldown", "Cooldown", "hitMap", "hitTargets", "hitPlayers", "lastTouch", "clock", "tick")
                )
                if not has_debounce:
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-PERF-004",
                            severity="CRITICAL",
                            domain="luau",
                            file=path,
                            line=cb_line,
                            evidence=line_snippet(cb_line),
                            why_it_matters="Undebounced `.Touched:Connect()` fires repeatedly on every limb contact, multiplying damage/currency grants and server load.",
                            fix="Use `Workspace:GetPartsInPart` / `Shapecast` for hitboxes, or add per-target timestamp debounce and disconnect cleanup.",
                        )
                    )
                else:
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-PERF-004",
                            severity="MAJOR",
                            domain="luau",
                            file=path,
                            line=cb_line,
                            evidence=line_snippet(cb_line),
                            why_it_matters="`.Touched` is physics-step unreliable for fast projectiles/melee and sensitive to client network ownership.",
                            fix="Prefer `Workspace:Shapecast` or `GetPartsInPart` with server-side range checks for combat/pickup detection.",
                        )
                    )

            # LUAU-MEM-001: Connection memory leaks
            # Flag :Connect() inside loops OR nested inside transient callbacks (PlayerAdded/CharacterAdded/Equipped/etc.)
            # unless stored/managed and paired with cleanup!
            if tokens[conn_idx + 1].value != "Once":
                in_loop = in_any_loop(conn_idx)
                parent_transient = [
                    p_sig
                    for p_idx, p_lo, p_hi, p_sig, _ in connect_callbacks
                    if p_idx != conn_idx and p_lo < conn_idx < p_hi and p_sig in ("PlayerAdded", "CharacterAdded", "Equipped", "OnServerEvent", "InputBegan", "Touched")
                ]
                if in_loop or parent_transient:
                    # Scan backward across the current statement (handles multi-line assignments / table.insert)
                    stmt_tokens: List[str] = []
                    for k in range(conn_idx - 1, max(-1, conn_idx - 18), -1):
                        kv = tokens[k].value
                        if kv in ("then", "do", "end", ";", "repeat", "until"):
                            break
                        stmt_tokens.append(kv)
                    is_captured = any(
                        m in stmt_tokens for m in ("=", "insert", "GiveTask", "Add", "AddPromise")
                    )
                    if not is_captured or not file_has_cleanup:
                        findings.append(
                            _make_finding(
                                rule_id="LUAU-MEM-001",
                                severity="CRITICAL",
                                domain="luau",
                                file=path,
                                line=cb_line,
                                evidence=line_snippet(cb_line) + (f" (nested in {parent_transient[0]})" if parent_transient else " (inside loop)"),
                                why_it_matters="Leaked RBXScriptConnections inside loops or per-player/character callbacks accumulate memory and retain dead Instances across respawns/rejoins.",
                                fix="Store connections in a Maid/Janitor or per-player table and call `:Disconnect()` on `CharacterRemoving` / `PlayerRemoving` / `Destroying`.",
                            )
                        )

        # Check `OnServerInvoke = ...` assignments
        for i, tok in enumerate(tokens):
            if tok.value == "OnServerInvoke" and i + 1 < n and tokens[i + 1].value == "=":
                cb_start, cb_end = i + 2, min(n - 1, i + 150)
                params: List[str] = []
                if i + 2 < n and tokens[i + 2].value == "function" and (i + 2) in fn_by_start:
                    fb = fn_by_start[i + 2]
                    cb_start, cb_end = fb.start_idx, fb.end_idx
                    params = self._extract_fn_params(tokens, fb.start_idx, paren_pairs)
                elif i + 2 < n and tokens[i + 2].kind == "IDENT" and tokens[i + 2].value in fn_map:
                    cb_start, cb_end, params = fn_map[tokens[i + 2].value]
                cb_slice = tokens[cb_start : cb_end + 1]
                extra_params = [p for idx_p, p in enumerate(params) if idx_p > 0]
                if extra_params and not _has_remote_validation_call(cb_slice):
                    findings.append(
                        _make_finding(
                            rule_id="LUAU-SEC-003",
                            severity="BLOCKER",
                            domain="luau",
                            file=path,
                            line=tok.line,
                            evidence=line_snippet(tok.line),
                            why_it_matters="RemoteFunction.OnServerInvoke callback does not validate client-supplied arguments.",
                            fix="Validate all argument types, finite numbers, and per-player cooldowns at the top of `OnServerInvoke`.",
                        )
                    )

        # 5. LUAU-ECO-003: Missing BindToClose when DataStore is used
        if has_datastore_usage and not has_bind_to_close:
            findings.append(
                _make_finding(
                    rule_id="LUAU-ECO-003",
                    severity="CRITICAL",
                    domain="luau",
                    file=path,
                    line=1,
                    evidence="DataStoreService calls detected without `game:BindToClose(...)` handler",
                    why_it_matters="Without `game:BindToClose`, server shutdowns terminate before pending DataStore saves flush, causing item/progress rollback on rejoin.",
                    fix="Register `game:BindToClose(function() ... end)` to flush and release all active player session locks before shutdown.",
                )
            )

        # 6. LUAU-MEM-002: PlayerAdded without PlayerRemoving cleanup
        has_player_added = any(t.value == "PlayerAdded" for t in tokens)
        if has_player_added and not file_has_player_removing:
            findings.append(
                _make_finding(
                    rule_id="LUAU-MEM-002",
                    severity="MAJOR",
                    domain="luau",
                    file=path,
                    line=1,
                    evidence="`Players.PlayerAdded` connected without `Players.PlayerRemoving` cleanup",
                    why_it_matters="Per-player state tables, rate-limit buckets, and tracks leak indefinitely in long-running servers unless cleaned on `PlayerRemoving`.",
                    fix="Bind `Players.PlayerRemoving` to clear per-player state, connections, and token buckets.",
                )
            )

        # 7. LUAU-GUI-001: TextScaled without UITextSizeConstraint in Luau source
        if has_text_scaled and not has_text_size_constraint:
            findings.append(
                _make_finding(
                    rule_id="GUI-TEXT-001",
                    severity="MAJOR",
                    domain="gui",
                    file=path,
                    line=1,
                    evidence="`TextScaled = true` set without `UITextSizeConstraint`",
                    why_it_matters="Unconstrained `TextScaled` balloons single-word labels to unreadable sizes on 4K displays and clips on mobile.",
                    fix="Attach a `UITextSizeConstraint` (`MinTextSize = 12, MaxTextSize = ...`) to every `TextScaled` element.",
                    auto_fixable=True,
                )
            )

        # 8. Container placement hints from path string
        norm_path = path.replace("\\", "/").lower()
        if "serverstorage/" in norm_path and norm_path.endswith(".server.luau"):
            findings.append(
                _make_finding(
                    rule_id="LUAU-ARCH-002",
                    severity="BLOCKER",
                    domain="luau",
                    file=path,
                    line=1,
                    evidence=f"Server Script located under ServerStorage: `{path}`",
                    why_it_matters="Scripts inside ServerStorage NEVER execute in Roblox.",
                    fix="Move executable server Scripts to `ServerScriptService`.",
                )
            )
        if any(seg in norm_path for seg in ("replicatedstorage/", "workspace/", "startergui/", "starterplayer/")):
            token_vals = {t.value for t in tokens}
            if "DataStoreService" in token_vals or "ProcessReceipt" in token_vals or "GetSecret" in token_vals:
                findings.append(
                    _make_finding(
                        rule_id="LUAU-ARCH-003",
                        severity="BLOCKER",
                        domain="luau",
                        file=path,
                        line=1,
                        evidence=f"Server-only API (`DataStoreService`/`ProcessReceipt`/`GetSecret`) inside replicated path `{path}`",
                        why_it_matters="All scripts and ModuleScripts inside replicated containers can be decompiled by exploiters.",
                        fix="Move server logic and secrets into `ServerScriptService` or `ServerStorage`.",
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # GUI, Animation, World, Plan/State & Cross-Check Audits
    # ------------------------------------------------------------------

    def _audit_gui(
        self,
        *,
        gui_spec: Optional[Dict[str, Any]] = None,
        design_lint: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []

        if isinstance(gui_spec, dict):
            viewport = gui_spec.get("viewport") or {"x": 1280, "y": 720}
            vw = float(viewport.get("x", 1280) or 1280)
            vh = float(viewport.get("y", 720) or 720)
            screen_guis = gui_spec.get("screen_guis") or gui_spec.get("screens") or []
            seen_orders: Dict[int, str] = {}
            total_canvas_groups = int(gui_spec.get("canvas_group_count", 0) or 0)

            for sg in screen_guis:
                if not isinstance(sg, dict):
                    continue
                sg_name = str(sg.get("name", "ScreenGui"))
                insets = str(sg.get("ScreenInsets") or sg.get("screen_insets") or "CoreUISafeInsets")
                z_beh = str(sg.get("ZIndexBehavior") or sg.get("zindex_behavior") or "Sibling")
                disp_order = sg.get("DisplayOrder", sg.get("display_order"))
                has_canvas = bool(sg.get("has_canvas_group")) or int(sg.get("canvas_groups", 0) or 0) > 0
                total_canvas_groups += int(sg.get("canvas_groups", 0) or 0)

                if disp_order is not None:
                    d_int = int(disp_order)
                    if d_int in seen_orders:
                        findings.append(
                            _make_finding(
                                rule_id="GUI-SAFE-002",
                                severity="MAJOR",
                                domain="gui",
                                evidence=f"Duplicate DisplayOrder={d_int} on '{sg_name}' and '{seen_orders[d_int]}'",
                                why_it_matters="Colliding DisplayOrders cause non-deterministic modal/HUD z-fighting.",
                                fix="Assign strictly unique DisplayOrder values per ScreenGui layer.",
                                auto_fixable=True,
                            )
                        )
                    else:
                        seen_orders[d_int] = sg_name

                if z_beh != "Sibling":
                    findings.append(
                        _make_finding(
                            rule_id="GUI-SAFE-003",
                            severity="BLOCKER" if has_canvas else "MAJOR",
                            domain="gui",
                            evidence=f"ScreenGui '{sg_name}' uses ZIndexBehavior={z_beh}",
                            why_it_matters="Global ZIndexBehavior breaks nested modal layering and is incompatible with CanvasGroup composition.",
                            fix="Set `ScreenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling` everywhere.",
                            auto_fixable=True,
                        )
                    )

                if insets == "None" and not bool(sg.get("is_full_bleed_backdrop", False)):
                    findings.append(
                        _make_finding(
                            rule_id="GUI-SAFE-001",
                            severity="CRITICAL",
                            domain="gui",
                            evidence=f"Interactive ScreenGui '{sg_name}' uses ScreenInsets=None",
                            why_it_matters="ScreenInsets=None places interactive controls under the Roblox Topbar / mobile notch.",
                            fix="Use `Enum.ScreenInsets.CoreUISafeInsets` for HUDs and `DeviceSafeInsets` for modals.",
                            auto_fixable=True,
                        )
                    )

                for ctrl in sg.get("controls") or sg.get("elements") or []:
                    if not isinstance(ctrl, dict):
                        continue
                    cname = str(ctrl.get("name", "Control"))
                    w = float(ctrl.get("width", 48) or 48)
                    h = float(ctrl.get("height", 48) or 48)
                    is_interactive = bool(ctrl.get("interactive", ctrl.get("class") in ("TextButton", "ImageButton", "TextBox")))
                    if is_interactive and (w < 44.0 or h < 44.0):
                        findings.append(
                            _make_finding(
                                rule_id="GUI-TOUCH-001",
                                severity="BLOCKER",
                                domain="gui",
                                evidence=f"Interactive control '{sg_name}.{cname}' size={w:.0f}x{h:.0f}px (<44x44px)",
                                why_it_matters="Controls under 44x44px fail mobile touch ergonomics and cause frequent mis-taps.",
                                fix="Enforce minimum 44x44px hit box (with UISizeConstraint MinSize = 44,44).",
                                auto_fixable=True,
                            )
                        )
                    if is_interactive and "x" in ctrl and "y" in ctrl:
                        cx = float(ctrl["x"])
                        cy = float(ctrl["y"])
                        in_thumbstick = cx < (vw * 0.28) and (cy + h) > (vh * 0.60)
                        in_jump = (cx + w) > (vw * 0.80) and (cy + h) > (vh * 0.64)
                        if in_thumbstick or in_jump:
                            zone = "left thumbstick" if in_thumbstick else "right jump button"
                            findings.append(
                                _make_finding(
                                    rule_id="GUI-MOBILE-001",
                                    severity="MAJOR",
                                    domain="gui",
                                    evidence=f"'{sg_name}.{cname}' at ({cx:.0f},{cy:.0f} {w:.0f}x{h:.0f}) enters mobile {zone} zone",
                                    why_it_matters="HUD buttons inside thumbstick/jump zones are covered by Roblox mobile touch controls.",
                                    fix="Anchor persistent HUD actions away from bottom-left (<28% W, >60% H) and bottom-right (>80% W, >64% H).",
                                )
                            )
                    if ctrl.get("text_scaled") and not ctrl.get("has_text_size_constraint", True):
                        findings.append(
                            _make_finding(
                                rule_id="GUI-TEXT-001",
                                severity="MAJOR",
                                domain="gui",
                                evidence=f"'{sg_name}.{cname}' has TextScaled=true without UITextSizeConstraint",
                                why_it_matters="Unbounded TextScaled breaks visual hierarchy across phone vs desktop screens.",
                                fix="Add `UITextSizeConstraint` with explicit MinTextSize and MaxTextSize.",
                                auto_fixable=True,
                            )
                        )
                    fg = ctrl.get("fg_hex") or ctrl.get("text_color")
                    bg = ctrl.get("bg_hex") or ctrl.get("background_color")
                    if fg and bg:
                        ratio = _wcag_contrast(str(fg), str(bg))
                        min_ratio = 3.0 if ctrl.get("large_or_icon") else 4.5
                        if ratio is not None and ratio < min_ratio:
                            findings.append(
                                _make_finding(
                                    rule_id="GUI-CONTRAST-001",
                                    severity="CRITICAL",
                                    domain="gui",
                                    evidence=f"'{sg_name}.{cname}' contrast {ratio:.2f}:1 ({fg} on {bg}) < {min_ratio:.1f}:1",
                                    why_it_matters="Low text/icon contrast fails WCAG readability on mobile sunlight and compressed video.",
                                    fix="Adjust foreground/background luminance to reach >= 4.5:1 for text (3.0:1 for large icons).",
                                    auto_fixable=True,
                                )
                            )

            if total_canvas_groups > 6 or gui_spec.get("canvas_group_in_scrolling_frame"):
                findings.append(
                    _make_finding(
                        rule_id="GUI-PERF-001",
                        severity="CRITICAL",
                        domain="gui",
                        evidence=f"CanvasGroup count={total_canvas_groups} (limit 6), inScrollingFrame={bool(gui_spec.get('canvas_group_in_scrolling_frame'))}",
                        why_it_matters="Excess CanvasGroups exhaust mobile VRAM and silently render completely blank on low QualityLevel.",
                        fix="Use CanvasGroup solely for whole-modal fade transitions (<=6 total), never inside ScrollingFrame items.",
                    )
                )

        # Ingest design-lint JSON from DesignEngine.lint_design
        if isinstance(design_lint, dict):
            raw_issues = design_lint.get("findings") or design_lint.get("issues") or design_lint.get("defects") or []
            for idx, item in enumerate(raw_issues):
                if isinstance(item, dict):
                    raw_sev = str(item.get("severity", "MAJOR")).upper()
                    mapped_sev = raw_sev if raw_sev in SEVERITIES else ("CRITICAL" if raw_sev in ("ERROR", "HIGH") else "MAJOR")
                    findings.append(
                        _make_finding(
                            rule_id=str(item.get("id") or f"GUI-SLOP-{idx + 1:03d}"),
                            severity=mapped_sev,
                            domain="gui",
                            evidence=str(item.get("evidence") or item.get("message") or item.get("detail") or json.dumps(item)),
                            why_it_matters=str(item.get("why_it_matters") or "Generic/flat AI-slop UI degrades game readability, visual identity, and mobile conversion."),
                            fix=str(item.get("fix") or item.get("recommendation") or "Apply a unique seeded design palette with glossy gradients, outer/inner strokes, and proper spacing."),
                            auto_fixable=bool(item.get("auto_fixable", False)),
                        )
                    )
            if design_lint.get("ok") is False and not raw_issues:
                findings.append(
                    _make_finding(
                        rule_id="GUI-SLOP-001",
                        severity="CRITICAL",
                        domain="gui",
                        evidence=str(design_lint.get("error") or "Design lint reported failure"),
                        why_it_matters="Design-system lint gate failed.",
                        fix="Fix anti-slop lint issues via `sharp_design_system` before continuing.",
                    )
                )

        return findings

    def _audit_animation(
        self,
        *,
        anim_clips: Optional[Dict[str, Any] | List[Dict[str, Any]]] = None,
        anim_analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []

        if isinstance(anim_analysis, dict):
            reports = anim_analysis.get("clips") if isinstance(anim_analysis.get("clips"), list) else [anim_analysis]
            for rep in reports:
                if not isinstance(rep, dict):
                    continue
                cname = str(rep.get("clip_name") or rep.get("name") or "clip")
                seam_delta = rep.get("loop_seam_delta")
                if rep.get("loop") and seam_delta is not None and float(seam_delta) > 5.0:
                    findings.append(
                        _make_finding(
                            rule_id="ANIM-SEAM-001",
                            severity="MAJOR",
                            domain="animation",
                            evidence=f"Clip '{cname}' loop_seam_delta={float(seam_delta):.2f} (> 5.0)",
                            why_it_matters="Large pose discontinuity between the last and first keyframes creates visible snap pops on every loop cycle.",
                            fix="Match final keyframe pose smoothly to frame 0 for all looping animations.",
                            auto_fixable=True,
                        )
                    )
                for issue in rep.get("issues") or rep.get("warnings") or []:
                    msg = str(issue)
                    sev = "CRITICAL" if ("leak" in msg.lower() or "humanoid" in msg.lower()) else "MAJOR"
                    findings.append(
                        _make_finding(
                            rule_id="ANIM-QUAL-001",
                            severity=sev,
                            domain="animation",
                            evidence=f"Clip '{cname}': {msg}",
                            why_it_matters="Animation quality defects cause robotic snapping, priority fights, or track leaks.",
                            fix="Correct easing/anticipation/priority and cache tracks on Animator.",
                        )
                    )

        clip_list: List[Dict[str, Any]] = []
        if isinstance(anim_clips, list):
            clip_list = [c for c in anim_clips if isinstance(c, dict)]
        elif isinstance(anim_clips, dict):
            if isinstance(anim_clips.get("clips"), dict):
                clip_list = [v for v in anim_clips["clips"].values() if isinstance(v, dict)]
            else:
                clip_list = [anim_clips]

        valid_priorities = {"Core", "Idle", "Movement", "Action", "Action2", "Action3", "Action4"}
        action4_count = 0
        for c in clip_list:
            cname = str(c.get("name", "clip"))
            prio = c.get("priority")
            if prio not in valid_priorities:
                findings.append(
                    _make_finding(
                        rule_id="ANIM-PRIO-001",
                        severity="MAJOR",
                        domain="animation",
                        evidence=f"Clip '{cname}' has invalid/missing AnimationPriority '{prio}'",
                        why_it_matters="Invalid or default Core priority causes idle/walk tracks to override combat and emote animations.",
                        fix="Set explicit Enum.AnimationPriority (e.g. Idle, Movement, Action, Action2).",
                        auto_fixable=True,
                    )
                )
            elif prio == "Action4":
                action4_count += 1
            elif prio in ("Core", "Idle") and any(w in cname.lower() for w in ("attack", "slash", "swing", "shoot", "block", "hit")):
                findings.append(
                    _make_finding(
                        rule_id="ANIM-PRIO-002",
                        severity="MAJOR",
                        domain="animation",
                        evidence=f"Action clip '{cname}' uses low priority '{prio}'",
                        why_it_matters="Combat/action clips at Core/Idle priority get overridden by default Animate locomotion.",
                        fix="Set combat clips to `Action` or `Action2`.",
                        auto_fixable=True,
                    )
                )

            frames = c.get("frames") or []
            if c.get("loop") and len(frames) >= 2:
                first_p = frames[0].get("poses") or {}
                last_p = frames[-1].get("poses") or {}
                max_diff = 0.0
                for jname in set(first_p.keys()) | set(last_p.keys()):
                    r1 = first_p.get(jname, {}).get("rot_deg") or first_p.get(jname, {}).get("rot") or []
                    r2 = last_p.get(jname, {}).get("rot_deg") or last_p.get(jname, {}).get("rot") or []
                    if len(r1) == len(r2) and r1:
                        max_diff = max(max_diff, max(abs(float(a) - float(b)) for a, b in zip(r1, r2, strict=True)))
                threshold = 5.0 if (first_p and any("rot_deg" in v for v in first_p.values() if isinstance(v, dict))) else 0.15
                if max_diff > threshold:
                    findings.append(
                        _make_finding(
                            rule_id="ANIM-SEAM-001",
                            severity="MAJOR",
                            domain="animation",
                            evidence=f"Looping clip '{cname}' start/end pose delta={max_diff:.3f} (> {threshold})",
                            why_it_matters="Non-matching start and end poses cause visible popping on loop wrap.",
                            fix="Make final keyframe match frame 0 pose cleanly.",
                            auto_fixable=True,
                        )
                    )

        if len(clip_list) >= 3 and action4_count == len(clip_list):
            findings.append(
                _make_finding(
                    rule_id="ANIM-PRIO-003",
                    severity="MAJOR",
                    domain="animation",
                    evidence=f"All {action4_count} clips use top priority Action4",
                    why_it_matters="Putting every animation on Action4 prevents hit-reacts, emotes, or upper-body equips from layering cleanly.",
                    fix="Reserve Action4 for highest-priority overrides (stun/death) and layer locomotion/actions on Movement/Action/Action2.",
                )
            )

        return findings

    @staticmethod
    def _unwrap_world_stats(world_stats: Any) -> Optional[Dict[str, Any]]:
        cur: Any = world_stats
        metric_keys = {
            "overlap_count", "overlapCount", "remainingOverlapCount",
            "floating_count", "floatingCount", "remainingFloatingCount",
            "part_count", "partCount", "spawn_location_count", "spawnLocationCount",
            "placements", "allClean",
        }
        for _ in range(6):
            if isinstance(cur, str):
                try:
                    cur = json.loads(cur)
                except (ValueError, TypeError):
                    return None
            if not isinstance(cur, dict):
                return None
            if any(k in cur for k in metric_keys):
                return cur
            next_val = None
            for wrapper_key in ("result", "decoded", "data", "bridgeResponse", "upstreamResponse", "world_stats"):
                if cur.get(wrapper_key) is not None:
                    next_val = cur.get(wrapper_key)
                    break
            if next_val is None:
                return cur
            cur = next_val
        return cur if isinstance(cur, dict) else None

    def _audit_world(
        self,
        *,
        world_stats: Optional[Dict[str, Any]] = None,
        plan_data: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        world_stats = self._unwrap_world_stats(world_stats)
        if not isinstance(world_stats, dict):
            return findings

        budget = (plan_data or {}).get("asset_budget") or {}
        max_parts = int(budget.get("max_workspace_parts", 15000) or 15000)
        part_count = int(world_stats.get("part_count", world_stats.get("partCount", 0)) or 0)
        precise_count = int(world_stats.get("precise_collision_count", world_stats.get("preciseCollisionCount", 0)) or 0)
        unanchored_count = int(world_stats.get("unanchored_count", world_stats.get("unanchoredCount", 0)) or 0)
        streaming_enabled = world_stats.get("streaming_enabled", world_stats.get("streamingEnabled"))
        spawn_count = world_stats.get("spawn_location_count", world_stats.get("spawnLocationCount"))

        if part_count > max_parts:
            findings.append(
                _make_finding(
                    rule_id="WORLD-BUDGET-001",
                    severity="CRITICAL",
                    domain="world",
                    evidence=f"Workspace BasePart count={part_count} exceeds budget={max_parts}",
                    why_it_matters="Excessive BaseParts blow mobile RAM, draw-call budgets, and streaming bandwidth.",
                    fix="Merge static detail into MeshParts, reduce scatter density, and enable StreamingEnabled.",
                )
            )
        if precise_count > 10:
            findings.append(
                _make_finding(
                    rule_id="WORLD-COL-001",
                    severity="MAJOR",
                    domain="world",
                    evidence=f"{precise_count} MeshParts/Unions use PreciseConvexDecomposition collision fidelity",
                    why_it_matters="PreciseConvexDecomposition on scattered/non-walkable props severely inflates physics solver CPU and memory.",
                    fix="Set CollisionFidelity=Box or Hull for props and CanCollide=false on decorative details.",
                    auto_fixable=True,
                )
            )
        if streaming_enabled is False and part_count > 1500:
            findings.append(
                _make_finding(
                    rule_id="WORLD-STREAM-001",
                    severity="CRITICAL",
                    domain="world",
                    evidence=f"Workspace.StreamingEnabled=false with {part_count} parts",
                    why_it_matters="Loading all geometry upfront stalls join times and causes out-of-memory crashes on phones.",
                    fix="Enable Workspace.StreamingEnabled = true and guard client scripts for streamed-out instances.",
                )
            )
        if unanchored_count > 25:
            findings.append(
                _make_finding(
                    rule_id="WORLD-PHYS-001",
                    severity="MAJOR",
                    domain="world",
                    evidence=f"{unanchored_count} unanchored BaseParts detected in Workspace",
                    why_it_matters="Unanchored parts fall through maps or become client-network-owned fling exploits.",
                    fix="Anchor all static architecture (`Anchored = true`) and call `SetNetworkOwner(nil)` on server-owned dynamic assemblies.",
                )
            )
        if spawn_count is not None and int(spawn_count) == 0:
            findings.append(
                _make_finding(
                    rule_id="WORLD-SPAWN-001",
                    severity="CRITICAL",
                    domain="world",
                    evidence="Zero SpawnLocation instances in Workspace",
                    why_it_matters="Players may spawn at (0,0,0) in void or inside terrain without a SpawnLocation.",
                    fix="Place an anchored SpawnLocation above ground inside valid playable bounds.",
                )
            )

        overlap_count = world_stats.get(
            "overlap_count",
            world_stats.get("overlapCount", world_stats.get("remainingOverlapCount")),
        )
        floating_count = int(
            world_stats.get(
                "floating_count",
                world_stats.get("floatingCount", world_stats.get("remainingFloatingCount", 0)),
            )
            or 0
        )
        placements = world_stats.get("placements")
        if isinstance(placements, list) and len(placements) >= 2:
            # Offline 3D AABB/box overlap verification between placed assets/buildings
            detected_overlaps: List[str] = []
            tol = float(world_stats.get("overlap_tolerance_studs", 0.15) or 0.15)
            for idx_i in range(len(placements)):
                a = placements[idx_i] if isinstance(placements[idx_i], dict) else {}
                pa = a.get("pos") or a.get("position") or a.get("center")
                sa = a.get("size")
                if not isinstance(pa, (list, tuple)) or not isinstance(sa, (list, tuple)) or len(pa) != 3 or len(sa) != 3:
                    continue
                for idx_j in range(idx_i + 1, len(placements)):
                    b = placements[idx_j] if isinstance(placements[idx_j], dict) else {}
                    pb = b.get("pos") or b.get("position") or b.get("center")
                    sb = b.get("size")
                    if not isinstance(pb, (list, tuple)) or not isinstance(sb, (list, tuple)) or len(pb) != 3 or len(sb) != 3:
                        continue
                    dx = abs(float(pa[0]) - float(pb[0])) - (float(sa[0]) + float(sb[0])) * 0.5
                    dy = abs(float(pa[1]) - float(pb[1])) - (float(sa[1]) + float(sb[1])) * 0.5
                    dz = abs(float(pa[2]) - float(pb[2])) - (float(sa[2]) + float(sb[2])) * 0.5
                    if dx < -tol and dy < -tol and dz < -tol:
                        pen = round(min(-dx, -dy, -dz), 3)
                        detected_overlaps.append(f"{a.get('name', idx_i)}<->{b.get('name', idx_j)} (pen={pen})")
            if detected_overlaps:
                overlap_count = max(int(overlap_count or 0), len(detected_overlaps))
        if overlap_count is not None and int(overlap_count) > 0:
            findings.append(
                _make_finding(
                    rule_id="WORLD-OVERLAP-001",
                    severity="CRITICAL",
                    domain="world",
                    evidence=f"Detected {int(overlap_count)} overlapping/clipping map asset pair(s) exceeding tolerance.",
                    why_it_matters="Interpenetrating map buildings/props cause Z-fighting, stuck players, and broken physics collisions.",
                    fix="Run `sharp_world_assembly_and_optimization(action='audit_overlaps')` then `'fix_overlaps'` before advancing.",
                    auto_fixable=True,
                )
            )
        if floating_count > 0:
            findings.append(
                _make_finding(
                    rule_id="WORLD-FLOAT-001",
                    severity="MAJOR",
                    domain="world",
                    evidence=f"Detected {floating_count} floating/ungrounded world prop(s).",
                    why_it_matters="Floating geometry destroys spatial immersion and breaks NPC pathfinding assumptions.",
                    fix="Raycast prop bases cleanly down to terrain/floor surfaces.",
                    auto_fixable=True,
                )
            )
        return findings

    def _audit_plan_and_cross_checks(
        self,
        *,
        project_library: Optional[Any] = None,
        plan_data: Optional[Dict[str, Any]] = None,
        game_state: Optional[Dict[str, Any]] = None,
        asset_manifest: Optional[Dict[str, Any]] = None,
        scanned_sources: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []

        if project_library is not None:
            if plan_data is None:
                plan_data = project_library.load_plan()
            if game_state is None:
                game_state = project_library.load_state()
            if asset_manifest is None:
                asset_manifest = project_library.load_manifest()

        # PLAN-001: Missing structured plan
        if not isinstance(plan_data, dict) or not plan_data.get("title"):
            findings.append(
                _make_finding(
                    rule_id="PLAN-001",
                    severity="BLOCKER",
                    domain="plan",
                    evidence="plan.json missing or empty in project directory",
                    why_it_matters="Building without a scoped plan, MVP gate, cut list, and asset budget causes feature sprawl and broken dependencies.",
                    fix="Run `sharp_game_plan(action='create', ...)` first to establish the MVP scope, DAG, and stage gates.",
                )
            )
            return findings

        state = game_state if isinstance(game_state, dict) else {}
        manifest = asset_manifest if isinstance(asset_manifest, dict) else {}
        assets = manifest.get("assets") if isinstance(manifest.get("assets"), dict) else {}
        active_systems = state.get("systems") if isinstance(state.get("systems"), dict) else {}

        # PLAN-002: Stage gates skipped & MVP-first lock violations
        stages = state.get("planner_stages") or plan_data.get("stages") or []
        stage_status_by_id: Dict[str, Dict[str, Any]] = {}
        mvp_steps_done: Set[str] = set()
        for st in stages:
            if not isinstance(st, dict):
                continue
            sid = str(st.get("stage_id", ""))
            stage_status_by_id[sid] = st
            for step in st.get("steps") or []:
                if isinstance(step, dict) and step.get("completed"):
                    mvp_steps_done.add(str(step.get("step_id", "")))

        mvp_green = all(req in mvp_steps_done for req in ("S0.1", "S1.1", "S2.1", "S4.1"))
        for locked_stage in ("S3", "S5", "S6", "S7"):
            st = stage_status_by_id.get(locked_stage)
            if st and (st.get("status") in ("completed", "in_progress") or any(s.get("completed") for s in (st.get("steps") or []))):
                if not mvp_green:
                    findings.append(
                        _make_finding(
                            rule_id="PLAN-002",
                            severity="BLOCKER",
                            domain="plan",
                            evidence=f"Stage {locked_stage} progressed while MVP steps (S0.1, S1.1, S2.1, S4.1) are incomplete: done={sorted(mvp_steps_done)}",
                            why_it_matters="Skipping MVP foundation/greybox/core-loop/minimal-HUD gates breaks vertical slice playability and hides early blockers.",
                            fix="Complete and audit S0, S1, S2, and minimal S4 HUD (S4.1) before executing S3/S5/S6.",
                        )
                    )

        # Check hard sequential order across S0 -> S1 -> S2 -> S4.1 -> S3 -> S4.2 -> S5 -> S6 -> S7
        ordered_checks = ["S0.1", "S1.1", "S2.1", "S4.1", "S3.1", "S4.2", "S5.1", "S6.1", "S7.1"]
        for idx, step_id in enumerate(ordered_checks):
            if step_id in mvp_steps_done:
                missing_prior = [p for p in ordered_checks[:idx] if p not in mvp_steps_done]
                if missing_prior:
                    findings.append(
                        _make_finding(
                            rule_id="PLAN-002",
                            severity="BLOCKER",
                            domain="plan",
                            evidence=f"Step {step_id} marked complete out of order; missing prior steps {missing_prior}",
                            why_it_matters="Skipping dependency gates violates build order and invalidates downstream verification.",
                            fix=f"Complete prerequisite steps {missing_prior} first via `sharp_game_plan`.",
                        )
                    )
                    break

        # PLAN-003: Assets required by plan not registered in asset_manifest.json
        budget = plan_data.get("asset_budget") or {}
        req_assets = budget.get("required_assets") or []
        for req in req_assets:
            if not isinstance(req, dict):
                continue
            req_stage = str(req.get("stage", "S0"))
            req_cats = set(req.get("categories") or ([req["category"]] if req.get("category") else []))
            req_key = req.get("key")
            st_obj = stage_status_by_id.get(req_stage, {})
            # Enforce when the stage is marked completed (never prematurely fail a stage before it's built)
            if st_obj.get("status") == "completed":
                matched = False
                if req_key and req_key in assets:
                    entry = assets[req_key]
                    matched = bool(entry.get("roblox_asset_id") or entry.get("local_path"))
                elif req_cats:
                    matched = any(
                        a.get("category") in req_cats and (a.get("roblox_asset_id") or a.get("local_path"))
                        for a in assets.values()
                        if isinstance(a, dict)
                    )
                if not matched:
                    findings.append(
                        _make_finding(
                            rule_id="PLAN-003",
                            severity="CRITICAL",
                            domain="plan",
                            evidence=f"Planned asset (stage={req_stage}, categories={sorted(req_cats)}, key={req_key}) missing or unregistered in asset_manifest.json",
                            why_it_matters="Unregistered assets cause missing MeshIds/AnimationIds/ImageIds and break SharpAssetRegistry.luau sync.",
                            fix="Register the asset via `sharp_game_library(action='register_asset', ...)` with a valid local_path or roblox_asset_id.",
                        )
                    )

        # PLAN-004: Version drift & registry sync checks
        if project_library is not None:
            history = project_library.load_plan_history()
            cur_ver = int(state.get("current_version", 0) or 0)
            if cur_ver > 0:
                if not history or int(history[-1].get("version", -1)) != cur_ver:
                    findings.append(
                        _make_finding(
                            rule_id="PLAN-004",
                            severity="MAJOR",
                            domain="plan",
                            evidence=f"Version drift: game_state current_version={cur_ver}, plan_history latest={history[-1].get('version') if history else 'none'}",
                            why_it_matters="Out-of-sync version history prevents safe rollback after faulty edits.",
                            fix="Take a fresh snapshot via `sharp_game_library(action='snapshot')`.",
                        )
                    )
                snap_file = project_library.snapshots_dir / f"v{cur_ver:04d}.json"
                if not snap_file.exists():
                    findings.append(
                        _make_finding(
                            rule_id="PLAN-004",
                            severity="MAJOR",
                            domain="plan",
                            evidence=f"Missing snapshot file for current version v{cur_ver:04d}",
                            why_it_matters="Rollback to current version will fail if snapshot JSON is absent.",
                            fix="Record a new snapshot via `sharp_game_library(action='snapshot')`.",
                        )
                    )
            if project_library.luau_registry_path.exists() and assets:
                reg_text = project_library.luau_registry_path.read_text(encoding="utf-8", errors="replace")
                missing_keys = [k for k in assets if k not in reg_text]
                if missing_keys:
                    findings.append(
                        _make_finding(
                            rule_id="PLAN-004",
                            severity="MAJOR",
                            domain="plan",
                            evidence=f"SharpAssetRegistry.luau missing manifest asset keys: {missing_keys[:5]}",
                            why_it_matters="Luau code referencing SharpAssetRegistry will fail to resolve newly registered assets.",
                            fix="Regenerate SharpAssetRegistry.luau via ProjectLibraryManager.",
                            auto_fixable=True,
                        )
                    )

        # XCHK-001: Cross-check plan systems / completed stages vs actual systems & scanned scripts
        joined_sources = "\n".join((scanned_sources or {}).values()).lower()
        dag_nodes = plan_data.get("systems_dependency_dag") or []
        for node in dag_nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", ""))
            node_stage = str(node.get("stage", ""))
            expected_domains = [str(d) for d in (node.get("system_domains") or [node_id])]
            st_obj = stage_status_by_id.get(node_stage, {})
            if st_obj.get("status") == "completed":
                has_sys = any(d in active_systems for d in expected_domains)
                has_code = bool(scanned_sources) and any(
                    kw in joined_sources for kw in (node_id.lower(), *(str(k).lower() for k in (node.get("code_keywords") or [])))
                )
                if not has_sys and not has_code:
                    findings.append(
                        _make_finding(
                            rule_id="XCHK-001",
                            severity="CRITICAL",
                            domain="cross_check",
                            evidence=f"Plan declares completed stage {node_stage} system '{node.get('name', node_id)}' (domains={expected_domains}), but neither game_state.systems nor scanned scripts implement it.",
                            why_it_matters="Claiming a stage is complete without a corresponding implemented system leaves dead/missing gameplay in Studio.",
                            fix=f"Build system `{node_id}` using `{node.get('tool', 'Sharp tool')}` and record execution before marking stage complete.",
                        )
                    )

        # Cross-check explicit `plan["features"]` / `mvp_scope["required_features"]` if provided
        plan_features = plan_data.get("features") or (plan_data.get("mvp_scope") or {}).get("required_features") or []
        if isinstance(plan_features, list):
            active_sys_text = " ".join(str(k).lower() for k in active_systems.keys())
            for feat in plan_features:
                if isinstance(feat, dict):
                    fname = str(feat.get("name") or feat.get("id") or "").strip()
                    fstage = str(feat.get("stage") or "S2")
                    fkeywords = [str(k).lower() for k in (feat.get("keywords") or [fname])]
                    check_needed = stage_status_by_id.get(fstage, {}).get("status") == "completed" or bool(feat.get("required_now"))
                else:
                    fname = str(feat).strip()
                    fkeywords = [fname.lower()]
                    check_needed = bool(fname) and (mvp_green or any(st.get("status") == "completed" for st in stage_status_by_id.values()))
                if fname and check_needed:
                    in_sys = any(kw and kw in active_sys_text for kw in fkeywords)
                    in_code = bool(scanned_sources) and any(kw and kw in joined_sources for kw in fkeywords)
                    if not in_sys and not in_code:
                        findings.append(
                            _make_finding(
                                rule_id="XCHK-001",
                                severity="CRITICAL",
                                domain="cross_check",
                                evidence=f"Plan requires feature '{fname}', but no matching active system or scanned Luau module implements it.",
                                why_it_matters="Unimplemented plan features break acceptance criteria and ship incomplete gameplay loops.",
                                fix=f"Implement '{fname}' and record its domain execution or pass its Luau module in audit sources.",
                            )
                        )

        return findings

    # ------------------------------------------------------------------
    # Public Modes: static, live, challenge, gate
    # ------------------------------------------------------------------

    def audit_static(
        self,
        *,
        luau_sources: Optional[Dict[str, str] | List[Any] | str] = None,
        file_paths: Optional[List[str]] = None,
        gui_spec: Optional[Dict[str, Any]] = None,
        design_lint: Optional[Dict[str, Any]] = None,
        anim_clips: Optional[Dict[str, Any] | List[Dict[str, Any]]] = None,
        anim_analysis: Optional[Dict[str, Any]] = None,
        world_stats: Optional[Dict[str, Any]] = None,
        project_library: Optional[Any] = None,
        plan_data: Optional[Dict[str, Any]] = None,
        game_state: Optional[Dict[str, Any]] = None,
        asset_manifest: Optional[Dict[str, Any]] = None,
        check_plan: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Run offline adversarial tokenizer-based audit across Luau, GUI, animation, world, and plan/state."""
        sources_map = self._normalize_luau_sources(luau_sources=luau_sources, file_paths=file_paths)
        all_tokens_text = " ".join(
            t.value for src in sources_map.values() for t in tokenize_luau(src)[0]
        )
        shared_bind = "BindToClose" in all_tokens_text

        findings: List[Dict[str, Any]] = []
        domains_audited: List[str] = []

        if sources_map:
            domains_audited.append("luau")
            for fpath, src in sources_map.items():
                findings.extend(self._analyze_single_luau_file(fpath, src, shared_bind_to_close_present=shared_bind))

        if gui_spec is not None or design_lint is not None:
            domains_audited.append("gui")
            findings.extend(self._audit_gui(gui_spec=gui_spec, design_lint=design_lint))

        if anim_clips is not None or anim_analysis is not None:
            domains_audited.append("animation")
            findings.extend(self._audit_animation(anim_clips=anim_clips, anim_analysis=anim_analysis))

        if world_stats is not None:
            domains_audited.append("world")
            findings.extend(self._audit_world(world_stats=world_stats, plan_data=plan_data))

        active_lib = project_library if project_library is not None else self.project_library
        has_domain_inputs = any(
            x is not None for x in (luau_sources, file_paths, gui_spec, design_lint, anim_clips, anim_analysis, world_stats)
        )
        should_check_plan = (
            check_plan
            if check_plan is not None
            else (
                plan_data is not None
                or game_state is not None
                or project_library is not None
                or not has_domain_inputs
                or (active_lib is not None and active_lib.load_plan() is not None)
            )
        )
        if should_check_plan:
            domains_audited.extend(["plan", "cross_check"])
            findings.extend(
                self._audit_plan_and_cross_checks(
                    project_library=active_lib,
                    plan_data=plan_data,
                    game_state=game_state,
                    asset_manifest=asset_manifest,
                    scanned_sources=sources_map,
                )
            )

        score, verdict, counts = _score_and_verdict(findings)
        return _sign_audit_report({
            "ok": True,
            "mode": "static",
            "score": score,
            "verdict": verdict,
            "summary": {
                **counts,
                "total": len(findings),
                "scripts_scanned": len(sources_map),
                "domains_audited": sorted(set(domains_audited)),
            },
            "findings": findings,
        })

    def compile_live_audit_luau(
        self,
        *,
        domains: Optional[List[str]] = None,
        run_smoke_test: bool = False,
        include_script_sources: bool = True,
        max_scripts: int = 40,
        max_source_chars: int = 8000,
    ) -> str:
        """Compile read-only Studio Luau audit + telemetry + script inventory via LuauAuditSnapshotEngine."""
        if self.luau_audit_engine is None:
            raise RuntimeError("CriticalAuditEngine requires luau_audit_engine for compile_live_audit_luau().")
        return self.luau_audit_engine.compile_critical_audit_luau(
            domains=domains,
            run_smoke_test=run_smoke_test,
            include_script_sources=include_script_sources,
            max_scripts=max_scripts,
            max_source_chars=max_source_chars,
        )

    def _convert_live_report_findings(
        self,
        decoded: Dict[str, Any],
        *,
        project_library: Optional[Any] = None,
        design_lint: Optional[Dict[str, Any]] = None,
        anim_analysis: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        findings: List[Dict[str, Any]] = []
        reports = decoded.get("reports") or {}

        # 1. luau_security (ArchitectureSecurityAudit)
        sec_rep = reports.get("luau_security")
        if isinstance(sec_rep, dict):
            for item in sec_rep.get("findings") or []:
                if not isinstance(item, dict):
                    continue
                sev_raw = str(item.get("severity", "PASS")).upper()
                if sev_raw == "PASS":
                    continue
                sev = "BLOCKER" if sev_raw == "FAIL" and str(item.get("id", "")).startswith("SEC-0") else (
                    "CRITICAL" if sev_raw == "FAIL" else "MAJOR"
                )
                findings.append(
                    _make_finding(
                        rule_id=f"LIVE-{item.get('id', 'SEC')}",
                        severity=sev,
                        domain="luau",
                        file=str(item.get("path", "")),
                        evidence=str(item.get("message", "")),
                        why_it_matters="Detected in live Studio DataModel security/architecture scan.",
                        fix=str(item.get("recommendation", "Fix finding in Studio Explorer / Script.")),
                    )
                )

        # 2. gui (audit_gui.luau)
        gui_rep = reports.get("gui")
        if isinstance(gui_rep, dict):
            for err in gui_rep.get("errors") or []:
                findings.append(
                    _make_finding(
                        rule_id="LIVE-GUI-ERR",
                        severity="BLOCKER" if "TouchTarget" in str(err) or "CanvasGroup" in str(err) else "CRITICAL",
                        domain="gui",
                        evidence=str(err),
                        why_it_matters="Live GUI layout audit detected an interactive clipping, inset, or touch-target defect.",
                        fix="Adjust ScreenInsets, ZIndexBehavior=Sibling, or UISizeConstraint >= 44x44px.",
                    )
                )
            for warn in gui_rep.get("warnings") or []:
                findings.append(
                    _make_finding(
                        rule_id="LIVE-GUI-WARN",
                        severity="MAJOR",
                        domain="gui",
                        evidence=str(warn),
                        why_it_matters="Live GUI audit flagged layout overlap, DisplayOrder collision, or CanvasGroup budget warning.",
                        fix="Resolve ScreenGui properties or thumb-zone placement.",
                    )
                )

        # 3. environment (audit_environment.luau)
        env_rep = reports.get("environment")
        if isinstance(env_rep, dict):
            for err in env_rep.get("errors") or []:
                findings.append(
                    _make_finding(
                        rule_id="LIVE-WORLD-ERR",
                        severity="CRITICAL",
                        domain="world",
                        evidence=str(err),
                        why_it_matters="Live environment audit reported a broken Atmosphere/Clouds/Terrain/Lighting setup.",
                        fix="Repair environment parenting or Lighting/Terrain properties.",
                    )
                )
            for warn in env_rep.get("warnings") or []:
                findings.append(
                    _make_finding(
                        rule_id="LIVE-WORLD-WARN",
                        severity="MAJOR",
                        domain="world",
                        evidence=str(warn),
                        why_it_matters="Live environment audit flagged visual or streaming/terrain issues.",
                        fix="Tune lighting/atmosphere/streaming settings.",
                    )
                )

        # 4. Telemetry (world + gui)
        telemetry = decoded.get("telemetry") or {}
        if isinstance(telemetry.get("world"), dict):
            findings.extend(
                self._audit_world(
                    world_stats=telemetry["world"],
                    plan_data=(project_library.load_plan() if project_library else None),
                )
            )
        if isinstance(telemetry.get("gui"), dict):
            gt = telemetry["gui"]
            if int(gt.get("textScaledWithoutConstraint", 0) or 0) > 0:
                findings.append(
                    _make_finding(
                        rule_id="GUI-TEXT-001",
                        severity="MAJOR",
                        domain="gui",
                        evidence=f"{gt['textScaledWithoutConstraint']} GUI text elements have TextScaled=true without UITextSizeConstraint in StarterGui",
                        why_it_matters="Unconstrained TextScaled clips on phones or balloons on desktop.",
                        fix="Add UITextSizeConstraint to each TextScaled element.",
                        auto_fixable=True,
                    )
                )
            if int(gt.get("canvasGroupCount", 0) or 0) > 6:
                findings.append(
                    _make_finding(
                        rule_id="GUI-PERF-001",
                        severity="CRITICAL",
                        domain="gui",
                        evidence=f"StarterGui contains {gt['canvasGroupCount']} CanvasGroups (> 6 budget)",
                        why_it_matters="Excess CanvasGroups render blank on low-end mobile GPUs.",
                        fix="Reduce CanvasGroups to modal fade containers only.",
                    )
                )

        # 5. Live extracted scripts analyzed by tokenizer static engine!
        inv = decoded.get("scriptInventory") or {}
        scripts_list = inv.get("scripts") if isinstance(inv, dict) else []
        scripts_map: Dict[str, str] = {}
        if isinstance(scripts_list, list):
            for entry in scripts_list:
                if isinstance(entry, dict) and entry.get("path"):
                    scripts_map[str(entry["path"])] = str(entry.get("source") or "")

        static_merged = self.audit_static(
            luau_sources=scripts_map or None,
            design_lint=design_lint,
            anim_analysis=anim_analysis,
            project_library=project_library,
            check_plan=bool(project_library is not None),
        )
        findings.extend(static_merged["findings"])
        return findings, len(scripts_map)

    def audit_live(
        self,
        *,
        live_report: Optional[Dict[str, Any] | str] = None,
        domains: Optional[List[str]] = None,
        run_smoke_test: bool = False,
        include_script_sources: bool = True,
        max_scripts: int = 40,
        max_source_chars: int = 8000,
        luau_sources: Optional[Dict[str, str] | List[Any] | str] = None,
        gui_spec: Optional[Dict[str, Any]] = None,
        design_lint: Optional[Dict[str, Any]] = None,
        anim_analysis: Optional[Dict[str, Any]] = None,
        project_library: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Compile live Studio audit Luau and merge any live bridge report with static/plan checks."""
        active_lib = project_library if project_library is not None else self.project_library
        compiled_luau: Optional[str] = None
        if self.luau_audit_engine is not None:
            compiled_luau = self.compile_live_audit_luau(
                domains=domains,
                run_smoke_test=run_smoke_test,
                include_script_sources=include_script_sources,
                max_scripts=max_scripts,
                max_source_chars=max_source_chars,
            )

        if live_report is None:
            offline = self.audit_static(
                luau_sources=luau_sources,
                gui_spec=gui_spec,
                design_lint=design_lint,
                anim_analysis=anim_analysis,
                project_library=active_lib,
            )
            return _sign_audit_report({
                **offline,
                "mode": "live",
                "live_executed": False,
                "compiledLuau": compiled_luau,
                "note": "No live Studio report supplied; compiledLuau is ready to execute via Studio bridge and pass back into live_report.",
            })

        decoded: Dict[str, Any]
        if isinstance(live_report, str):
            try:
                decoded = json.loads(live_report)
            except json.JSONDecodeError:
                decoded = {"raw": live_report}
        elif isinstance(live_report, dict):
            decoded = live_report
        else:
            decoded = {}

        # Support unwrapped Studio bridgeResponse envelopes
        if "result" in decoded and isinstance(decoded["result"], str):
            try:
                decoded = json.loads(decoded["result"])
            except json.JSONDecodeError:
                pass

        live_findings, live_scripts_cnt = self._convert_live_report_findings(
            decoded,
            project_library=active_lib,
            design_lint=design_lint,
            anim_analysis=anim_analysis,
        )
        if luau_sources is not None or gui_spec is not None:
            extra = self.audit_static(
                luau_sources=luau_sources,
                gui_spec=gui_spec,
                check_plan=False,
            )
            live_findings.extend(extra["findings"])

        score, verdict, counts = _score_and_verdict(live_findings)
        return _sign_audit_report({
            "ok": True,
            "mode": "live",
            "live_executed": True,
            "score": score,
            "verdict": verdict,
            "summary": {
                **counts,
                "total": len(live_findings),
                "scripts_scanned": live_scripts_cnt,
                "domains_audited": sorted({"luau", "gui", "world", "plan", "cross_check"}),
            },
            "findings": live_findings,
            "compiledLuau": compiled_luau,
        })

    # ------------------------------------------------------------------
    # Challenge Mode ("100 players / phone / after rejoin")
    # ------------------------------------------------------------------

    def challenge(
        self,
        *,
        luau_sources: Optional[Dict[str, str] | List[Any] | str] = None,
        file_paths: Optional[List[str]] = None,
        gui_spec: Optional[Dict[str, Any]] = None,
        design_lint: Optional[Dict[str, Any]] = None,
        anim_clips: Optional[Dict[str, Any] | List[Dict[str, Any]]] = None,
        anim_analysis: Optional[Dict[str, Any]] = None,
        world_stats: Optional[Dict[str, Any]] = None,
        project_library: Optional[Any] = None,
        plan_data: Optional[Dict[str, Any]] = None,
        game_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Produce a skeptic's adversarial failure list across 100 concurrent players, mobile phone, and rejoin."""
        active_lib = project_library if project_library is not None else self.project_library
        static_res = self.audit_static(
            luau_sources=luau_sources,
            file_paths=file_paths,
            gui_spec=gui_spec,
            design_lint=design_lint,
            anim_clips=anim_clips,
            anim_analysis=anim_analysis,
            world_stats=world_stats,
            project_library=active_lib,
            plan_data=plan_data,
            game_state=game_state,
            check_plan=bool(active_lib is not None or plan_data is not None or game_state is not None),
        )
        found_ids = {f["id"] for f in static_res["findings"]}
        sources_map = self._normalize_luau_sources(luau_sources=luau_sources, file_paths=file_paths)
        joined_tokens = " ".join(t.value for s in sources_map.values() for t in tokenize_luau(s)[0])
        plan = plan_data or (active_lib.load_plan() if active_lib else None) or {}
        platforms = [str(p).lower() for p in (plan.get("platforms") or ["desktop", "mobile"])]

        def _scenario(
            cid: str,
            axis: str,
            title: str,
            trigger_rules: Set[str],
            base_sev: str,
            failure_scenario: str,
            verification_test: str,
            mitigation: str,
        ) -> Dict[str, Any]:
            confirmed = bool(found_ids & trigger_rules)
            return {
                "id": cid,
                "axis": axis,
                "severity": "BLOCKER" if confirmed and base_sev == "BLOCKER" else ("CRITICAL" if confirmed else base_sev),
                "confirmed_in_inputs": confirmed,
                "title": title,
                "trigger_evidence": (
                    f"Confirmed by static findings {sorted(found_ids & trigger_rules)}"
                    if confirmed
                    else "Proactive stress probe (verify in Studio multi-client / mobile sim)"
                ),
                "failure_scenario": failure_scenario,
                "verification_test": verification_test,
                "mitigation": mitigation,
            }

        scenarios_100 = [
            _scenario(
                "CHAL-100P-01",
                "100_players",
                "RemoteEvent flood & N^2 FireAllClients broadcast saturation",
                {"LUAU-SEC-003", "LUAU-SEC-004"},
                "CRITICAL",
                "At 100 players, unthrottled OnServerEvent or per-frame FireAllClients causes >50 KB/s per-client server replication saturation and queue drops.",
                "Simulate 20Hz bursts per client and measure Studio Network Receive/Send KB/s.",
                "Enforce per-player token buckets via SafeRemoteGateway and spatial relevance filtering instead of FireAllClients.",
            ),
            _scenario(
                "CHAL-100P-02",
                "100_players",
                "DataStore request-per-minute quota exhaustion (60 + 10*N budget)",
                {"LUAU-ECO-002"},
                "CRITICAL",
                "Writing to DataStore on every coin pickup/combat kill exceeds Roblox's per-minute budget with 100 active players, silently dropping saves.",
                "Audit all SetAsync/UpdateAsync call sites; verify writes only occur on join/autosave(60s+)/leave/receipt.",
                "Maintain an in-memory server ledger with dirty flags, 60-90s autosave jitter, and pcall backoff.",
            ),
            _scenario(
                "CHAL-100P-03",
                "100_players",
                "Instance.new / Touched / AnimationTrack GC & thread spike",
                {"LUAU-PERF-003", "LUAU-PERF-004", "LUAU-ANIM-002", "LUAU-PERF-005"},
                "MAJOR",
                "100 players firing projectiles or colliding triggers unpooled Instance.new, Touched floods, and AnimationTrack leaks.",
                "Inspect MicroProfiler under 20+ simultaneous active combatants and confirm track count stays bounded.",
                "Pool projectiles/VFX/damage popups, replace Touched with Shapecast, and cache AnimationTracks.",
            ),
        ]

        has_mobile = any("mobile" in p or "phone" in p or "ios" in p or "android" in p for p in platforms)
        scenarios_phone = [
            _scenario(
                "CHAL-PHN-01",
                "phone",
                "Thumbstick / jump occlusion & <44px touch miss-taps",
                {"GUI-TOUCH-001", "GUI-MOBILE-001", "GUI-SAFE-001"},
                "CRITICAL" if has_mobile else "MAJOR",
                "On a 667x375 phone screen, bottom-left/right buttons collide with Roblox touch controls and <44px buttons become unclickable.",
                "Run sharp_gui_inspect + deviceSim at iPhone SE / 667x375 and inspect touch rect intersections.",
                "Keep buttons >= 44x44px, CoreUISafeInsets on HUD, and stay outside virtual thumbstick/jump corners.",
            ),
            _scenario(
                "CHAL-PHN-02",
                "phone",
                "Low-VRAM CanvasGroup blanking & StreamingEnabled OOM crash",
                {"GUI-PERF-001", "WORLD-STREAM-001", "WORLD-BUDGET-001"},
                "CRITICAL",
                "Over 6 CanvasGroups or >15k parts without StreamingEnabled causes silent blank UI panels and iOS Jetsam crashes.",
                "Check Studio QualityLevel=1 + StreamingEnabled=true with device emulation.",
                "Cap CanvasGroups <= 6 (none inside ScrollingFrames), enable StreamingEnabled, and keep PreciseConvex <= 10.",
            ),
            _scenario(
                "CHAL-PHN-03",
                "phone",
                "Missing mobile touch controls / unconstrained TextScaled overflow",
                {"GUI-TEXT-001"},
                "MAJOR",
                "PC-only KeyCode bindings leave mobile players unable to interact, while TextScaled overflows narrow buttons.",
                "Verify InputActionSystem has Touch InputBindings or touch button fallback + UITextSizeConstraint everywhere.",
                "Wire InputActionSystem touch bindings and attach UITextSizeConstraint to every TextScaled label.",
            ),
        ]

        scenarios_rejoin = [
            _scenario(
                "CHAL-REJ-01",
                "after_rejoin",
                "Cross-server session-lock dupe & BindToClose data loss",
                {"LUAU-ECO-001", "LUAU-ECO-002", "LUAU-ECO-003"},
                "BLOCKER" if ("LUAU-ECO-001" in found_ids or "LUAU-ECO-003" in found_ids) else "CRITICAL",
                "Quickly rejoining or teleporting while old server hasn't flushed causes currency duplication or total rollback on server close.",
                "Test rapid leave->rejoin and BindToClose shutdown with active dirty profile + ProcessReceipt replay.",
                "Use UpdateAsync session locking, BindToClose flush barrier, and PurchaseId deduplication.",
            ),
            _scenario(
                "CHAL-REJ-02",
                "after_rejoin",
                "Leaked PlayerAdded/CharacterAdded connections across joins/respawns",
                {"LUAU-MEM-001", "LUAU-MEM-002", "LUAU-STREAM-001"},
                "CRITICAL",
                "Undisconnected CharacterAdded/Heartbeat/Touched bindings survive player leave, firing on nil characters and leaking RAM.",
                "Join, respawn 3 times, leave, and inspect Heap / active connection count in Luau Heap Profiler.",
                "Bind every per-player/per-character connection to a Maid/Janitor cleaned on CharacterRemoving & PlayerRemoving.",
            ),
            _scenario(
                "CHAL-REJ-03",
                "after_rejoin",
                "Respawn UI reset / missing StarterGui direct-child ResetOnSpawn=false",
                {"LIVE-GUI-WARN"},
                "MAJOR",
                "ScreenGuis nested in Folders or missing ResetOnSpawn=false wipe client HUD state or duplicate bindings on character respawn.",
                "Respawn character in Play Solo and verify HUD survives with zero duplicate Remote/Input bindings.",
                "Place persistent ScreenGuis directly under StarterGui with ResetOnSpawn=false.",
            ),
        ]

        if "UserInputService" in joined_tokens and "InputContext" not in joined_tokens and "Touch" not in joined_tokens:
            scenarios_phone[2]["confirmed_in_inputs"] = True
            scenarios_phone[2]["severity"] = "CRITICAL"
            scenarios_phone[2]["trigger_evidence"] = "Scripts use UserInputService without InputActionSystem or Touch handling"

        all_scenarios = scenarios_100 + scenarios_phone + scenarios_rejoin
        findings = list(static_res["findings"])
        for sc in all_scenarios:
            if sc["confirmed_in_inputs"]:
                findings.append(
                    _make_finding(
                        rule_id=sc["id"],
                        severity=sc["severity"],
                        domain="challenge",
                        evidence=f"[{sc['axis']}] {sc['title']}: {sc['trigger_evidence']}",
                        why_it_matters=sc["failure_scenario"],
                        fix=sc["mitigation"],
                    )
                )

        score, verdict, counts = _score_and_verdict(findings)
        return _sign_audit_report({
            "ok": True,
            "mode": "challenge",
            "score": score,
            "verdict": verdict,
            "summary": {
                **counts,
                "total": len(findings),
                "challenge_scenarios": len(all_scenarios),
                "confirmed_risks": sum(1 for s in all_scenarios if s["confirmed_in_inputs"]),
            },
            "scenarios_by_axis": {
                "100_players": scenarios_100,
                "phone": scenarios_phone,
                "after_rejoin": scenarios_rejoin,
            },
            "findings": findings,
        })

    # ------------------------------------------------------------------
    # Gate Mode & Unified Dispatcher
    # ------------------------------------------------------------------

    def audit_gate(
        self,
        *,
        stage_id: Optional[str] = None,
        step_id: Optional[str] = None,
        luau_sources: Optional[Dict[str, str] | List[Any] | str] = None,
        file_paths: Optional[List[str]] = None,
        live_report: Optional[Dict[str, Any] | str] = None,
        gui_spec: Optional[Dict[str, Any]] = None,
        design_lint: Optional[Dict[str, Any]] = None,
        anim_clips: Optional[Dict[str, Any] | List[Dict[str, Any]]] = None,
        anim_analysis: Optional[Dict[str, Any]] = None,
        world_stats: Optional[Dict[str, Any]] = None,
        project_library: Optional[Any] = None,
        plan_data: Optional[Dict[str, Any]] = None,
        game_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Evaluate whether a stage/release gate passes strict severity thresholds."""
        active_lib = project_library if project_library is not None else self.project_library
        if live_report is not None:
            res = self.audit_live(
                live_report=live_report,
                luau_sources=luau_sources,
                gui_spec=gui_spec,
                design_lint=design_lint,
                anim_analysis=anim_analysis,
                project_library=active_lib,
            )
        else:
            res = self.audit_static(
                luau_sources=luau_sources,
                file_paths=file_paths,
                gui_spec=gui_spec,
                design_lint=design_lint,
                anim_clips=anim_clips,
                anim_analysis=anim_analysis,
                world_stats=world_stats,
                project_library=active_lib,
                plan_data=plan_data,
                game_state=game_state,
                check_plan=True,
            )

        counts = res["summary"]
        is_release = (stage_id or "").upper() == "S7" or (step_id or "").upper().startswith("S7")
        max_major = 0 if is_release else 2
        blocking_reasons: List[str] = []

        if counts["blocker"] > 0:
            blocking_reasons.append(f"{counts['blocker']} BLOCKER finding(s) present (must be 0)")
        if counts["critical"] > 0:
            blocking_reasons.append(f"{counts['critical']} CRITICAL finding(s) present (must be 0)")
        if counts["major"] > max_major:
            blocking_reasons.append(f"{counts['major']} MAJOR finding(s) exceed gate cap {max_major}")
        if is_release and res["verdict"] != "SHIP":
            blocking_reasons.append(f"Release gate S7 requires verdict='SHIP' (got '{res['verdict']}', score={res['score']})")

        gate_passed = len(blocking_reasons) == 0
        return _sign_audit_report({
            **res,
            "mode": "gate",
            "stage_id": stage_id,
            "step_id": step_id,
            "gate_passed": gate_passed,
            "blocking_reasons": blocking_reasons,
        })

    def run_audit(self, mode: str = "static", **kwargs: Any) -> Dict[str, Any]:
        """Unified entry point supporting `static`, `live`, `challenge`, and `gate` modes."""
        norm = (mode or "static").strip().lower()
        if norm == "static":
            return self.audit_static(**kwargs)
        if norm == "live":
            return self.audit_live(**kwargs)
        if norm == "challenge":
            return self.challenge(**kwargs)
        if norm == "gate":
            return self.audit_gate(**kwargs)
        return {"ok": False, "error": f"Unknown audit mode '{mode}'. Expected static|live|challenge|gate."}
