# Credit Bureau API Clients — The Life Shield

Production-ready Python clients for all three major US credit bureaus plus soft-pull monitoring.

## Architecture

```
api/credit_bureaus/
├── __init__.py           # Package exports
├── base.py               # BaseBureauClient ABC + exceptions + audit logging
├── equifax.py            # Equifax (OAuth 2.0)
├── experian.py           # Experian (OAuth 2.0)
├── transunion.py         # TransUnion (HMAC API Key + Secret)
├── isoftpull.py          # iSoftPull (API Key, soft pulls only)
├── client_factory.py     # Factory pattern + Bureau enum + concurrent ops
└── README.md             # This file
```

## Quick Start

```python
from api.credit_bureaus import CreditBureauFactory, Bureau

# Build from environment variables (recommended)
factory = CreditBureauFactory.from_env()

# Pull a report from one bureau
report = factory.pull_report(
    Bureau.EQUIFAX,
    client_id="ls-client-001",
    consumer={
        "ssn": "123-45-6789",
        "dob": "1985-03-17",
        "first_name": "John",
        "last_name": "Smith",
        "address": {
            "line1": "123 Main St",
            "city": "Charlotte",
            "state": "NC",
            "zip": "28201",
        },
    },
)
print(report["score"])  # e.g. 712

# Pull from ALL 3 bureaus concurrently
reports = factory.pull_all_reports("ls-client-001", consumer={...})
# reports["equifax"]["score"], reports["experian"]["score"], reports["transunion"]["score"]

# File a dispute
dispute = factory.file_dispute(
    Bureau.TRANSUNION, "ls-client-001", consumer={...},
    item_id="TU-TL-12345", reason="NOT_MY_ACCOUNT",
    statement="This account does not belong to me.",
)
print(dispute["case_number"])

# Check dispute status
status = factory.get_dispute_status(
    Bureau.TRANSUNION, "ls-client-001",
    case_number=dispute["case_number"], ssn="123-45-6789",
)

# Soft pull (no score impact) via iSoftPull
soft = factory.pull_report(Bureau.ISOFTPULL, "ls-client-001", consumer={...})

# Health check all providers
health = factory.health_check_all()
# {"equifax": True, "experian": True, "transunion": True, "isoftpull": True}
```

## Environment Variables

### Equifax
| Variable | Required | Description |
|---|---|---|
| `EQUIFAX_CLIENT_ID` | Yes | OAuth client ID |
| `EQUIFAX_CLIENT_SECRET` | Yes | OAuth client secret |
| `EQUIFAX_ORG_ID` | Yes | Organisation ID |
| `EQUIFAX_SANDBOX` | No | "true" for sandbox (default: false) |
| `EQUIFAX_BASE_URL` | No | Override API base URL |
| `EQUIFAX_TOKEN_URL` | No | Override token endpoint |
| `EQUIFAX_TIMEOUT` | No | Request timeout in seconds (default: 30) |
| `EQUIFAX_MAX_RETRIES` | No | Max retry attempts (default: 3) |

### Experian
| Variable | Required | Description |
|---|---|---|
| `EXPERIAN_CLIENT_ID` | Yes | OAuth client ID |
| `EXPERIAN_CLIENT_SECRET` | Yes | OAuth client secret |
| `EXPERIAN_SANDBOX` | No | "true" for sandbox |
| `EXPERIAN_BASE_URL` | No | Override API base URL |
| `EXPERIAN_TOKEN_URL` | No | Override token endpoint |
| `EXPERIAN_TIMEOUT` | No | Timeout seconds (default: 30) |
| `EXPERIAN_MAX_RETRIES` | No | Max retries (default: 3) |

### TransUnion
| Variable | Required | Description |
|---|---|---|
| `TRANSUNION_API_KEY` | Yes | API key |
| `TRANSUNION_API_SECRET` | Yes | API secret (HMAC signing) |
| `TRANSUNION_SANDBOX` | No | "true" for sandbox |
| `TRANSUNION_BASE_URL` | No | Override base URL |
| `TRANSUNION_TOKEN_URL` | No | Override token endpoint |
| `TRANSUNION_TIMEOUT` | No | Timeout seconds (default: 30) |
| `TRANSUNION_MAX_RETRIES` | No | Max retries (default: 3) |

### iSoftPull
| Variable | Required | Description |
|---|---|---|
| `ISOFTPULL_API_KEY` | Yes | API key |
| `ISOFTPULL_SANDBOX` | No | "true" for sandbox |
| `ISOFTPULL_BASE_URL` | No | Override base URL |
| `ISOFTPULL_WEBHOOK_URL` | No | Webhook URL for alerts |
| `ISOFTPULL_TIMEOUT` | No | Timeout seconds (default: 15) |
| `ISOFTPULL_MAX_RETRIES` | No | Max retries (default: 3) |

## Features

### Built Into Every Client
- **OAuth/HMAC token management** — auto-refresh before expiry
- **Retry logic** — exponential backoff for 429/5xx responses
- **Rate limiting** — configurable per-minute request cap
- **Structured audit logging** — every API call logged for FCRA compliance
- **Request timeouts** — configurable per-client
- **Response validation** — required field checks with clear error messages
- **SSN sanitisation** — dashes automatically stripped before API calls

### Exception Hierarchy
```
CreditBureauError (base)
├── AuthenticationError    — token/auth failures
├── RateLimitError         — 429 responses
├── ValidationError        — missing/invalid fields
├── DisputeError           — dispute filing failures
└── ReportPullError        — report pull failures
```

### Normalised Response Schema
All bureau reports are normalised to a consistent schema:
```python
{
    "bureau": "equifax",          # Bureau name
    "client_id": "ls-client-001", # Life Shield client ID
    "report_date": "2026-...",    # ISO 8601 UTC timestamp
    "score": 712,                 # Credit score (int or None)
    "tradelines": [...],          # Trade line accounts
    "inquiries": [...],           # Credit inquiries
    "public_records": [...],      # Bankruptcies, judgments, etc.
    "disputes": [...],            # Active disputes
    "collections": [...],         # Collection accounts
    "raw": {...},                 # Full raw API response
}
```

### iSoftPull-Specific Features
- `get_soft_pull()` — zero score impact credit check
- `setup_monitoring()` — webhook-based change alerts (daily/weekly/monthly)
- `get_changes()` — poll for recent credit file changes
- `get_score_history()` — historical snapshots with trend analysis
- `cancel_monitoring()` — remove monitoring subscription

### Factory Concurrent Operations
- `pull_all_reports()` — pull from all 3 bureaus in parallel (ThreadPoolExecutor)
- `file_dispute_all_bureaus()` — file disputes across bureaus in parallel
- `health_check_all()` — check all 4 providers concurrently

## Testing

```bash
# Run credit bureau tests only (avoids project-wide FastAPI deps)
python3 -m pytest tests/credit_bureaus/ -v -o "addopts="

# 131 tests covering:
#   - Authentication (OAuth, HMAC, API key)
#   - Report pulls (success, validation, errors, normalisation)
#   - Dispute filing (success, missing fields, API errors)
#   - Dispute status checks
#   - Change monitoring
#   - Health checks
#   - Rate limiting
#   - Factory pattern (client building, delegation, concurrent ops)
#   - from_env() construction
#   - SSN sanitisation
```

## FCRA Compliance Notes

1. **Permissible Purpose** — Every report pull includes the FCRA-required permissible purpose field
2. **Audit Trail** — All API calls are logged via the `credit_bureau.audit` logger
3. **Dispute Timeline** — 30-day expected resolution date calculated per FCRA requirements
4. **Consumer Statements** — Support for consumer statements on disputes (100-word FCRA limit)
5. **Soft Pulls** — iSoftPull integration ensures monitoring has zero score impact
