# EDI 210 校验器使用说明

## 当前版本能力

`edi_210_validator.py` 已按你提供的增强校验口径扩展，覆盖 4 层：

1. **包络层**：ISA/IEA、GS/GE、ST/SE（含计数与控制号匹配）
2. **210 结构层**：关键必需段、基本顺序
3. **字段层**：必填、枚举、日期/时间、数值、长度、成对字段
4. **业务层**：金额汇总、stop/location 关系、可选 204 对照（B3）

## 使用方式

```bash
# 校验文件
python3 edi_210_validator.py your_210.edi

# 从标准输入校验
python3 edi_210_validator.py < your_210.edi
```

## 输出格式

输出 JSON 数组：

- `[]`：通过
- 非空：返回错误/警告对象

字段：

- `code`: 错误码（如 `E022`）
- `segment`: 段名（如 `SE`）
- `element`: 元素位（如 `SE01`）
- `severity`: `Error` 或 `Warning`
- `message`: 可读说明

## Python 调用（可传 204 对照）

```python
from edi_210_validator import validate_edi_210

edi_text = open('your_210.edi', 'r', encoding='utf-8').read()
errors = validate_edi_210(
    edi_text,
    expected_204={
        'B204': 'SHIPMENT_ID_FROM_204',
        'B202': 'SCAC_FROM_204',
    },
    strict_profile=False,  # 默认：按 spec 对 “recommended / may be required” 输出 Warning 或不强制
)
```

## 重要说明

- 默认模式是 **spec-aligned**：
  - `N9*MB` / `N9*PO`
  - `S5`
  - `S5` 内 `G62`
  - 停靠点 `N1/N3` 位置循环
  这些带有 `recommended` / `may be required` 的 profile 规则不再默认按 Error 强制。
- 如需保留旧的企业强校验口径，可传 `strict_profile=True`。
- `ISA16` 非 `>` 当前按 **Warning** 输出（BluJay 偏好）。
- L1 汇总默认以 `L104` 求和并比对 `L305`（`E407`）。

## 规则明细文档

请查看：`EDI_210_增强校验逻辑说明.md`
