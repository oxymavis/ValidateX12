# PowerMax 856 校验说明整理版

## 1. 文档目的

本文档基于 [`PowerMax校验.docx`](/Users/shelia/Desktop/桌面%20-%20Shelia的MacBook%20Air/Validation%20EDI/powermax/PowerMax校验.docx) 整理，目的是将当前 PowerMax 856 项目的客户识别规则、报文归属结果以及样例 ASN 校验结论统一整理为一份清晰、可读、可持续维护的说明文档。

本文档适用于以下场景：

- 根据 `ISA/GS` 信息判断 ASN 属于哪个 retailer
- 判断一份 ASN 应使用哪个 retailer 的校验 spec
- 快速查看当前生成 ASN 的主要报错类型
- 为后续修正映射逻辑、报文结构和字段生成规则提供依据

## 2. Retailer 识别规则

### 2.1 统一判断格式

判断规则统一使用以下格式：

`Powermax [EDI标识符]:[ISA ID]/[GS ID] | Retailer [EDI标识符]:[ISA ID]/[GS ID] | EDI版本`

### 2.2 Retailer 对照表

| Retailer | PowerMax 标识 | Retailer 标识 | EDI 版本 | 辅助识别信息 |
|---|---|---|---|---|
| Delhaize America | `12:5036759180/5036759180` | `07:5400110000009/540011000` | `005010` | `DELHAIZE AMERICA` / `51007HO` |
| DO IT BEST HARDWARE | `12:8888323557/8888323557` | `ZZ:DOITBESTVP/DOITBESTVP` | `004010` | `Do It Best` / `0051064` |
| Amazon Warehouse | `12:5036759180/5036759180` | `ZZ:AMAZON/AMAZON` | `005010` | `AMAZON.COM.DEDC, INC` / `AMAZON.COM.CANADA` / `/0004588\|4588B/` |
| Walmart USA | `ZZ:231472/231472` | `08:925485US00/925485US00` | `005010` | `WAL-MART STORES, INC` / `51010B` |
| Burlington Coat Factory | `12:9099452111/9099452111` | `08:6126750000/6126750000` | `004010` | `BURLINGTON MERCHANDISING CORP.` / `0051065` |
| Fleet Farm | `12:5036759180/5036759180` | `12:4147318121/4147318121` | `004010` | `MILLS FLEET FARM` / `0004627` |
| Topco | `12:SPS6759180/SPS6759180` | `08:9256490000/8473293489` | `004010UCS` | `51012SP` / `51012SI` / `51012NF` |

### 2.3 判断原则

1. 主判断依据是 `ISA` 与 `GS` 中的 qualifier、sender/receiver ID，以及版本号。
2. `N1` 名称、收货方显示名称、业务别名仅作为辅助判断，不作为第一优先级。
3. 即使报文本身存在 `GS01`、`GS08` 等字段错误，只要 `ISA/GS` 主体标识匹配，仍可以先判断其所属 retailer，并使用对应 spec 校验。

## 3. 已识别文件归属

以下文件已经根据识别规则完成 retailer 归属判断：

| 文件名 | Retailer | 建议使用的校验脚本 |
|---|---|---|
| `0074072_79HFKDZP_20260311181704.edi` | Amazon Warehouse | `validate_amazon_856_spec.py` |
| `0074099_13532765_20260311181954.edi` | Delhaize America | `validate_delhaize_856_spec.py` |
| `0073721_4864877_20260311181809.edi` | Fleet Farm | `validate_fleet_farm_856_spec.py` |
| `0073894_384562802_20260311181739.edi` | Burlington Coat Factory | `validate_burlington_856_spec.py` |
| `0073464_821384_20260311181929.edi` | Topco | `validate_sps_commerce_856_spec.py` |
| `0073801_830962_20260311181839.edi` | Topco | `validate_sps_commerce_856_spec.py` |
| `0073927_082335_20260311181904.edi` | Topco | `validate_sps_commerce_856_spec.py` |

### 3.1 当前目录中未匹配到的 Retailer

- DO IT BEST HARDWARE
- Walmart USA

## 4. 各 Retailer ASN 校验结果汇总

---

## 5. Burlington Coat Factory

### 5.1 文件

`Burlington-0073894_384562802_20260311181739.edi`

### 5.2 去重后的主要报错

#### Error

- `GS01` 不是 `SH`，当前是 `SW`
- `TD3` 缺少 `TD303 equipment number`
- `LIN02` 不是 Burlington 允许的 `EN/IN/UK/UP`
- 缺少 `LIN03 item ID`
- `LIN04` 不符合该位置允许值 `IT`
- `LIN06` 不符合该位置允许值 `BO`
- 使用 `LIN06` 时缺少 `LIN07`
- `LIN08` 不符合该位置允许值 `IZ`
- 使用 `LIN08` 时缺少 `LIN09`
- `LIN10` 不符合该位置允许值 `PU`
- 使用 `LIN10` 时缺少 `LIN11`
- `LIN12` 不符合该位置允许值 `BL`
- `SN103` 必须是 `AS` 或 `EA`

#### Warning

- shipment 级 `TD101` 不在允许值 `BAG/CTN/SLP/SRW` 中
- 出现 Burlington 规范外的 `REF01='23'`
- 国家代码用了 `USA`，建议使用 `US`

### 5.3 结论

Burlington 这份 ASN 的问题主要集中在 3 类：

1. 头部功能组错误：`GS01=SW`
2. shipment 级运输信息不完整：`TD3/N4/REF`
3. item 级 `LIN/SN1` 结构明显不符合 Burlington 856 规范

---

## 6. Delhaize America

### 6.1 文件

`Delhaize-0074099_13532765_20260311181954.edi`

### 6.2 主要报错

#### Error

- `GS01` 应为 `SH`，实际为 `SW`
- 缺少 shipment 级 `DTM`
- 出现不支持的 `HL03='T'`
- `Pack HL` 的父级不是 `Order HL`
- 缺少 pack 级 `LIN`
- 缺少 pack 级 `SN1`
- 缺少 item 级 `LIN03`
- `SN103` 必须是 `EA`

#### Warning

- Delhaize DSD sample/profile 不使用 `Tare HL`
- sample/profile 中通常要求 shipment `PO4`
- shipment `TD502` 在样例中通常为 `9`
- 国家代码建议使用 `US` 而不是 `USA`

### 6.3 结论

Delhaize 这份 ASN 的问题主要集中在 4 类：

1. 头部 `GS01` 不符合规范
2. HL 层级结构不符合 DSD profile
3. shipment 级缺关键日期段
4. pack/item 级字段生成方式与 Delhaize sample/profile 不一致

---

## 7. Fleet Farm

### 7.1 文件

`Fleet Farm-0073721_4864877_20260311181809.edi`

### 7.2 去重后的主要报错

#### Error

- `GS01` 必须是 `SH`，当前是 `SW`
- 缺少 `PER*CE` 供应商联系人
- 缺少 `DTM*011` 发运日期
- shipment 级 `N1*ST` 必须 `N103=92`
- shipment 级 `N1*ST` 缺少 3-5 位门店/DC 编号 `N104`
- order 级缺少 `REF*IA`
- item 级 `LIN02` 后缺少 `LIN03`
- 使用 `LIN08` 时缺少 `LIN09`
- 使用 `LIN10` 时缺少 `LIN11`
- item 级 `SN103` 必须是 `EA`

#### Warning

- `PRF04` 的 PO 日期按 mapping 期望存在
- 出现了未预期的 `LIN qualifier 'BP'`
- 出现了未预期的 `LIN qualifier 'UK'`
- 出现了未预期的 `LIN qualifier 'UA'`
- 出现了未预期的 `LIN qualifier 'SKU'`

### 7.3 结论

Fleet Farm 这份 ASN 的主要硬错误集中在 3 类：

1. 头部和 shipment 级基础段不合规：`GS01/PER/DTM/N1`
2. order 级缺少 `REF*IA`
3. item 层 `LIN/SN1` 结构不符合 Fleet Farm sample/profile

---

## 8. Topco / SPS Commerce

Topco 相关文件当前使用 SPS Commerce 856 通用规则进行校验。

### 8.1 文件一

文件：`NASH FINCH BELLEFONTAINE-0073464_821384_20260311181929.edi`

#### Error

- `GS01` 必须是 `SH`，实际为 `SW`
- `GS08` 必须是 `004010`、`004030` 或 `005010`
- `REF02` 或 `REF03` 至少需要一个
- `TD108` 必须是数值
- `TD110` 必须是数值
- `LIN03` 缺失
- `LIN` 成对规则不满足
  - `LIN02/LIN03`
  - `LIN04/LIN05`
  - `LIN10/LIN11`
- `PO402` 和 `PO403` 必须成对出现

#### Warning

- `TD107 '1794.4'` 不在 SPS 常见重量单位列表中
- `TD109 '59.6414'` 或 `59.64` 不在 SPS 常见体积单位列表中
- `TD504='L'` 不在 SPS 常见承运代码限定值中
- `N101='SO'` 不在 SPS 常见实体代码中
- `LIN10 qualifier 'UA'` 不在 SPS 常见 qualifier 中
- `LIN12 qualifier 'SKU'` 不在 SPS 常见 qualifier 中

### 8.2 文件二

文件：`NASH FINCH HBC GM-0073801_830962_20260311181839.edi`

#### Error

- `GS01` 必须是 `SH`，实际为 `SW`
- `GS08` 必须是 `004010`、`004030` 或 `005010`
- `TD108` 必须是数值
- `TD110` 必须是数值
- `LIN03` 缺失
- `LIN` 成对规则不满足
  - `LIN02/LIN03`
  - `LIN04/LIN05`
  - `LIN10/LIN11`
- `PO402` 和 `PO403` 必须成对出现

#### Warning

- `TD107 '975.3'` 不在 SPS 常见重量单位列表中
- `TD109 '27.5409'` 或 `27.54` 不在 SPS 常见体积单位列表中
- `TD504='L'` 不在 SPS 常见承运代码限定值中
- `N101='SO'` 不在 SPS 常见实体代码中
- `LIN10 qualifier 'UA'` 不在 SPS 常见 qualifier 中
- `LIN12 qualifier 'SKU'` 不在 SPS 常见 qualifier 中

### 8.3 文件三

文件：`SPARTAN STORES INC-0073927_082335_20260311181904.edi`

#### Error

- `GS01` 必须是 `SH`，实际为 `SW`
- `GS08` 必须是 `004010`、`004030` 或 `005010`
- `TD108` 必须是数值
- `TD110` 必须是数值
- `LIN03` 缺失
- `LIN` 成对规则不满足
  - `LIN02/LIN03`
  - `LIN04/LIN05`
  - `LIN10/LIN11`
- `PO402` 和 `PO403` 必须成对出现

#### Warning

- `TD107 '1347.5'`、`855.5`、`492` 不在 SPS 常见重量单位列表中
- `TD109 '43.9706'`、`31.75`、`12.22` 不在 SPS 常见体积单位列表中
- `TD504='L'` 不在 SPS 常见承运代码限定值中
- `LIN10 qualifier 'UA'` 不在 SPS 常见 qualifier 中
- `LIN12 qualifier 'SKU'` 不在 SPS 常见 qualifier 中

### 8.4 总结

这 3 份 Topco/SPS 文件的问题模式基本一致：

1. 头部 `GS01/GS08` 不符合 SPS 856
2. `TD1` 的重量、体积字段位置疑似错位
3. item 层 `LIN` 成对字段缺失
4. `PO4` 也缺少成对字段

---

## 9. 共性问题汇总

结合当前已校验的几个 retailer 文件，可以看到以下共性问题：

### 9.1 头部问题

- 多个文件将 `GS01` 生成成了 `SW`，但 856 应为 `SH`
- 部分文件 `GS08` 与目标 spec 版本不匹配

### 9.2 HL 结构问题

- 不同 retailer 对 `S/O/P/I` 或 `S/O/T/P/I` 的要求不同
- 当前生成逻辑在 Delhaize、Topco/SPS 等场景下，仍存在层级结构不匹配

### 9.3 shipment 级段问题

- `DTM`、`PER`、`REF`、`TD3` 等段缺失或元素不完整
- `N1/N4` 的 qualifier、国家代码、标识符字段不符合客户规范

### 9.4 item 级段问题

- `LIN` 的 qualifier/value 成对规则经常不满足
- `SN103` 单位代码与 retailer spec 不一致
- `PO4` 的成对字段缺失较常见

## 10. 建议修正顺序

建议按以下顺序修正生成逻辑：

1. 先修正 envelope 和头部字段
   - `GS01`
   - `GS08`
   - `ISA/GS` 与 retailer mapping 的对应关系

2. 再修正 HL 结构模板
   - 不同 retailer 使用不同 HL 模板
   - 避免一个通用模板硬套全部客户

3. 再修正 shipment/order 级必填段
   - `DTM`
   - `PER`
   - `PRF`
   - `REF`
   - `N1/N4`
   - `TD3`

4. 最后修正 item 级字段拼装
   - `LIN` qualifier/value 成对输出
   - `SN103` 单位按客户规范输出
   - `PO4` 成对字段完整输出

## 11. 当前文档用途说明

本整理版文档适合作为以下用途：

- 项目内部对照说明
- ASN 生成逻辑修正清单
- retailer 规则识别手册
- 后续补充更多 retailer 校验结论的基础模板

后续如果继续新增 retailer 或新增校验结论，建议继续沿用本文件的结构补充。
