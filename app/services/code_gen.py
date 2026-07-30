"""
app/services/code_gen.py
────────────────────────
Multi-agent code generation pipeline.
Simulates a Developer → QA Reviewer → Lead Developer conversation.
"""

import re

from core.llm import groq_chat


def generate_advanced_code(instruction: str, language: str = "python") -> dict:
    """
    Simulates a multi-agent Code Generation & Review Squad by storing
    and passing a conversational log between a Developer and a QA Reviewer.
    """
    chat_log = []

    # --- 1. DEVELOPER AGENT ---
    dev_prompt = f"""
You are an expert {language} Developer. The user wants to build: "{instruction}".
Write the code, explain your thought process briefly, and directly ask the "QA Reviewer" to check it for bugs or improvements.
Make it sound like a real conversation.
"""
    dev_response = groq_chat(dev_prompt, temperature=0.5).strip()
    chat_log.append({"role": "Developer 🧑‍💻", "message": dev_response})

    # --- 2. QA/REVIEWER AGENT ---
    qa_prompt = f"""
You are the QA and Security Reviewer. The Developer just sent you this message:

"{dev_response}"

Talk directly back to the Developer. Point out any missing edge cases, security flaws, or inefficiencies in their code. Suggest fixes in a conversational tone.
If it's perfect, just say "Looks great to me."
"""
    qa_review = groq_chat(qa_prompt, temperature=0.3).strip()
    chat_log.append({"role": "QA Reviewer 🕵️", "message": qa_review})

    # --- 3. LEAD DEVELOPER AGENT (Final Fix) ---
    lead_prompt = f"""
You are the Developer again. You wrote this:
"{dev_response}"

The QA Reviewer replied with:
"{qa_review}"

Reply to the Reviewer, thank them (or agree/disagree), and then provide the FINAL fixed {language} code. 
IMPORTANT: Put the final code inside standard markdown blocks like ```{language} ... ``` so it can be extracted.
"""
    final_response = groq_chat(lead_prompt, temperature=0.3).strip()
    chat_log.append({"role": "Developer 🧑‍💻", "message": final_response})

    # Extract code from the final response
    code_match = re.search(r"```(?:\w+)?\n(.*?)```", final_response, re.DOTALL)
    if code_match:
        final_code = code_match.group(1).strip()
    else:
        # Fallback cleanup
        final_code = re.sub(r"^```[\w]*\n?", "", final_response, flags=re.MULTILINE)
        final_code = re.sub(r"\n?```$", "", final_code).strip()

    return {"code": final_code, "trace": {"chat_log": chat_log}}
