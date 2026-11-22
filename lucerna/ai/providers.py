"""AI provider abstraction with Humanitarian Data Protection enforcement.

* Default provider: local Ollama.
* `openai_compatible` supports local servers (LM Studio, llama.cpp server, vLLM) and, only if
  explicitly enabled and approved, external services.
* An EXTERNAL provider is usable only when ALL are true:
    1. env LUCERNA_EXTERNAL_AI_ENABLED=1 (deployment owner opt-in),
    2. app setting privacy.external_ai_allowed = 1 (System Administrator),
    3. the provider row is approved, with a recorded review of retention/training terms,
    4. the project classification is not 'Restricted' / 'Strictly confidential'.
  Otherwise a PrivacyBlocked error is raised — there is never a silent fallback.
* AI execution logs record sizes, timings and status only — never prompt or response content.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from .. import db
from ..config import settings
from ..services.bootstrap import get_setting


class AIError(Exception):
    """A model call failed. The message is actionable for the user."""


class PrivacyBlocked(AIError):
    pass


BLOCKING_CLASSIFICATIONS = {"restricted", "strictly confidential", "highly sensitive"}


@dataclass
class Provider:
    id: int
    name: str
    kind: str
    base_url: str
    model: str
    is_external: bool
    approved: bool
    api_key_env: str | None
    options: dict

    @staticmethod
    def from_row(r: dict) -> "Provider":
        return Provider(r["id"], r["name"], r["kind"], r["base_url"], r["model"], bool(r["is_external"]), bool(r.get("approved_at")),
                        r.get("api_key_env"), db.loads(r.get("options_json"), {}) or {})


def looks_local(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1") or host.startswith("192.168.") or host.startswith("10.") or host.endswith(".local")


def list_providers() -> list[dict]:
    return db.query("SELECT id, name, kind, base_url, model, is_external, enabled, approved_by, approved_at, terms_review_note, api_key_env, is_default FROM ai_providers ORDER BY is_default DESC, name")


def save_provider(actor, *, name: str, kind: str, base_url: str, model: str, api_key_env: str | None = None,
                  provider_id: int | None = None, is_default: bool = False, options: dict | None = None) -> int:
    from ..security import audit
    from ..security.rbac import require
    require(actor, "ai.configure")
    if kind not in ("ollama", "openai_compatible"):
        raise AIError("Provider type must be 'ollama' or 'openai_compatible'.")
    if not urlparse(base_url).scheme in ("http", "https"):
        raise AIError("Base URL must start with http:// or https://")
    external = 0 if looks_local(base_url) else 1
    if external and urlparse(base_url).scheme != "https":
        raise AIError("External providers must use HTTPS (encryption in transit).")
    if is_default:
        db.execute("UPDATE ai_providers SET is_default=0")
    if provider_id:
        db.execute("UPDATE ai_providers SET name=?, kind=?, base_url=?, model=?, api_key_env=?, is_external=?, is_default=?, options_json=?,"
                   " approved_by=CASE WHEN base_url<>? THEN NULL ELSE approved_by END, approved_at=CASE WHEN base_url<>? THEN NULL ELSE approved_at END WHERE id=?",
                   (name, kind, base_url, model, api_key_env, external, int(is_default), db.dumps(options or {}), base_url, base_url, provider_id))
        pid = provider_id
    else:
        pid = db.execute("INSERT INTO ai_providers(name, kind, base_url, model, is_external, enabled, api_key_env, is_default, options_json, created_at) VALUES(?,?,?,?,?,1,?,?,?,?)",
                         (name, kind, base_url, model, external, api_key_env, int(is_default), db.dumps(options or {}), db.now()))
    audit.log(actor.username, "AI_PROVIDER_SAVED", f"{name} external={bool(external)}", "WARNING" if external else "INFO", object_type="ai_provider", object_id=pid)
    return pid


def approve_external(actor, provider_id: int, terms_review_note: str) -> None:
    from ..security import audit
    from ..security.rbac import require
    require(actor, "ai.configure")
    if len((terms_review_note or "").strip()) < 30:
        raise AIError("Record who reviewed the provider's data-retention, training-exclusion and contractual terms, when, and the outcome (at least 30 characters).")
    db.execute("UPDATE ai_providers SET approved_by=?, approved_at=?, terms_review_note=? WHERE id=?", (actor.username, db.now(), terms_review_note.strip(), provider_id))
    audit.log(actor.username, "AI_PROVIDER_APPROVED", f"provider #{provider_id}", "HIGH", object_type="ai_provider", object_id=provider_id)


def resolve(project_classification: str | None = None, provider_id: int | None = None) -> Provider:
    row = db.query_one("SELECT * FROM ai_providers WHERE id=?", (provider_id,)) if provider_id else \
        db.query_one("SELECT * FROM ai_providers WHERE enabled=1 ORDER BY is_default DESC, id LIMIT 1")
    if not row:
        raise AIError("No AI provider is configured. Add one in AI & Model Settings.")
    p = Provider.from_row(row)
    if p.is_external:
        reasons = []
        if not settings().external_ai_enabled:
            reasons.append("LUCERNA_EXTERNAL_AI_ENABLED is not set to 1 in this deployment")
        if get_setting("privacy.external_ai_allowed", "0") != "1":
            reasons.append("external AI is disabled in Humanitarian Data Protection settings")
        if not p.approved:
            reasons.append("the provider's terms have not been reviewed and approved")
        if (project_classification or "").strip().lower() in BLOCKING_CLASSIFICATIONS:
            reasons.append(f"the project is classified '{project_classification}'")
        if reasons:
            raise PrivacyBlocked("Data was NOT sent to the external provider '" + p.name + "' because " + "; ".join(reasons) +
                                 ". Use the local Ollama provider or ask the System Administrator.")
    return p


def _log(project_id, job_id, p: Provider, prompt_name, prompt_version, in_chars, out_chars, status, attempts, started, error=None):
    db.execute("INSERT INTO ai_runs(project_id, job_id, provider, model, prompt_name, prompt_version, input_chars, output_chars, status, attempts, duration_ms, error, created_at)"
               " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (project_id, job_id, p.name, p.model, prompt_name, prompt_version, in_chars, out_chars, status, attempts,
                int((time.time() - started) * 1000), (error or "")[:500], db.now()))


def _ollama_error(exc: Exception, p: Provider) -> AIError:
    if isinstance(exc, requests.ConnectionError):
        return AIError(f"Cannot reach Ollama at {p.base_url}. Start it (open the Ollama app, or run `ollama serve`) and try again.")
    if isinstance(exc, requests.Timeout):
        return AIError(f"The model did not answer within {settings().llm_timeout}s. Large models on CPU can be slow: increase OLLAMA_TIMEOUT_SECONDS, "
                       "use a smaller model, or reduce MAX_SEGMENTS_PER_LLM_BATCH.")
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        body = exc.response.text[:300]
        if exc.response.status_code == 404 or "not found" in body.lower():
            return AIError(f"Model '{p.model}' is not installed in Ollama. Run: ollama pull {p.model}")
        if "memory" in body.lower():
            return AIError(f"Ollama ran out of memory loading '{p.model}'. Close other programs, choose a smaller model, or set OLLAMA_NUM_GPU=0 to use CPU only.")
        return AIError(f"Ollama returned HTTP {exc.response.status_code}: {body}")
    return AIError(f"Model call failed: {exc}")


def chat_json(messages: list[dict], *, prompt_name: str, prompt_version: str, project_id: int | None = None,
              classification: str | None = None, job_id: str | None = None, provider_id: int | None = None,
              validator=None) -> dict:
    """Call the model expecting a JSON object. `validator(obj)` must raise ValueError for schema violations;
    invalid outputs are retried up to LLM_JSON_RETRIES times and then fail loudly."""
    p = resolve(classification, provider_id)
    s = settings()
    in_chars = sum(len(m.get("content", "")) for m in messages)
    started = time.time()
    last: Exception | None = None
    attempts = max(1, s.llm_retries)
    for attempt in range(1, attempts + 1):
        try:
            content = _send(p, messages)
            obj = parse_json_object(content)
            if validator:
                validator(obj)
            _log(project_id, job_id, p, prompt_name, prompt_version, in_chars, len(content), "ok", attempt, started)
            return obj
        except PrivacyBlocked:
            raise
        except (requests.RequestException,) as exc:
            last = _ollama_error(exc, p) if p.kind == "ollama" else AIError(f"Provider error: {exc}")
            if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code in (401, 403, 404):
                break
        except ValueError as exc:
            last = AIError(f"The model returned output that does not match the required structure: {exc}")
    _log(project_id, job_id, p, prompt_name, prompt_version, in_chars, 0, "failed", attempts, started, str(last))
    raise last or AIError("Unknown model failure")


def _send(p: Provider, messages: list[dict]) -> str:
    s = settings()
    if p.kind == "ollama":
        opts = {"temperature": 0, "num_predict": s.llm_num_predict}
        gpu = p.options.get("num_gpu") if p.options.get("num_gpu") not in (None, "") else (s.ollama_num_gpu or None)
        if gpu not in (None, ""):
            opts["num_gpu"] = int(gpu)
        r = requests.post(p.base_url, json={"model": p.model, "messages": messages, "stream": False, "format": "json", "options": opts}, timeout=s.llm_timeout)
        r.raise_for_status()
        return (r.json().get("message") or {}).get("content", "")
    headers = {"Content-Type": "application/json"}
    if p.api_key_env:
        key = os.getenv(p.api_key_env)
        if not key:
            raise AIError(f"Environment variable {p.api_key_env} (API key) is not set.")
        headers["Authorization"] = f"Bearer {key}"
    url = p.base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    r = requests.post(url, headers=headers, timeout=s.llm_timeout,
                      json={"model": p.model, "messages": messages, "temperature": 0, "response_format": {"type": "json_object"}})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def parse_json_object(content: str) -> dict:
    if not content or not content.strip():
        raise ValueError("empty response")
    c = content.strip()
    if c.startswith("```"):
        c = "\n".join(l for l in c.splitlines() if not l.strip().startswith("```"))
    try:
        obj = json.loads(c)
    except json.JSONDecodeError:
        a, b = c.find("{"), c.rfind("}")
        if a < 0 or b <= a:
            raise ValueError("no JSON object found")
        obj = json.loads(c[a:b + 1])
    if not isinstance(obj, dict):
        raise ValueError("top-level JSON is not an object")
    return obj


def health_check(provider_id: int | None = None) -> dict:
    """Connectivity + model availability check for the settings page."""
    p = resolve(None, provider_id) if provider_id is None else Provider.from_row(db.query_one("SELECT * FROM ai_providers WHERE id=?", (provider_id,)))
    out = {"provider": p.name, "model": p.model, "reachable": False, "model_installed": None, "message": ""}
    try:
        if p.kind == "ollama":
            base = p.base_url.split("/api/")[0]
            r = requests.get(base + "/api/tags", timeout=5)
            r.raise_for_status()
            names = [m.get("name") for m in r.json().get("models", [])]
            out["reachable"] = True
            out["installed_models"] = names
            out["model_installed"] = p.model in names or any(n.split(":")[0] == p.model for n in names)
            out["message"] = "Ollama is running." + ("" if out["model_installed"] else f" Model '{p.model}' is not installed: run `ollama pull {p.model}`.")
        else:
            out["message"] = "OpenAI-compatible providers are checked on first use."
            out["reachable"] = None
    except Exception as exc:
        out["message"] = str(_ollama_error(exc, p)) if p.kind == "ollama" else str(exc)
    return out
