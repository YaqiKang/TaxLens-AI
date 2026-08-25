from __future__ import annotations

import hashlib
import json
import tempfile
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from taxlens_core.models import AssessmentParameters, AssessmentStatus
from taxlens_agent import build_default_agent
from taxlens_web.services import (
    CONDITIONAL_CODES,
    FORMAT_CODES,
    MISSING_CODES,
    assess_checked_workbook,
    build_asset_rows,
    check_workbook,
    summarize_assessment,
)


STATUS_ORDER = ["可选择适用", "不适用", "待补充", "需人工复核"]
STATUS_TONE = {
    "可选择适用": "status-positive",
    "不适用": "status-neutral",
    "待补充": "status-pending",
    "需人工复核": "status-review",
}

PRODUCT_VERSION = "Competition MVP · Phase 4.2"
NAV_ITEMS = [
    ("upload", "任务中心"),
    ("check", "数据质量"),
    ("overview", "影响总览"),
    ("detail", "证据链"),
    ("review", "复核清单"),
]


def apply_page_style() -> None:
    st.markdown("""
    <style>
      :root { --ink:#102A43; --muted:#60758A; --line:#D8E1E8; --teal:#087E72;
        --teal-soft:#E8F5F3; --navy:#12344D; --canvas:#F3F6F8; --white:#FFFFFF; }
      #MainMenu, footer, [data-testid="stHeader"], [data-testid="stToolbar"],
      [data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton,
      .viewerBadge_container__1QSob { display:none !important; }
      html, body, [class*="css"], .stApp { font-size:16px; }
      .stApp { background:var(--canvas); color:var(--ink); }
      .block-container { max-width:1320px; padding-top:1rem; padding-bottom:3rem; }
      h1, h2, h3 { color:var(--ink); letter-spacing:-0.025em; }
      h3 { font-size:1.5rem !important; margin-top:1.4rem !important; }
      p, label, [data-testid="stCaptionContainer"] { font-size:1rem; line-height:1.55; }
      .product-header { background:var(--white); border:1px solid var(--line); border-radius:14px;
        padding:16px 18px; display:flex; align-items:center; justify-content:space-between;
        gap:20px; box-shadow:0 2px 10px rgba(16,42,67,.045); }
      .taxlens-brand { display:flex; align-items:center; gap:13px; min-width:0; }
      .taxlens-mark { width:42px; height:42px; flex:0 0 42px; border-radius:10px;
        background:var(--navy); color:white; display:flex; align-items:center; justify-content:center;
        font-weight:800; font-size:.92rem; border-bottom:4px solid #22A699; }
      .taxlens-title { font-size:1.18rem; font-weight:780; color:var(--ink); line-height:1.2; }
      .taxlens-sub { color:var(--muted); font-size:.9rem; margin-top:3px; white-space:nowrap; }
      .header-meta { display:flex; gap:8px; align-items:center; justify-content:flex-end; flex-wrap:wrap; }
      .meta-chip { padding:7px 10px; background:#F6F8FA; border:1px solid var(--line);
        border-radius:7px; color:#486275; font-size:.78rem; white-space:nowrap; }
      .meta-chip strong { color:var(--ink); }
      .primary-nav-spacer { height:12px; }
      .primary-nav-bottom { height:10px; }
      .st-key-nav_upload button, .st-key-nav_check button, .st-key-nav_overview button,
      .st-key-nav_detail button, .st-key-nav_review button {
        min-height:50px; font-size:1.02rem; font-weight:700;
      }
      .page-title { font-size:2rem; line-height:1.18; font-weight:790; color:var(--ink); margin:.7rem 0 .35rem; }
      .page-lead { color:var(--muted); font-size:1.06rem; margin-bottom:1.25rem; }
      .eyebrow { color:var(--teal); font-size:.8rem; font-weight:750; letter-spacing:.08em;
        text-transform:uppercase; margin-bottom:10px; }
      .hero { background:linear-gradient(120deg,#102F48 0%,#174B60 72%,#0B746D 100%);
        border-radius:16px; padding:38px 40px; color:white; margin:18px 0 16px;
        box-shadow:0 12px 28px rgba(16,42,67,.13); }
      .hero .eyebrow { color:#89DDD4; }
      .hero h1 { color:white; font-size:2.2rem; line-height:1.15; margin:0 0 12px; }
      .hero p { color:#D9E7ED; font-size:1.08rem; max-width:780px; margin:0; }
      .section-card { background:var(--white); border:1px solid var(--line); border-radius:12px;
        padding:18px 20px; }
      .policy-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:8px 0 22px; }
      .policy-card { background:var(--white); border:1px solid var(--line); border-radius:10px; padding:15px 16px; }
      .policy-label { color:var(--muted); font-size:.78rem; margin-bottom:5px; }
      .policy-value { color:var(--ink); font-size:1rem; font-weight:720; }
      .notice { background:#F1F5F8; border-left:3px solid #78909C; padding:13px 15px;
        border-radius:7px; color:#40596B; font-size:.94rem; }
      .success-note { background:#EAF6F4; border-left:3px solid var(--teal); padding:13px 15px;
        border-radius:7px; color:#155E59; }
      .block-note { background:#FFF7E7; border-left:3px solid #C58A16; padding:13px 15px;
        border-radius:7px; color:#76530E; }
      .empty-state { background:var(--white); border:1px dashed #B8C6D1; border-radius:12px;
        padding:34px; text-align:center; color:var(--muted); margin:18px 0; }
      [data-testid="stMetric"] { background:var(--white); border:1px solid var(--line);
        border-radius:11px; padding:16px; box-shadow:0 1px 4px rgba(16,42,67,.035); }
      [data-testid="stMetricLabel"] { color:var(--muted); font-size:.88rem; }
      [data-testid="stMetricValue"] { color:var(--ink); font-size:1.55rem; }
      .status-row { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:8px 0 20px; }
      .status-card { background:white; border:1px solid var(--line); border-radius:10px; padding:14px; }
      .status-label { color:var(--muted); font-size:.86rem; }
      .status-value { color:var(--ink); font-size:1.55rem; font-weight:760; margin-top:3px; }
      .status-positive { border-top:3px solid var(--teal); }
      .status-neutral { border-top:3px solid #78909C; }
      .status-pending { border-top:3px solid #C48A12; }
      .status-review { border-top:3px solid #7A6AA6; }
      .status-chart-row { display:grid; grid-template-columns:110px 1fr 42px; gap:12px;
        align-items:center; margin:11px 0; font-size:.9rem; }
      .status-track { height:10px; background:#E9EEF2; border-radius:20px; overflow:hidden; }
      .status-fill { height:100%; border-radius:20px; min-width:4px; }
      .fill-positive { background:#0A8A7D; } .fill-neutral { background:#7A8B99; }
      .fill-pending { background:#D69A22; } .fill-review { background:#7D70A8; }
      .trace-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:8px 0 12px; }
      .trace-item { background:var(--white); border:1px solid var(--line); border-radius:10px;
        padding:14px; display:flex; gap:11px; min-height:94px; }
      .trace-icon { width:26px; height:26px; border-radius:50%; background:var(--teal-soft);
        color:var(--teal); display:flex; align-items:center; justify-content:center; font-weight:800; flex:0 0 26px; }
      .trace-icon.degraded { background:#F4F0FA; color:#725F9D; }
      .trace-label { color:var(--ink); font-weight:720; font-size:.92rem; }
      .trace-summary { color:var(--muted); font-size:.8rem; line-height:1.4; margin-top:5px; }
      .detail-card { background:white; border:1px solid var(--line); border-radius:10px; padding:17px; }
      .muted { color:var(--muted); font-size:.86rem; }
      .evidence-flow { display:grid; grid-template-columns:repeat(5,1fr); gap:9px; margin:10px 0 22px; }
      .flow-node { position:relative; background:white; border:1px solid var(--line); border-radius:9px;
        padding:13px 12px; text-align:center; color:var(--ink); font-weight:680; font-size:.88rem; }
      .flow-node:not(:last-child)::after { content:'›'; position:absolute; right:-9px; top:7px;
        z-index:2; color:#8AA0AF; font-size:1.4rem; }
      .flow-node span { display:block; color:var(--muted); font-size:.72rem; font-weight:500; margin-top:3px; }
      .stButton > button, .stDownloadButton > button { border-radius:8px; font-weight:680;
        min-height:42px; font-size:.95rem; }
      div[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:9px; overflow:hidden; }
      [data-testid="stDataFrame"] { font-size:.92rem; }
      [data-testid="stFileUploader"] { background:white; border:1px solid var(--line); border-radius:10px; padding:8px; }
      @media (max-width: 850px) {
        .status-row, .policy-grid, .trace-grid, .evidence-flow { grid-template-columns:1fr; }
        .product-header { align-items:flex-start; flex-direction:column; }
        .header-meta { justify-content:flex-start; }
        .hero { padding:28px 24px; }
        .block-container { padding-left:1rem; padding-right:1rem; }
      }
    </style>
    """, unsafe_allow_html=True)


def init_state() -> None:
    defaults = {
        "page": "upload",
        "source_path": None,
        "source_name": None,
        "source_hash": None,
        "check_result": None,
        "assessment_result": None,
        "agent_run": None,
        "agent_error": None,
        "parameters": None,
        "detail_asset_id": None,
        "task_setup_open": True,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def render_product_header(policy: dict) -> None:
    document = policy["core_official_sources"][0]["document_number"].replace("财政部 税务总局公告", "公告")
    updated = policy["knowledge_base_updated_at"]
    st.markdown(f"""
    <div class="product-header">
      <div class="taxlens-brand">
        <div class="taxlens-mark">TL</div>
        <div><div class="taxlens-title">TaxLens AI</div>
        <div class="taxlens-sub">新购设备税务政策影响评估智能体</div></div>
      </div>
      <div class="header-meta">
        <div class="meta-chip"><strong>{PRODUCT_VERSION}</strong></div>
        <div class="meta-chip">政策版本 · <strong>{document}</strong></div>
        <div class="meta-chip">知识库快照 · <strong>{updated}</strong></div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_navigation() -> None:
    st.markdown('<div class="primary-nav-spacer"></div>', unsafe_allow_html=True)
    columns = st.columns([1, 1, 1, 1, 1])
    current = st.session_state.page
    for column, (target, label) in zip(columns, NAV_ITEMS):
        with column:
            button_label = f"● {label}" if current == target else label
            if st.button(button_label, key=f"nav_{target}", width="stretch"):
                if target == "detail" and not st.session_state.detail_asset_id:
                    result = st.session_state.assessment_result
                    if result and result.assessments:
                        st.session_state.detail_asset_id = result.assessments[0].asset_id
                st.session_state.page = target
                st.rerun()
    st.markdown('<div class="primary-nav-bottom"></div>', unsafe_allow_html=True)


def load_policy(root: Path) -> dict:
    return json.loads((root / "configs/policy_snapshot.json").read_text(encoding="utf-8"))


def format_money(value: Decimal | float | int | None) -> str:
    if value is None:
        return "—"
    return f"¥{Decimal(str(value)):,.2f}"


def persist_upload(uploaded_file) -> tuple[str, str]:
    payload = uploaded_file.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != st.session_state.source_hash:
        runtime_dir = Path(tempfile.gettempdir()) / "taxlens_uploads"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        target = runtime_dir / f"{digest}.xlsx"
        target.write_bytes(payload)
        st.session_state.source_path = str(target)
        st.session_state.source_name = uploaded_file.name
        st.session_state.source_hash = digest
        st.session_state.check_result = None
        st.session_state.assessment_result = None
        st.session_state.agent_run = None
        st.session_state.agent_error = None
    return st.session_state.source_path, st.session_state.source_name


def parameters_from_inputs(cit_rate: float, cutoff: date, residual_rate: float) -> AssessmentParameters:
    return AssessmentParameters(
        assessment_year=2026,
        cit_rate_percent=Decimal(str(cit_rate)),
        cutoff_date=cutoff,
        default_residual_rate_percent=Decimal(str(residual_rate)),
    )


def render_upload_page(root: Path, policy: dict) -> None:
    document = policy["core_official_sources"][0]["document_number"]
    updated = policy["knowledge_base_updated_at"]
    st.markdown("""
    <div class="hero">
      <div class="eyebrow">Enterprise Tax Decision Support</div>
      <h1>新购设备税务政策影响评估</h1>
      <p>面向企业所得税税务专员，将资产台账、政策条件与确定性测算组织成可追溯、可复核的专项评估任务。</p>
    </div>
    """, unsafe_allow_html=True)

    action_left, action_right, action_space = st.columns([1.15, 1.15, 2.7])
    with action_left:
        if st.button("开始评估", key="begin_assessment", type="primary", width="stretch"):
            st.session_state.task_setup_open = True
    with action_right:
        if st.button("加载Demo案例", key="load_demo", width="stretch"):
            demo_path = root / "data/demo/TaxLens_AI_Official_Demo_Asset_Ledger.xlsx"
            st.session_state.source_path = str(demo_path)
            st.session_state.source_name = demo_path.name
            st.session_state.source_hash = "official-demo"
            st.session_state.check_result = None
            st.session_state.assessment_result = None
            st.session_state.agent_run = None
            st.session_state.agent_error = None
            st.session_state.task_setup_open = True
            st.rerun()

    st.markdown(f"""
    <div class="policy-grid">
      <div class="policy-card"><div class="policy-label">当前政策版本</div><div class="policy-value">{document}</div></div>
      <div class="policy-card"><div class="policy-label">受控知识库快照更新时间</div><div class="policy-value">{updated}</div></div>
      <div class="policy-card"><div class="policy-label">当前评估年度</div><div class="policy-value">2026 · 固定Demo口径</div></div>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("创建评估任务")
    st.markdown('<div class="page-lead">确认测算参数并选择资产台账。评估年度为冻结范围，不允许修改。</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.text_input("评估年度", value="2026", disabled=True, help="当前MVP固定为2026")
    with c2:
        cit_rate = st.number_input(
            "企业所得税税率（%）", min_value=0.0, max_value=100.0, value=25.0, step=0.5
        )
    with c3:
        cutoff = st.date_input(
            "测算基准日", value=date(2026, 12, 31), min_value=date(2026, 1, 1)
        )
    with c4:
        residual_rate = st.number_input(
            "默认残值率（%）", min_value=0.0, max_value=10.0, value=5.0, step=0.5
        )
    parameters = parameters_from_inputs(cit_rate, cutoff, residual_rate)

    st.subheader("数据来源")
    left, right = st.columns([1, 2])
    with left:
        template_path = root / "data/templates/TaxLens_AI_Asset_Ledger_Template.xlsx"
        st.download_button(
            "下载官方Excel模板",
            data=template_path.read_bytes(),
            file_name=template_path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
        st.caption("模板包含字段字典和输入校验，不包含任何预置评估结果。")
    with right:
        uploaded = st.file_uploader(
            "上传已填写的资产台账",
            type=["xlsx"],
            help="仅支持.xlsx，不超过2 MB，1–500条资产记录",
        )
        if uploaded is not None:
            persist_upload(uploaded)
        if st.session_state.source_name:
            st.markdown(
                f'<div class="success-note"><b>已选择文件</b><br>{st.session_state.source_name}</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    start = st.button(
        "运行数据质量检查",
        key="start_check",
        type="primary",
        disabled=not bool(st.session_state.source_path),
        width="stretch",
    )
    if start:
        st.session_state.parameters = parameters
        with st.spinner("正在检查台账结构与字段..."):
            st.session_state.check_result = check_workbook(
                st.session_state.source_path, parameters
            )
        st.session_state.page = "check"
        st.rerun()

    st.markdown("""
    <div class="notice"><b>辅助评估免责声明</b><br>
    本工具用于企业所得税政策影响的辅助分析，不构成税务申报意见或专业鉴证结论。
    “可选择适用”仍需企业结合真实业务、凭证及申报口径作出决定；所得税影响表示时间性现金流影响，不代表永久节税。</div>
    """, unsafe_allow_html=True)


def _preview_dataframe(records: list[dict]) -> pd.DataFrame:
    rows = [{key: value for key, value in record.items() if key != "_row_number"} for record in records]
    return pd.DataFrame(rows)


def render_check_page() -> None:
    st.markdown('<div class="eyebrow">Data Quality Control</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-title">数据质量检查</div>', unsafe_allow_html=True)
    check = st.session_state.check_result
    if check is None:
        st.markdown(
            '<div class="empty-state"><b>尚未创建数据检查任务</b><br>请先在任务中心选择Excel台账或加载Demo案例。</div>',
            unsafe_allow_html=True,
        )
        if st.button("前往任务中心", key="empty_to_home_check", type="primary"):
            st.session_state.page = "upload"
            st.rerun()
        return

    st.markdown(
        f'<div class="page-lead">检查对象 · {st.session_state.source_name or Path(check.source_path).name}</div>',
        unsafe_allow_html=True,
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("总行数", check.total_rows)
    m2.metric("可处理行数", check.processable_rows)
    m3.metric("错误数", check.error_count)
    m4.metric("警告数", check.warning_count)

    st.subheader("问题分类")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("缺失字段", check.count_codes(MISSING_CODES))
    c2.metric("格式问题", check.count_codes(FORMAT_CODES))
    c3.metric("重复资产ID", check.count_codes({"DUPLICATE_ASSET_ID"}))
    c4.metric("条件必填问题", check.count_codes(CONDITIONAL_CODES))

    if check.can_assess:
        if check.row_issues:
            st.markdown(
                '<div class="block-note"><b>存在行级问题，但不阻断其他有效资产。</b> '
                '问题资产将在评估结果中标记为“待补充”。</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="success-note"><b>数据检查通过。</b> 当前文件可以进入政策影响评估。</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div class="block-note"><b>存在批次级阻断问题。</b> 请修正文件后重新上传；当前不能进入评估。</div>',
            unsafe_allow_html=True,
        )

    if check.all_issues:
        st.subheader("问题明细")
        st.dataframe(pd.DataFrame(check.issue_rows()), width="stretch", hide_index=True)

    st.subheader("原始数据预览")
    preview = _preview_dataframe(check.records)
    if preview.empty:
        st.info("未读取到可预览的资产记录。")
    else:
        st.dataframe(preview, width="stretch", hide_index=True, height=330)

    back, proceed = st.columns([1, 2])
    with back:
        if st.button("返回任务中心", key="back_upload", width="stretch"):
            st.session_state.page = "upload"
            st.rerun()
    with proceed:
        if st.button(
            "进入政策影响评估",
            key="run_assessment",
            type="primary",
            disabled=not check.can_assess,
            width="stretch",
        ):
            try:
                with st.spinner("TaxLens Agent正在调用专业工具完成评估..."):
                    agent = build_default_agent(Path(__file__).resolve().parents[2])
                    agent_run = agent.run(
                        check.source_path,
                        st.session_state.parameters,
                        checked=check,
                    )
                    st.session_state.agent_run = agent_run
                    st.session_state.assessment_result = agent_run.assessment
                    st.session_state.agent_error = None
                st.session_state.page = "overview"
                st.rerun()
            except Exception:
                # Agent/enrichment failure must never disable the frozen Phase 1 path.
                try:
                    st.session_state.assessment_result = assess_checked_workbook(
                        check, st.session_state.parameters
                    )
                    st.session_state.agent_run = None
                    st.session_state.agent_error = (
                        "Agent增强层未完成，已安全降级为Phase 1确定性评估；状态与金额未受影响。"
                    )
                    st.session_state.page = "overview"
                    st.rerun()
                except Exception:
                    st.error("评估未完成。请返回上传页重新检查文件，系统未生成任何推断结果。")


def _status_cards(counts: dict[str, int]) -> None:
    cards = "".join(
        f'<div class="status-card {STATUS_TONE[status]}"><div class="status-label">{status}</div>'
        f'<div class="status-value">{counts.get(status, 0)}</div></div>'
        for status in STATUS_ORDER
    )
    st.markdown(f'<div class="status-row">{cards}</div>', unsafe_allow_html=True)


def _status_distribution_visual(counts: dict[str, int]) -> None:
    total = max(sum(counts.values()), 1)
    tone = {
        "可选择适用": "fill-positive",
        "不适用": "fill-neutral",
        "待补充": "fill-pending",
        "需人工复核": "fill-review",
    }
    rows = "".join(
        f'<div class="status-chart-row"><span>{status}</span>'
        f'<div class="status-track"><div class="status-fill {tone[status]}" '
        f'style="width:{counts.get(status, 0) / total:.1%}"></div></div>'
        f'<strong>{counts.get(status, 0)}</strong></div>'
        for status in STATUS_ORDER
    )
    st.markdown(f'<div class="section-card">{rows}</div>', unsafe_allow_html=True)


def _render_agent_trace(agent_run) -> None:
    if agent_run is None:
        st.warning(st.session_state.agent_error or "Agent轨迹当前不可用，已保留确定性评估结果。")
        return
    items = []
    for step in agent_run.tool_trace:
        degraded = step.status != "success"
        icon = "△" if degraded else "✓"
        items.append(
            f'<div class="trace-item"><div class="trace-icon {"degraded" if degraded else ""}">{icon}</div>'
            f'<div><div class="trace-label">{step.label}</div>'
            f'<div class="trace-summary">{step.summary}</div></div></div>'
        )
    st.markdown(f'<div class="trace-grid">{"".join(items)}</div>', unsafe_allow_html=True)
    st.caption(
        f"模型增强状态：{agent_run.provider_status}。仅展示工具执行摘要，不展示模型内部推理。"
    )
    for warning in agent_run.warnings:
        st.info(warning)


def _render_asset_detail(asset_id: str, rows: list[dict], result) -> None:
    row = next(item for item in rows if item["资产ID"] == asset_id)
    assessment = next(item for item in result.assessments if item.asset_id == asset_id)
    st.markdown("#### 资产详情")
    st.markdown('<div class="detail-card">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("资产ID", row["资产ID"])
    c2.metric("状态", row["状态"])
    c3.metric("购进日期", str(row["购进日期"] or "—"))
    c4.metric("扣除所属年度", row["扣除所属年度"] or "—")
    st.write("**主要原因**")
    for message in assessment.reason_messages:
        st.write(f"- {message}")
    if assessment.calculations:
        calc = assessment.calculations
        x1, x2, x3, x4 = st.columns(4)
        x1.metric("一次性税前扣除", format_money(calc.one_time_tax_deduction))
        x2.metric("本年会计折旧", format_money(calc.accounting_depreciation))
        x3.metric("当期税会差异", format_money(calc.tax_accounting_difference))
        x4.metric("所得税时间性影响", format_money(calc.cit_timing_impact))
    else:
        st.markdown(
            '<div class="notice">当前状态不生成最终政策金额测算，避免对待补充、需复核或不适用记录作扩展推断。</div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)


def render_overview_page() -> None:
    st.markdown('<div class="eyebrow">Policy Impact Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-title">政策影响总览</div>', unsafe_allow_html=True)
    result = st.session_state.assessment_result
    check = st.session_state.check_result
    if result is None or check is None:
        st.markdown(
            '<div class="empty-state"><b>尚无可展示的评估结果</b><br>完成数据质量检查并运行政策影响评估后，Dashboard将在此生成。</div>',
            unsafe_allow_html=True,
        )
        if st.button("前往任务中心", key="empty_to_home_overview", type="primary"):
            st.session_state.page = "upload"
            st.rerun()
        return

    summary = summarize_assessment(result)
    st.markdown(
        f'<div class="page-lead">任务对象 · {st.session_state.source_name}　|　评估年度 · 2026</div>',
        unsafe_allow_html=True,
    )
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("分析资产总数", summary.record_count)
    k2.metric("可选择适用", summary.status_counts.get("可选择适用", 0))
    k3.metric("待复核数量", summary.status_counts.get("需人工复核", 0))
    k4.metric("当期税会差异", format_money(summary.tax_accounting_difference))
    k5.metric("所得税时间性影响", format_money(summary.cit_timing_impact))
    st.caption("金额仅汇总“可选择适用”资产；所得税影响为时间性现金流影响，不表示永久节税。")

    st.subheader("智能评估轨迹")
    agent_run = st.session_state.agent_run
    _render_agent_trace(agent_run)

    st.subheader("评估状态分布")
    _status_cards(summary.status_counts)
    chart_col, reason_col = st.columns([1, 1])
    with chart_col:
        _status_distribution_visual(summary.status_counts)
    reason_counter = Counter(
        assessment.reason_messages[0] if assessment.reason_messages else "未提供原因"
        for assessment in result.assessments
    )
    reason_table = pd.DataFrame([
        {"主要原因": reason, "资产数": count}
        for reason, count in reason_counter.most_common()
    ])
    with reason_col:
        st.dataframe(reason_table, width="stretch", hide_index=True, height=220)

    rows = build_asset_rows(result, check.records)
    st.subheader("影响金额排序")
    impact_rows = [
        {
            "排名": index,
            "资产ID": row["资产ID"],
            "资产名称": row["资产名称"],
            "当期税会差异": row["当期税会差异"],
            "所得税时间性影响": row["所得税时间性影响"],
        }
        for index, row in enumerate(
            sorted(
                [item for item in rows if item["当期税会差异"] is not None],
                key=lambda item: item["所得税时间性影响"],
                reverse=True,
            ),
            start=1,
        )
    ]
    if impact_rows:
        st.dataframe(
            pd.DataFrame(impact_rows),
            width="stretch",
            hide_index=True,
            height=225,
            column_config={
                "当期税会差异": st.column_config.NumberColumn(format="¥%.2f"),
                "所得税时间性影响": st.column_config.NumberColumn(format="¥%.2f"),
            },
        )

    st.subheader("复核事项")
    review_rows = [row for row in rows if row["状态"] in {"待补充", "需人工复核"}]
    if review_rows:
        st.dataframe(
            pd.DataFrame(review_rows)[["资产ID", "资产名称", "状态", "主要原因"]],
            width="stretch",
            hide_index=True,
            height=220,
        )
        if st.button("查看完整复核清单", key="open_review_queue"):
            st.session_state.page = "review"
            st.rerun()
    else:
        st.success("当前批次没有待补充或需人工复核事项。")

    st.subheader("资产级清单")
    selected_statuses = st.multiselect(
        "状态筛选", STATUS_ORDER, default=STATUS_ORDER, key="status_filter"
    )
    filtered = [row for row in rows if row["状态"] in selected_statuses]
    display_df = pd.DataFrame(filtered)
    if not display_df.empty:
        st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
            height=390,
            column_config={
                "单台（套）计税基础": st.column_config.NumberColumn(format="¥%.2f"),
                "当期税会差异": st.column_config.NumberColumn(format="¥%.2f"),
                "所得税时间性影响": st.column_config.NumberColumn(format="¥%.2f"),
            },
        )
    else:
        st.info("当前筛选条件下没有资产。")

    detail_options = [row["资产ID"] for row in filtered]
    if detail_options:
        d1, d2 = st.columns([2, 1])
        with d1:
            selected_id = st.selectbox("选择资产", detail_options, key="detail_selector")
        with d2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("进入资产详情", key="open_detail", width="stretch"):
                st.session_state.detail_asset_id = selected_id
                st.session_state.page = "detail"
                st.rerun()

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    nav_back, nav_review = st.columns([1, 1])
    with nav_back:
        if st.button("返回数据质量检查", key="back_check", width="stretch"):
            st.session_state.page = "check"
            st.rerun()
    with nav_review:
        if st.button("进入复核清单", key="dashboard_to_review", width="stretch"):
            st.session_state.page = "review"
            st.rerun()

    st.markdown("""
    <div class="notice"><b>结果边界</b><br>
    “不适用”仅表示不满足本次一次性税前扣除政策条件，不代表违规或高风险。
    待补充和需人工复核资产不生成最终金额结论。</div>
    """, unsafe_allow_html=True)


def _facts_table(facts: dict) -> pd.DataFrame:
    fields = [
        ("原始类别", "fixed_asset_category"),
        ("资产名称", "asset_name"),
        ("资产描述", "asset_description"),
        ("单台（套）单位价值", "unit_tax_basis"),
        ("购进方式", "acquisition_method"),
        ("发票日期", "invoice_date"),
        ("到货日期", "arrival_date"),
        ("竣工结算日期", "completion_settlement_date"),
        ("投入使用日期", "placed_in_service_date"),
        ("building_flag", "building_flag"),
        ("evidence_status", "evidence_status"),
    ]
    return pd.DataFrame([
        {"字段": label, "原始值": facts.get(key) if facts.get(key) not in (None, "") else "—"}
        for label, key in fields
    ])


def render_detail_page() -> None:
    asset_id = st.session_state.detail_asset_id
    result = st.session_state.assessment_result
    agent_run = st.session_state.agent_run
    if not asset_id or result is None or agent_run is None or asset_id not in agent_run.asset_results:
        st.markdown('<div class="eyebrow">Asset Evidence View</div>', unsafe_allow_html=True)
        st.markdown('<div class="page-title">资产级证据链</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="empty-state"><b>尚未选择可查看的资产</b><br>请先完成评估，并从政策影响总览或复核清单进入资产详情。</div>',
            unsafe_allow_html=True,
        )
        if st.button("前往政策影响总览", key="empty_to_overview_detail", type="primary"):
            st.session_state.page = "overview"
            st.rerun()
        return

    assessment = next(item for item in result.assessments if item.asset_id == asset_id)
    agent_asset = agent_run.asset_results[asset_id]
    verification = agent_asset.evidence_verification
    action_text = {
        "可选择适用": "确认选择并留存资料",
        "不适用": "记录不适用依据",
        "待补充": "补充缺失事实",
        "需人工复核": "进入税务人工复核",
    }[assessment.status.value]
    st.markdown('<div class="eyebrow">Asset Evidence View</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-title">资产级证据链</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="page-lead">资产ID · {asset_id}　|　只读评估结果　|　证据状态 · {verification.evidence_status}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"""
    <div class="evidence-flow">
      <div class="flow-node">事实<span>资产台账与结构化字段</span></div>
      <div class="flow-node">规则<span>冻结政策条件与原因代码</span></div>
      <div class="flow-node">判断<span>{assessment.status.value}</span></div>
      <div class="flow-node">影响<span>{format_money(assessment.calculations.cit_timing_impact) if assessment.calculations else '不生成金额推断'}</span></div>
      <div class="flow-node">行动<span>{action_text}</span></div>
    </div>
    """, unsafe_allow_html=True)
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("当前评估结论", assessment.status.value)
    a2.metric("规则购进日期", str(assessment.acquisition_date or "—"))
    a3.metric("扣除所属年度", assessment.deduction_year or "—")
    a4.metric("证据核验状态", verification.evidence_status)

    st.subheader("A. 原始资产事实")
    st.dataframe(_facts_table(agent_asset.raw_facts), width="stretch", hide_index=True)
    st.caption("所有AI辅助结果均与原始字段分栏展示；系统不会覆盖building_flag或其他结构化事实。")

    st.subheader("B. AI辅助识别")
    classification = agent_asset.classification
    b1, b2, b3 = st.columns(3)
    b1.metric("建议类别", classification.suggested_category)
    b2.metric("置信度", f"{classification.confidence:.0%}" if classification.called else "未调用")
    b3.metric("触发人工复核", "是" if classification.requires_human_review else "否")
    st.write(classification.reason)
    st.caption(f"调用状态：{classification.provider_status}；该建议不构成税务结论。")

    st.subheader("C. 政策条件判断")
    st.dataframe(
        pd.DataFrame([item.to_dict() for item in agent_asset.conditions]).rename(columns={
            "condition_name": "条件名称", "current_fact": "当前事实",
            "status": "结果", "reason_code": "原因代码",
        }),
        width="stretch",
        hide_index=True,
    )

    st.subheader("D. 政策依据")
    if agent_asset.policy_evidence:
        for index, evidence in enumerate(agent_asset.policy_evidence, start=1):
            with st.expander(
                f"{index}. {evidence.document_number} · {evidence.clause_reference}",
                expanded=index == 1,
            ):
                st.write(evidence.relevant_text)
                p1, p2 = st.columns(2)
                p1.write(f"**政策名称：** {evidence.policy_name}")
                p1.write(f"**发布机关：** {evidence.issuing_authority}")
                p2.write(f"**适用/有效期间：** {evidence.effective_or_applicable_period}")
                p2.write(f"**知识库更新时间：** {evidence.knowledge_base_updated_at}")
                st.markdown(f"[查看官方来源]({evidence.source_url})")
    else:
        st.info("当前未检索到与该待补充事项直接对应的受控政策依据；系统未自行补充政策条款。")

    st.subheader("E. 计算过程")
    calc = assessment.calculations
    if calc is not None:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("政策计税基础合计", format_money(calc.policy_basis_total))
        c2.metric("会计折旧", format_money(calc.accounting_depreciation))
        c3.metric("一次性税前扣除", format_money(calc.one_time_tax_deduction))
        c4.metric("税会差异", format_money(calc.tax_accounting_difference))
        c5.metric("所得税时间性影响", format_money(calc.cit_timing_impact))
        st.markdown(
            "- 政策计税基础合计 = 单台（套）单位价值 × 数量\n"
            "- 一次性税前扣除 = 政策计税基础合计\n"
            "- 税会差异 = 一次性税前扣除 − 当年会计折旧\n"
            "- 所得税时间性影响 = 税会差异 × 企业所得税税率"
        )
        source_text = "台账提供值" if calc.depreciation_source == "provided" else "直线法确定性计算"
        st.caption(
            f"会计折旧来源：{source_text}；折旧月数：{calc.accounting_depreciation_months or '按台账提供值'}。"
            "统一假设有足够应纳税所得额，未建模亏损、税率变动、递延所得税会计与折现。"
        )
    else:
        st.info("该资产当前状态不生成政策金额测算，系统未对缺失或需复核事项作金额推断。")

    st.subheader("F. 当前评估结论")
    st.markdown(f'<div class="detail-card"><b>{assessment.status.value}</b><br>{agent_asset.explanation}</div>', unsafe_allow_html=True)
    st.caption(
        f"证据核验状态：{verification.evidence_status}。"
        + (f" 缺口：{'、'.join(verification.missing_items)}。" if verification.missing_items else " 资产事实、原因代码、政策来源及适用计算依据已核验。")
    )

    st.subheader("人工复核原因与建议行动")
    if assessment.status in {
        AssessmentStatus.NEEDS_INFORMATION,
        AssessmentStatus.NEEDS_MANUAL_REVIEW,
    }:
        review_reasons = "".join(f"<li>{message}</li>" for message in assessment.reason_messages)
        st.markdown(
            f'<div class="block-note"><b>{action_text}</b><ul>{review_reasons}</ul>'
            '当前页面为只读版本，不执行人工确认、字段修改或重新评估。</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="notice"><b>{action_text}</b><br>当前资产无需进入本批次复核清单；'
            '税务专员仍需结合真实凭证与申报口径完成最终业务判断。</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    back_col, review_col = st.columns(2)
    with back_col:
        if st.button("返回政策影响总览", key="back_overview", width="stretch"):
            st.session_state.page = "overview"
            st.rerun()
    with review_col:
        if st.button("查看复核清单", key="detail_to_review", width="stretch"):
            st.session_state.page = "review"
            st.rerun()


def render_review_page() -> None:
    st.markdown('<div class="eyebrow">Tax Review Queue</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-title">复核清单</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-lead">集中查看现有评估结果中的“待补充”和“需人工复核”资产。本页面只读，不增加审批或重评功能。</div>',
        unsafe_allow_html=True,
    )
    result = st.session_state.assessment_result
    check = st.session_state.check_result
    if result is None or check is None:
        st.markdown(
            '<div class="empty-state"><b>尚无复核事项</b><br>完成一次政策影响评估后，相关资产将自动汇总到此页面。</div>',
            unsafe_allow_html=True,
        )
        if st.button("前往任务中心", key="empty_to_home_review", type="primary"):
            st.session_state.page = "upload"
            st.rerun()
        return

    all_rows = build_asset_rows(result, check.records)
    review_rows = [row for row in all_rows if row["状态"] in {"待补充", "需人工复核"}]
    manual_count = sum(row["状态"] == "需人工复核" for row in review_rows)
    pending_count = sum(row["状态"] == "待补充" for row in review_rows)
    r1, r2, r3 = st.columns(3)
    r1.metric("复核清单资产数", len(review_rows))
    r2.metric("需人工复核", manual_count)
    r3.metric("待补充", pending_count)

    selected_review_statuses = st.multiselect(
        "清单筛选",
        ["需人工复核", "待补充"],
        default=["需人工复核", "待补充"],
        key="review_status_filter",
    )
    filtered = [row for row in review_rows if row["状态"] in selected_review_statuses]
    review_display = []
    agent_run = st.session_state.agent_run
    for row in filtered:
        evidence_status = "—"
        if agent_run is not None and row["资产ID"] in agent_run.asset_results:
            evidence_status = agent_run.asset_results[row["资产ID"]].raw_facts.get("evidence_status") or "—"
        review_display.append({
            "资产ID": row["资产ID"],
            "资产名称": row["资产名称"],
            "原始类别": row["固定资产类别"],
            "状态": row["状态"],
            "evidence_status": evidence_status,
            "复核原因": row["主要原因"],
        })
    if review_display:
        st.dataframe(pd.DataFrame(review_display), width="stretch", hide_index=True, height=360)
        select_col, action_col = st.columns([2, 1])
        with select_col:
            review_asset_id = st.selectbox(
                "选择资产查看证据链",
                [row["资产ID"] for row in review_display],
                key="review_asset_selector",
            )
        with action_col:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("查看资产证据链", key="review_open_detail", type="primary", width="stretch"):
                st.session_state.detail_asset_id = review_asset_id
                st.session_state.page = "detail"
                st.rerun()
    else:
        st.info("当前筛选条件下没有复核事项。")

    st.markdown(
        '<div class="notice"><b>清单边界</b><br>该页面只汇总现有四级状态和原因代码。'
        '复杂人工确认、字段修改、意见留痕与重新评估不在本阶段范围内。</div>',
        unsafe_allow_html=True,
    )


def run_app(root: Path) -> None:
    st.set_page_config(
        page_title="TaxLens AI｜新购设备税务政策影响评估",
        page_icon="TL",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_page_style()
    init_state()
    policy = load_policy(root)
    render_product_header(policy)
    render_navigation()
    page = st.session_state.page
    if page == "upload":
        render_upload_page(root, policy)
    elif page == "check":
        render_check_page()
    elif page == "overview":
        render_overview_page()
    elif page == "detail":
        render_detail_page()
    elif page == "review":
        render_review_page()
    else:
        st.session_state.page = "upload"
        st.rerun()
