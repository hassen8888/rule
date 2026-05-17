import argparse
import json
from pathlib import Path

from modules.makespec import run_makespec
from modules.generate import run_generate
from modules.preprocess import run_preprocess
from modules.analyze import run_analyze

# ★ PoC ルートを一元管理（サブフォルダ対応）
POC_ROOT = Path(r"C:\Users\hasej\Claude\PoCs")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--poc", required=True, help="PoC フォルダ（例: SimpleOutcome/PoC-0009）")
    parser.add_argument("--step", required=True,
                        choices=["makespec", "generate", "preprocess", "analyze"])
    parser.add_argument("--csv", help="preprocess / analyze のとき必須")
    parser.add_argument("--base_mq5", help="ベースEAのパス")

    args = parser.parse_args()

    # ★ サブフォルダ対応：poc_id はサブパスとして扱う
    poc_dir = POC_ROOT / args.poc
    poc_id = args.poc

    base_mq5 = Path(args.base_mq5).resolve() if args.base_mq5 else None

    # preprocess / analyze のとき CSV 必須
    csv_path = None
    if args.step in ("preprocess", "analyze"):
        if not args.csv:
            raise ValueError(f"--step {args.step} の場合は --csv が必須です")
        csv_path = Path(args.csv).resolve()

    # ステップ振り分け
    if args.step == "makespec":
        run_makespec(poc_id, base_mq5)

    elif args.step == "generate":
        run_generate(poc_id, base_mq5)

    elif args.step == "preprocess":
        schema = poc_dir / "csvschema.json"
        rules  = poc_dir / "preprocess_rules.json"
        summary = run_preprocess(csv_path, schema, rules)
        (poc_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[preprocess] 完了: {poc_dir/'summary.json'}")

    elif args.step == "analyze":
        run_analyze(poc_id, csv_path)


if __name__ == "__main__":
    main()
