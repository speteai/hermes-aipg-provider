"""AI Power Grid provider profile (community plugin, not an official AIPG project)."""

from providers import register_provider
from providers.base import ProviderProfile


aipg = ProviderProfile(
    name="aipg", aliases=("ai-power-grid", "aipowergrid"), display_name="AI Power Grid",
    description="AI Power Grid — open models served by independent GPU operators (community plugin)",
    signup_url="https://aipowergrid.io", env_vars=("AIPG_API_KEY", "AIPG_BASE_URL"),
    base_url="https://api.aipowergrid.io/v1", auth_type="api_key",
    default_aux_model="qwen38-flash-next-nvfp4",
    # gpt-oss-120b is left out on purpose: its tool calls currently come back inside the reasoning
    # text on multi-step tasks (AIPowerGrid/aipg-documentation#70), so agent runs end with no reply.
    fallback_models=("qwen38-flash-next-nvfp4",),
)

register_provider(aipg)
