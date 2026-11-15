"""Local provider response records for debugging; never used as recommendation data."""
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import threading
from uuid import uuid4

from trojanbites_extract.settings import get_settings

_lock = threading.Lock()
logger = logging.getLogger(__name__)
_SENSITIVE = {'authorization', 'x-goog-api-key', 'api_key', 'apikey', 'openai_api_key',
              'google_maps_api_key', 'gemini_api_key', 'anthropic_api_key', 'access_token', 'refresh_token'}


def _redact(value, secrets):
    if isinstance(value, dict):
        return {key: '[REDACTED]' if key.lower() in _SENSITIVE else _redact(item,secrets) for key,item in value.items()}
    if isinstance(value, list): return [_redact(item,secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret: value=value.replace(secret,'[REDACTED]')
        return value
    return value


def record_response(provider, operation, response, *, model=None):
    """Save success/error response bodies; do not record request headers, keys or prompts."""
    settings=get_settings()
    if not settings.provider_records_enabled: return
    try:
        try: body=response.json()
        except ValueError: body={'non_json_body':response.text}
        now=datetime.now(timezone.utc)
        secrets=[getattr(settings,key,None) for key in ['openai_api_key','google_maps_api_key','gemini_api_key','anthropic_api_key']]
        record=_redact({'record_id':str(uuid4()),'recorded_at':now.isoformat(),'provider':provider,
            'operation':operation,'model':model,'http_status':response.status_code,
            'provider_request_id':response.headers.get('x-request-id') or response.headers.get('x-goog-request-id'),
            'response':body},secrets)
        directory=Path(settings.provider_records_dir)
        if not directory.is_absolute(): directory=settings.root/directory
        with _lock:
            directory.mkdir(parents=True,exist_ok=True,mode=0o700)
            path=directory/f'{now:%Y-%m-%d}.jsonl'
            fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
            with os.fdopen(fd,'a',encoding='utf-8') as output:
                output.write(json.dumps(record,ensure_ascii=False)+'\n')
    except (OSError,ValueError,TypeError):
        # Logging must never cause a meal request to fail.
        logger.warning('Could not save a local provider response record.')
