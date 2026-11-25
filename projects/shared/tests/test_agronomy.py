"""TEST-AGR-01, TEST-AGR-02, AC-05: agronomic directive engine."""

from __future__ import annotations

from mekong_shared.agronomy import AgriDecisionEngine, primary_directive
from mekong_shared.models import CropStage, RiskTier, Urgency

engine = AgriDecisionEngine()


def test_test_agr_01_warning_ripening_harvest_directive():
    """TEST-AGR-01: WARNING + RIPENING => emergency harvest with Khmer text."""
    directives = engine.evaluate(RiskTier.WARNING, CropStage.RIPENING, lead_time_hours=48)
    primary = primary_directive(directives)
    assert primary.action_code == "EMERGENCY_HARVEST_ACCELERATION"
    assert primary.urgency is Urgency.HIGH
    assert "ប្រមូលផល" in primary.instruction_kh
    assert "48" in primary.instruction_en


def test_test_agr_02_advisory_vegetative_heavy_rain_hold_fertilizer():
    """TEST-AGR-02: ADVISORY + VEGETATIVE + 65mm rain => fertilizer hold."""
    directives = engine.evaluate(
        RiskTier.ADVISORY, CropStage.VEGETATIVE, rain_48h_mm=65.0, soil_moisture_pct=88.0
    )
    hold = next(d for d in directives if d.action_code == "HOLD_CHEMICAL_FERTILIZER")
    assert "ផ្អាកការបាចជី" in hold.instruction_kh
    assert hold.family == "FERTILIZER_HOLD"
    assert hold.urgency is Urgency.MEDIUM  # ADVISORY tier


def test_ac05_heavy_rain_tillering_triggers_hold():
    """AC-05: >60mm rain + saturated soil at tillering => must trigger hold."""
    directives = engine.evaluate(
        RiskTier.ADVISORY, CropStage.TILLERING, rain_48h_mm=65.0, soil_moisture_pct=90.0
    )
    assert any(d.action_code == "HOLD_CHEMICAL_FERTILIZER" for d in directives)


def test_light_rain_does_not_trigger_hold():
    directives = engine.evaluate(RiskTier.ADVISORY, CropStage.VEGETATIVE, rain_48h_mm=45.0)
    assert all(d.action_code != "HOLD_CHEMICAL_FERTILIZER" for d in directives)


def test_ripening_heavy_rain_does_not_hold_fertilizer():
    """Fertilizer advice targets young rice; ripening rice gets harvest guidance."""
    directives = engine.evaluate(RiskTier.ADVISORY, CropStage.RIPENING, rain_48h_mm=65.0)
    assert [d.action_code for d in directives] == ["MONITOR_NORMAL_OPERATIONS"]


def test_normal_operations_monitor_only():
    directives = engine.evaluate(RiskTier.NORMAL, CropStage.TILLERING)
    assert [d.action_code for d in directives] == ["MONITOR_NORMAL_OPERATIONS"]
    assert directives[0].urgency is Urgency.INFO


def test_danger_ripening_ordered_directives():
    directives = engine.evaluate(
        RiskTier.DANGER, CropStage.RIPENING, rain_48h_mm=70.0, lead_time_hours=12
    )
    codes = [d.action_code for d in directives]
    assert codes == [
        "EMERGENCY_HARVEST_ACCELERATION",
        "SLUICE_OPEN",
        "PROTECT_ASSETS_HIGH_GROUND",
    ]
    assert directives[0].urgency is Urgency.HIGH


def test_danger_tillering_includes_sluice_but_no_harvest():
    directives = engine.evaluate(
        RiskTier.DANGER, CropStage.TILLERING, rain_48h_mm=65.0, lead_time_hours=6
    )
    codes = [d.action_code for d in directives]
    assert "HOLD_CHEMICAL_FERTILIZER" in codes
    assert "SLUICE_OPEN" in codes
    assert "EMERGENCY_HARVEST_ACCELERATION" not in codes


def test_warning_non_ripening_still_sluice():
    directives = engine.evaluate(RiskTier.WARNING, CropStage.FLOWERING)
    codes = [d.action_code for d in directives]
    assert codes == ["SLUICE_OPEN"]


def test_all_khmer_strings_present():
    for tier, stage in [
        (RiskTier.NORMAL, CropStage.TILLERING),
        (RiskTier.WARNING, CropStage.RIPENING),
        (RiskTier.DANGER, CropStage.VEGETATIVE),
    ]:
        for d in engine.evaluate(tier, stage, rain_48h_mm=70.0):
            assert d.title_kh and d.instruction_kh
            assert d.title_en and d.instruction_en


def test_stage_for_planting_date_boundaries():
    """IMP-10: 90-120 day rice cycle stage boundaries."""
    from datetime import date
    from mekong_shared.agronomy import stage_for_planting_date

    today = date(2026, 10, 16)
    assert stage_for_planting_date(date(2026, 10, 1), today) is CropStage.TILLERING  # 15d
    assert stage_for_planting_date(date(2026, 9, 16), today) is CropStage.TILLERING  # 30d
    assert stage_for_planting_date(date(2026, 9, 15), today) is CropStage.VEGETATIVE  # 31d
    assert stage_for_planting_date(date(2026, 8, 17), today) is CropStage.VEGETATIVE  # 60d
    assert stage_for_planting_date(date(2026, 8, 16), today) is CropStage.FLOWERING  # 61d
    assert stage_for_planting_date(date(2026, 7, 18), today) is CropStage.FLOWERING  # 90d
    assert stage_for_planting_date(date(2026, 7, 17), today) is CropStage.RIPENING  # 91d


def test_vegetables_and_livestock_directives_bilingual():
    """IMP-10: VEGETABLES and LIVESTOCK profiles emit bilingual Khmer + English directives."""
    from mekong_shared.models import CropType

    veg_warn = engine.evaluate(
        RiskTier.WARNING,
        CropStage.VEGETATIVE,
        rain_48h_mm=60.0,
        lead_time_hours=24,
        crop_type=CropType.VEGETABLES,
    )
    veg_codes = [d.action_code for d in veg_warn]
    assert "VEGETABLE_EARLY_HARVEST" in veg_codes
    assert "VEGETABLE_RAISED_BED_DRAINAGE" in veg_codes
    assert "VEGETABLE_HOLD_SPRAY_AND_MULCH" in veg_codes
    assert all(d.title_kh and d.instruction_kh and d.title_en and d.instruction_en for d in veg_warn)

    live_danger = engine.evaluate(
        RiskTier.DANGER,
        CropStage.RIPENING,
        lead_time_hours=12,
        crop_type=CropType.LIVESTOCK,
    )
    live_codes = [d.action_code for d in live_danger]
    assert "LIVESTOCK_EVACUATE_HIGH_GROUND" in live_codes
    assert "LIVESTOCK_SECURE_SHELTER_AND_WATER" in live_codes
    assert all(d.title_kh and d.instruction_kh and d.title_en and d.instruction_en for d in live_danger)


def test_find_stage_advances_identifies_advanced_rice_subscriptions():
    """IMP-10: digest.find_stage_advances detects rice subscriptions due for stage confirmation."""
    from datetime import date
    from mekong_shared.digest import find_stage_advances
    from mekong_shared.models import CropType, Subscription

    today = date(2026, 10, 16)
    subs = [
        Subscription(
            telegram_chat_id="1",
            commune_id="080404",
            crop_stage=CropStage.TILLERING,
            crop_type=CropType.RICE,
            planting_date=date(2026, 9, 1),  # 45d -> VEGETATIVE
        ),
        Subscription(
            telegram_chat_id="2",
            commune_id="080404",
            crop_stage=CropStage.VEGETATIVE,
            crop_type=CropType.RICE,
            planting_date=date(2026, 9, 1),  # already VEGETATIVE -> skip
        ),
        Subscription(
            telegram_chat_id="3",
            commune_id="080404",
            crop_stage=CropStage.TILLERING,
            crop_type=CropType.VEGETABLES,
            planting_date=date(2026, 9, 1),  # non-rice -> skip
        ),
    ]
    advances = find_stage_advances(subs, today)
    assert len(advances) == 1
    assert advances[0].subscription.telegram_chat_id == "1"
    assert advances[0].previous_stage is CropStage.TILLERING
    assert advances[0].suggested_stage is CropStage.VEGETATIVE
    assert advances[0].days_since_planting == 45
