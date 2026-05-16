# modules/analyze.py
import json
import os
from pathlib import Path
from openai import OpenAI

from modules.preprocess import run_preprocess


# ============================================================
# 設定
# ============================================================

PocRoot = Path(r"C:\Users\hasej\PoC_Runtime\PoCs")
RulesDir = Path(r"C:\Users\hasej\PoC_Runtime\rules")

POC_MANAGEMENT_MD = RulesDir / "PoC管理ルール.md"
ANALYZE_RULES_MD  = RulesDir / "analyze時注意点.md"   # ★ 新規追加


# ============================================================
# ユーティリティ
# ============================================================

def load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {path}")
    return path.read_text(encoding="utf-8")


def save_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_status(poc_dir: Path) -> dict:
    status_path = poc_dir / "status.json"
    if status_path.exists():
        return json.loads(status_path.read_text(encoding="utf-8"))
    return {
        "makespec_done": False,
        "generate_done": False,
        "preprocess_done": False,
        "analyze_done": False,
    }


def save_status(poc_dir: Path, status: dict):
    status_path = poc_dir / "status.json"
    save_text(status_path, json.dumps(status, ensure_ascii=False, indent=2))


# ============================================================
# OpenAI 呼び出し（analysis）
# ============================================================

def call_openai_analyze(
    poc_id: str,
    summary_json: dict,
    implementation_md: str,
    poc_management_text: str,
    analyze_rules_text: str,     # ★ 新規追加
) -> str:

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "環境変数 OPENAI_API_KEY が設定されていません。\n"
            "PowerShell なら以下で設定できます：\n"
            '  setx OPENAI_API_KEY "sk-xxxx"\n'
            "設定後、PowerShell を再起動してください。"
        )

    client = OpenAI(api_key=api_key)

    # ★ analyze 専用の system_prompt に analyze_rules を追加
    system_prompt = f"""
あなたは金融市場の構造分析と特徴量解析に長けたアナリストです。

以下の情報を参照し、PoC の評価レポート（Markdown）を作成してください。

【参照情報】
1. summary.json（特徴量サマリ）
2. PoC-XXXX_implementation.md（実装仕様）
3. PoC管理ルール（評価仕様の構造）
4. analyze時注意点.md（分析時のルール）

分析時注意点:
{analyze_rules_text}

レポートには以下を必ず含めてください：

- PoC ID
- Purpose（目的）
- Evaluation Specification（評価仕様）
- Results（評価結果）
- Analysis（考察）
- Improvement Plan（改善点）
- Next Step（次のステップ）

Markdown 形式で返してください。
"""

    user_prompt = f"""
PoC ID: {poc_id}

--- summary.json ---
{json.dumps(summary_json, ensure_ascii=False, indent=2)}
--------------------

--- implementation.md ---
{implementation_md}
-------------------------

--- PoC管理ルール ---
{poc_management_text}
-------------------------

--- analyze時注意点 ---
{analyze_rules_text}
-------------------------

以上を踏まえて、PoC-XXXX_report.md を生成してください。
"""

    print(f"[analyze] OpenAI にレポート生成を依頼中... ({poc_id})")

    response = client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content


# ============================================================
# メイン処理（run_poc.py から呼ばれる）
# ============================================================

def run_analyze(poc_id: str, csv_path: Path):
    poc_dir = PocRoot / poc_id
    poc_dir.mkdir(parents=True, exist_ok=True)

    poc_name = Path(poc_id).name

    print(f"[analyze] 開始: {poc_id}")
    print(f"[analyze] 対象 CSV: {csv_path}")

    # ① preprocess
    schema_path = poc_dir / "csvschema.json"
    rules_path = poc_dir / "preprocess_rules.json"

    print("[analyze] preprocess（内部実行）...")
    summary_json = run_preprocess(csv_path, schema_path, rules_path)

    summary_path = poc_dir / "summary.json"
    save_text(summary_path, json.dumps(summary_json, ensure_ascii=False, indent=2))

    # ② implementation.md 読み込み
    impl_path = poc_dir / f"{poc_name}_implementation.md"
    implementation_md = load_text(impl_path)

    poc_management_text = load_text(POC_MANAGEMENT_MD)

    # ★ analyze時注意点.md を読み込む
    analyze_rules_text = load_text(ANALYZE_RULES_MD)

    # ③ OpenAI にレポート生成依頼
    report_md = call_openai_analyze(
        poc_id=poc_id,
        summary_json=summary_json,
        implementation_md=implementation_md,
        poc_management_text=poc_management_text,
        analyze_rules_text=analyze_rules_text,   # ★ 追加
    )

    # ④ 保存
    report_path = poc_dir / f"{poc_name}_report.md"
    save_text(report_path, report_md)

    # ⑤ status 更新
    status = load_status(poc_dir)
    status["analyze_done"] = True
    save_status(poc_dir, status)

    print(f"[analyze] 完了: {report_path}")
    return report_path
