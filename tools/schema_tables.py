#!/usr/bin/env python3
"""
schema_tables.py — render markdown tables from tools/record-schema-1.json.

The schema is JSON; the whitepaper is prose. This is the one place that turns
one into the other, so the appendix in `docs/compost.md` never has to be typed
by hand and can never drift from what `record-schema-1.json` actually says —
`tools/build_whitepaper.py` calls `render()` and writes the result back between
two markers; `tests/test_grammar.py` asserts the file already holds exactly
that output.

Three tables, in the order the roadmap names them
(`docs/roadmap.md`, "v0.2.12 — the grammar, untangled"):

1. **Node types**, with each type's params split required / optional.
2. **Edge `(layer, type)` pairs.**
3. **A params-by-type table** — every distinct param name across every node
   type. Its third column was to be marked up by hand, deciding which params
   counted as content; v0.2.13 removed that question rather than answering it
   (`docs/compost.md`, *the mapping is the whitelist*), so nothing reads it.

Nothing in this file reads `docs/record-grammar.md` or any other prose. The
only input is the schema.
"""
import json
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "record-schema-1.json"


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def node_types_table(schema: dict) -> str:
    """One row per node type: required params, optional params, whether it
    carries pandoc inline `content` (as opposed to holding everything in
    `params`)."""
    node_types = schema["$defs"]["node_types"]
    lines = ["| type | required params | optional params | carries content |",
             "|---|---|---|---|"]
    for name in sorted(node_types):
        spec = node_types[name]
        props = spec["params"]["properties"]
        required = set(spec["params"].get("required", []))
        optional = set(props) - required
        req_cell = ", ".join(f"`{p}`" for p in sorted(required)) or "—"
        opt_cell = ", ".join(f"`{p}`" for p in sorted(optional)) or "—"
        content_cell = "yes" if spec.get("carries_content") else "—"
        lines.append(f"| `{name}` | {req_cell} | {opt_cell} | {content_cell} |")
    return "\n".join(lines)


def edge_pairs_table(schema: dict) -> str:
    """One row per `(layer, type)` pair the schema names."""
    pairs = schema["$defs"]["edge_pairs"]
    lines = ["| layer | type |", "|---|---|"]
    for p in sorted(pairs, key=lambda p: (p["layer"], p["type"])):
        lines.append(f"| `{p['layer']}` | `{p['type']}` |")
    return "\n".join(lines)


def params_review_table(schema: dict) -> str:
    """One row per distinct param name, the node types it appears on, and a
    column nothing fills in — kept because the table is generated. See
    `render()` for why the review it was built for never happened."""
    node_types = schema["$defs"]["node_types"]
    by_param: dict[str, set] = {}
    for name, spec in node_types.items():
        for p in spec["params"]["properties"]:
            by_param.setdefault(p, set()).add(name)
    lines = ["| param | appears on | content? (unused) |", "|---|---|---|"]
    for p in sorted(by_param):
        types_cell = ", ".join(f"`{t}`" for t in sorted(by_param[p]))
        lines.append(f"| `{p}` | {types_cell} |  |")
    return "\n".join(lines), len(by_param)


def render(schema: dict) -> str:
    """The whole appendix body: three captioned tables, markdown."""
    node_types = schema["$defs"]["node_types"]
    edge_pairs = schema["$defs"]["edge_pairs"]
    params_table, n_params = params_review_table(schema)

    return "\n\n".join([
        f"**{len(node_types)} node types.** Params split required / optional; "
        "\"carries content\" means the type also holds pandoc inline content, "
        "not only `params`.",
        node_types_table(schema),
        f"**{len(edge_pairs)} `(layer, type)` edge pairs.**",
        edge_pairs_table(schema),
        f"**{n_params} distinct params.** Which node types each appears on. "
        "The third column is a leftover: it was to be filled in by hand, one "
        "row at a time, deciding which params counted as content. `v0.2.13` "
        "removed that question rather than answering it — the mapping is the "
        "whitelist — so nothing reads this column. It is still rendered "
        "because the table is generated and an empty column is cheaper than "
        "a special case.",
        params_table,
    ])


def main():
    print(render(load_schema()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
