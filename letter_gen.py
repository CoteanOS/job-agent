"""
Turns a job description into a tailored motivation letter using an LLM.

Design choices:
- Plain REST via requests, not an SDK. The endpoint shape (generateContent)
  has been stable across model versions, so this won't break when the model
  string bumps. Only the model name lives in config.
- The CV facts block (facts.txt) is passed as the ONLY allowed source of truth,
  and the system instruction forbids inventing anything. Smaller/cheaper models
  hallucinate more freely, so the leash is short on purpose.
- Voice and structure are described generically here. Everything specific to
  the candidate (name, employers, stories) comes from facts.txt at runtime,
  which is not committed to the repo.
"""
import requests
import config

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_SYSTEM = """You write short motivation letters for job applications, in the voice of the candidate described in the CANDIDATE FACTS block. Match their voice and use only their real facts.

VOICE:
- Plain, short, declarative sentences. Direct, not polished or corporate.
- Never use filler like "results-driven", "passionate", "synergy", "leverage", "proven track record".
- No em-dashes or en-dashes. Plain punctuation only.

STRUCTURE (one page, about 250 to 320 words, four short paragraphs):
1. Open with the role and who the candidate is in two sentences. Do not start with "I am writing to apply"; the reader knows. Lead with the strongest relevant fit for this specific role.
2. One short paragraph on the candidate's background, drawn from the facts.
3. One concrete story from the facts that fits the role, told plainly. If none fits well, pick the closest real example.
4. Close in one or two lines. Location and a note that they welcome a conversation.

HARD RULES:
- Use ONLY facts from the CANDIDATE FACTS block. Never invent employers, titles, dates, skills or numbers. If the job wants something the candidate lacks, do not claim it; point to the closest real experience.
- Be honest about being early in a domain when relevant, rather than claiming seniority not earned.
- Output ONLY the letter body starting with "Dear ...". No address block, no subject line."""

_USER_TMPL = """CANDIDATE FACTS (the only truth you may use):
---
{facts}
---

JOB POSTING:
Title: {title}
Company: {company}
Description:
{description}
---

Write the motivation letter body now. Only the body text, nothing else."""


class LetterError(RuntimeError):
    pass


def generate_letter(*, title: str, company: str, description: str, facts: str) -> str:
    if not config.GEMINI_API_KEY:
        raise LetterError("GEMINI_API_KEY missing")

    url = _ENDPOINT.format(model=config.GEMINI_MODEL)
    payload = {
        "systemInstruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{
            "role": "user",
            "parts": [{"text": _USER_TMPL.format(
                facts=facts, title=title, company=company, description=description,
            )}],
        }],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048},
    }
    try:
        r = requests.post(url, headers={"x-goog-api-key": config.GEMINI_API_KEY},
                          json=payload, timeout=60)
    except requests.RequestException as e:
        raise LetterError(f"network error calling the model: {e}") from e

    if r.status_code != 200:
        raise LetterError(f"model HTTP {r.status_code}: {r.text[:300]}")

    data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise LetterError(f"unexpected model response: {str(data)[:300]}") from e

    text = text.strip().replace("\u2014", ", ").replace(" -- ", ", ")
    if not text:
        raise LetterError("model returned an empty letter")
    return text


if __name__ == "__main__":
    # smoke test with placeholder facts; real facts live in facts.txt
    demo = generate_letter(
        title="Example Role",
        company="Example Company",
        description="A short example job description for local testing.",
        facts="Candidate with relevant experience. Based in the Netherlands.",
    )
    print(demo)
