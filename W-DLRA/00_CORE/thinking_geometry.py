"""Observable thinking-geometry builder for W-DLRA.

This module only uses externally visible traces (prompt, response, optional events)
and never claims access to hidden chain-of-thought.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
    "this",
    "these",
    "those",
    "or",
    "but",
    "if",
    "then",
    "than",
    "so",
    "we",
    "you",
    "they",
    "i",
    "our",
    "your",
    "their",
}
NEGATIONS = {"not", "never", "no", "none", "cannot", "can't", "won't", "without"}


@dataclass(frozen=True)
class ObservableTrace:
    prompt: str
    response: str
    events: list[dict[str, Any]]


class TraceParseError(RuntimeError):
    """Raised when a trace file cannot be parsed into prompt/response."""


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9']+", text.lower())


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    return [c.strip() for c in chunks if c.strip()]


def _split_clauses(sentence: str) -> list[str]:
    coarse = re.split(r"[;,:()]", sentence)
    clauses: list[str] = []
    for part in coarse:
        subparts = re.split(r"\b(?:and|but|because|while|although|however)\b", part, flags=re.IGNORECASE)
        clauses.extend(s.strip(" -\n\t") for s in subparts if s.strip(" -\n\t"))
    return clauses or [sentence.strip()]


def _extract_keyphrases(clause: str, limit: int = 3) -> list[str]:
    tokens = [t for t in _tokenize(clause) if len(t) > 2 and t not in STOPWORDS]
    if not tokens:
        return []
    counts = Counter(tokens)
    ranked = sorted(counts.items(), key=lambda x: (-x[1], -len(x[0]), x[0]))
    return [token for token, _ in ranked[:limit]]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _safe_text_label(text: str, width: int = 36) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= width else f"{text[: width - 1]}…"


def load_trace(path: Path) -> ObservableTrace:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        records: list[dict[str, Any]] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            records.append(json.loads(line))
        if not records:
            raise TraceParseError("JSONL trace is empty.")
        merged = {
            "prompt": records[0].get("prompt", ""),
            "response": "\n".join(r.get("response", "") for r in records if r.get("response")),
            "events": [e for r in records for e in r.get("events", []) if isinstance(e, dict)],
        }
        return ObservableTrace(
            prompt=merged["prompt"].strip(),
            response=merged["response"].strip(),
            events=merged["events"],
        )

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return ObservableTrace(
            prompt=str(data.get("prompt", "")).strip(),
            response=str(data.get("response", "")).strip(),
            events=[e for e in data.get("events", []) if isinstance(e, dict)],
        )

    raw = path.read_text(encoding="utf-8")
    prompt_match = re.search(r"(?is)prompt\s*:\s*(.+?)\n\s*response\s*:", raw)
    response_match = re.search(r"(?is)response\s*:\s*(.+?)(?:\n\s*events\s*:|$)", raw)
    events_match = re.search(r"(?is)events\s*:\s*(\[.*\])\s*$", raw)

    if not prompt_match or not response_match:
        raise TraceParseError("Text trace must contain 'prompt:' and 'response:' sections.")

    events: list[dict[str, Any]] = []
    if events_match:
        loaded = json.loads(events_match.group(1))
        if isinstance(loaded, list):
            events = [e for e in loaded if isinstance(e, dict)]

    return ObservableTrace(
        prompt=prompt_match.group(1).strip(),
        response=response_match.group(1).strip(),
        events=events,
    )


def build_thinking_geometry(trace: ObservableTrace) -> tuple[dict[str, Any], dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def add_node(node_type: str, text: str, **extra: Any) -> str:
        node_id = f"n{len(nodes)}"
        nodes.append({"id": node_id, "type": node_type, "text": text, **extra})
        return node_id

    def add_edge(src: str, dst: str, relation: str, weight: float = 1.0) -> None:
        edges.append(
            {
                "id": f"e{len(edges)}",
                "source": src,
                "target": dst,
                "relation": relation,
                "weight": round(weight, 3),
            }
        )

    sentence_ids: list[str] = []
    clause_records: list[dict[str, Any]] = []

    sentences = _split_sentences(trace.response)
    for s_idx, sentence in enumerate(sentences):
        s_id = add_node("sentence", sentence, sentence_index=s_idx)
        sentence_ids.append(s_id)
        clauses = _split_clauses(sentence)
        for c_idx, clause in enumerate(clauses):
            c_id = add_node("clause", clause, sentence_index=s_idx, clause_index=c_idx)
            add_edge(s_id, c_id, "elaborates", 0.8)
            c_tokens = {t for t in _tokenize(clause) if t not in STOPWORDS}
            c_negated = any(n in c_tokens for n in NEGATIONS)
            clause_records.append(
                {
                    "id": c_id,
                    "text": clause,
                    "tokens": c_tokens,
                    "negated": c_negated,
                    "sentence_index": s_idx,
                }
            )
            for phrase in _extract_keyphrases(clause):
                p_id = add_node("keyphrase", phrase, sentence_index=s_idx, clause_index=c_idx)
                add_edge(c_id, p_id, "supports", 0.6)

    for i in range(len(clause_records)):
        for j in range(i + 1, len(clause_records)):
            left = clause_records[i]
            right = clause_records[j]
            overlap = _jaccard(left["tokens"], right["tokens"])
            if overlap <= 0.0:
                continue
            if overlap >= 0.72:
                add_edge(left["id"], right["id"], "repeats", overlap)
            elif left["negated"] != right["negated"] and overlap >= 0.22:
                add_edge(left["id"], right["id"], "contradicts", overlap)
            elif right["sentence_index"] > left["sentence_index"] and overlap >= 0.14:
                add_edge(left["id"], right["id"], "elaborates", overlap)
            elif overlap >= 0.26:
                add_edge(left["id"], right["id"], "supports", overlap)

    graph = {
        "meta": {
            "source": "observable_trace",
            "disclaimer": "Derived from prompt/response/events only; no hidden chain-of-thought inference.",
            "events_count": len(trace.events),
        },
        "nodes": nodes,
        "edges": edges,
    }

    metrics = compute_metrics(trace, nodes, edges)
    return graph, metrics


def compute_metrics(trace: ObservableTrace, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    response_tokens = [t for t in _tokenize(trace.response) if t not in STOPWORDS]
    prompt_tokens = [t for t in _tokenize(trace.prompt) if t not in STOPWORDS]

    response_set = set(response_tokens)
    prompt_set = set(prompt_tokens)
    novelty = 1.0
    if response_set:
        novelty = len(response_set - prompt_set) / len(response_set)

    relation_counts = Counter(edge["relation"] for edge in edges)
    total_rel = sum(relation_counts.values())
    relation_entropy = 0.0
    if total_rel:
        for count in relation_counts.values():
            p = count / total_rel
            relation_entropy += -p * math.log2(p)

    clause_count = sum(1 for n in nodes if n["type"] == "clause")
    repetition_ratio = relation_counts.get("repeats", 0) / max(clause_count, 1)
    contradiction_edges = [edge["id"] for edge in edges if edge["relation"] == "contradicts"]

    out_degree = defaultdict(int)
    for edge in edges:
        out_degree[edge["source"]] += 1
    branching_factor = sum(out_degree.values()) / max(len(out_degree), 1)

    return {
        "disclaimer": "Metrics are computed from observable text and optional metadata only.",
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "events": len(trace.events),
            "clauses": clause_count,
        },
        "metrics": {
            "repetition_ratio": round(repetition_ratio, 4),
            "contradiction_flags": contradiction_edges,
            "contradiction_count": len(contradiction_edges),
            "novelty": round(novelty, 4),
            "compression_ratio": round(len(response_tokens) / max(len(prompt_tokens), 1), 4),
            "branching_factor": round(branching_factor, 4),
            "relation_entropy": round(relation_entropy, 4),
        },
        "relation_breakdown": dict(relation_counts),
    }


def render_svg(graph: dict[str, Any], destination: Path) -> None:
    layer_x = {"sentence": 120, "clause": 420, "keyphrase": 720}
    layer_count: dict[str, int] = defaultdict(int)
    positions: dict[str, tuple[int, int]] = {}

    for node in graph["nodes"]:
        ntype = node["type"]
        layer_count[ntype] += 1
        y = 50 + layer_count[ntype] * 60
        x = layer_x.get(ntype, 120)
        positions[node["id"]] = (x, y)

    colors = {
        "supports": "#2e7d32",
        "elaborates": "#1565c0",
        "contradicts": "#c62828",
        "repeats": "#6a1b9a",
    }
    node_fill = {"sentence": "#eef7ff", "clause": "#f8fff0", "keyphrase": "#fff8e8"}

    width = 920
    max_layer = max((pos[1] for pos in positions.values()), default=200)
    height = max(260, max_layer + 80)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="24" y="24" font-family="Arial" font-size="14" fill="#222">W-DLRA Thinking Geometry (observable traces)</text>',
    ]

    for edge in graph["edges"]:
        sx, sy = positions[edge["source"]]
        tx, ty = positions[edge["target"]]
        color = colors.get(edge["relation"], "#777")
        parts.append(
            f'<line x1="{sx + 90}" y1="{sy}" x2="{tx - 90}" y2="{ty}" stroke="{color}" stroke-width="1.2" opacity="0.85" />'
        )

    for node in graph["nodes"]:
        x, y = positions[node["id"]]
        fill = node_fill.get(node["type"], "#f3f3f3")
        label = _safe_text_label(node["text"])
        parts.append(
            f'<rect x="{x - 90}" y="{y - 18}" width="180" height="36" rx="8" ry="8" fill="{fill}" stroke="#888" stroke-width="0.8" />'
        )
        parts.append(
            f'<text x="{x - 82}" y="{y - 2}" font-family="Arial" font-size="11" fill="#222">{label}</text>'
        )
        parts.append(
            f'<text x="{x - 82}" y="{y + 12}" font-family="Arial" font-size="9" fill="#555">{node["type"]}</text>'
        )

    parts.append("</svg>")
    destination.write_text("\n".join(parts), encoding="utf-8")


def generate_geometry(input_path: Path, output_dir: Path) -> tuple[Path, Path, Path]:
    trace = load_trace(input_path)
    graph, metrics = build_thinking_geometry(trace)

    output_dir.mkdir(parents=True, exist_ok=True)
    graph_json_path = output_dir / "graph.json"
    svg_path = output_dir / "graph.svg"
    metrics_path = output_dir / "metrics.json"

    graph_json_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    render_svg(graph, svg_path)

    return graph_json_path, svg_path, metrics_path
