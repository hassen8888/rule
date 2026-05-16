# modules/makespec.py
import json
import os
from pathlib import Path
from openai import OpenAI

# ============================================================
# 設定（必要に応じて run_poc.py 側で上書き可能）
# ============================================================

PocRoot = Path(r"C:\Users\hasej\PoC_Runtime\PoCs")
RulesDir = Path(r"C:\Users\hasej\PoC_Runtime\rules")

# 必須ファイル
CODEGEN_RULES_MD = RulesDir / "コード生成時注意点.md"
POC_MANAGEMENT_MD = RulesDir / "PoC管理ルール.md"


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
# RULE ブロック抽出（コード生成時注意点.md）
# ============================================================

def extract_rule_blocks(rules_md: str) -> str:
    lines = rules_md.splitlines()
    blocks = []

    current_id = None
    buf = []

    for line in lines:
        if line.startswith(":::rule "):
            if current_id and buf:
                blocks.append("\n".join(buf))
            buf = [line]
            parts = line.split('id="')
            if len(parts) >= 2:
                current_id = parts[1].split('"')[0]
            else:
                current_id = None

        elif line.startswith(":::endrule"):
            if current_id and buf:
                buf.append(line)
                blocks.append("\n".join(buf))
            current_id = None
            buf = []

        else:
            if current_id:
                buf.append(line)

    return "\n\n".join(blocks)


# ============================================================
# OpenAI 呼び出し（makespec）
# ============================================================

def call_openai_makespec(
    poc_id: str,
    request_md: str,
    base_ea_code: str | None,
    csvschema_text: str,
    poc_management_text: str,
    rules_text: str,
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

    system_prompt = """
あなたは MQL5 と EA 設計に精通したアシスタントです。
以下の情報をすべて参照し、PoC の実装仕様（implementation.md）を作成してください。

【参照情報】
1. PoC要求仕様（request.md）
2. ベースEAコード（任意）
3. csvschema.json（ログ仕様）
4. PoC管理ルール（PoC管理ルール.md）
5. コード生成時注意点（RULE ブロック）

これらを踏まえ、以下を必ず含む実装仕様を Markdown で作成してください：

- Purpose（目的）
- Implementation（実装内容）
- Execution Conditions（実行条件）
- Evaluation Hypotheses（評価仮説）
- Evaluation Specification（評価仕様）
- Next Step（次のステップ）
- Question（不明点・追加質問）

質問がある場合は必ず列挙し、ユーザーの回答後に再生成される前提で書いてください。
"""

    if base_ea_code:
        base_section = (
            f"\n--- ベースEAコード（{poc_id} の継承元: PoC-0007/PoC-0007.mq5） ---\n"
            f"{base_ea_code}\n"
            "---------------------------\n"
        )
    else:
        base_section = ""

    user_prompt = f"""
PoC ID: {poc_id}

--- PoC要求仕様（request.md） ---
{request_md}
---------------------------------

--- csvschema.json（ログ仕様） ---
{csvschema_text}
---------------------------------

--- PoC管理ルール ---
{poc_management_text}
---------------------------------

--- コード生成時注意点（RULE ブロック） ---
{rules_text}
---------------------------------

{base_section}

以上を踏まえて、PoC-XXXX_implementation.md を生成してください。
"""

    print(f"[makespec] OpenAI に実装仕様生成を依頼中... ({poc_id})")

    response = client.chat.completions.create(
        model="gpt-5.4",
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

def run_makespec(poc_id: str, base_mq5_path: Path | None):
    poc_dir = PocRoot / poc_id
    poc_dir.mkdir(parents=True, exist_ok=True)

    # ★ サブフォルダ対応：ファイル名用に PoC-xxxx 部分だけ取り出す
    poc_name = Path(poc_id).name  # 例: "PoC-0009"

    print(f"[makespec] 開始: {poc_id}")

    request_md_path = poc_dir / f"{poc_name}_request.md"
    csvschema_path = poc_dir / "csvschema.json"

    request_md = load_text(request_md_path)
    csvschema_text = load_text(csvschema_path)
    poc_management_text = load_text(POC_MANAGEMENT_MD)
    rules_md = load_text(CODEGEN_RULES_MD)
    rules_text = extract_rule_blocks(rules_md)

    base_ea_code = None
    if base_mq5_path and base_mq5_path.exists():
        base_ea_code = load_text(base_mq5_path)

    implementation_md = call_openai_makespec(
        poc_id=poc_id,
        request_md=request_md,
        base_ea_code=base_ea_code,
        csvschema_text=csvschema_text,
        poc_management_text=poc_management_text,
        rules_text=rules_text,
    )

    impl_path = poc_dir / f"{poc_name}_implementation.md"
    save_text(impl_path, implementation_md)

    status = load_status(poc_dir)
    status["makespec_done"] = True
    save_status(poc_dir, status)

    print(f"[makespec] 完了: {impl_path}")
    return impl_path
