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
    agent_mode: str = os.getenv("AGENT_MODE", "react")
    agent_max_steps: int = _env_int("AGENT_MAX_STEPS", 6)
    agent_timeout_seconds: float = _env_float("AGENT_TIMEOUT_SECONDS", 45.0)
    agent_tool_timeout_seconds: float = _env_float("AGENT_TOOL_TIMEOUT_SECONDS", 10.0)
    # 连续相同 Action 的软忽略次数；超过后若已有变更则自动 final，否则报错。
    agent_max_repeated_actions: int = _env_int("AGENT_MAX_REPEATED_ACTIONS", 1)
    agent_goal_repair_attempts: int = _env_int("AGENT_GOAL_REPAIR_ATTEMPTS", 1)
    agent_max_model_calls: int = _env_int("AGENT_MAX_MODEL_CALLS", 6)
    agent_max_observation_chars: int = _env_int("AGENT_MAX_OBSERVATION_CHARS", 2000)
    agent_trace_enabled: bool = os.getenv("AGENT_TRACE_ENABLED", "true").lower() in {"1", "true", "yes"}
    agent_prefer_tool_calls: bool = os.getenv("AGENT_PREFER_TOOL_CALLS", "false").lower() in {"1", "true", "yes"}
    # false：决策只看本轮 userMessage + 当前画布 + 本轮 Observation，不带聊天历史/会话摘要。
    agent_include_chat_history: bool = os.getenv("AGENT_INCLUDE_CHAT_HISTORY", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    # 当前画布是本轮决策事实，默认始终携带方程表达式，与聊天历史开关解耦。
    agent_include_graph_expressions: bool = os.getenv("AGENT_INCLUDE_GRAPH_EXPRESSIONS", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    max_equations: int = _env_int("MAX_EQUATIONS", 20)
    max_expression_length: int = _env_int("MAX_EXPRESSION_LENGTH", 256)
    max_ast_nodes: int = _env_int("MAX_AST_NODES", 128)
    max_ast_depth: int = _env_int("MAX_AST_DEPTH", 32)
    max_numeric_constant: float = _env_float("MAX_NUMERIC_CONSTANT", 1_000_000.0)
    max_power_exponent: float = _env_float("MAX_POWER_EXPONENT", 100.0)
    max_viewport_abs: float = _env_float("MAX_VIEWPORT_ABS", 1_000_000.0)
    max_analysis_chars: int = _env_int("MAX_ANALYSIS_CHARS", 4000)
    math_sample_count: int = _env_int("MATH_SAMPLE_COUNT", 400)
    math_tolerance: float = _env_float("MATH_TOLERANCE", 1e-6)
    math_max_points: int = _env_int("MATH_MAX_POINTS", 32)
    context_recent_message_chars: int = _env_int("CONTEXT_RECENT_MESSAGE_CHARS", 2400)
    context_max_recent_messages: int = _env_int("CONTEXT_MAX_RECENT_MESSAGES", 16)
    context_summary_max_chars: int = _env_int("CONTEXT_SUMMARY_MAX_CHARS", 1200)
    message_page_size: int = _env_int("MESSAGE_PAGE_SIZE", 30)


settings = Settings()
