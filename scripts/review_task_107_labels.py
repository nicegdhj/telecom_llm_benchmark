#!/usr/bin/env python3
"""Triage suspicious task_107 labels with explainable regex rules.

The script does not overwrite source labels.  It ranks rows for human review
and only suggests ``Yes`` when a ``No``-labelled payload contains at least one
strong attack signature.
"""

from __future__ import annotations

import argparse
import html
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT
    / "outputs/lora-ckpt1200_aggregated_reports_20260730_150710"
    / "task_107_suite/sp_0729_qwen-3-6-27b-lora-ckpt1200"
    / "task_107_errors.xlsx"
)
REQUIRED_COLUMNS = ("payload", "标记", "模型输出")
ANALYSIS_COLUMNS = (
    "规范化模型输出",
    "建议标签",
    "复核等级",
    "风险分",
    "规则类别",
    "命中证据",
    "判断说明",
)


@dataclass(frozen=True)
class Rule:
    name: str
    category: str
    pattern: re.Pattern[str]
    score: int
    strength: str
    description: str


def _rule(
    name: str,
    category: str,
    pattern: str,
    score: int,
    strength: str,
    description: str,
    flags: int = re.IGNORECASE,
) -> Rule:
    return Rule(
        name=name,
        category=category,
        pattern=re.compile(pattern, flags),
        score=score,
        strength=strength,
        description=description,
    )


RULES = (
    _rule(
        "SQL_UNION",
        "SQL注入",
        r"\bunion\s+(?:all\s+)?select\b",
        6,
        "strong",
        "出现 UNION SELECT 查询拼接",
    ),
    _rule(
        "SQL_BOOLEAN_OR_TIME",
        "SQL注入",
        (
            r"(?:['\"]\s*)?\b(?:or|and)\s+(?:\d+|['\"][^'\"]*['\"])\s*"
            r"=\s*(?:\d+|['\"][^'\"]*['\"])"
            r"|\b(?:sleep|benchmark|pg_sleep)\s*\("
            r"|\bwaitfor\s+delay\b"
        ),
        6,
        "strong",
        "出现布尔盲注或时间盲注结构",
    ),
    _rule(
        "SQL_STACKED",
        "SQL注入",
        r";\s*(?:select|insert|update|delete|drop|alter|exec(?:ute)?)\b",
        6,
        "strong",
        "出现 SQL 堆叠语句",
    ),
    _rule(
        "SHELL_SUBSTITUTION",
        "命令注入/代码执行",
        (
            r"`[^`\r\n]{0,100}\b(?:ping|wget|curl|cat|whoami|uname|"
            r"bash|sh|nslookup|dig|chmod|chown|touch|python|perl|php)\b"
            r"[^`\r\n]{0,200}`"
            r"|\$\([^)\r\n]{0,100}\b(?:ping|wget|curl|cat|whoami|uname|"
            r"bash|sh|nslookup|dig|chmod|chown|touch|python|perl|php)\b"
            r"[^)\r\n]{0,200}\)"
        ),
        7,
        "strong",
        "出现 shell 反引号或命令替换",
    ),
    _rule(
        "SHELL_COMMAND_CHAIN",
        "命令注入/代码执行",
        (
            r"(?:;|&&|\|\||\|)\s*(?:/bin/(?:sh|bash)|sh\b|bash\b|"
            r"wget\b|curl\b|chmod\b|chown\b|nc\b|netcat\b|"
            r"powershell\b|cmd\.exe\b|whoami\b|uname\b|id\b)"
        ),
        7,
        "strong",
        "出现 shell 分隔符和可执行命令链",
    ),
    _rule(
        "COMMAND_PARAMETER",
        "命令注入/代码执行",
        (
            r"(?:^|[?&\s])(?:cmd|command|exec|execute|shell)\s*="
            r"[^&\r\n]{0,180}(?:/bin/|wget\b|curl\b|chmod\b|"
            r"powershell\b|whoami\b|uname\b|cat\s+/etc/)"
        ),
        7,
        "strong",
        "命令参数中出现系统命令",
    ),
    _rule(
        "SHELLSHOCK",
        "命令注入/代码执行",
        r"\(\)\s*\{\s*:\s*;\s*\}\s*;",
        8,
        "strong",
        "出现 Shellshock 利用结构",
    ),
    _rule(
        "DEEP_PATH_TRAVERSAL",
        "路径遍历/文件包含",
        r"(?:\.\.;?[/\\]){3,}",
        6,
        "strong",
        "出现多级路径遍历",
    ),
    _rule(
        "SENSITIVE_PATH_TRAVERSAL",
        "路径遍历/文件包含",
        (
            r"(?:\.\.;?[/\\]){1,}[^?\r\n]{0,240}"
            r"(?:etc[/\\](?:passwd|shadow)|proc[/\\]self|"
            r"windows[/\\]win\.ini|boot\.ini|web-inf|\.ssh|"
            r"(?:^|[/\\])env(?:$|[?&\s]))"
        ),
        7,
        "strong",
        "路径遍历目标指向敏感文件或配置",
    ),
    _rule(
        "FILE_INCLUDE_WRAPPER",
        "路径遍历/文件包含",
        r"\b(?:php|expect|data|zip|phar)://",
        7,
        "strong",
        "出现可用于文件包含或代码执行的协议包装器",
    ),
    _rule(
        "SENSITIVE_FILE_ACCESS",
        "路径遍历/文件包含",
        (
            r"(?:/etc/(?:passwd|shadow|hosts)|/proc/self/(?:environ|cmdline)|"
            r"(?:^|[/\\])boot\.ini(?:$|[?&\s])|"
            r"(?:^|[/\\])windows[/\\]win\.ini)"
        ),
        6,
        "strong",
        "请求包含操作系统敏感文件",
    ),
    _rule(
        "XSS_EXECUTION",
        "XSS",
        (
            r"<\s*script\b|"
            r"\bon(?:error|load|focus|mouseover|mouseenter)\s*="
            r"|<\s*(?:svg|img|iframe)\b[^>]{0,300}\bon(?:load|error)\s*="
        ),
        6,
        "strong",
        "出现可执行 XSS 上下文",
    ),
    _rule(
        "SERVER_SIDE_CODE_TAG",
        "WebShell/代码执行",
        r"<\?(?:php|=)|<%@\s*page",
        7,
        "strong",
        "出现服务端代码标签",
    ),
    _rule(
        "JNDI_LOOKUP",
        "JNDI/反序列化/XXE",
        r"\$\{\s*jndi\s*:\s*(?:ldap|rmi|dns|iiop|http)s?\s*:",
        8,
        "strong",
        "出现 JNDI 远程查找载荷",
    ),
    _rule(
        "XXE_EXTERNAL_ENTITY",
        "JNDI/反序列化/XXE",
        r"<!entity\s+[^>]{0,300}\bsystem\s+['\"](?:file|http|https)://",
        8,
        "strong",
        "出现 XXE 外部实体声明",
    ),
    _rule(
        "JAVA_SERIALIZED_HEX",
        "JNDI/反序列化/XXE",
        r"%ac%ed%00%05",
        6,
        "strong",
        "出现 URL 编码的 Java 序列化魔数",
    ),
    _rule(
        "JAVA_SERIALIZED_BASE64",
        "JNDI/反序列化/XXE",
        r"rO0AB[A-Za-z0-9+/=]{12,}",
        6,
        "strong",
        "出现大小写精确的 Java 序列化 Base64 特征",
        flags=0,
    ),
    _rule(
        "JAVASCRIPT_URI",
        "XSS",
        r"javascript\s*:",
        2,
        "medium",
        "出现 javascript: URI，但缺少可执行 HTML 上下文",
    ),
    _rule(
        "DANGEROUS_EXEC_FUNCTION",
        "WebShell/代码执行",
        (
            r"\b(?:eval|assert|system|shell_exec|passthru|"
            r"proc_open|popen)\s*\([^)\r\n]{0,400}\)"
        ),
        2,
        "medium",
        "出现危险执行函数文本，但缺少服务端代码上下文",
    ),
    _rule(
        "SCANNER_USER_AGENT",
        "扫描/探测",
        (
            r"(?:user-agent\s*:\s*[^\r\n]*)"
            r"(?:sqlmap|nikto|nmap|masscan|acunetix|nessus|"
            r"zgrab|gobuster|dirbuster|wpscan)"
        ),
        2,
        "medium",
        "User-Agent 命中常见安全扫描工具",
    ),
    _rule(
        "SUSPICIOUS_ADMIN_PATH",
        "扫描/探测",
        (
            r"\s/(?:cgi-bin|phpmyadmin|wp-admin|wp-login\.php|"
            r"manager/html|actuator(?:/|$)|console(?:/|$)|"
            r"webadmin|admin(?:/|$))"
        ),
        2,
        "medium",
        "请求敏感管理或常见探测路径",
    ),
    _rule(
        "CONNECT_TUNNEL",
        "代理隧道",
        r"^\s*connect\s+(?:\d{1,3}\.){3}\d{1,3}:\d+\s+http/",
        2,
        "medium",
        "CONNECT 请求直连 IP 和端口",
    ),
    _rule(
        "SCRIPT_EXTENSION",
        "可疑脚本路径",
        r"\s/\S*\.(?:php\d*|phtml|jsp|jspx|asp|aspx|cgi)(?:[?/\s]|$)",
        1,
        "medium",
        "请求动态脚本文件",
    ),
    _rule(
        "FILE_URL_PARAMETER",
        "可疑文件参数",
        r"(?:[?&=]|:\s*)file://",
        1,
        "medium",
        "参数中包含 file:// URL",
    ),
    _rule(
        "DENSE_URL_ENCODING",
        "异常编码",
        r"(?:%[0-9a-f]{2}){5,}",
        2,
        "medium",
        "出现连续高密度 URL 编码",
    ),
)


def build_match_views(payload: str) -> list[str]:
    """Return stable raw/decoded views used only for regex matching."""
    raw = str(payload or "")
    html_decoded = html.unescape(raw)
    once = unquote(html_decoded)
    twice = unquote(once)
    return list(dict.fromkeys([raw, html_decoded, once, twice]))


def normalize_model_output(value: object) -> str:
    """Normalize only exact Yes/No answers; verbose responses remain Other."""
    match = re.fullmatch(r"\s*(yes|no)\s*", str(value or ""), re.IGNORECASE)
    return match.group(1).title() if match else "Other"


def _evidence(view: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 35)
    end = min(len(view), match.end() + 35)
    excerpt = re.sub(r"\s+", " ", view[start:end]).strip()
    return excerpt[:120]


def match_rules(payload: str) -> list[tuple[Rule, str]]:
    """Match each rule at most once across raw and decoded views."""
    matches = []
    views = build_match_views(payload)
    for rule in RULES:
        for view in views:
            match = rule.pattern.search(view)
            if match:
                matches.append((rule, _evidence(view, match)))
                break
    return matches


def _build_explanation(
    gold: str,
    level: str,
    matches: list[tuple[Rule, str]],
) -> str:
    if level == "高置信疑似错标":
        strong_names = [rule.name for rule, _ in matches if rule.strength == "strong"]
        return (
            f"原标记为 No，但命中明确攻击规则：{', '.join(strong_names)}；"
            "建议人工复核是否应标记为 Yes。"
        )
    if level == "标签有攻击证据":
        return "原标记为 Yes，且正则发现明确攻击证据，当前标签有规则支持。"
    if matches:
        return (
            f"原标记为 {gold}，仅发现中等或不足以自动改标的证据；"
            "需要结合业务上下文人工复核。"
        )
    return (
        f"原标记为 {gold}，当前规则库未发现明确攻击证据；"
        "未命中规则不代表请求安全，仅作为低优先级复核提示。"
    )


def analyze_row(payload: str, gold: str, model_output: object) -> dict[str, object]:
    """Analyze one row without changing its source label."""
    normalized_gold = str(gold or "").strip().title()
    if normalized_gold not in {"Yes", "No"}:
        raise ValueError(f"标记必须是 Yes 或 No，收到: {gold!r}")

    matches = match_rules(payload)
    score = sum(rule.score for rule, _ in matches)
    has_strong = any(rule.strength == "strong" for rule, _ in matches)

    if normalized_gold == "No" and has_strong:
        level, suggestion = "高置信疑似错标", "Yes"
    elif normalized_gold == "No" and score >= 4:
        level, suggestion = "中置信待复核", ""
    elif normalized_gold == "No":
        level, suggestion = "低置信/暂未发现错标证据", ""
    elif has_strong:
        level, suggestion = "标签有攻击证据", "Yes"
    elif matches:
        level, suggestion = "中置信待复核", ""
    else:
        level, suggestion = "低置信待复核", ""

    categories = list(dict.fromkeys(rule.category for rule, _ in matches))
    evidence = [f"{rule.name}: {text}" for rule, text in matches]
    return {
        "规范化模型输出": normalize_model_output(model_output),
        "建议标签": suggestion,
        "复核等级": level,
        "风险分": score,
        "规则类别": "；".join(categories),
        "命中证据": "；".join(evidence),
        "判断说明": _build_explanation(normalized_gold, level, matches),
    }


def _style_sheet(sheet) -> None:
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    widths = {
        "payload": 78,
        "标记": 10,
        "模型输出": 34,
        "提示词": 78,
        "规范化模型输出": 16,
        "建议标签": 12,
        "复核等级": 24,
        "风险分": 10,
        "规则类别": 34,
        "命中证据": 80,
        "判断说明": 58,
    }
    headers = {cell.value: cell.column_letter for cell in sheet[1]}
    for name, width in widths.items():
        if name in headers:
            sheet.column_dimensions[headers[name]].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")


def _append_table(sheet, headers: list[str], rows: list[dict[str, object]]) -> None:
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header, "") for header in headers])
    _style_sheet(sheet)


def review_workbook(input_path: Path, output_path: Path) -> dict[str, object]:
    """Analyze a source workbook and write the three-sheet review workbook."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.is_file():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("输入文件和输出文件不能相同，避免覆盖原始数据")

    source = load_workbook(input_path, read_only=True, data_only=False)
    try:
        sheet = source.active
        source_headers = [
            cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))
        ]
        if any(not isinstance(header, str) or not header.strip() for header in source_headers):
            raise ValueError("输入 Excel 表头不能包含空值")
        if len(set(source_headers)) != len(source_headers):
            raise ValueError("输入 Excel 表头存在重复列名")
        conflicts = sorted(set(source_headers) & set(ANALYSIS_COLUMNS))
        if conflicts:
            raise ValueError(
                f"输入 Excel 表头与分析列冲突: {', '.join(conflicts)}"
            )
        missing = [column for column in REQUIRED_COLUMNS if column not in source_headers]
        if missing:
            raise ValueError(f"输入 Excel 缺少必需列: {', '.join(missing)}")

        records = []
        for row_index, values in enumerate(
            sheet.iter_rows(min_row=2, values_only=True),
            start=2,
        ):
            source_row = dict(zip(source_headers, values))
            try:
                analysis = analyze_row(
                    payload=source_row["payload"] or "",
                    gold=source_row["标记"],
                    model_output=source_row["模型输出"],
                )
            except ValueError as error:
                raise ValueError(f"第 {row_index} 行: {error}") from error
            records.append({**source_row, **analysis})
    finally:
        source.close()

    all_headers = [*source_headers, *ANALYSIS_COLUMNS]
    workbook = Workbook()
    all_sheet = workbook.active
    all_sheet.title = "全部错误_规则分析"
    _append_table(all_sheet, all_headers, records)

    high_sheet = workbook.create_sheet("高置信疑似错标")
    high_confidence = [
        record
        for record in records
        if record["复核等级"] == "高置信疑似错标"
    ]
    _append_table(high_sheet, all_headers, high_confidence)

    summary_sheet = workbook.create_sheet("规则汇总")
    summary_sheet.append(["汇总类型", "名称", "数量"])
    summary_sheet.append(["总体", "输入样本数", len(records)])

    level_counts = Counter(record["复核等级"] for record in records)
    for name, count in sorted(level_counts.items()):
        summary_sheet.append(["复核等级", name, count])

    suggestion_counts = Counter(record["建议标签"] or "无建议" for record in records)
    for name, count in sorted(suggestion_counts.items()):
        summary_sheet.append(["建议标签", name, count])

    category_counts = Counter()
    for record in records:
        for category in filter(None, str(record["规则类别"]).split("；")):
            category_counts[category] += 1
    for name, count in sorted(category_counts.items()):
        summary_sheet.append(["规则类别", name, count])
    _style_sheet(summary_sheet)
    summary_sheet.column_dimensions["A"].width = 16
    summary_sheet.column_dimensions["B"].width = 38
    summary_sheet.column_dimensions["C"].width = 12

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp.xlsx")
    try:
        workbook.save(temporary_path)
        temporary_path.replace(output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    return {
        "input_rows": len(records),
        "high_confidence": len(high_confidence),
        "review_levels": dict(level_counts),
        "output": str(output_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用可解释正则规则筛选 task_107 疑似错标样本。"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--output",
        type=Path,
        help="输出路径；默认在输入文件旁生成 task_107_label_review.xlsx。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output or args.input.with_name("task_107_label_review.xlsx")
    stats = review_workbook(args.input, output_path)
    print(f"输入样本数: {stats['input_rows']}")
    for level, count in sorted(stats["review_levels"].items()):
        print(f"{level}: {count}")
    print(f"高置信疑似错标: {stats['high_confidence']}")
    print(f"输出文件: {stats['output']}")


if __name__ == "__main__":
    main()
