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

## Error Code Ranges

| Range | Category | Description |
|-------|----------|-------------|
| **0** | Success | Operation successful |
| **1000-1999** | General Errors | Validation, bad request, internal errors |
| **2000-2999** | Authentication Errors | Login, token, session issues |
| **3000-3999** | Permission Errors | Authorization, access control |
| **4000-4999** | Resource Errors | Not found, conflicts |
| **5000-5099** | Registration Errors | Account creation issues |
| **5100-5199** | Duplicate Errors | Resource already exists |
| **5200-5299** | Operation Forbidden | Cannot perform action |
| **5300-5399** | Login Security | Account locked, captcha |
| **5400-5499** | Rate Limiting | Too many requests |
| **6000-6099** | Knowledge Base Errors | KB-specific issues |
| **6100-6199** | Model Errors | LLM model issues |
| **6200-6299** | Agent Errors | Agent-specific issues |
| **6300-6399** | SSO Errors | Single Sign-On issues |

## Success Code

### 0 - Success

**Description**: Operation completed successfully

**HTTP Status**: 200 OK or 201 Created

**Example**:
```json
{
  "code": 0,
  "data": {"id": "123", "name": "Example"},
  "msg": "success"
}
```

## General Errors (1000-1999)

### 1000 - Bad Request

**Description**: Invalid request format or parameters

**HTTP Status**: 400 Bad Request

**Example**:
```json
{
  "code": 1000,
  "data": null,
  "msg": "Bad request: Invalid parameters"
}
```

### 1001 - Validation Error

**Description**: Request validation failed

**HTTP Status**: 400 Bad Request

**Data Structure**:
```json
{
  "code": 1001,
  "data": {
    "errors": [
      {"field": "email", "message": "Invalid email format"},
      {"field": "password", "message": "Password too short"}
    ]
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

### 1002 - Internal Server Error

**Description**: Unexpected server error

**HTTP Status**: 500 Internal Server Error

**Example**:
```json
{
  "code": 1002,
  "data": null,
  "msg": "Internal server error"
}
```

**Action**: Contact administrator if this persists

## Authentication Errors (2000-2999)

### 2000 - Unauthorized

**Description**: Authentication required but not provided

**HTTP Status**: 401 Unauthorized

**Example**:
```json
{
  "code": 2000,
  "data": null,
  "msg": "Unauthorized: Authentication required"
}
```

**Solution**: Provide valid authentication token or API key

### 2001 - Invalid Credentials

**Description**: Wrong username or password

**HTTP Status**: 401 Unauthorized

**Example**:
```json
{
  "code": 2001,
  "data": null,
  "msg": "Invalid credentials"
}
```

**Solution**: Check username and password

### 2002 - Token Expired

**Description**: JWT token or API key has expired

**HTTP Status**: 401 Unauthorized

**Example**:
```json
{
  "code": 2002,
  "data": {
    "expired_at": "2026-02-11T10:00:00Z"
  },
  "msg": "Token expired"
}
```

**Solution**: Refresh token or login again

### 2003 - Invalid Token

**Description**: Malformed or invalid authentication token

**HTTP Status**: 401 Unauthorized

**Example**:
```json
{
  "code": 2003,
  "data": null,
  "msg": "Invalid token"
}
```

**Solution**: Provide valid token format

### 2004 - Account Inactive

**Description**: User account has been deactivated

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

### 2005 - Account Locked

**Description**: Account locked due to security reasons

**HTTP Status**: 401 Unauthorized

**Example**:
```json
{
  "code": 2005,
  "data": {
    "locked_until": "2026-02-11T10:15:00Z",
    "reason": "Too many failed login attempts"
  },
  "msg": "Account locked"
}
```

**Solution**: Wait for unlock time or contact administrator

## Permission Errors (3000-3999)

### 3000 - Permission Denied

**Description**: Insufficient permissions for this operation

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 3000,
  "data": {
    "required_permission": "agent:delete"
  },
  "msg": "Permission denied"
}
```

**Solution**: Request appropriate permissions from administrator

### 3001 - Not Team Member

**Description**: User is not a member of the required team

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 3001,
  "data": {
    "team_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "msg": "Not a member of this team"
}
```

**Solution**: Join the team or request access

## Resource Errors (4000-4999)

### 4000 - Not Found

**Description**: Requested resource does not exist

**HTTP Status**: 404 Not Found

**Example**:
```json
{
  "code": 4000,
  "data": {
    "resource_type": "agent",
    "resource_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "msg": "Agent not found"
}
```

**Solution**: Verify resource ID is correct

### 4001 - Resource Conflict

**Description**: Resource already exists or conflicts with existing resource

**HTTP Status**: 409 Conflict

**Example**:
```json
{
  "code": 4001,
  "data": {
    "conflicting_field": "name"
  },
  "msg": "Resource with this name already exists"
}
```

**Solution**: Use different name or update existing resource

## Registration Errors (5000-5099)

### 5000 - Registration Disabled

**Description**: User registration is disabled by administrator

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 5000,
  "data": null,
  "msg": "Registration is disabled"
}
```

**Solution**: Contact administrator for account creation

### 5001 - User Already Exists

**Description**: User with this email or username already exists

**HTTP Status**: 409 Conflict

**Example**:
```json
{
  "code": 5001,
  "data": {
    "field": "email"
  },
  "msg": "User with this email already exists"
}
```

**Solution**: Use different email or login to existing account

### 5002 - Email Verification Required

**Description**: Email verification is required before login

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 5002,
  "data": {
    "email": "user@example.com"
  },
  "msg": "Email verification required"
}
```

**Solution**: Check email and click verification link

## Duplicate Resource Errors (5100-5199)

### 5100 - Name Already Exists

**Description**: Resource with this name already exists

**HTTP Status**: 409 Conflict

**Example**:
```json
{
  "code": 5100,
  "data": {
    "name": "My Agent"
  },
  "msg": "Agent with this name already exists"
}
```

**Solution**: Choose a different name

### 5101 - Already Team Member

**Description**: User is already a member of this team

**HTTP Status**: 409 Conflict

**Example**:
```json
{
  "code": 5101,
  "data": null,
  "msg": "User is already a team member"
}
```

**Solution**: No action needed

## Operation Forbidden Errors (5200-5299)

### 5200 - Cannot Delete System Role

**Description**: System roles cannot be deleted

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 5200,
  "data": {
    "role_name": "Admin"
  },
  "msg": "Cannot delete system role"
}
```

**Solution**: Only custom roles can be deleted

### 5201 - Cannot Remove Owner

**Description**: Cannot remove team owner

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 5201,
  "data": null,
  "msg": "Cannot remove team owner"
}
```

**Solution**: Transfer ownership first, then remove

## Login Security Errors (5300-5399)

### 5300 - Account Locked

**Description**: Account locked due to failed login attempts

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 5300,
  "data": {
    "locked_until": "2026-02-11T10:15:00Z",
    "attempts": 5
  },
  "msg": "Account locked due to too many failed attempts"
}
```

**Solution**: Wait 15 minutes or contact administrator

### 5301 - Too Many Attempts

**Description**: Too many login attempts

**HTTP Status**: 429 Too Many Requests

**Example**:
```json
{
  "code": 5301,
  "data": {
    "retry_after": 60
  },
  "msg": "Too many login attempts. Try again in 60 seconds"
}
```

**Solution**: Wait before retrying

### 5302 - Captcha Required

**Description**: CAPTCHA verification required

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 5302,
  "data": {
    "captcha_url": "/api/v1/captcha"
  },
  "msg": "CAPTCHA verification required"
}
```

**Solution**: Complete CAPTCHA challenge

## Rate Limiting Errors (5400-5499)

### 5400 - Rate Limit Exceeded

**Description**: Too many requests in time window

**HTTP Status**: 429 Too Many Requests

**Example**:
```json
{
  "code": 5400,
  "data": {
    "retry_after": 3600,
    "limit": 1000,
    "remaining": 0,
    "reset": 1644580800
  },
  "msg": "Rate limit exceeded. Retry after 3600 seconds"
}
```

**Solution**: Wait for rate limit reset

## Knowledge Base Errors (6000-6099)

### 6000 - KB Not Found

**Description**: Knowledge base not found

**HTTP Status**: 404 Not Found

**Example**:
```json
{
  "code": 6000,
  "data": {
    "kb_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "msg": "Knowledge base not found"
}
```

### 6001 - Document Processing Failed

**Description**: Document processing failed

**HTTP Status**: 500 Internal Server Error

**Example**:
```json
{
  "code": 6001,
  "data": {
    "document_id": "550e8400-e29b-41d4-a716-446655440000",
    "error": "Unsupported file format"
  },
  "msg": "Document processing failed"
}
```

### 6002 - Embedding Failed

**Description**: Failed to generate embeddings

**HTTP Status**: 500 Internal Server Error

**Example**:
```json
{
  "code": 6002,
  "data": {
    "error": "Embedding model unavailable"
  },
  "msg": "Embedding generation failed"
}
```

## Model Errors (6100-6199)

### 6100 - Model Not Found

**Description**: LLM model not found

**HTTP Status**: 404 Not Found

**Example**:
```json
{
  "code": 6100,
  "data": {
    "model_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "msg": "Model not found"
}
```

### 6101 - Model Not Authorized

**Description**: Team not authorized to use this model

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 6101,
  "data": {
    "model_name": "gpt-4"
  },
  "msg": "Team not authorized to use this model"
}
```

### 6102 - Model API Error

**Description**: Error calling LLM provider API

**HTTP Status**: 500 Internal Server Error

**Example**:
```json
{
  "code": 6102,
  "data": {
    "provider": "openai",
    "error": "API key invalid"
  },
  "msg": "Model API error"
}
```

## Agent Errors (6200-6299)

### 6200 - Agent Not Found

**Description**: Agent not found

**HTTP Status**: 404 Not Found

**Example**:
```json
{
  "code": 6200,
  "data": {
    "agent_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "msg": "Agent not found"
}
```

### 6201 - Agent Not Published

**Description**: Agent is not published

**HTTP Status**: 403 Forbidden

**Example**:
```json
{
  "code": 6201,
  "data": null,
  "msg": "Agent is not published"
}
```

## SSO Errors (6300-6399)

### 6300 - SSO Provider Not Found

**Description**: SSO provider not configured

**HTTP Status**: 404 Not Found

**Example**:
```json
{
  "code": 6300,
  "data": {
    "provider_name": "github"
  },
  "msg": "SSO provider not found"
}
```

### 6301 - SSO Authentication Failed

**Description**: SSO authentication failed

**HTTP Status**: 401 Unauthorized

**Example**:
```json
{
  "code": 6301,
  "data": {
    "provider": "github",
    "error": "Invalid authorization code"
  },
  "msg": "SSO authentication failed"
}
```

### 6302 - SSO Session Expired

**Description**: SSO session expired

**HTTP Status**: 401 Unauthorized

**Example**:
```json
{
  "code": 6302,
  "data": null,
  "msg": "SSO session expired"
}
```

## Error Handling Best Practices

### Check Error Codes

```python
response = requests.post(url, json=data, headers=headers)
result = response.json()

if result['code'] == 0:
    # Success
    return result['data']
elif result['code'] == 2002:
    # Token expired - refresh and retry
    refresh_token()
    return retry_request()
elif result['code'] == 5400:
    # Rate limit - wait and retry
    time.sleep(result['data']['retry_after'])
    return retry_request()
else:
    # Other error
    raise Exception(f"Error {result['code']}: {result['msg']}")
```

### Handle Validation Errors

```python
if result['code'] == 1001:
    errors = result['data']['errors']
    for error in errors:
        print(f"{error['field']}: {error['message']}")
```

### Retry Logic

```python
def make_request_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)
        result = response.json()

        if result['code'] == 0:
            return result['data']
        elif result['code'] == 5400:
            # Rate limit - wait and retry
            time.sleep(result['data']['retry_after'])
        elif result['code'] in [2002, 2003]:
            # Auth error - refresh token
            refresh_token()
        else:
            # Other error - don't retry
            raise Exception(result['msg'])

    raise Exception("Max retries exceeded")
```

## Related Documentation

- [API Overview](./overview.md) - API introduction
- [Authentication](./authentication.md) - Authentication methods
- [Response Format](./response-format.md) - Response structure
- [Rate Limiting](./rate-limiting.md) - Rate limit details

---

**Last Updated**: 2026-02-11
