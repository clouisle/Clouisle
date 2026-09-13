# Authentication & Login API

This document describes the API endpoints for user authentication, registration, password recovery, and email verification.

**Base URL**: `/api/v1`

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/captcha` | Generate a new click-based human verification challenge |
| `POST` | `/api/v1/captcha/click` | Validate user click interactions and obtain a one-time captcha proof token |
| `POST` | `/api/v1/login/access-token` | Authenticate with username/email and password to obtain JWT access token |
| `POST` | `/api/v1/login/verify-totp` | Complete two-factor authentication challenge using a temporary token |
| `POST` | `/api/v1/logout` | Invalidate current user session and blacklist token |
| `POST` | `/api/v1/register` | Register a new user account |
| `POST` | `/api/v1/send-verification` | Send an email verification code for registration or email binding |
| `POST` | `/api/v1/verify-email` | Verify email address using a 6-digit verification code |
| `GET` | `/api/v1/verify` | Verify email address using an email verification token link |
| `POST` | `/api/v1/resend-verification` | Resend verification email |
| `POST` | `/api/v1/forgot-password` | Request a password reset verification code or link |
| `POST` | `/api/v1/reset-password` | Reset password using a valid reset token or code |

---

## 1. Captcha Verification

### Get Captcha Challenge

```http
GET /api/v1/captcha HTTP/1.1
```

#### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "captcha_id": "captcha-uuid-1234",
    "challenge": {
      "target_text": "Please click the red circle",
      "image": "data:image/png;base64,..."
    }
  },
  "msg": "success"
}
```

### Complete Captcha Click

```http
POST /api/v1/captcha/click HTTP/1.1
Content-Type: application/json

{
  "captcha_id": "captcha-uuid-1234",
  "challenge": "challenge-token",
  "clicked_option": 2,
  "elapsed_ms": 1420,
  "pointer": [{"x": 120, "y": 85, "t": 1400}]
}
```

#### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "captcha_id": "captcha-uuid-1234",
    "captcha_token": "proof-token-string"
  },
  "msg": "success"
}
```

---

## 2. Login & Token Exchange

### Password Login

```http
POST /api/v1/login/access-token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=alice@example.com&password=SecurePassword123!&captcha_id=captcha-uuid&captcha_token=proof-token
```

#### Response (`200 OK` - Direct Login)

```json
{
  "code": 0,
  "data": {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "expires_in": 11520,
    "user": {
      "id": "user-uuid",
      "email": "alice@example.com",
      "username": "alice",
      "is_superuser": false,
      "totp_enabled": false
    }
  },
  "msg": "Login successful"
}
```

#### Response (`200 OK` - 2FA Required)

If TOTP 2FA is enabled on the account, a `temp_token` is returned instead of the standard `access_token`:

```json
{
  "code": 0,
  "data": {
    "temp_token": "temp-2fa-token",
    "totp_required": true,
    "expires_in": 300
  },
  "msg": "Two-factor authentication required"
}
```

### Verify TOTP Login Challenge

```http
POST /api/v1/login/verify-totp HTTP/1.1
Content-Type: application/x-www-form-urlencoded

temp_token=temp-2fa-token&code=123456
```

Returns standard `access_token` on success.

---

## 3. User Registration

```http
POST /api/v1/register HTTP/1.1
Content-Type: application/json

{
  "username": "bob",
  "email": "bob@example.com",
  "password": "StrongPassword123!",
  "verification_code": "654321"
}
```

---

## 4. Password Recovery

### Request Password Reset

```http
POST /api/v1/forgot-password HTTP/1.1
Content-Type: application/json

{
  "email": "bob@example.com",
  "captcha_id": "captcha-uuid",
  "captcha_token": "proof-token"
}
```

### Confirm Password Reset

```http
POST /api/v1/reset-password HTTP/1.1
Content-Type: application/json

{
  "token": "reset-token-received-via-email",
  "new_password": "NewStrongPassword123!"
}
```
