"""Resiris language analysis built on the real Resiris language core.

Everything here uses the actual `resiris` package (tokenizer, parser, AST,
module loader). The IDE never invents its own Resiris rules.
"""

from __future__ import annotations

import ast as py_ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from resiris import ast_nodes
from resiris.parser import Parser
from resiris.tokenizer import ResirisSyntaxError, TokenType, Tokenizer


RESIRIS_TYPES = [
    "UnknownObject",
    "int",
    "float",
    "string",
    "bool",
    "ModuleObject",
    "FunctionalObject",
]

RESIRIS_KEYWORDS = [
    "include",
    "v",
    "c",
    "fn",
    "START",
    "PROCESS",
    "if",
    "elif",
    "else",
    "mat",
    "return",
    "pass",
    "print_cmd",
    "true",
    "false",
]


class SyntaxErrorInfo:
    """Extracted position of a ResirisSyntaxError."""

    def __init__(self, line: int, column: int | None, message: str):
        self.line = line
        self.column = column
        self.message = message


# Resiris errors that the interpreter can raise at runtime. The IDE only
# reports these when statically provable; runtime ones surface via Run.
ERROR_PATTERN = re.compile(
    r"^line (\d+)(?:, column (\d+))?:\s*(.*)$", re.DOTALL
)


def parse_syntax_error(error: ResirisSyntaxError) -> SyntaxErrorInfo:
    text = str(error)
    match = ERROR_PATTERN.match(text)
    if match:
        line = int(match.group(1))
        column = int(match.group(2)) if match.group(2) else None
        message = match.group(3)
        return SyntaxErrorInfo(line, column, message)
    match = re.match(r"^line (\d+):\s*(.*)$", text, re.DOTALL)
    if match:
        return SyntaxErrorInfo(int(match.group(1)), None, match.group(2))
    return SyntaxErrorInfo(1, None, text)


# ---------------------------------------------------------------------------
# Module metadata (read WITHOUT executing module code)
# ---------------------------------------------------------------------------


@dataclass
class ConstantInfo:
    name: str
    type_name: str = ""


@dataclass
class ModuleInfo:
    name: str
    file: str
    functions: list[str] = field(default_factory=list)
    constants: list[ConstantInfo] = field(default_factory=list)


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _extract_metadata(module_file: Path, fallback_name: str) -> ModuleInfo:
    info = ModuleInfo(name=fallback_name, file=str(module_file))
    try:
        tree = py_ast.parse(module_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return info

    for node in tree.body:
        if not isinstance(node, py_ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, py_ast.Name):
            continue
        if target.id == "NAME" and isinstance(node.value, py_ast.Constant) and isinstance(
            node.value.value, str
        ):
            info.name = node.value.value
        elif target.id == "FUNCTIONS" and isinstance(node.value, py_ast.Constant) and isinstance(
            node.value.value, str
        ):
            info.functions = _csv(node.value.value)
        elif target.id == "VARIABLES" and isinstance(node.value, py_ast.Constant) and isinstance(
            node.value.value, str
        ):
            for item in node.value.value.split(","):
                item = item.strip()
                if not item or ":" not in item:
                    continue
                name, type_name = (part.strip() for part in item.split(":", 1))
                if name:
                    info.constants.append(ConstantInfo(name, type_name))

    return info


def list_modules(modules_dir: Path) -> list[ModuleInfo]:
    if not modules_dir.is_dir():
        return []
    modules = []
    for module_file in sorted(modules_dir.glob("*.py")):
        if module_file.name.startswith("_"):
            continue
        fallback = module_file.stem
        modules.append(_extract_metadata(module_file, fallback))
    return modules


def module_exists(modules_dir: Path, name: str) -> bool:
    return any(module.name == name for module in list_modules(modules_dir))


# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------


@dataclass
class Symbol:
    kind: str
    name: str
    line: int
    column: int
    detail: str = ""


def _walk_statements(statements: list, visitor) -> None:
    for statement in statements:
        visitor(statement)


def collect_symbols(program) -> list[Symbol]:
    symbols: list[Symbol] = []

    def visit(node) -> None:
        if isinstance(node, ast_nodes.Declaration):
            kind = "constant" if node.kind == "c" else "variable"
            symbols.append(
                Symbol(
                    kind=kind,
                    name=node.name,
                    line=getattr(node, "source_line", 1),
                    column=getattr(node, "source_column", 1),
                    detail=f"{node.type_name}",
                )
            )
        elif isinstance(node, ast_nodes.FunctionDef):
            params = ", ".join(node.parameters)
            symbols.append(
                Symbol(
                    kind="function",
                    name=node.name,
                    line=getattr(node, "source_line", 1),
                    column=getattr(node, "source_column", 1),
                    detail=f"fn {node.name}({params})",
                )
            )
            for body_statement in node.body:
                visit(body_statement)
        elif isinstance(node, ast_nodes.LifecycleDef):
            if node.name == "START":
                detail = "START()"
            else:
                detail = "PROCESS(FPS)"
            symbols.append(
                Symbol(
                    kind="lifecycle",
                    name=node.name,
                    line=getattr(node, "source_line", 1),
                    column=getattr(node, "source_column", 1),
                    detail=detail,
                )
            )
            for body_statement in node.body:
                visit(body_statement)
        elif isinstance(node, ast_nodes.IfStmt):
            for body_statement in node.body:
                visit(body_statement)
            for _cond, elif_body in node.elif_blocks:
                for body_statement in elif_body:
                    visit(body_statement)
            if node.else_body is not None:
                for body_statement in node.else_body:
                    visit(body_statement)
        elif isinstance(node, ast_nodes.MatStmt):
            for case in node.cases:
                for body_statement in case.body:
                    visit(body_statement)
            if node.else_body is not None:
                for body_statement in node.else_body:
                    visit(body_statement)

    _walk_statements(program.statements, visit)
    return symbols


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


@dataclass
class TokenRun:
    tokens: list


def _find_token(tokens: list, token_type: TokenType, value, after: int = 0) -> int:
    for index in range(after, len(tokens)):
        token = tokens[index]
        if token.type is token_type and token.value == value:
            return index
    return -1


@dataclass
class ModuleUsage:
    module: str
    line: int
    column: int


def _usage_locations(tokens: list, module_names: set[str]) -> list[ModuleUsage]:
    """Find where existing module names are referenced in the source."""
    usages: list[ModuleUsage] = []
    declared_names: set[str] = set()

    for index, token in enumerate(tokens):
        if token.type is TokenType.IDENTIFIER:
            next_token = tokens[index + 1] if index + 1 < len(tokens) else None
            next_next = tokens[index + 2] if index + 2 < len(tokens) else None

            # `Module.func` or `Module[CONST]`
            if next_token is not None and next_token.type is TokenType.DOT:
                if token.value in module_names:
                    usages.append(ModuleUsage(token.value, token.line, token.column))
                    continue
            if (
                next_token is not None
                and next_token.type is TokenType.LBRACKET
                and next_next is not None
                and next_next.type is TokenType.IDENTIFIER
            ):
                if token.value in module_names:
                    usages.append(ModuleUsage(token.value, token.line, token.column))
                    continue

            # `v x ModuleObject = RSBase`
            if token.value in module_names and token.value not in declared_names:
                usages.append(ModuleUsage(token.value, token.line, token.column))
    return usages


@dataclass
class IncludeInfo:
    module: str
    line: int
    column: int


def _included_modules(tokens: list) -> list[IncludeInfo]:
    """Return every module included via `<include>`, in source order."""
    included: list[IncludeInfo] = []
    inside = False

    for token in tokens:
        if token.type is TokenType.INCLUDE:
            inside = True
            continue
        if inside:
            if token.type is TokenType.NEWLINE or token.type is TokenType.EOF:
                inside = False
                continue
            if token.type is TokenType.IDENTIFIER:
                included.append(IncludeInfo(token.value, token.line, token.column))
    return included


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


@dataclass
class Diagnostic:
    line: int
    column: int
    length: int
    severity: str
    message: str
    quick_fix_module: str | None = None


def _include_line_sources(source: str) -> list[int]:
    """Line numbers (0-based) that are include lines."""
    lines = []
    for index, line in enumerate(source.splitlines()):
        if "<include>" in line:
            lines.append(index)
    return lines


def compute_include_edit(source: str, module_name: str) -> tuple[int, str]:
    """Return (offset, text) for the minimal insertion of `<include> X`."""
    include_lines = _include_line_sources(source)

    if include_lines:
        last_line = include_lines[-1]
        split = source.splitlines(keepends=True)
        offset = sum(len(line) for line in split[: last_line + 1])
        ends_with_newline = split[last_line].endswith("\n")
        text = ("\n" if not ends_with_newline else "") + f"<include> {module_name}\n"
        return offset, text

    return 0, f"<include> {module_name}\n"


def analyze_source(source: str, modules_dir: Path) -> dict:
    """Full static analysis of one .resy source text.

    Returns {"diagnostics": [...], "symbols": [...], "includes": [...]}.
    Positions are converted to 0-based line and column for the UI.
    """
    module_list = list_modules(modules_dir)
    module_names = {module.name for module in module_list}

    try:
        tokens = Tokenizer().tokenize(source)
    except ResirisSyntaxError as error:
        info = parse_syntax_error(error)
        return {
            "diagnostics": [
                {
                    "line": info.line - 1,
                    "column": max(0, (info.column or 1) - 1),
                    "length": 1,
                    "severity": "ERROR",
                    "message": info.message,
                    "quickFixModule": None,
                }
            ],
            "symbols": [],
            "includes": [],
            "modules": [module_to_json(module) for module in module_list],
        }

    try:
        program = Parser(tokens).parse()
    except ResirisSyntaxError as error:
        info = parse_syntax_error(error)
        return {
            "diagnostics": [
                {
                    "line": info.line - 1,
                    "column": max(0, (info.column or 1) - 1),
                    "length": 1,
                    "severity": "ERROR",
                    "message": info.message,
                    "quickFixModule": None,
                }
            ],
            "symbols": [],
            "includes": [],
            "modules": [module_to_json(module) for module in module_list],
        }

    included = _included_modules(tokens)
    included_by_name: dict[str, IncludeInfo] = {}
    for info in included:
        if info.module not in included_by_name:
            included_by_name[info.module] = info

    usages = _usage_locations(tokens, module_names)

    declarations = {
        symbol.name
        for symbol in collect_symbols(program)
        if symbol.kind in {"variable", "constant", "function", "lifecycle"}
    }

    diagnostics: list[Diagnostic] = []
    seen_usage: set[tuple[str, int, int]] = set()

    # Unknown module in include -> ERROR
    for module_name, info in included_by_name.items():
        if module_name not in module_names:
            diagnostics.append(
                Diagnostic(
                    line=info.line,
                    column=info.column,
                    length=len(module_name),
                    severity="ERROR",
                    message=f"{module_name} not found! Error code: \"MissingModule\"",
                )
            )

    # Duplicate include -> ERROR (mirrors SameModuleMultiCall)
    include_names = [info.module for info in included]
    duplicate_names = {
        name for name in include_names if include_names.count(name) > 1
    }
    seen_duplicates: set[str] = set()
    for info in included:
        if info.module in duplicate_names and info.module not in seen_duplicates:
            seen_duplicates.add(info.module)
            diagnostics.append(
                Diagnostic(
                    line=info.line,
                    column=info.column,
                    length=len(info.module),
                    severity="ERROR",
                    message=(
                        f"{info.module} is already included. "
                        'Error code: "SameModuleMultiCall"'
                    ),
                )
            )

    # Module used without include -> WARNING + Quick Fix
    for usage in usages:
        if usage.module in included_by_name:
            continue
        if usage.module in declarations:
            continue
        key = (usage.module, usage.line, usage.column)
        if key in seen_usage:
            continue
        # only warn for modules that actually exist and can be included
        if usage.module not in module_names:
            continue
        seen_usage.add(key)
        diagnostics.append(
            Diagnostic(
                line=usage.line,
                column=usage.column,
                length=len(usage.module),
                severity="WARNING",
                message=f"Missing include: {usage.module}",
                quick_fix_module=usage.module,
            )
        )

    return {
        "diagnostics": [
            {
                "line": diag.line - 1,
                "column": max(0, diag.column - 1),
                "length": diag.length,
                "severity": diag.severity,
                "message": diag.message,
                "quickFixModule": diag.quick_fix_module,
            }
            for diag in diagnostics
        ],
        "symbols": [symbol_to_json(symbol) for symbol in collect_symbols(program)],
        "includes": [
            {"module": info.module, "line": info.line - 1, "column": info.column - 1}
            for info in included
        ],
        "modules": [module_to_json(module) for module in module_list],
    }


def module_to_json(module: ModuleInfo) -> dict:
    return {
        "name": module.name,
        "file": module.file,
        "functions": module.functions,
        "constants": [
            {"name": constant.name, "type": constant.type_name}
            for constant in module.constants
        ],
    }


def symbol_to_json(symbol: Symbol) -> dict:
    return {
        "kind": symbol.kind,
        "name": symbol.name,
        "line": symbol.line - 1,
        "column": symbol.column - 1,
        "detail": symbol.detail,
    }


# ---------------------------------------------------------------------------
# Hover
# ---------------------------------------------------------------------------


def hover_at(source: str, line0: int, column0: int, modules_dir: Path) -> dict | None:
    try:
        tokens = Tokenizer().tokenize(source)
    except ResirisSyntaxError:
        return None

    module_list = list_modules(modules_dir)
    modules_by_name = {module.name: module for module in module_list}

    for index, token in enumerate(tokens):
        if token.type is not TokenType.IDENTIFIER:
            continue
        if token.line - 1 != line0:
            continue
        if not (token.column - 1 <= column0 < token.column - 1 + len(str(token.value))):
            continue
        next_token = tokens[index + 1] if index + 1 < len(tokens) else None
        if next_token is None or next_token.type is not TokenType.DOT:
            continue
        member_token = tokens[index + 2] if index + 2 < len(tokens) else None
        if member_token is None or member_token.type is not TokenType.IDENTIFIER:
            continue

        module = modules_by_name.get(token.value)
        if module is None:
            return None
        member = member_token.value
        if member in module.functions:
            return {
                "label": f"{module.name}.{member}(...)",
                "detail": f"{module.name} module function",
            }
        return None
    return None


# ---------------------------------------------------------------------------
# Autocomplete
# ---------------------------------------------------------------------------


def autocomplete(
    source: str,
    line0: int,
    column0: int,
    modules_dir: Path,
) -> list[dict]:
    lines = source.splitlines()
    if line0 < 0 or line0 >= len(lines):
        prefix = ""
    else:
        prefix = lines[line0][:column0]

    word_match = re.search(r"[A-Za-z_][A-Za-z0-9_]*$", prefix)
    word = word_match.group(0) if word_match else ""

    module_list = list_modules(modules_dir)
    modules_by_name = {module.name: module for module in module_list}
    included = {info.module for info in _included_modules(Tokenizer().tokenize(source))}

    # `<include>` then module names -> only real modules
    if re.search(r"<include>\s+[A-Za-z0-9_]*$", prefix):
        return [
            {
                "label": module.name,
                "kind": "module",
                "detail": f"module with {len(module.functions)} functions",
                "insertText": module.name,
                "replaceLength": len(word),
            }
            for module in module_list
            if module.name.startswith(word)
        ]

    # typing inside `<...>` -> the include keyword itself
    if re.search(r"<\s*[A-Za-z0-9_]*$", prefix) and word.lower().startswith("inc"):
        return [
            {
                "label": "include",
                "kind": "keyword",
                "detail": "<include> ModuleName",
                "insertText": "include",
                "replaceLength": len(word),
            }
        ]

    # `Module.member` -> real module members
    dot_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z0-9_]*)$", prefix)
    if dot_match:
        module_name, member_prefix = dot_match.group(1), dot_match.group(2)
        module = modules_by_name.get(module_name)
        if module is not None:
            return [
                {
                    "label": member,
                    "kind": "member",
                    "detail": f"{module.name} module function",
                    "insertText": member,
                    "replaceLength": len(member_prefix),
                }
                for member in module.functions
                if member.startswith(member_prefix)
            ]

    # `Module[CONST` -> real module constants
    bracket_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\[([A-Za-z0-9_]*)$", prefix)
    if bracket_match:
        module_name, const_prefix = bracket_match.group(1), bracket_match.group(2)
        module = modules_by_name.get(module_name)
        if module is not None:
            return [
                {
                    "label": constant.name,
                    "kind": "constant_member",
                    "detail": f"{module.name} module constant ({constant.type_name})",
                    "insertText": constant.name,
                    "replaceLength": len(const_prefix),
                }
                for constant in module.constants
                if constant.name.startswith(const_prefix)
            ]

    # General completion: keywords, types, symbols, module names
    decl_match = re.search(r"^\s*[vc]\s+[A-Za-z_][A-Za-z0-9_]*\s+(\w*)$", prefix)
    if decl_match:
        type_prefix = decl_match.group(1)
        return [
            {
                "label": type_name,
                "kind": "type",
                "detail": "Resiris type",
                "insertText": type_name,
                "replaceLength": len(type_prefix),
            }
            for type_name in RESIRIS_TYPES
            if type_name.startswith(type_prefix)
        ]

    if not word:
        return [
            {
                "label": "include",
                "kind": "keyword",
                "detail": "<include> ModuleName",
                "insertText": "<include> ",
                "replaceLength": 0,
            }
        ]

    items: list[dict] = []

    for keyword in RESIRIS_KEYWORDS:
        if keyword.startswith(word):
            items.append(
                {
                    "label": keyword,
                    "kind": "keyword",
                    "detail": "Resiris keyword",
                    "insertText": keyword,
                    "replaceLength": len(word),
                }
            )

    for type_name in RESIRIS_TYPES:
        if type_name.startswith(word):
            items.append(
                {
                    "label": type_name,
                    "kind": "type",
                    "detail": "Resiris type",
                    "insertText": type_name,
                    "replaceLength": len(word),
                }
            )

    try:
        symbols = collect_symbols(Parser(Tokenizer().tokenize(source)).parse())
    except ResirisSyntaxError:
        symbols = []

    for symbol in symbols:
        if symbol.name.startswith(word) and symbol.name != word:
            items.append(
                {
                    "label": symbol.name,
                    "kind": symbol.kind,
                    "detail": symbol.detail,
                    "insertText": symbol.name,
                    "replaceLength": len(word),
                }
            )

    for module in module_list:
        if module.name.startswith(word):
            items.append(
                {
                    "label": module.name,
                    "kind": "module",
                    "detail": f"module with {len(module.functions)} functions",
                    "insertText": module.name,
                    "replaceLength": len(word),
                }
            )

    return items