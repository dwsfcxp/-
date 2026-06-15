# -*- coding: utf-8 -*-
"""
命令行入口

起诉状：
  python cli.py samples/普通起诉状_民间借贷.txt                      # Markdown 输出到终端
  python cli.py samples/普通起诉状_民间借贷.txt --format docx        # 输出 Word 到 output/
  python cli.py samples/普通起诉状_民间借贷.txt --use-llm            # 启用 LLM 补抽
  python cli.py samples/普通起诉状_民间借贷.txt --court              # 法院官方格式（znszj）

强制执行申请书：
  python cli.py samples/普通强制执行申请书_借贷.txt --execution      # 普通执行申请书→要素式
  python cli.py samples/普通强制执行申请书_借贷.txt --execution --format docx --cutoff 2025-06-14
"""
import argparse
import sys
from datetime import date

from element_complaint import convert, convert_via_court, convert_application, all_causes


def main():
    causes = ["自动识别"] + all_causes()
    parser = argparse.ArgumentParser(
        description="普通起诉状/申请书 → 要素式 转换器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="普通起诉状/申请书文本文件路径")
    parser.add_argument("--cause", default="自动识别",
                        help=f"案由（起诉状用）: {' / '.join(causes)}（默认自动识别）")
    parser.add_argument("--format", choices=["text", "markdown", "docx"], default="markdown",
                        help="输出格式（默认 markdown）")
    parser.add_argument("--use-llm", action="store_true", help="启用 LLM 补抽（起诉状，需配置 GLM API Key）")
    parser.add_argument("--court", action="store_true",
                        help="使用法院官方 API 后端(znszj)，产出法院格式 docx（需联网）")
    parser.add_argument("--execution", action="store_true",
                        help="使用强制执行申请书引擎（普通执行申请书 → 要素式，移植自法穿）")
    parser.add_argument("--cutoff", default=None,
                        help="利息截止日 YYYY-MM-DD（执行申请书用，默认今天）")
    parser.add_argument("--paid", default=None,
                        help="被执行人已付款金额（执行申请书用，单位元）")
    parser.add_argument("--out", default=None, help="输出路径（docx 时默认 output/ 目录）")
    args = parser.parse_args()

    try:
        with open(args.input, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"❌ 无法读取文件 {args.input}: {e}", file=sys.stderr)
        sys.exit(1)

    cause = None if args.cause == "自动识别" else args.cause

    cutoff = None
    if args.cutoff:
        try:
            y, m, d = args.cutoff.split('-')
            cutoff = date(int(y), int(m), int(d))
        except Exception:
            print("❌ --cutoff 格式应为 YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)

    try:
        if args.execution:
            res = convert_application(
                text, fmt=args.format, out_path=args.out,
                cutoff_date=cutoff, paid_amount=args.paid,
            )
            if args.format == "docx":
                print(f"✅ 要素式强制执行申请书已生成: {res['output']}")
            else:
                print(res['output'])
            total = res['computation'].structured_params.get('total')
            warns = res['computation'].warnings
            tail = f"  |  合计: {total}元" + (f"  |  ⚠️ {len(warns)}条提示" if warns else "")
            print(f"\n[文书类型: 强制执行申请书  |  引擎: execution_request{tail}]",
                  file=sys.stderr)
        elif args.court:
            res = convert_via_court(text, cause=cause, out_path=args.out)
            print("✅ 法院官方格式转换完成")
            print(f"   案由: {res['cause']}    mbid: {res['mbid']}")
            print(f"   输出: {res['output']}")
        else:
            res = convert(text, cause=cause, use_llm=args.use_llm,
                          fmt=args.format, out_path=args.out)
            if args.format == "docx":
                print(f"✅ 要素式起诉状已生成: {res['output']}")
            else:
                print(res['output'])
            print(f"\n[案由: {res['cause']}  |  抽取来源: {res['source']}]",
                  file=sys.stderr)
    except Exception as e:
        print(f"❌ 转换失败: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
