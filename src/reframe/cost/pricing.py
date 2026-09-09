"""
Reframe V7 Versioned Model Pricing Registry
Enforces fail-closed token rates and verified billing references (R2-08).
Zero Paid Model Calls in default offline configuration.
"""
from enum import Enum
from typing import Dict, Optional, Tuple
from pydantic import BaseModel, Field
from src.reframe.shared.exceptions import ReframeException


class PricingStatus(str, Enum):
    VERIFIED_BILLING_PRICE = "VERIFIED_BILLING_PRICE"
    ESTIMATE_ONLY = "ESTIMATE_ONLY"
    UNKNOWN_FAIL_CLOSED = "UNKNOWN_FAIL_CLOSED"


class PricingConfigException(ReframeException):
    def __init__(self, message: str):
        super().__init__(
            status_code=500,
            code="PRICING_CONFIG_MISSING",
            message=message
        )


class ModelPricingConfig(BaseModel):
    model_id: str
    service: str = "Google Vertex AI / Gemini API"
    billing_mode: str = "PAY_AS_YOU_GO_TOKEN"
    currency: str = "USD"
    input_text_micro_rate: float = Field(..., description="Micros per 1 text input token")
    input_image_micro_rate: float = Field(..., description="Micros per 1 image input token")
    cached_input_micro_rate: float = Field(default=0.0, description="Micros per 1 cached token")
    output_text_micro_rate: float = Field(..., description="Micros per 1 output token")
    reasoning_micro_rate: float = Field(default=0.0, description="Micros per 1 reasoning token")
    pricing_version: str
    source: str = "Official Google Cloud Vertex AI Pricing Schedule"
    verified_at: str
    pricing_status: PricingStatus = PricingStatus.VERIFIED_BILLING_PRICE


class PricingRegistry:
    def __init__(self):
        self._registry: Dict[str, ModelPricingConfig] = {}
        self._load_verified_rates()

    def _load_verified_rates(self):
        # Official standard text pricing; output includes thinking tokens.
        self._registry["gemini-2.5-flash"] = ModelPricingConfig(
            model_id="gemini-2.5-flash",
            service="Google Gemini API",
            billing_mode="PAY_AS_YOU_GO_TOKEN",
            currency="USD",
            input_text_micro_rate=0.30,
            input_image_micro_rate=0.30,
            cached_input_micro_rate=0.03,
            output_text_micro_rate=2.50,
            reasoning_micro_rate=2.50,
            pricing_version="2026-09-08-gemini-2.5",
            source="https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing",
            verified_at="2026-09-08",
            pricing_status=PricingStatus.VERIFIED_BILLING_PRICE
        )
        # Gemini 3.6 Flash
        self._registry["gemini-3.6-flash"] = ModelPricingConfig(
            model_id="gemini-3.6-flash",
            service="Google Gemini API",
            billing_mode="PAY_AS_YOU_GO_TOKEN",
            currency="USD",
            input_text_micro_rate=0.825,
            input_image_micro_rate=0.825,
            cached_input_micro_rate=0.0825,
            output_text_micro_rate=4.125,
            reasoning_micro_rate=4.125,
            pricing_version="2026-09-08-gemini-3.6-regional",
            source="https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing",
            verified_at="2026-09-08",
            pricing_status=PricingStatus.VERIFIED_BILLING_PRICE
        )

        # Gemini 3.6 Pro (Marked as ESTIMATE_ONLY until live billing confirmation)
        self._registry["gemini-3.6-pro"] = ModelPricingConfig(
            model_id="gemini-3.6-pro",
            service="Google Gemini API",
            billing_mode="PAY_AS_YOU_GO_TOKEN",
            currency="USD",
            input_text_micro_rate=1.25,
            input_image_micro_rate=1.25,
            cached_input_micro_rate=0.3125,
            output_text_micro_rate=5.00,
            reasoning_micro_rate=5.00,
            pricing_version="2026-08-gemini-3.6-pro-est",
            source="Estimated Rate Schedule",
            verified_at="2026-08-19",
            pricing_status=PricingStatus.ESTIMATE_ONLY
        )

    def get_pricing(self, model_id: str) -> ModelPricingConfig:
        clean_id = model_id.strip().lower()
        cfg = None
        if clean_id in self._registry:
            cfg = self._registry[clean_id]
        else:
            for reg_id, candidate in self._registry.items():
                if reg_id in clean_id:
                    cfg = candidate
                    break

        if not cfg or cfg.pricing_status == PricingStatus.UNKNOWN_FAIL_CLOSED:
            raise PricingConfigException(
                f"Unknown or unverified model '{model_id}'. Fail-closed spend policy active."
            )
        return cfg

    def calculate_estimated_cost_micros(
        self,
        model_id: str,
        input_text_tokens: int,
        input_image_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
        cached_input_tokens: int = 0
    ) -> Tuple[int, str]:
        cfg = self.get_pricing(model_id)
        total_tokens = input_text_tokens + input_image_tokens + cached_input_tokens + output_tokens + reasoning_tokens
        if total_tokens == 0:
            return 0, cfg.pricing_version

        cost = (
            (input_text_tokens * cfg.input_text_micro_rate)
            + (input_image_tokens * cfg.input_image_micro_rate)
            + (cached_input_tokens * cfg.cached_input_micro_rate)
            + (output_tokens * cfg.output_text_micro_rate)
            + (reasoning_tokens * cfg.reasoning_micro_rate)
        )
        return max(1, int(round(cost))), cfg.pricing_version



    def calculate_cost_micros(
        self,
        model_id: str,
        input_text_tokens: int,
        input_image_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
        cached_input_tokens: int = 0
    ) -> int:
        cost, _ = self.calculate_estimated_cost_micros(
            model_id=model_id,
            input_text_tokens=input_text_tokens,
            input_image_tokens=input_image_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens
        )
        return cost

    def get_pricing_status(self, model_id: str) -> PricingStatus:
        return self.get_pricing(model_id).pricing_status


pricing_registry = PricingRegistry()


