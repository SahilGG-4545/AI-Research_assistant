"""
core/agents.py
──────────────
AutoGen agent definitions (no Docker execution).
"""

from autogen import AssistantAgent, UserProxyAgent

NO_DOCKER = {"use_docker": False}

controller_agent = UserProxyAgent(
    name="controller",
    system_message="Coordinates processing across agents.",
    code_execution_config=NO_DOCKER,
    human_input_mode="NEVER",
)

search_agent = AssistantAgent(
    name="search_agent",
    system_message="Retrieve academic papers.",
    code_execution_config=NO_DOCKER,
)

qa_agent = AssistantAgent(
    name="qa_agent",
    system_message="Answer questions using provided context only.",
    code_execution_config=NO_DOCKER,
)

code_agent = AssistantAgent(
    name="code_agent",
    system_message="Generate production-grade code.",
    code_execution_config=NO_DOCKER,
)
