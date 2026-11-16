import json
import os

from django.conf import settings
from groq import Groq


QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "question": {"type": "string"},
        "options": {
            "type": "array",
            "items": {"type": "string"},
        },
        "correct_index": {"type": "integer"},
        "explanation": {"type": "string"},
    },
    "required": ["topic", "question", "options", "correct_index", "explanation"],
}


def generate_question(skill, difficulty, previous_questions=None, programming_language=None):
    """
    Generate and validate one MCQ using Groq's Chat Completions API.

    Uses JSON mode for broad model compatibility, then validates the returned
    structure locally before the question is stored.
    """
    api_key = getattr(settings, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing. Add your Groq API key to the .env file."
        )

    model = getattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b")
    previous_questions = previous_questions or []

    system_prompt = """
You are a careful technical assessment author.
Return only valid JSON. Do not include markdown fences or commentary.
Create original, accurate, unambiguous multiple-choice questions.
Exactly one answer must be correct. The correct_index is zero-based.
"""

    user_prompt = f"""
Create ONE multiple-choice assessment question.

Selected skill path: {skill}
Primary programming language: {programming_language or 'Not explicitly identified'}
Difficulty: {difficulty}

STRICT SCOPE RULES:
- Assess ONLY the selected skill path above. Do not switch to a different language or technology.
- If a primary programming language is specified, every code snippet, syntax example, API, terminology-specific question, and answer option must use that exact language.
- Never substitute Python for C++, C++ for Python, Java for JavaScript, or any other language.
- If the selected skill is a sub-skill, keep the question focused on that sub-skill while staying within its parent language.
- Do not ask generic questions from another language just because the concept has a similar name.

Requirements:
- Exactly four distinct answer options.
- Exactly one unambiguously correct answer.
- correct_index must be an integer from 0 to 3.
- Include a concise topic label and a short explanation.
- Test practical understanding, not trivia.
- For programming skills, use valid code when appropriate.
- Avoid repeating these previous question texts:
{json.dumps(previous_questions, ensure_ascii=False)}

Return a JSON object with exactly these fields:
{{
  "topic": "short topic label",
  "question": "question text",
  "options": ["option 1", "option 2", "option 3", "option 4"],
  "correct_index": 0,
  "explanation": "short explanation"
}}
"""

    client = Groq(api_key=api_key)
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=1200,
        )
        content = completion.choices[0].message.content
        if not content:
            raise RuntimeError("Groq returned an empty response.")

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Groq returned invalid JSON. Please retry.") from exc

    except Exception as exc:
        # Keep useful API error details for Django's user-facing error handler.
        raise RuntimeError(f"Groq API request failed: {exc}") from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    if not isinstance(data, dict):
        raise RuntimeError("Groq returned an invalid question format.")

    topic = data.get("topic", "General")
    question = data.get("question")
    options = data.get("options")
    correct_index = data.get("correct_index")
    explanation = data.get("explanation")

    if not isinstance(question, str) or not question.strip():
        raise RuntimeError("Groq generated an empty question.")

    if not isinstance(options, list) or len(options) != 4:
        raise RuntimeError("Groq must generate exactly four answer options.")

    if not all(isinstance(option, str) and option.strip() for option in options):
        raise RuntimeError("Groq generated an invalid answer option.")

    if len({option.strip() for option in options}) != 4:
        raise RuntimeError("Groq generated duplicate answer options.")

    if (
        not isinstance(correct_index, int)
        or isinstance(correct_index, bool)
        or correct_index not in range(4)
    ):
        raise RuntimeError("Groq generated an invalid correct answer index.")

    if not isinstance(explanation, str) or not explanation.strip():
        raise RuntimeError("Groq generated an invalid explanation.")

    return {
        "topic": str(topic)[:100],
        "question": question.strip(),
        "options": [option.strip() for option in options],
        "correct_index": correct_index,
        "explanation": explanation.strip(),
    }


def generate_coding_task(skill, difficulty, programming_language=None):
    """Generate a small, self-contained coding exercise for question five."""
    api_key = getattr(settings, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing. Add your Groq API key to .env.")
    client = Groq(api_key=api_key)
    try:
        completion = client.chat.completions.create(
            model=getattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b"),
            messages=[
                {"role": "system", "content": "Create concise beginner-friendly coding assessment tasks. Return only valid JSON."},
                {"role": "user", "content": (
                    f"Selected skill path: {skill}. Required programming language: {programming_language or 'Choose the most directly relevant language from the selected skill path'}. Difficulty: {difficulty}. "
                    "Create one small coding exercise focused on the selected skill path. "
                    "If a required programming language is provided, the language field MUST be exactly that language, "
                    "and the prompt, starter snippets, syntax, input/output examples, and terminology MUST use only that language. "
                    "Do not use Python examples for a C++ assessment or C++ examples for a Python assessment. "
                    "It should be solvable in about 10-15 minutes, have clear input/output requirements, "
                    "one or two examples, and no external libraries. Return JSON with fields "
                    "topic, language, prompt. Keep prompt under 1800 characters."
                )},
            ],
            response_format={"type": "json_object"},
            temperature=0.35,
            max_tokens=900,
        )
        data = json.loads(completion.choices[0].message.content or "{}")
        if not all(isinstance(data.get(k), str) and data[k].strip() for k in ("topic", "language", "prompt")):
            raise RuntimeError("Groq returned an incomplete coding task.")
        returned_language = data["language"].strip()
        if programming_language and returned_language.casefold() != programming_language.casefold():
            raise RuntimeError(
                f"Groq generated a {returned_language} task, but this assessment requires {programming_language}. Please retry."
            )
        return {"topic": data["topic"][:100], "language": programming_language or returned_language[:40], "prompt": data["prompt"][:4000]}
    except Exception as exc:
        raise RuntimeError(f"Could not generate coding task: {exc}") from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def grade_coding_submission(skill, language, prompt, submission):
    """Ask Groq to mark submitted code and return a validated 0-100 score."""
    api_key = getattr(settings, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing. Add your Groq API key to .env.")
    client = Groq(api_key=api_key)
    try:
        completion = client.chat.completions.create(
            model=getattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b"),
            messages=[
                {"role": "system", "content": (
                    "You are a fair programming assessment grader. Evaluate code against the task. "
                    "Consider correctness, edge cases, logic, readability and whether it follows requirements. "
                    "Do not execute code or claim you executed it. Award partial credit. Return only JSON."
                )},
                {"role": "user", "content": (
                    f"Selected skill path: {skill}\nREQUIRED LANGUAGE: {language}\nTask:\n{prompt}\n"
                    f"Student submission (must be graded as {language}):\n{submission}\n"
                    f"Grade this submission strictly as {language}. Do not reinterpret it as another language, do not silently translate it, "
                    f"and do not penalize valid {language} syntax for differing from Python or another language. If the submission is clearly written in a different language, explain that and award an appropriately low score. "
                    "Return JSON with integer score from 0 to 100 and concise actionable feedback."
                )},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=700,
        )
        data = json.loads(completion.choices[0].message.content or "{}")
        score = data.get("score")
        feedback = data.get("feedback")
        if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 100:
            raise RuntimeError("AI grader returned an invalid score.")
        if not isinstance(feedback, str) or not feedback.strip():
            raise RuntimeError("AI grader returned no feedback.")
        return score, feedback.strip()[:2000]
    except Exception as exc:
        raise RuntimeError(f"Could not grade coding submission: {exc}") from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
