"""Agronomic decision engine (FR-04, INV-03).

Deterministic mapping from (risk tier, crop stage, forecast rain) to ordered
field directives in Khmer and English. Strings are stable so tests can assert
exact Khmer tokens (TEST-AGR-01: ប្រមូលផល, TEST-AGR-02: ផ្អាកការបាចជី).
"""

from __future__ import annotations

from .models import CropStage, Directive, RiskTier, Urgency

RAIN_FERTILIZER_HOLD_48H_MM = 50.0


class AgriDecisionEngine:
    def evaluate(
        self,
        tier: RiskTier,
        crop_stage: CropStage,
        *,
        rain_48h_mm: float = 0.0,
        soil_moisture_pct: float | None = None,
        lead_time_hours: int | None = None,
    ) -> list[Directive]:
        directives: list[Directive] = []

        # 1) Ripening rice under real flood threat: harvest now (FR-04 / JRN-03).
        if crop_stage is CropStage.RIPENING and tier.at_least(RiskTier.WARNING):
            lead = f" within about {lead_time_hours} hours" if lead_time_hours else ""
            directives.append(
                Directive(
                    action_code="EMERGENCY_HARVEST_ACCELERATION",
                    family="HARVEST",
                    title_en="Emergency harvest acceleration",
                    title_kh="ប្រមូលផលបន្ទាន់",
                    instruction_en=(
                        f"Harvest ripened rice immediately{lead}, before floodwater reaches the "
                        "fields. Mobilize combine harvesters and hire extra labor now."
                    ),
                    instruction_kh=(
                        "សូមប្រមូលផលស្រូវទុំជាបន្ទាន់ មុនពេលទឹកជំនន់មកដល់ស្រែ។ "
                        "រៀបចំគ្រឿងចក្រច្រូតកាត់ និងជួលកម្លាំងពលកម្មបន្ថែមឥឡូវនេះ។"
                    ),
                    urgency=Urgency.HIGH,
                    priority=10,
                )
            )

        # 2) Heavy rain on young rice: fertilizer would be washed away (AC-05).
        if rain_48h_mm >= RAIN_FERTILIZER_HOLD_48H_MM and crop_stage in (
            CropStage.TILLERING,
            CropStage.VEGETATIVE,
        ):
            saturated = soil_moisture_pct is not None and soil_moisture_pct > 85.0
            directives.append(
                Directive(
                    action_code="HOLD_CHEMICAL_FERTILIZER",
                    family="FERTILIZER_HOLD",
                    title_en="Hold chemical fertilizer application",
                    title_kh="ផ្អាកការបាចជី",
                    instruction_en=(
                        f"Do not apply chemical fertilizer: {rain_48h_mm:.0f}mm of rain is forecast "
                        "in the next 48 hours and will wash the fertilizer away"
                        + (" (soil is already near saturation)." if saturated else ".")
                    ),
                    instruction_kh=(
                        "សូមផ្អាកការបាចជីគីមីទាំងអស់ ព្រោះភ្លៀងធ្ងន់ក្នុងរយៈពេល ៤៨ ម៉ោង "
                        "នឹងលាងជីទៅអស់ ហើយអ្នកនឹងខាតបង់លុយដោយឥតប្រយោជន៍។"
                    ),
                    urgency=Urgency.HIGH if tier.at_least(RiskTier.WARNING) else Urgency.MEDIUM,
                    priority=20,
                )
            )

        # 3) Water is coming to the fields: prepare drainage infrastructure.
        if tier.at_least(RiskTier.WARNING):
            directives.append(
                Directive(
                    action_code="SLUICE_OPEN",
                    family="SLUICE_OPEN",
                    title_en="Prepare sluice gates and field drainage",
                    title_kh="បើកទ្វារទឹក និងរំដោះទឹកចេញពីស្រែ",
                    instruction_en=(
                        "Open sluice gates and clear drainage channels so rising water can flow "
                        "out of the paddy. Check that gates operate freely before the crest."
                    ),
                    instruction_kh=(
                        "សូមបើកទ្វារទឹក និងសម្អាតប្រឡាយចេញទឹក ដើម្បីឱ្យទឹកហូរចេញពីស្រែបាន។ "
                        "ត្រួតពិនិត្យទ្វារទឹកឱ្យដំណើរការល្អ មុនពេលទឹកឡើងកំពូល។"
                    ),
                    urgency=Urgency.HIGH if tier is RiskTier.DANGER else Urgency.MEDIUM,
                    priority=30,
                )
            )

        # 4) Danger: protect movable assets and livestock.
        if tier is RiskTier.DANGER:
            directives.append(
                Directive(
                    action_code="PROTECT_ASSETS_HIGH_GROUND",
                    family="MONITOR",
                    title_en="Move assets and livestock to high ground",
                    title_kh="ផ្លាស់ទ្រព្យសម្បត្តិ និងសត្វទៅទីទួលខ្ពស់",
                    instruction_en=(
                        "Move stored seed, fertilizer, fuel, and machinery to higher ground and "
                        "prepare livestock for relocation. Follow commune committee instructions."
                    ),
                    instruction_kh=(
                        "សូមផ្លាស់គ្រាប់ពូជ ជី ប្រេង និងគ្រឿងចក្រ ទៅទីទួលខ្ពស់។ "
                        "ត្រៀមផ្លាស់សត្វពាហនៈ និងគោរពតាមការណែនាំរបស់គណៈកម្មការឃុំ។"
                    ),
                    urgency=Urgency.HIGH,
                    priority=40,
                )
            )

        # 5) Nothing urgent: confirm normal operations are safe (AC-02).
        if not directives:
            directives.append(
                Directive(
                    action_code="MONITOR_NORMAL_OPERATIONS",
                    family="MONITOR",
                    title_en="Continue normal farming operations",
                    title_kh="បន្តការងារកសិកម្មធម្មតា",
                    instruction_en=(
                        "River levels are within the normal range for your area. Normal planting, "
                        "fertilizing, and harvesting activities are safe to proceed."
                    ),
                    instruction_kh=(
                        "កម្រិតទឹកទន្លេស្ថិតក្នុងកម្រិតធម្មតា។ "
                        "លោកអ្នកអាចបន្តការងារកសិកម្មធម្មតាបានដោយសុវត្ថិភាព។"
                    ),
                    urgency=Urgency.INFO,
                    priority=90,
                )
            )

        return sorted(directives, key=lambda d: d.priority)


def primary_directive(directives: list[Directive]) -> Directive:
    return min(directives, key=lambda d: d.priority)
