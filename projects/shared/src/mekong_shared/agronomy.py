"""Agronomic decision engine (FR-04, INV-03, IMP-10).

Deterministic mapping from (risk tier, crop stage, crop type, forecast rain) to
ordered field directives in Khmer and English. Strings are stable so tests can
assert exact Khmer tokens (TEST-AGR-01: ប្រមូលផល, TEST-AGR-02: ផ្អាកការបាចជី).
"""

from __future__ import annotations

from datetime import date

from .models import CropStage, CropType, Directive, RiskTier, Urgency

RAIN_FERTILIZER_HOLD_48H_MM = 50.0


def stage_for_planting_date(planting_date: date, today: date | None = None) -> CropStage:
    """Map rice planting date to the current growth stage over a 90-120 day cycle.

    - <= 30 days: TILLERING
    - 31-60 days: VEGETATIVE
    - 61-90 days: FLOWERING
    - > 90 days: RIPENING
    """
    ref = today or date.today()
    days = (ref - planting_date).days
    if days <= 30:
        return CropStage.TILLERING
    if days <= 60:
        return CropStage.VEGETATIVE
    if days <= 90:
        return CropStage.FLOWERING
    return CropStage.RIPENING


class AgriDecisionEngine:
    def evaluate(
        self,
        tier: RiskTier,
        crop_stage: CropStage,
        *,
        rain_48h_mm: float = 0.0,
        soil_moisture_pct: float | None = None,
        lead_time_hours: int | None = None,
        crop_type: CropType = CropType.RICE,
    ) -> list[Directive]:
        if crop_type is CropType.VEGETABLES:
            return self._evaluate_vegetables(
                tier, rain_48h_mm=rain_48h_mm, lead_time_hours=lead_time_hours
            )
        if crop_type is CropType.LIVESTOCK:
            return self._evaluate_livestock(tier, lead_time_hours=lead_time_hours)

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
            directives.append(self._protect_assets_directive())

        # 5) Nothing urgent: confirm normal operations are safe (AC-02).
        if not directives:
            directives.append(self._normal_operations_directive())

        return sorted(directives, key=lambda d: d.priority)

    def _evaluate_vegetables(
        self,
        tier: RiskTier,
        *,
        rain_48h_mm: float = 0.0,
        lead_time_hours: int | None = None,
    ) -> list[Directive]:
        directives: list[Directive] = []
        if tier.at_least(RiskTier.WARNING):
            lead = f" within about {lead_time_hours} hours" if lead_time_hours else ""
            directives.append(
                Directive(
                    action_code="VEGETABLE_EARLY_HARVEST",
                    family="HARVEST",
                    title_en="Harvest market-ready vegetables early",
                    title_kh="ប្រមូលផលបន្លែទាន់ពេលមុនទឹកឡើង",
                    instruction_en=(
                        f"Harvest mature riverbank vegetables immediately{lead} before beds "
                        "submerge. Store produce above flood level and prepare for early market sale."
                    ),
                    instruction_kh=(
                        "សូមប្រមូលផលបន្លែដែលគ្រប់អាយុនៅតាមមាត់ទន្លេជាបន្ទាន់ មុនពេលទឹកលិចរង។ "
                        "រក្សាទុកផលិតផលនៅទីខ្ពស់ និងរៀបចំលក់ឱ្យទាន់ពេល។"
                    ),
                    urgency=Urgency.HIGH,
                    priority=10,
                )
            )
            directives.append(
                Directive(
                    action_code="VEGETABLE_RAISED_BED_DRAINAGE",
                    family="SLUICE_OPEN",
                    title_en="Clear raised-bed drainage trenches",
                    title_kh="សម្អាតប្រឡាយបង្ហូរទឹកតាមរងបន្លែ",
                    instruction_en=(
                        "Deepen drainage furrows between raised beds and lift irrigation pumps "
                        "and seedlings onto higher ground."
                    ),
                    instruction_kh=(
                        "សូមជីកបង្ហូរទឹកតាមចន្លោះរងបន្លែឱ្យជ្រៅ និងលើកម៉ាស៊ីនបូមទឹក "
                        "ព្រមទាំងកូនបន្លែទៅទីទួលខ្ពស់។"
                    ),
                    urgency=Urgency.HIGH if tier is RiskTier.DANGER else Urgency.MEDIUM,
                    priority=25,
                )
            )
        if rain_48h_mm >= RAIN_FERTILIZER_HOLD_48H_MM:
            directives.append(
                Directive(
                    action_code="VEGETABLE_HOLD_SPRAY_AND_MULCH",
                    family="FERTILIZER_HOLD",
                    title_en="Delay foliar inputs and protect beds from heavy rain",
                    title_kh="ផ្អាកការបាចជី និងការពាររងបន្លែពីភ្លៀងធ្ងន់",
                    instruction_en=(
                        f"Hold fertilizer and foliar sprays ({rain_48h_mm:.0f}mm rain forecast "
                        "in 48h) and secure plastic mulch or shade netting over fragile seedlings."
                    ),
                    instruction_kh=(
                        "សូមផ្អាកការបាចជី និងការបាញ់ថ្នាំបំប៉ន ព្រោះភ្លៀងធ្ងន់ក្នុង ៤៨ ម៉ោងខាងមុខ "
                        "ហើយគ្របការពារកូនបន្លែឱ្យបានល្អ។"
                    ),
                    urgency=Urgency.MEDIUM,
                    priority=20,
                )
            )
        if tier is RiskTier.DANGER:
            directives.append(self._protect_assets_directive())
        if not directives:
            directives.append(self._normal_operations_directive())
        return sorted(directives, key=lambda d: d.priority)

    def _evaluate_livestock(
        self,
        tier: RiskTier,
        *,
        lead_time_hours: int | None = None,
    ) -> list[Directive]:
        directives: list[Directive] = []
        if tier is RiskTier.DANGER:
            lead = f" within {lead_time_hours} hours" if lead_time_hours else ""
            directives.append(
                Directive(
                    action_code="LIVESTOCK_EVACUATE_HIGH_GROUND",
                    family="MONITOR",
                    title_en="Evacuate livestock to safe mounds immediately",
                    title_kh="ជម្លៀសសត្វពាហនៈទៅទីទួលសុវត្ថិភាពជាបន្ទាន់",
                    instruction_en=(
                        f"Move cattle, buffalo, pigs, and poultry to designated high-ground "
                        f"mounds immediately{lead}. Keep veterinary kits and clean drinking water ready."
                    ),
                    instruction_kh=(
                        "សូមជម្លៀសគោ ក្របី ជ្រូក និងបសុបក្សីទៅទីទួលសុវត្ថិភាពជាបន្ទាន់។ "
                        "ត្រៀមថ្នាំសត្វ និងទឹកស្អាតសម្រាប់សត្វផឹកឱ្យបានគ្រប់គ្រាន់។"
                    ),
                    urgency=Urgency.HIGH,
                    priority=10,
                )
            )
        elif tier is RiskTier.WARNING:
            directives.append(
                Directive(
                    action_code="LIVESTOCK_PREPARE_RELOCATION",
                    family="MONITOR",
                    title_en="Prepare livestock relocation and stockpile fodder",
                    title_kh="ត្រៀមផ្លាស់ទីសត្វពាហនៈ និងស្តុកចំណីសត្វ",
                    instruction_en=(
                        "Identify safe high-ground shelter routes for livestock, stockpile dry "
                        "straw and feed above flood level, and check boat or cart transport."
                    ),
                    instruction_kh=(
                        "សូមត្រៀមផ្លូវផ្លាស់ទីសត្វពាហនៈទៅទីទួលខ្ពស់ ស្តុកចំបើង និងចំណីស្ងួតនៅទីខ្ពស់ "
                        "ព្រមទាំងពិនិត្យមធ្យោបាយដឹកជញ្ជូនទុកជាមុន។"
                    ),
                    urgency=Urgency.HIGH,
                    priority=15,
                )
            )
        if tier.at_least(RiskTier.WARNING):
            directives.append(
                Directive(
                    action_code="LIVESTOCK_SECURE_SHELTER_AND_WATER",
                    family="MONITOR",
                    title_en="Secure pens and store clean drinking water",
                    title_kh="ពង្រឹងទ្រុងសត្វ និងស្តុកទឹកស្អាត",
                    instruction_en=(
                        "Elevate poultry coops, disconnect low electrical lines in barns, and "
                        "store clean drinking water to prevent waterborne livestock disease."
                    ),
                    instruction_kh=(
                        "សូមលើកទ្រុងបសុបក្សីឱ្យខ្ពស់ ផ្តាច់ខ្សែភ្លើងនៅទីទាប និងស្តុកទឹកស្អាត "
                        "ដើម្បីការពារជំងឺសត្វឆ្លងតាមទឹក។"
                    ),
                    urgency=Urgency.MEDIUM,
                    priority=25,
                )
            )
        if not directives:
            directives.append(self._normal_operations_directive())
        return sorted(directives, key=lambda d: d.priority)

    @staticmethod
    def _protect_assets_directive() -> Directive:
        return Directive(
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

    @staticmethod
    def _normal_operations_directive() -> Directive:
        return Directive(
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


def primary_directive(directives: list[Directive]) -> Directive:
    return min(directives, key=lambda d: d.priority)
