from datetime import date
from decimal import Decimal

ASSET_LEDGER_SHEET = "asset_ledger"
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024
MIN_RECORDS = 1
MAX_RECORDS = 500

ASSET_COLUMNS = [
    "asset_id",
    "asset_name",
    "asset_description",
    "fixed_asset_category",
    "acquisition_method",
    "invoice_date",
    "arrival_date",
    "completion_settlement_date",
    "placed_in_service_date",
    "unit_tax_basis",
    "quantity",
    "building_flag",
    "accounting_useful_life_years",
    "residual_rate",
    "depreciation_method",
    "current_year_accounting_depreciation",
    "policy_already_claimed",
    "evidence_status",
    "note",
]

ACQUISITION_METHODS = {"普通购进", "分期或赊销", "自行建造"}
CONDITIONAL_DATE_FIELD = {
    "普通购进": "invoice_date",
    "分期或赊销": "arrival_date",
    "自行建造": "completion_settlement_date",
}
BUILDING_FLAGS = {"是", "否", "不确定"}
CLAIMED_FLAGS = {"是", "否", "不确定"}
EVIDENCE_STATUSES = {"完整", "部分缺失", "缺失"}
SUPPORTED_DEPRECIATION_METHOD = "直线法"

DEMO_ASSESSMENT_YEAR = 2026
SUPPORTED_ASSESSMENT_YEARS = frozenset({DEMO_ASSESSMENT_YEAR})
POLICY_ACQUISITION_START = date(2024, 1, 1)
POLICY_ACQUISITION_END = date(2027, 12, 31)
UNIT_TAX_BASIS_THRESHOLD = Decimal("5000000.00")

AMBIGUOUS_CATEGORIES = {"待确认", "其他待确认", "不确定"}
BUILDING_CATEGORIES = {"房屋", "建筑物", "房屋及建筑物"}
STRONG_BUILDING_KEYWORDS = ("厂房", "办公楼", "仓库主体", "建筑物", "房屋主体")
