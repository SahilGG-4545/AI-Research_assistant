"""
core/llm.py
───────────
Groq client singleton and groq_chat() wrapper.
All service modules call groq_chat() from here.
"""

from groq import Groq
from core.config import GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY)


def groq_chat(
    prompt: str,
    model: str = "llama-3.3-70b-versatile",
    conversation_history=None,
    temperature: float = 0.4,
) -> str:
    """Send a prompt to Groq and return the response string."""
    messages = []
    if conversation_history:
        messages.extend(conversation_history)

    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=1800,
    )

    return response.choices[0].message.content
