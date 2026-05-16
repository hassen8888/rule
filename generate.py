# modules/generate.py
import json
import os
from pathlib import Path
from openai import OpenAI
import shutil
import subprocess

# ============================================================
# 設定
# ============================================================

PocRoot = Path(r"C:\Users\hasej\PoC_Runtime\PoCs")
RulesDir = Path(r"C:\Users\hasej\PoC_Runtime\rules")

CODEGEN_RULES_MD = RulesDir / "コード生成時注意点.md"
POC_MANAGEMENT_MD = RulesDir / "PoC管理ルール.md"

MT5_EDITOR = r"C:\Program Files\Gaitame Finest MetaTrader 5 Terminal\MetaEditor64.exe"
MT5_EXPERTS_POC_DIR = Path(
    r"C:\Users\hasej\AppData\Roaming\MetaQuotes\Terminal\52E30E5000D12076386E4B78F270129E\MQL5\Experts\PoCs"
)


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
# RULE ブロック抽出
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
# コードブロック除去
# ============================================================

def clean_codeblock(text: str) -> str:
    t = text.strip()

    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1 :]

    if t.endswith("```"):
        t = t[:-3]

    t = t.replace("```", "")
    t = t.replace("\ufeff", "")

    return t.strip()


# ============================================================
# OpenAI 呼び出し（EAコード生成）
# ============================================================

def call_openai_generate(
    poc_id: str,
    implementation_md: str,
    base_ea_code: str | None,
    csvschema_text: str,
    poc_management_text: str,
    rules_text: str,
    extra_comment: str | None,
) -> str:

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("環境変数 OPENAI_API_KEY が設定されていません。")

    client = OpenAI(api_key=api_key)

    if base_ea_code:
        base_section = (
            f"\n--- ベースEAコード（{poc_id} の継承元: PoC-0007/PoC-0007.mq5） ---\n"
            f"{base_ea_code}\n"
            "---------------------------\n"
        )
    else:
        base_section = ""

    if extra_comment:
        extra_section = (
            f"\n--- generate時追加コメント ---\n"
            f"{extra_comment}\n"
            "-------------------------------------\n"
        )
    else:
        extra_section = ""

    system_prompt = """
あなたは MQL5 の専門家です。
以下の仕様に基づき、完全な MQL5 EA コードのみを返してください。
コードブロック（```）は禁止です。
"""

    user_prompt = f"""
PoC ID: {poc_id}

--- 実装仕様 ---
{implementation_md}

--- csvschema.json ---
{csvschema_text}

--- PoC管理ルール ---
{poc_management_text}

--- コード生成時注意点（RULE） ---
{rules_text}

{base_section}
{extra_section}

以上を踏まえて、MQL5 EA コードのみを返してください。
"""

    print(f"[generate] OpenAI に EA コード生成を依頼中... ({poc_id})")

    response = client.chat.completions.create(
        model="gpt-5.4",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    raw = response.choices[0].message.content
    cleaned = clean_codeblock(raw)
    return cleaned


# ============================================================
# MetaEditor ビルド & デプロイ
# ============================================================

def build_ea(mq5_path: Path) -> Path:
    print("[generate] EA をビルド中...")

    cmd = [
        MT5_EDITOR,
        f"/compile:{mq5_path}",
        "/log",
    ]

    result = subprocess.run(cmd)

    if result.returncode not in (0, 1):
        raise RuntimeError(f"MetaEditor build failed (exit code={result.returncode})")

    ex5_path = mq5_path.with_suffix(".ex5")

    if not ex5_path.exists():
        raise RuntimeError("ビルドに失敗しました。ex5 が生成されていません")

    print(f"[generate] ビルド成功: {ex5_path}")
    return ex5_path


def deploy_ex5(ex5_path: Path):
    MT5_EXPERTS_POC_DIR.mkdir(parents=True, exist_ok=True)
    target = MT5_EXPERTS_POC_DIR / ex5_path.name
    shutil.copy2(ex5_path, target)
    print(f"[generate] ex5 を MT5 にデプロイしました: {target}")
    return target


# ============================================================
# メイン処理
# ============================================================

def run_generate(poc_id: str, base_mq5_path: Path | None):
    poc_dir = PocRoot / poc_id
    poc_dir.mkdir(parents=True, exist_ok=True)

    # ★ サブフォルダ対応：ファイル名用に PoC-xxxx 部分だけ取り出す
    poc_name = Path(poc_id).name  # 例: "PoC-0009"

    print(f"[generate] 開始: {poc_id}")

    impl_path = poc_dir / f"{poc_name}_implementation.md"
    csvschema_path = poc_dir / "csvschema.json"

    implementation_md = load_text(impl_path)
    csvschema_text = load_text(csvschema_path)
    poc_management_text = load_text(POC_MANAGEMENT_MD)
    rules_md = load_text(CODEGEN_RULES_MD)
    rules_text = extract_rule_blocks(rules_md)

    extra_comment_path = poc_dir / "generate時追加コメント.md"
    extra_comment = load_text(extra_comment_path) if extra_comment_path.exists() else None

    base_ea_code = None
    if base_mq5_path and base_mq5_path.exists():
        base_ea_code = load_text(base_mq5_path)

    ea_code = call_openai_generate(
        poc_id=poc_id,
        implementation_md=implementation_md,
        base_ea_code=base_ea_code,
        csvschema_text=csvschema_text,
        poc_management_text=poc_management_text,
        rules_text=rules_text,
        extra_comment=extra_comment,
    )

    mq5_path = poc_dir / f"{poc_name}.mq5"
    save_text(mq5_path, ea_code)

    # バックアップとして .mq5.txt も保存
    save_text(poc_dir / f"{poc_name}.mq5.txt", ea_code)

    ex5_path = build_ea(mq5_path)
    deploy_ex5(ex5_path)

    status = load_status(poc_dir)
    status["generate_done"] = True
    save_status(poc_dir, status)

    print(f"[generate] 完了: {mq5_path}")
    return mq5_path
