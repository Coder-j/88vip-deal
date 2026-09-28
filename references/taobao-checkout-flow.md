# 淘宝单笔下单流程（Browser Use + TypeSafe 辅助判断）

本文件描述使用 `computer_use_tool`（plane="bu"）完成单笔88VIP红包订单的完整步骤。
**关键决策点必须使用 TypeSafe 结构化判断**，不要靠肉眼猜 DOM 文本。

## 风控节奏：随机等待工具

每步操作前后必须加入随机等待，模拟真人行为。在浏览器单元开头定义：

```python
import seed_browser_use as bu
import time, random

def human_wait(min_s=1, max_s=3):
    time.sleep(random.uniform(min_s, max_s))

def page_wait():
    time.sleep(random.uniform(3, 8))
```

---

## TypeSafe 判断调用方式

在浏览器操作之间，用 Bash 调用辅助脚本做结构化判断：

```bash
# 1. 先把当前页面文本保存到临时文件
# （在浏览器单元里用 bu.get_page_text() 拿到文本，写入 /tmp/page_state.txt）

# 2. 构造 questions JSON，调用 TypeSafe
python3 <skill_dir>/scripts/ts_judge.py \
  --state-file /tmp/page_state.txt \
  --questions /tmp/questions.json
```

判断结果直接决定下一步动作：
- `choice` 返回的选项 → 路由到对应分支
- `noul` 返回的概率 → ≥0.8 视为"是"，≤0.2 视为"否"，中间值需截图复核

> 需要 API key：环境变量 `TYPESAFE_API_KEY`。如果未设置或调用失败，降级为截图人工判断，不要卡住流程。

---

## 前置：确认登录态 + 页面分类

```python
import seed_browser_use as bu
bu.navigate(config["item_url"])
bu.wait_for_load(timeout=20)
page_wait()
info = bu.page_info()
page_text = bu.get_page_text()
# 保存到文件供 TypeSafe 判断
with open("/tmp/page_state.txt", "w") as f:
    f.write(page_text + "\nURL: " + info["url"] + "\nTitle: " + info["title"])
```

**用 TypeSafe 判断页面类型**（choice）：

```json
{
  "page_type": {
    "type": "choice",
    "instructions": "这是淘宝的什么页面？",
    "criteria": {
      "login": "登录页，要求扫码或输入账号密码",
      "product": "商品详情页，能看到商品图、SKU选项、领券购买按钮",
      "confirm_order": "确认订单页，有收货地址、商品明细、付款金额、提交订单按钮",
      "risk_control": "安全验证、滑块、人机校验、交易风险提示",
      "out_of_stock": "商品已下架、库存不足、宝贝不存在",
      "other": "其他页面"
    }
  }
}
```

| TypeSafe 结果 | 动作 |
|---|---|
| `login` | 会话失效，调用 `interaction.request_action` 交还用户登录 |
| `risk_control` | 风控拦截，停止并报告 |
| `out_of_stock` | 商品已下架/无货，停止本单并报告，不尝试换商品 |
| `product` | 继续步骤0.5（订单去重检查） |
| `other` | 截图查看，判断是否需要刷新 |

## 步骤0.5：订单去重检查（防止重复下单）

**在进入商品页之前**，先快速检查今日是否已成功下过单：

1. 导航到已买到的宝贝列表 `https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm`
2. `page_wait()`，保存页面文本。
3. 用 TypeSafe `noul` 判断："列表中是否已有今天创建的、商品为 `item_title`、实付¥0.00的订单？"
4. **如果已存在今日订单** → 本单可能已成功，跳过下单，记录"今日订单已存在，跳过"。
5. 如果没有，回到商品页继续。

> 这一步防止定时任务重复触发或上一单结果不确定时重复提交。

## 步骤1：商品页确认

1. 自然滚动一次：`bu.scroll(500, 500, "down", amount=2)`，等待2秒。
2. 截图确认 SKU 选中状态。
3. **用 TypeSafe 验证 SKU 和数量**：
   - 把页面文本+截图描述写入 state
   - 问 `noul`: "页面中选中的SKU是否为用户配置的 `expected_sku`？数量是否为1？"
4. 如果 SKU 不对，点击对应 SKU 选项后重新判断。
5. 找到"领券购买"按钮并点击，`human_wait()`。

## 步骤2：确认订单页金额校验

等待跳转到 `buy.taobao.com/auction/buy_now.jhtml`，`page_wait()`。

1. 展开"查看付款详情"。
2. 保存完整页面文本到 `/tmp/page_state.txt`。
3. **用 TypeSafe 一次性并行判断三项**：

```json
{
  "red_packet_applied": {
    "type": "noul",
    "instructions": "付款详情中红包是否已抵扣 -2.00元？",
    "criteria": {
      "true": "红包行显示-2.00或类似负数抵扣",
      "false": "红包行显示不可用、0元、或未出现红包抵扣"
    }
  },
  "total_is_001": {
    "type": "noul",
    "instructions": "订单合计应付金额是否恰好为 ¥0.01？",
    "criteria": {
      "true": "合计显示0.01元",
      "false": "合计不是0.01元（如2.01、3.01等）"
    }
  },
  "shop_discount_ok": {
    "type": "noul",
    "instructions": "店铺优惠是否为满5元减3元（-3.00）？",
    "criteria": {"true": "店铺优惠行显示-3.00", "false": "店铺优惠金额不符"}
  },
  "payment_method": {
    "type": "choice",
    "instructions": "当前选中的支付方式是？",
    "criteria": {
      "first_use_then_pay": "先用后付",
      "alipay": "支付宝",
      "huabei": "花呗",
      "other": "其他"
    }
  }
}
```

### 金额判断逻辑（基于 TypeSafe 结果）

| 条件 | 动作 |
|---|---|
| `total_is_001` ≥0.8 且 `red_packet_applied` ≥0.8 且 `payment_method`=先用后付 | ✅ 继续步骤3提交 |
| `red_packet_applied` ≤0.2（红包不可用） | 执行红包恢复流程 |
| `total_is_001` ≤0.2 且红包恢复后仍不满足 | ❌ 不提交，报告金额不符 |
| 任何 noul 在 0.3–0.7 之间 | 截图人工复核，不要凭猜测提交 |

4. 核对收货地址：用 TypeSafe `noul` 判断"地址中是否包含 `address_keyword`"。不匹配则停止报告。

## 步骤3：提交订单

**仅当步骤2全部判断通过时**，点击"提交订单"按钮。

- 提交按钮只点击一次。
- 点击后 `page_wait()`。
- **用 TypeSafe 判断提交后状态**：
  - `noul`: "页面是否要求输入支付密码、短信验证码、人脸识别？"
  - `noul`: "页面是否显示下单成功/订单已提交？"
- 如果出现密码/验证码 → 立即调用 `interaction.request_action` 交还控制权。
- 如果不确定 → **不要重试点击**，去订单列表核实。

## 步骤4：验证订单

1. 导航到已买到的宝贝列表，`page_wait()`。
2. 保存页面文本，用 TypeSafe `choice` 选出最新订单：
   - 问题："以下哪个订单是今天刚下的、商品为 `expected_item_title`、实付¥0.00的订单？"
   - 选项为页面上可见的各订单摘要。
3. 对选中订单用 `noul` 确认：
   - "该订单实付款是否为¥0.00？"
   - "该订单创建时间是否为今天？"
4. 截图留证，记录订单号。

---

## 红包恢复流程

当 TypeSafe 判断 `red_packet_applied` ≤0.2 时执行：

> **关键认知**：88VIP天天2元红包是每天0点**自动发放**到卡券包的，不需要手动领取。
> 88VIP中心的"天天2元红包"卡片只是介绍页，点进去不会有领取按钮。

1. 点击"红包"行展开面板。
2. 保存面板文本，用 TypeSafe `choice` 判断红包不可用原因：
   - `already_used`: 今日红包已使用（当天已用过一次，不会再发）
   - `not_in_wallet`: 卡券包里没有今日红包（可能0点延迟，等几分钟刷新）
   - `wrong_category`: 红包限特定品类（百亿补贴/外卖专享）
   - `threshold_not_met`: 商品价格不满足2.01元门槛
   - `unchecked`: 红包存在但未勾选
   - `unknown`: 其他原因
3. 根据原因分支：
   - `unchecked`: 在红包面板中勾选2元红包，重新计算金额。
   - `already_used`: 今日红包已用完，跳过本单，报告"今日红包已使用"。
   - `not_in_wallet`: 等待3分钟后刷新确认订单页重试一次；仍无则跳过。
   - `wrong_category`: 该红包不适用此商品，停止并报告。
   - `threshold_not_met`: 商品价格不满足门槛，停止并报告。
4. 如果是 `not_in_wallet` 且等待后仍无红包，去"我的淘宝-红包卡券"确认。
5. 红包恢复后重新走步骤1-2确认金额。
6. 仍不可用则停止，报告"红包未恢复，未下单"。

---

## 常见故障处理

| 故障 | TypeSafe 辅助 | 处理 |
|---|---|---|
| 页面加载超时 | — | 刷新一次 |
| SKU未选中 | noul 判断SKU状态 | 点击对应选项 |
| 金额数字读不准 | TypeSafe 判 total_is_001 | 不要猜，用判断结果 |
| 提交后白页 | noul 判断是否下单成功 | 去订单列表查 |
| 会话断开 | — | `bu.resync()` |
| 滑块/验证码 | choice 识别为 risk_control | 交还用户 |
| 下单过多/交易风险 | choice 识别 | 停止，不重试 |
| TypeSafe 调用失败 | — | 降级为截图人工判断，不卡住流程 |

## 关键URL速查

| 用途 | URL |
|---|---|
| 商品页 | 配置中的 `item_url` |
| 确认订单 | `buy.taobao.com/auction/buy_now.jhtml` |
| 已买到的宝贝 | `https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm` |
| 88VIP会员中心 | `https://pages-fast.m.taobao.com/wow/z/blackvip/v/pc-super?x-render-mode=csr` |
| 我的淘宝 | `https://i.taobao.com/my_itaobao` |
