# -*- coding: utf-8 -*-
"""
命令行入口

示例：
  python cli.py samples/普通起诉状_民间借贷.txt                      # Markdown 输出到终端
  python cli.py samples/普通起诉状_民间借贷.txt --format docx        # 输出 Word 到 output/
  python cli.py samples/普通起诉状_民间借贷.txt --use-llm            # 启用 LLM 补抽
  python cli.py samples/普通起诉状_民间借贷.txt --court              # 法院官方格式（znszj）
"""
import argparse
import sys

from element_complaint import convert, convert_via_court, all_causes


def main():
    causes = ["自动识别"] + all_causes()
    parser = argparse.ArgumentParser(
        description="普通起诉状 → 要素式起诉状 转换器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="普通起诉状文本文件路径")
    parser.add_argument("--cause", default="自动识别",
                        help=f"案由，可选: {' / '.join(causes)}（默认自动识别）")
    parser.add_argument("--format", choices=["text", "markdown", "docx"], default="markdown",
                        help="输出格式（默认 markdown）")
    parser.add_argument("--use-llm", action="store_true", help="启用 LLM 补抽（需配置 GLM API Key）")
    parser.add_argument("--court", action="store_true",
                        help="使用法院官方 API 后端(znszj)，直接产出法院格式 docx（需联网）")
    parser.add_argument("--out", default=None, help="输出路径（docx 时默认 output/ 目录）")
    args = parser.parse_args()

    try:
        with open(args.input, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"❌ 无法读取文件 {args.input}: {e}", file=sys.stderr)
        sys.exit(1)

    cause = None if args.cause == "自动识别" else args.cause

    try:
        if args.court:
            res = convert_via_court(text, cause=cause, out_path=args.out)
            print(f"✅ 法院官方格式转换完成")
            print(f"   案由: {res['cause']}    mbid: {res['mbid']}")
            print(f"   输出: {res['output']}")
        else:
            res = convert(text, cause=cause, use_llm=args.use_llm,
                          fmt=args.format, out_path=args.out)
            if args.format == "docx":
                print(f"✅ 要素式起诉状已生成: {res['output']}")
            else:
                print(res["output"])
            print(f"\n[案由: {res['cause']}  |  抽取来源: {res['source']}]",
                  file=sys.stderr)
    except Exception as e:
        print(f"❌ 转换失败: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
