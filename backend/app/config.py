from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./math_graph_ai.db")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    deepseek_timeout_seconds: float = _env_float("DEEPSEEK_TIMEOUT_SECONDS", 30.0)
    deepseek_max_retries: int = _env_int("DEEPSEEK_MAX_RETRIES", 2)
    agent_mode: str = os.getenv("AGENT_MODE", "off")
    max_equations: int = _env_int("MAX_EQUATIONS", 20)
    max_expression_length: int = _env_int("MAX_EXPRESSION_LENGTH", 256)
    max_ast_nodes: int = _env_int("MAX_AST_NODES", 128)
    max_ast_depth: int = _env_int("MAX_AST_DEPTH", 32)
    max_numeric_constant: float = _env_float("MAX_NUMERIC_CONSTANT", 1_000_000.0)
    max_power_exponent: float = _env_float("MAX_POWER_EXPONENT", 100.0)
    max_viewport_abs: float = _env_float("MAX_VIEWPORT_ABS", 1_000_000.0)
    max_analysis_chars: int = _env_int("MAX_ANALYSIS_CHARS", 4000)


settings = Settings()
