# Error Codes

This document provides a complete reference of all error codes used in the Clouisle API.

## Error Code Format

All errors follow the unified response format:

```json
{
  "code": <error_code>,
  "data": <additional_error_data>,
  "msg": "<error_message>"
}
```

The `code` field is the authoritative application-level error code defined in `backend/app/schemas/response.py`. The HTTP status is a transport-level indicator; see [HTTP Status Mapping](#http-status-mapping) below.

## Error Code Ranges

| Range | Category | Description |
|-------|----------|-------------|
| **0** | Success | Operation successful |
| **1000-1999** | General Errors | Unknown error, validation, bad request, internal errors |
| **2000-2999** | Authentication Errors | Login, token, session issues |
| **3000-3999** | Permission Errors | Authorization, access control |
| **4000-4999** | Resource Errors | Not found |
| **5000-5099** | Registration Errors | Account creation, verification issues |
| **5100-5199** | Duplicate Errors | Resource already exists |
| **5200-5299** | Operation Forbidden | Cannot perform action |
| **5300-5399** | Login Security | Account locked, captcha, password policy |
| **5310-5319** | TOTP 2FA | TOTP-specific security errors |
| **5400-5499** | Rate Limiting | Email quota, provider rate limit mapping |
| **6000-6099** | Knowledge Base Errors | KB-specific issues |
| **6100-6199** | Model Errors | LLM model issues |
| **6200-6299** | Agent Errors | Agent-specific issues |
| **6300-6399** | SSO Errors | Single Sign-On issues |

## HTTP Status Mapping

Error responses carry both an HTTP status and an application `code`. The mapping is not 1:1:

| Source | HTTP Status | Response Code |
|--------|-------------|---------------|
| `BusinessError` (default) | 400 | its `code` (e.g. `5002` for username exists) |
| Validation errors (Pydantic) | 422 | `1001` (`VALIDATION_ERROR`) |
| JWT authentication failure | 403 | `2003` (`INVALID_CREDENTIALS`) |
| API key expired / invalid | 401 | `2002` (`TOKEN_EXPIRED`) / `2001` (`INVALID_TOKEN`) |
| No authentication provided | 401 | `2000` (`UNAUTHORIZED`) |
| Permission denied | 403 | `3000` (`PERMISSION_DENIED`) / `3001` (`INSUFFICIENT_PRIVILEGES`) |
| Generic `HTTPException` 400 | 400 | `1000` (`UNKNOWN_ERROR`) |
| Generic `HTTPException` 401 | 401 | `2000` (`UNAUTHORIZED`) |
| Generic `HTTPException` 403 | 403 | `3000` (`PERMISSION_DENIED`) |
| Generic `HTTPException` 404 | 404 | `4000` (`NOT_FOUND`) |

**Important**: Many `BusinessError`s are raised with an explicit `status_code` (e.g. 404 for `NOT_FOUND`, 403 for permission errors, 401 for auth errors). The authoritative `code` field in the body is what you should branch on in client code.

## Success Code

### 0 - Success

**Description**: Operation completed successfully

**HTTP Status**: 200 OK (or 201 Created where a resource is created)

**Example**:
```json
{
  "code": 0,
  "data": {"id": "550e8400-e29b-41d4-a716-446655440000", "name": "Example"},
  "msg": "success"
}
```

## General Errors (1000-1999)

### 1000 - Unknown Error

**Description**: Unexpected or unclassified error

**HTTP Status**: 400 (or 500 when raised by LLM processing)

**Example**:
```json
{
  "code": 1000,
  "data": null,
  "msg": "Unknown error"
}
```

### 1001 - Validation Error

**Description**: Request validation failed (Pydantic validation)

**HTTP Status**: 422 Unprocessable Entity

**Data Structure** (a dictionary of field name → list of messages, **not** an array):
```json
{
  "code": 1001,
  "data": {
    "errors": {
      "email": ["Invalid email address"],
      "password": ["String should have at least 8 characters"]
    }
  },
  "msg": "Validation failed"
}
```

**Common Validation Errors**:
- Invalid email format
- Password too short
- Required field missing
- Invalid data type
- Value out of range

### 1002 - Bad Request

**Description**: Invalid request format or parameters

**HTTP Status**: 400 Bad Request

**Example**:
```json
{
  "code": 1002,
  "data": null,
  "msg": "Bad request"
}
```

### 1003 - Internal Error

**Description**: Unexpected server error

**HTTP Status**: 500 Internal Server Error

**Example**:
```json
{
  "code": 1003,
  "data": null,
  "msg": "Internal server error"
}
```

**Action**: Contact administrator if this persists

### 1004 - Forbidden

**Description**: Operation forbidden at the generic level

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 1004,
  "data": null,
  "msg": "Forbidden"
}
```

## Authentication Errors (2000-2999)

### 2000 - Unauthorized

**Description**: Authentication required but not provided

**HTTP Status**: 401 Unauthorized

**Example**:
```json
{
  "code": 2000,
  "data": null,
  "msg": "Not authenticated"
}
```

**Solution**: Provide valid authentication token or API key

### 2001 - Invalid Token

**Description**: Token is malformed, revoked, or the API key is invalid

**HTTP Status**: 401 Unauthorized

**Example**:
```json
{
  "code": 2001,
  "data": null,
  "msg": "Invalid API key"
}
```

**Also used for**: revoked/blacklisted JWT tokens (`token_revoked`), invalid API key format, and single-session conflicts (`session_expired_new_login`).

### 2002 - Token Expired

**Description**: API key has expired (JWT expiry is reported as `2003` — see below)

**HTTP Status**: 401 Unauthorized

**Example**:
```json
{
  "code": 2002,
  "data": null,
  "msg": "API key expired"
}
```

**Solution**: Create a new API key or login again

### 2003 - Invalid Credentials

**Description**: Wrong username/password, or the JWT token could not be validated / has expired

**HTTP Status**: 403 Forbidden (for JWT decode failures, including expired JWTs)

**Example**:
```json
{
  "code": 2003,
  "data": null,
  "msg": "Could not validate credentials"
}
```

**Solution**: Login again to obtain a fresh token

### 2004 - Inactive User

**Description**: User account has been deactivated or is pending approval

**HTTP Status**: 401 Unauthorized

**Example**:
```json
{
  "code": 2004,
  "data": null,
  "msg": "Account inactive"
}
```

**Solution**: Contact administrator to reactivate account

## Permission Errors (3000-3999)

### 3000 - Permission Denied

**Description**: Insufficient permissions for this operation

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 3000,
  "data": null,
  "msg": "Operation not permitted"
}
```

**Solution**: Request appropriate permissions from administrator

### 3001 - Insufficient Privileges

**Description**: User lacks superuser/admin-level privileges

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 3001,
  "data": null,
  "msg": "Insufficient privileges"
}
```

### 3002 - Not Team Member

**Description**: User is not a member of the required team

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 3002,
  "data": null,
  "msg": "Not a member of this team"
}
```

**Solution**: Join the team or request access

### 3003 - Team Admin Required

**Description**: Operation requires team admin role

**HTTP Status**: 403 Forbidden

### 3004 - Team Owner Required

**Description**: Operation requires team owner role

**HTTP Status**: 403 Forbidden

## Resource Errors (4000-4999)

### 4000 - Not Found

**Description**: Requested resource does not exist

**HTTP Status**: 404 Not Found

**Example**:
```json
{
  "code": 4000,
  "data": null,
  "msg": "Not found"
}
```

**Solution**: Verify resource ID is correct

### 4001 - User Not Found

**Description**: User does not exist

**HTTP Status**: 404 Not Found

**Example**:
```json
{
  "code": 4001,
  "data": null,
  "msg": "User not found"
}
```

### 4002 - Role Not Found

**Description**: Role does not exist

**HTTP Status**: 404 Not Found

### 4003 - Permission Not Found

**Description**: Permission does not exist

**HTTP Status**: 404 Not Found

### 4004 - Team Not Found

**Description**: Team does not exist

**HTTP Status**: 404 Not Found

### 4005 - Team Member Not Found

**Description**: Team member does not exist

**HTTP Status**: 404 Not Found

## Registration Errors (5000-5099)

### 5000 - Registration Disabled

**Description**: User registration is disabled by administrator

**HTTP Status**: 403 Forbidden (registration disabled)

**Solution**: Contact administrator for account creation

### 5001 - Already Exists

**Description**: Resource already exists

**HTTP Status**: 409 Conflict

### 5002 - Username Exists

**Description**: A user with this username already exists

**HTTP Status**: 400 Bad Request (BusinessError default)

**Example**:
```json
{
  "code": 5002,
  "data": null,
  "msg": "Username already exists"
}
```

### 5003 - Email Exists

**Description**: A user with this email already exists

**HTTP Status**: 400 Bad Request

### 5004 - Email Not Verified

**Description**: Email verification is required before login

**HTTP Status**: 403 Forbidden

**Solution**: Check email and click verification link

### 5005 - Verification Code Invalid

**Description**: Email verification code is invalid

### 5006 - Verification Code Expired

**Description**: Email verification code has expired

### 5007 - Email Send Failed

**Description**: Failed to send email

### 5008 - Email Send Too Frequent

**Description**: Email sending too frequently

## Duplicate Resource Errors (5100-5199)

### 5100 - Role Name Exists

**Description**: A role with this name already exists

**HTTP Status**: 400 Bad Request

### 5101 - Permission Code Exists

**Description**: A permission with this code already exists

**HTTP Status**: 400 Bad Request

### 5102 - Team Name Exists

**Description**: A team with this name already exists

**HTTP Status**: 400 Bad Request

### 5103 - Already Team Member

**Description**: User is already a member of this team

**HTTP Status**: 400 Bad Request

### 5104 - Duplicate Name

**Description**: A resource with this name already exists (generic)

**HTTP Status**: 400 Bad Request

## Operation Forbidden Errors (5200-5299)

### 5200 - Cannot Delete System Role

**Description**: System roles cannot be deleted

**HTTP Status**: 403 Forbidden

**Solution**: Only custom roles can be deleted

### 5201 - Cannot Delete Superuser

**Description**: The superuser cannot be deleted

**HTTP Status**: 403 Forbidden

### 5202 - Cannot Delete System Permission

**Description**: System permissions cannot be deleted

### 5203 - Cannot Update System Permission

**Description**: System permissions cannot be updated

### 5204 - Cannot Modify System Role

**Description**: System roles cannot be modified

### 5205 - Cannot Delete Default Team

**Description**: The default team cannot be deleted

### 5206 - Cannot Add As Owner

**Description**: Cannot add user as owner

### 5207 - Cannot Change Owner Role

**Description**: Cannot change the owner's role

### 5208 - Cannot Promote To Owner

**Description**: Cannot promote user to owner

### 5209 - Cannot Remove Owner

**Description**: Cannot remove team owner

**HTTP Status**: 403 Forbidden

**Solution**: Transfer ownership first, then remove

### 5210 - Owner Cannot Leave

**Description**: The owner cannot leave the team

### 5211 - Role In Use

**Description**: The role is currently in use

### 5212 - User Already Active

**Description**: User is already active

### 5213 - User Already Inactive

**Description**: User is already inactive

### 5214 - Cannot Deactivate Superuser

**Description**: Cannot deactivate the superuser

## Login Security Errors (5300-5399)

### 5300 - Account Locked

**Description**: Account locked due to failed login attempts

**HTTP Status**: 403 Forbidden (login flow raises this with the account-locked message key)

**Example**:
```json
{
  "code": 5300,
  "data": {
    "remaining_seconds": 600
  },
  "msg": "Account locked"
}
```

When the failure that triggers the lock is the last allowed attempt, the response carries `lockout_seconds` instead. Failed logins that do **not** lock the account return `2003` (`INVALID_CREDENTIALS`) with `data.remaining_attempts`.

**Solution**: Wait for the lockout period (default 15 minutes) or contact administrator

### 5301 - Too Many Login Attempts

**Description**: Too many login attempts (reserved code; the login flow reports lockout as `5300`)

**Solution**: Wait before retrying

### 5302 - Captcha Required

**Description**: CAPTCHA verification required

**HTTP Status**: 403 Forbidden

### 5303 - Captcha Invalid

**Description**: CAPTCHA verification failed

### 5304 - Password Expired

**Description**: Password has expired

### 5305 - Force Password Change Required

**Description**: Password change is required

### 5306 - Password Min Age Not Met

**Description**: Password minimum age not met

### 5307 - Password Recently Used

**Description**: Password was recently used

## TOTP 2FA Errors (5310-5319)

### 5310 - TOTP Required

**Description**: TOTP verification is required

### 5311 - TOTP Invalid

**Description**: TOTP code is invalid

### 5312 - TOTP Rate Limited

**Description**: Too many failed TOTP attempts; response data contains the lockout seconds

**Example**:
```json
{
  "code": 5312,
  "data": {
    "seconds": 60
  },
  "msg": "Too many failed attempts. Please try again in 60 seconds."
}
```

### 5313 - TOTP Not Enabled

**Description**: TOTP 2FA is not enabled

### 5314 - TOTP Already Enabled

**Description**: TOTP 2FA is already enabled

### 5315 - TOTP Setup Expired

**Description**: TOTP setup session expired

### 5316 - TOTP Setup Required

**Description**: TOTP setup is required

## Rate Limiting Errors (5400-5499)

### 5400 - Rate Limited

**Description**: A rate limit or quota was exceeded. Clouisle does **not** implement per-endpoint request throttling; this code is raised for specific throttled operations:

- **Email sending quota** (admin bulk invite / email dispatch): `data={"limit": 100, "period": "hour"}` (100 emails/hour) or `data={"requested": ..., "remaining": ...}` when the daily quota is insufficient
- **Provider rate-limit mapping**: when a model provider (e.g. OpenAI, DashScope, SiliconFlow) returns HTTP 429/rate-limit errors during knowledge-base document processing, the error is mapped to `5400` (`RATE_LIMITED`)
- **LLM provider rate limits during streaming chat** are surfaced as stream `error` events

**HTTP Status**: 400 (BusinessError default) unless the endpoint raises with a specific status (e.g. 429)

**Example (email quota)**:
```json
{
  "code": 5400,
  "data": {
    "limit": 100,
    "period": "hour"
  },
  "msg": "Email sending rate limit exceeded. Please try again later."
}
```

**Solution**: Wait for the quota window to reset, or raise the limit in site settings / provider quota

## Knowledge Base Errors (6000-6099)

### 6000 - KB Not Found

**Description**: Knowledge base not found

**HTTP Status**: 404 Not Found

### 6001 - KB Name Exists

**Description**: A knowledge base with this name already exists

### 6002 - Document Not Found

**Description**: Document not found

**HTTP Status**: 404 Not Found

### 6003 - Invalid Document Type

**Description**: The uploaded file type is not supported for KB documents

### 6004 - Document Processing Failed

**Description**: Document processing failed

**HTTP Status**: 500 Internal Server Error

### 6005 - Chunk Not Found

**Description**: Chunk not found

### 6006 - Document Processing

**Description**: Document is still processing

## Model Errors (6100-6199)

### 6100 - Model Not Found

**Description**: LLM model not found

**HTTP Status**: 404 Not Found

### 6101 - Team Model Not Found

**Description**: The team's model authorization record not found

**HTTP Status**: 404 Not Found

### 6102 - Team Model Exists

**Description**: The model is already authorized for this team

### 6103 - Model Quota Exceeded

**Description**: Team has exceeded the model's daily/monthly token or request quota

**HTTP Status**: 429 Too Many Requests

**Example**:
```json
{
  "code": 6103,
  "data": {
    "quota_type": "daily_tokens"
  },
  "msg": "Model quota exceeded"
}
```

### 6104 - Model Not Authorized

**Description**: Team not authorized to use this model

**HTTP Status**: 403 Forbidden

### 6105 - Model Vision Not Supported

**Description**: The model does not support vision inputs

## Agent Errors (6200-6299)

### 6200 - Agent Not Found

**Description**: Agent not found

**HTTP Status**: 404 Not Found

### 6201 - Agent Access Denied

**Description**: The current user/API key has no access to this agent

**HTTP Status**: 403 Forbidden

### 6202 - Agent Not Published

**Description**: Agent is not published

**HTTP Status**: 403 Forbidden

### 6210 - Conversation Not Found

**Description**: Conversation not found

**HTTP Status**: 404 Not Found

### 6211 - Message Not Found

**Description**: Message not found

**HTTP Status**: 404 Not Found

## SSO Errors (6300-6399)

### 6300 - SSO Provider Not Found

**Description**: SSO provider not configured

**HTTP Status**: 404 Not Found

### 6301 - SSO Session Expired

**Description**: SSO session expired

**HTTP Status**: 401 Unauthorized

### 6302 - SSO Registration Disabled

**Description**: SSO-based registration is disabled

**HTTP Status**: 403 Forbidden

### 6303 - SSO Authentication Failed

**Description**: SSO authentication failed (e.g. invalid authorization code)

**HTTP Status**: 401 Unauthorized

### 6304 - SSO Invalid Configuration

**Description**: SSO provider configuration is invalid

### 6305 - SSO Provider Name Exists

**Description**: An SSO provider with this name already exists

### 6306 - Password Login Disabled

**Description**: Password login is disabled (SSO-only mode)

## Error Handling Best Practices

### Check Error Codes

```python
response = requests.post(url, json=data, headers=headers)
result = response.json()

if result['code'] == 0:
    # Success
    return result['data']
elif result['code'] in (2000, 2001, 2003):
    # Authentication error - login again and retry
    login_again()
    return retry_request()
else:
    # Other error
    raise Exception(f"Error {result['code']}: {result['msg']}")
```

### Handle Validation Errors

Validation errors use a **field → messages dictionary**, not an array:

```python
if result['code'] == 1001:
    errors = result['data']['errors']
    for field, messages in errors.items():
        print(f"{field}: {', '.join(messages)}")
```

### Retry Logic

```python
def make_request_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)
        result = response.json()

        if result['code'] == 0:
            return result['data']
        elif result['code'] == 6103:
            # Quota exceeded - wait and retry
            time.sleep(30)
        elif result['code'] in (2000, 2001, 2003):
            # Auth error - re-authenticate
            login_again()
        else:
            # Other error - don't retry
            raise Exception(result['msg'])

    raise Exception("Max retries exceeded")
```

## Related Documentation

- [API Overview](./overview.md) - API introduction
- [Authentication](./authentication.md) - Authentication methods
- [Response Format](./response-format.md) - Response structure
- [Error Handling](./error-handling.md) - Error handling patterns

---

**Last Updated**: 2026-08-14
