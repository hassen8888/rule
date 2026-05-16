# modules/preprocess.py (PoC-0009 専用版)
import json
import pandas as pd
import numpy as np
from pathlib import Path


# ============================================================
# ユーティリティ
# ============================================================

def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# JSON キーをすべて str に変換
# ============================================================

def convert_keys_to_str(obj):
    if isinstance(obj, dict):
        return {str(k): convert_keys_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_keys_to_str(v) for v in obj]
    else:
        return obj


# ============================================================
# CSV 読み込み（schema.json に従う）
# ============================================================

def load_csv_with_schema(csv_path: Path, schema: dict) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    # 型変換
    for col, spec in schema["columns"].items():
        if col not in df.columns:
            raise ValueError(f"CSV に列 {col} が存在しません")

        t = spec["type"]

        if t == "float":
            df[col] = pd.to_numeric(df[col], errors="coerce")

        elif t == "int":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        elif t == "string":
            df[col] = df[col].astype(str)

        else:
            raise ValueError(f"未知の型: {t}")

    return df


# ============================================================
# ルール：basic_stats
# ============================================================

def compute_basic_stats(df: pd.DataFrame, rules: dict) -> dict:
    out = {}

    if "basic_stats" not in rules["summaries"]:
        return out

    cfg = rules["summaries"]["basic_stats"]

    if cfg.get("samples", False):
        out["samples"] = len(df)

    if "outcome_type_counts" in cfg:
        col = cfg["outcome_type_counts"]["group_by"]
        out["outcome_type_counts"] = df[col].value_counts().sort_index().to_dict()

    return out


# ============================================================
# ルール：time_distribution
# ============================================================

def compute_time_distribution(df: pd.DataFrame, rules: dict) -> dict:
    if "time_distribution" not in rules["summaries"]:
        return {}

    cfg = rules["summaries"]["time_distribution"]
    col = cfg["columns"][0]
    group = cfg["group_by"]

    out = {}
    grouped = df.groupby(group)[col]

    for g, series in grouped:
        out[str(g)] = {
            "count": int(series.count()),
            "mean": float(series.mean()) if series.count() > 0 else None,
            "median": float(series.median()) if series.count() > 0 else None,
            "p25": float(series.quantile(0.25)) if series.count() > 0 else None,
            "p75": float(series.quantile(0.75)) if series.count() > 0 else None,
        }

    return out


# ============================================================
# ルール：hourly_stats
# ============================================================

def compute_hourly_stats(df: pd.DataFrame, rules: dict) -> dict:
    if "hourly_stats" not in rules["summaries"]:
        return {}

    cfg = rules["summaries"]["hourly_stats"]
    col = cfg["columns"][0]
    group = cfg["group_by"]

    out = {}
    grouped = df.groupby(group)[col].value_counts().unstack(fill_value=0)

    for hour, row in grouped.iterrows():
        out[str(hour)] = row.to_dict()

    return out


# ============================================================
# ルール：spread_binned_stats
# ============================================================

def compute_spread_binned(df: pd.DataFrame, rules: dict) -> dict:
    if "spread_binned_stats" not in rules["summaries"]:
        return {}

    cfg = rules["summaries"]["spread_binned_stats"]
    col = cfg["columns"][0]
    bins = cfg["bins"]
    group = cfg["group_by"]

    out = {}

    series = df[col].dropna()
    if len(series) == 0:
        return out

    qs = np.linspace(0, 1, bins + 1)
    edges = series.quantile(qs).values

    binned_list = []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]

        if i < bins - 1:
            mask = (df[col] >= lo) & (df[col] < hi)
        else:
            mask = (df[col] >= lo) & (df[col] <= hi)

        sub = df[mask]
        if len(sub) == 0:
            binned_list.append({
                "bin": f"[{lo:.4f},{hi:.4f}]",
                "samples": 0
            })
            continue

        binned_list.append({
            "bin": f"[{lo:.4f},{hi:.4f}]",
            "samples": len(sub),
            "outcome_type_counts": sub[group].value_counts().to_dict(),
            "avg_outcome_time": float(sub["outcome_time_sec"].mean())
        })

    out[col] = binned_list
    return out


# ============================================================
# ルール：direction_relation
# ============================================================

def compute_direction_relation(df: pd.DataFrame, rules: dict) -> dict:
    if "direction_relation" not in rules["summaries"]:
        return {}

    cfg = rules["summaries"]["direction_relation"]
    col = cfg["columns"][0]
    group = cfg["group_by"]

    out = {}
    grouped = df.groupby(group)[col].value_counts().unstack(fill_value=0)

    for d, row in grouped.iterrows():
        out[str(d)] = row.to_dict()

    return out


# ============================================================
# メイン：schema/rules に基づく汎用 preprocess
# ============================================================

def run_preprocess(csv_path: Path, schema_path: Path, rules_path: Path) -> dict:
    print(f"[preprocess] CSV 読み込み: {csv_path}")

    schema = load_json(schema_path)
    rules = load_json(rules_path)

    df = load_csv_with_schema(csv_path, schema)

    print("[preprocess] 集計ルールに従って summary.json を生成中...")

    summary = {}

    summary.update(compute_basic_stats(df, rules))
    summary["time_distribution"] = compute_time_distribution(df, rules)
    summary["hourly_stats"] = compute_hourly_stats(df, rules)
    summary["spread_binned_stats"] = compute_spread_binned(df, rules)
    summary["direction_relation"] = compute_direction_relation(df, rules)

    return convert_keys_to_str(summary)
