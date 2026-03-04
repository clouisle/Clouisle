# Environment Variables

This document provides a complete reference of all environment variables used in Clouisle.

## Overview

Environment variables configure:

- **Application settings**: URLs, ports, debug mode
- **Database connections**: PostgreSQL, Redis, Qdrant
- **Security**: Secrets, keys, authentication
- **Email**: SMTP configuration
- **LLM providers**: API keys and settings
- **Storage**: File upload configuration
- **Features**: Enable/disable features

## Configuration File

### .env File

**Location**: Root directory of the project

**Format**:
```bash
# Comments start with #
VARIABLE_NAME=value
ANOTHER_VARIABLE=another_value
```

**Example .env file**:
```bash
# Application
SITE_URL=https://your-domain.com
FRONTEND_URL=https://your-domain.com
DEBUG=false

# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=clouisle
POSTGRES_USER=clouisle
POSTGRES_PASSWORD=secure_password

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=secure_password

# Security
SECRET_KEY=your-secret-key-here
JWT_SECRET=your-jwt-secret-here

# LLM
OPENAI_API_KEY=sk-your-api-key-here
```

## Application Settings

### SITE_URL

**Description**: Public URL of the application

**Required**: Yes

**Default**: None

**Example**:
```bash
SITE_URL=https://clouisle.example.com
```

**Usage**:
- OAuth callback URLs
- Email links
- API documentation
- Webhook URLs

### FRONTEND_URL

**Description**: Frontend application URL

**Required**: Yes

**Default**: Same as SITE_URL

**Example**:
```bash
FRONTEND_URL=https://clouisle.example.com
```

**Usage**:
- CORS configuration
- Redirect URLs
- Email templates

### DEBUG

**Description**: Enable debug mode

**Required**: No

**Default**: `false`

**Values**: `true`, `false`

**Example**:
```bash
DEBUG=false
```

**Warning**: Never enable in production!

### PORT

**Description**: Backend server port

**Required**: No

**Default**: `8000`

**Example**:
```bash
PORT=8000
```

### LOG_LEVEL

**Description**: Logging level

**Required**: No

**Default**: `INFO`

**Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

**Example**:
```bash
LOG_LEVEL=INFO
```

## Database Configuration

### PostgreSQL

#### POSTGRES_HOST

**Description**: PostgreSQL server hostname

**Required**: Yes

**Default**: `localhost`

**Example**:
```bash
POSTGRES_HOST=postgres
```

#### POSTGRES_PORT

**Description**: PostgreSQL server port

**Required**: No

**Default**: `5432`

**Example**:
```bash
POSTGRES_PORT=5432
```

#### POSTGRES_DB

**Description**: Database name

**Required**: Yes

**Default**: None

**Example**:
```bash
POSTGRES_DB=clouisle
```

#### POSTGRES_USER

**Description**: Database username

**Required**: Yes

**Default**: None

**Example**:
```bash
POSTGRES_USER=clouisle
```

#### POSTGRES_PASSWORD

**Description**: Database password

**Required**: Yes

**Default**: None

**Example**:
```bash
POSTGRES_PASSWORD=secure_password_here
```

**Security**: Use strong password, never commit to git

#### DATABASE_URL

**Description**: Complete database connection URL

**Required**: Alternative to individual settings

**Format**: `postgresql://user:password@host:port/database`

**Example**:
```bash
DATABASE_URL=postgresql://clouisle:password@localhost:5432/clouisle
```

### Redis

#### REDIS_HOST

**Description**: Redis server hostname

**Required**: Yes

**Default**: `localhost`

**Example**:
```bash
REDIS_HOST=redis
```

#### REDIS_PORT

**Description**: Redis server port

**Required**: No

**Default**: `6379`

**Example**:
```bash
REDIS_PORT=6379
```

#### REDIS_PASSWORD

**Description**: Redis password

**Required**: No (but recommended)

**Default**: None

**Example**:
```bash
REDIS_PASSWORD=secure_password_here
```

#### REDIS_DB

**Description**: Redis database number

**Required**: No

**Default**: `0`

**Example**:
```bash
REDIS_DB=0
```

#### REDIS_URL

**Description**: Complete Redis connection URL

**Required**: Alternative to individual settings

**Format**: `redis://[:password@]host:port/db`

**Example**:
```bash
REDIS_URL=redis://:password@localhost:6379/0
```

### Qdrant (Vector Database)

#### QDRANT_HOST

**Description**: Qdrant server hostname

**Required**: Yes

**Default**: `localhost`

**Example**:
```bash
QDRANT_HOST=qdrant
```

#### QDRANT_PORT

**Description**: Qdrant server port

**Required**: No

**Default**: `6333`

**Example**:
```bash
QDRANT_PORT=6333
```

#### QDRANT_API_KEY

**Description**: Qdrant API key (if authentication enabled)

**Required**: No

**Default**: None

**Example**:
```bash
QDRANT_API_KEY=your-api-key-here
```

#### QDRANT_URL

**Description**: Complete Qdrant connection URL

**Required**: Alternative to individual settings

**Format**: `http://host:port`

**Example**:
```bash
QDRANT_URL=http://qdrant:6333
```

## Security Settings

### SECRET_KEY

**Description**: Application secret key for encryption

**Required**: Yes

**Default**: None

**Example**:
```bash
SECRET_KEY=your-very-secure-random-key-here
```

**Generate**:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Security**:
- Must be random and unique
- Never commit to git
- Change if compromised

### JWT_SECRET

**Description**: JWT token signing secret

**Required**: Yes

**Default**: None

**Example**:
```bash
JWT_SECRET=your-jwt-secret-key-here
```

**Generate**:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Security**:
- Must be different from SECRET_KEY
- Never commit to git
- Changing invalidates all tokens

### JWT_ALGORITHM

**Description**: JWT signing algorithm

**Required**: No

**Default**: `HS256`

**Values**: `HS256`, `HS384`, `HS512`

**Example**:
```bash
JWT_ALGORITHM=HS256
```

### JWT_EXPIRATION

**Description**: JWT token expiration time in seconds

**Required**: No

**Default**: `1800` (30 minutes)

**Example**:
```bash
JWT_EXPIRATION=1800
```

### CORS_ORIGINS

**Description**: Allowed CORS origins (comma-separated)

**Required**: No

**Default**: `*` (all origins)

**Example**:
```bash
CORS_ORIGINS=https://clouisle.example.com,https://app.example.com
```

**Production**: Always specify exact origins

## Email Configuration

### SMTP_HOST

**Description**: SMTP server hostname

**Required**: For email features

**Default**: None

**Example**:
```bash
SMTP_HOST=smtp.gmail.com
```

### SMTP_PORT

**Description**: SMTP server port

**Required**: No

**Default**: `587`

**Common ports**:
- `587`: TLS (recommended)
- `465`: SSL
- `25`: Unencrypted (not recommended)

**Example**:
```bash
SMTP_PORT=587
```

### SMTP_USER

**Description**: SMTP username

**Required**: For email features

**Default**: None

**Example**:
```bash
SMTP_USER=your-email@gmail.com
```

### SMTP_PASSWORD

**Description**: SMTP password or app password

**Required**: For email features

**Default**: None

**Example**:
```bash
SMTP_PASSWORD=your-app-password
```

**Gmail**: Use app-specific password

### SMTP_FROM_EMAIL

**Description**: Default sender email address

**Required**: No

**Default**: Same as SMTP_USER

**Example**:
```bash
SMTP_FROM_EMAIL=noreply@example.com
```

### SMTP_FROM_NAME

**Description**: Default sender name

**Required**: No

**Default**: `Clouisle`

**Example**:
```bash
SMTP_FROM_NAME=Clouisle Platform
```

### SMTP_TLS

**Description**: Enable TLS encryption

**Required**: No

**Default**: `true`

**Values**: `true`, `false`

**Example**:
```bash
SMTP_TLS=true
```

## LLM Provider Configuration

### OpenAI

#### OPENAI_API_KEY

**Description**: OpenAI API key

**Required**: For OpenAI models

**Default**: None

**Example**:
```bash
OPENAI_API_KEY=sk-your-api-key-here
```

**Get key**: https://platform.openai.com/api-keys

#### OPENAI_API_BASE

**Description**: OpenAI API base URL

**Required**: No

**Default**: `https://api.openai.com/v1`

**Example**:
```bash
OPENAI_API_BASE=https://api.openai.com/v1
```

**Use case**: Custom proxy or Azure OpenAI

#### OPENAI_ORGANIZATION

**Description**: OpenAI organization ID

**Required**: No

**Default**: None

**Example**:
```bash
OPENAI_ORGANIZATION=org-your-org-id
```

### Anthropic

#### ANTHROPIC_API_KEY

**Description**: Anthropic API key

**Required**: For Claude models

**Default**: None

**Example**:
```bash
ANTHROPIC_API_KEY=sk-ant-your-api-key-here
```

### Azure OpenAI

#### AZURE_OPENAI_API_KEY

**Description**: Azure OpenAI API key

**Required**: For Azure OpenAI

**Default**: None

**Example**:
```bash
AZURE_OPENAI_API_KEY=your-azure-key-here
```

#### AZURE_OPENAI_ENDPOINT

**Description**: Azure OpenAI endpoint URL

**Required**: For Azure OpenAI

**Default**: None

**Example**:
```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
```

#### AZURE_OPENAI_API_VERSION

**Description**: Azure OpenAI API version

**Required**: No

**Default**: `2023-05-15`

**Example**:
```bash
AZURE_OPENAI_API_VERSION=2023-05-15
```

## Storage Configuration

### UPLOAD_DIR

**Description**: Directory for file uploads

**Required**: No

**Default**: `./uploads`

**Example**:
```bash
UPLOAD_DIR=/var/lib/clouisle/uploads
```

### MAX_UPLOAD_SIZE

**Description**: Maximum file upload size in bytes

**Required**: No

**Default**: `104857600` (100 MB)

**Example**:
```bash
MAX_UPLOAD_SIZE=104857600
```

**Convert**:
- 10 MB = 10485760
- 50 MB = 52428800
- 100 MB = 104857600

### STORAGE_BACKEND

**Description**: Storage backend type

**Required**: No

**Default**: `local`

**Values**: `local`, `s3`, `azure`, `gcs`

**Example**:
```bash
STORAGE_BACKEND=local
```

### S3 Configuration

#### AWS_ACCESS_KEY_ID

**Description**: AWS access key ID

**Required**: For S3 storage

**Default**: None

**Example**:
```bash
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
```

#### AWS_SECRET_ACCESS_KEY

**Description**: AWS secret access key

**Required**: For S3 storage

**Default**: None

**Example**:
```bash
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

#### AWS_S3_BUCKET

**Description**: S3 bucket name

**Required**: For S3 storage

**Default**: None

**Example**:
```bash
AWS_S3_BUCKET=clouisle-uploads
```

#### AWS_REGION

**Description**: AWS region

**Required**: No

**Default**: `us-east-1`

**Example**:
```bash
AWS_REGION=us-west-2
```

## Feature Flags

### ENABLE_REGISTRATION

**Description**: Allow user registration

**Required**: No

**Default**: `true`

**Values**: `true`, `false`

**Example**:
```bash
ENABLE_REGISTRATION=true
```

### ENABLE_SSO

**Description**: Enable SSO authentication

**Required**: No

**Default**: `false`

**Values**: `true`, `false`

**Example**:
```bash
ENABLE_SSO=true
```

### ENABLE_EMAIL_VERIFICATION

**Description**: Require email verification

**Required**: No

**Default**: `true`

**Values**: `true`, `false`

**Example**:
```bash
ENABLE_EMAIL_VERIFICATION=true
```

### ENABLE_2FA

**Description**: Enable two-factor authentication

**Required**: No

**Default**: `false`

**Values**: `true`, `false`

**Example**:
```bash
ENABLE_2FA=true
```

### ENABLE_AUDIT_LOG

**Description**: Enable audit logging

**Required**: No

**Default**: `true`

**Values**: `true`, `false`

**Example**:
```bash
ENABLE_AUDIT_LOG=true
```

## Celery Configuration

### CELERY_BROKER_URL

**Description**: Celery broker URL (usually Redis)

**Required**: For background tasks

**Default**: Same as REDIS_URL

**Example**:
```bash
CELERY_BROKER_URL=redis://:password@localhost:6379/0
```

### CELERY_RESULT_BACKEND

**Description**: Celery result backend URL

**Required**: No

**Default**: Same as CELERY_BROKER_URL

**Example**:
```bash
CELERY_RESULT_BACKEND=redis://:password@localhost:6379/0
```

## Monitoring and Logging

### SENTRY_DSN

**Description**: Sentry error tracking DSN

**Required**: No

**Default**: None

**Example**:
```bash
SENTRY_DSN=https://your-key@sentry.io/your-project
```

### SENTRY_ENVIRONMENT

**Description**: Sentry environment name

**Required**: No

**Default**: `production`

**Example**:
```bash
SENTRY_ENVIRONMENT=production
```

## Best Practices

### Security

**✅ Do:**
- Use strong, random secrets
- Never commit secrets to git
- Use different secrets per environment
- Rotate secrets regularly
- Use environment-specific values
- Encrypt secrets at rest

**❌ Don't:**
- Use default or weak secrets
- Commit .env to version control
- Share secrets via email/chat
- Use same secrets everywhere
- Hardcode secrets in code

### Organization

**✅ Do:**
- Group related variables
- Use clear, descriptive names
- Document custom variables
- Use .env.example template
- Validate required variables

**❌ Don't:**
- Mix unrelated variables
- Use cryptic names
- Skip documentation
- Forget to update template

### Management

**✅ Do:**
- Use secret management tools
- Backup .env files securely
- Test configuration changes
- Document dependencies
- Version control .env.example

**❌ Don't:**
- Store secrets in plain text
- Forget to backup
- Change without testing
- Skip documentation

## Validation

### Check Configuration

**Validate environment variables:**

```bash
# Backend
cd backend
python -m app.scripts.check_config

# Expected output
✓ All required environment variables are set
✓ Database connection successful
✓ Redis connection successful
✓ Qdrant connection successful
```

### Common Issues

**Missing required variables:**
```
Error: POSTGRES_PASSWORD is not set
```

**Solution**: Set the variable in .env

**Invalid format:**
```
Error: POSTGRES_PORT must be an integer
```

**Solution**: Check variable format

**Connection failed:**
```
Error: Cannot connect to database
```

**Solution**: Verify host, port, credentials

## Related Documentation

- [Docker Deployment](./docker-compose.md) - Docker setup
- [Kubernetes Deployment](./kubernetes.md) - K8s setup
- [Security Best Practices](../best-practices/security.md) - Security guide
- [Troubleshooting](./troubleshooting.md) - Common issues

---

**Last Updated**: 2026-02-11
