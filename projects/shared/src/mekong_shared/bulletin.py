"""Bilingual bulletin composition (FR-05).

Deterministic Khmer/English templates always work offline; when a Gemini text
key is configured the Khmer bulletin is additionally polished by
`gemini_text_model` under hard "no new facts" constraints. The template output
is the fallback and the source of truth for tests.
"""

from __future__ import annotations

import asyncio

from .config import Settings
from .models import Commune, CommuneRisk, Directive, FloodReason, RiskTier, StationSnapshot, WeatherSnapshot

_REASON_KH = {
    FloodReason.NONE: "លក្ខខណ្ឌធម្មតា",
    FloodReason.RIVER_PULSE: "ទឹកទន្លេឡើងលឿន",
    FloodReason.RIVER_OVERFLOW: "ទឹកទន្លេហូរលើសកម្រិត",
    FloodReason.LOCAL_FLASH_FLOOD: "ហានិភ័យទឹកជំនន់ភ្លាមៗពីភ្លៀងធ្ងន់",
}
_REASON_EN = {
    FloodReason.NONE: "normal conditions",
    FloodReason.RIVER_PULSE: "rapid river rise",
    FloodReason.RIVER_OVERFLOW: "river above alarm level",
    FloodReason.LOCAL_FLASH_FLOOD: "localized flash-flood risk from heavy rain",
}


class GeminiTextClient:
    """Thin async wrapper around google-genai text generation (mockable)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None

    async def generate(self, prompt: str) -> str:
        from google import genai  # local import: optional in offline runs

        if self._client is None:
            if self._settings.use_vertex_ai:
                self._client = genai.Client(
                    vertexai=True,
                    project=self._settings.vertex_project,
                    location=self._settings.vertex_location,
                )
            else:
                self._client = genai.Client(api_key=self._settings.gemini_api_key)

        def _run() -> str:
            response = self._client.models.generate_content(
                model=self._settings.gemini_text_model, contents=prompt
            )
            return (response.text or "").strip()

        return await asyncio.to_thread(_run)

    async def polish_khmer(self, template_text: str) -> str:
        prompt = (
            "អ្នកគឺជាអ្នកជំនាញភាសាខ្មែរដែលសរសេរសារព្រមានទឹកជំនន់ឱ្យកសិករអាន។ "
            "សូមសរសេរឡើងវិញនូវសារខាងក្រោមជាភាសាខ្មែរសុភាពរាបសា និងងាយស្រួលយល់។ "
            "ច្បាប់ដាច់ខាត៖ មិនត្រូវបន្ថែម ឬដកលេខ កម្រិតទឹក ឬការណែនាំណាមួយឡើយ។ "
            "រក្សាប្រយោគឱ្យខ្លី និងសម្រាប់ការអានចេញសំឡេងប្រហែល 45 វិនាទី។\n\n"
            f"សារដើម:\n{template_text}"
        )
        polished = await self.generate(prompt)
        return polished or template_text


class BulletinBuilder:
    def __init__(self, text_client: GeminiTextClient | None = None) -> None:
        self._text = text_client

    # ---- deterministic templates -----------------------------------------
    def build_templates(
        self,
        commune: Commune,
        risk: CommuneRisk,
        directives: list[Directive],
        station: StationSnapshot | None,
        weather: WeatherSnapshot | None,
    ) -> tuple[str, str]:
        kh = [f"សារព្រមានទឹកជំនន់ពី MekongPulse សម្រាប់ឃុំ {commune.name_kh}"]
        if commune.district_en and commune.province_en:
            kh.append(f"({commune.district_en}, {commune.province_en})")
        kh.append("")
        kh.append(f"កម្រិតហានិភ័យ: {risk.tier.emoji} {risk.tier.label_kh} ({risk.tier.value})")
        if station is not None:
            kh.append(
                f"ទឹកទន្លេ {station.river} នៅស្ថានីយ៍ {station.name}: {station.level_m:.2f} ម៉ែត្រ"
            )
            kh.append(
                f"កម្រិតព្រមាន {station.alarm_stage_m:.2f} ម៉ែត្រ | កម្រិតគ្រោះថ្នាក់ {station.flood_stage_m:.2f} ម៉ែត្រ"
            )
            if station.rate_of_rise_m_per_hr >= 0.08:
                kh.append(f"ទឹកកំពុងឡើងលឿន {station.rate_of_rise_m_per_hr:.2f} ម៉ែត្រក្នុងមួយម៉ោង។")
            elif station.rate_of_rise_m_per_hr > 0.01:
                kh.append(f"ទឹកកំពុងឡើងថ្នមៗ {station.rate_of_rise_m_per_hr:.2f} ម៉ែត្រក្នុងមួយម៉ោង។")
            else:
                kh.append("កម្រិតទឹកមានស្ថេរភាពប្រហាក់ប្រហែល។")
        if weather is not None:
            kh.append(f"ភ្លៀងព្យាករណ៍ 48 ម៉ោងខាងមុខ: {weather.precipitation_48h_mm:.0f} មីលីម៉ែត្រ។")
        if risk.lead_time_hours:
            kh.append(f"ប្រហែល {risk.lead_time_hours} ម៉ោងទៀត ទឹកអាចមកដល់។")
        kh.append(f"មូលហេតុ: {_REASON_KH.get(risk.reason, '')}។")
        kh.append("")
        kh.append("សកម្មភាពដែលត្រូវអនុវត្ត:")
        for d in directives:
            kh.append(f"• {d.title_kh}: {d.instruction_kh}")
        kh.append("")
        kh.append("សូមអនុវត្តតាមការណែនាំ និងតាមដានសារបន្ទាប់ពី MekongPulse។ សូមសុវត្ថិភាព!")

        en = [f"MekongPulse flood bulletin for {commune.name_en} commune"]
        if commune.district_en and commune.province_en:
            en.append(f"({commune.district_en}, {commune.province_en})")
        en.append("")
        en.append(f"Risk tier: {risk.tier.emoji} {risk.tier.value} (score {risk.score}/100)")
        if station is not None:
            en.append(
                f"{station.river} at {station.name}: {station.level_m:.2f} m "
                f"(alarm {station.alarm_stage_m:.2f} m, flood {station.flood_stage_m:.2f} m), "
                f"rising {station.rate_of_rise_m_per_hr:.2f} m/hr"
            )
        if weather is not None:
            en.append(f"Rain forecast next 48h: {weather.precipitation_48h_mm:.0f} mm")
        if risk.lead_time_hours:
            en.append(f"Estimated time until water arrival: ~{risk.lead_time_hours} hours")
        en.append(f"Reason: {_REASON_EN.get(risk.reason, '')}")
        en.append("")
        en.append("Actions:")
        for d in directives:
            en.append(f"• {d.title_en}: {d.instruction_en}")
        return "\n".join(kh), "\n".join(en)

    async def build(
        self,
        commune: Commune,
        risk: CommuneRisk,
        directives: list[Directive],
        station: StationSnapshot | None,
        weather: WeatherSnapshot | None,
    ) -> tuple[str, str]:
        kh, en = self.build_templates(commune, risk, directives, station, weather)
        if self._text is not None:
            try:
                kh = await self._text.polish_khmer(kh)
            except Exception:  # noqa: BLE001 - template remains the source of truth
                pass
        return kh, en
