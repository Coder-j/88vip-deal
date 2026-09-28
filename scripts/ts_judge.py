#!/usr/bin/env python3
"""TypeSafe 结构化判断辅助 — 供 88vip-deal 流程在关键决策点调用。

用法（在 Bash 中）：
  python3 ts_judge.py --state-file page_text.txt --questions questions.json

questions.json 示例：
{
  "page_type": {
    "type": "choice",
    "instructions": "这是淘宝的什么页面？",
    "criteria": {
      "login": "登录页",
      "product": "商品详情页",
      "confirm_order": "确认订单页",
      "risk_control": "安全验证/风控拦截页",
      "order_list": "已买到的宝贝列表",
      "other": "其他页面"
    }
  },
  "is_total_correct": {
    "type": "noul",
    "instructions": "订单合计应付是否恰好为 ¥0.01？",
    "criteria": {"true": "合计显示0.01元", "false": "合计不是0.01元"}
  }
}

返回 JSON：{"answers": {...}, "usage": {...}}
API key 从环境变量 TYPESAFE_API_KEY 读取。
"""
import argparse, json, os, sys, urllib.request

def call_typesafe(state, questions, model="jev-latest"):
    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        print(json.dumps({"error": "TYPESAFE_API_KEY not set"}, ensure_ascii=False))
        sys.exit(1)
    body = json.dumps({"state": state, "model": model, "questions": questions}).encode()
    req = urllib.request.Request(
        "https://api.typesafe.ai/v1/systemone",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="包含页面文本的文件路径")
    ap.add_argument("--questions", required=True, help="questions JSON 文件路径或 JSON 字符串")
    args = ap.parse_args()

    with open(args.state_file, "r") as f:
        state = f.read()

    # questions 可以是文件路径或 JSON 字符串
    if os.path.exists(args.questions):
        with open(args.questions, "r") as f:
            questions = json.load(f)
    else:
        questions = json.loads(args.questions)

    result = call_typesafe(state, questions)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
