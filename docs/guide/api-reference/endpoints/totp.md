# Two-Factor Authentication (TOTP) API

The TOTP API provides endpoints for setting up, enabling, verifying, and disabling Time-based One-Time Password (TOTP) two-factor authentication (2FA) for user accounts.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/totp/setup` | Generate a TOTP secret, QR code, and backup codes for 2FA binding |
| `POST` | `/api/v1/totp/enable` | Verify code and permanently activate TOTP 2FA |
| `POST` | `/api/v1/totp/disable` | Disable TOTP 2FA for the account |
| `GET` | `/api/v1/totp/status` | Get TOTP 2FA status and remaining backup code count |
| `POST` | `/api/v1/totp/regenerate-backup-codes` | Regenerate backup codes after verifying a TOTP code |

> **Note**: The two-factor login challenge is completed by `POST /api/v1/login/verify-totp` (an `application/x-www-form-urlencoded` request with `temp_token` and `code`). It is documented in the [Authentication API](./auth.md).

---

## Setup TOTP

Generate a TOTP secret, an authenticator QR code, and a set of backup codes. This does not enable 2FA yet — confirm a code via **Enable TOTP** first.

```http
POST /api/v1/totp/setup HTTP/1.1
Authorization: Bearer <token>
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "secret": "JBSWY3DPEHPK3PXP",
    "qr_code": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...",
    "backup_codes": [
      "1234-5678",
      "8765-4321",
      "2468-1357"
    ]
  }
}
```

`qr_code` is a base64 `data:image/png;base64,...` URL. `backup_codes` contains 10 one-time codes in `XXXX-XXXX` format; store them securely, as they are only returned here (or from **Regenerate Backup Codes**).

---

## Enable TOTP

Verify the initial 6-digit verification code from your authenticator app to enable 2FA.

```http
POST /api/v1/totp/enable HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "code": "123456"
}
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "msg": "Two-factor authentication enabled successfully",
  "data": null
}
```

---

## Disable TOTP

Disable TOTP 2FA for the authenticated user. Requires the current account password and either a valid TOTP code or a recovery backup code.

```http
POST /api/v1/totp/disable HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "password": "CurrentPassword123!",
  "code": "123456",
  "is_backup_code": false
}
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "msg": "Two-factor authentication disabled successfully",
  "data": null
}
```

---

## Get TOTP Status

Return whether TOTP 2FA is enabled for the authenticated user, when it was enabled, and how many backup codes remain unused.

```http
GET /api/v1/totp/status HTTP/1.1
Authorization: Bearer <token>
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "enabled": true,
    "enabled_at": "2026-09-26T10:15:00+00:00",
    "remaining_backup_codes": 10
  }
}
```

`enabled_at` is `null` when TOTP has never been enabled, and `remaining_backup_codes` is `0` when no backup codes are stored.

---

## Regenerate Backup Codes

Replace all existing backup codes with a fresh set of 10. Requires a currently valid TOTP code.

```http
POST /api/v1/totp/regenerate-backup-codes HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "code": "123456"
}
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "msg": "Backup codes regenerated successfully",
  "data": {
    "codes": [
      "1234-5678",
      "8765-4321",
      "2468-1357"
    ]
  }
}
```

