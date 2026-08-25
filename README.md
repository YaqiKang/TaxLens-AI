# TaxLens AI — Phase 4.2 公网Demo

This workspace implements only the frozen PRD V1.0 scope for the PRC corporate income tax assessment of newly purchased equipment and appliance one-time deduction policy impact.

The competition Demo assessment year is fixed at 2026. The 2024–2027 period is treated only as the verified asset acquisition window, not as a blanket deduction-year range.

## 当前版本

当前部署版本固定为 **Phase 4.2**。本仓库是面向德勤税务数字科技精英个人赛初赛评委的可运行Streamlit原型，业务范围与Phase 1–3冻结成果保持一致。

已实现：

- Excel `.xlsx` contract and pre-upload structural validation;
- field, date, amount, duplicate ID and conditional-required checks;
- deterministic four-level status assessment;
- deterministic policy applicability rules;
- one-time deduction, accounting depreciation, tax-accounting timing difference and CIT timing impact;
- 12条官方Demo数据与真实确定性pipeline；
- 企业级任务中心、数据质量、影响总览、资产证据链和只读复核清单五页导航；
- 一个TaxLens Agent编排台账解析、资产分类辅助、政策检索、冻结规则、确定性计算和证据核验工具；
- 仅包含公告2023年第37号与公告2018年第46号的受控官方政策知识库；
- 可选OpenAI-compatible结构化LLM接口；未配置、超时或输出无效时安全降级。

明确未实现：

- ERP/OCR integration, live policy crawling or other taxes;
- enterprise authentication, workflow, database or report export;
- standard tax depreciation baseline, loss utilization, rate changes, DTA/DTL accounting or discounting.
- 多Agent、开放式税务聊天、开放互联网检索；
- 复杂人工复核、字段修改/确认后重新评估和最终XLSX导出。

## Run

From this directory:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py

```

LLM不是启动必需项。Demo读取
`data/demo/TaxLens_AI_Official_Demo_Asset_Ledger.xlsx`，所有状态与金额仍由冻结的
`taxlens_core`生成；Agent只增加受控语义辅助、政策证据与解释层。

## Streamlit Community Cloud

- Repository：本仓库根目录；
- Main file：`app.py`；
- Python：3.12；
- Secrets：不配置也可启动并运行确定性评估；如需启用可选LLM增强，仅通过部署平台的Secrets设置环境变量，禁止写入仓库。

可选环境变量为 `TAXLENS_LLM_API_KEY`、`TAXLENS_LLM_ENDPOINT`、
`TAXLENS_LLM_MODEL`和`TAXLENS_LLM_TIMEOUT_SECONDS`。本次公网Demo不依赖这些变量。

## 冻结Demo结果

- 资产总数：12；
- 可选择适用：5；
- 不适用：2；
- 待补充：1；
- 需人工复核：4；
- 所得税时间性影响：2,547,744.79元。

本工具用于企业所得税政策影响的辅助分析，不构成税务申报意见或专业鉴证结论。
