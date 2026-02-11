# Troubleshooting

This guide helps you diagnose and resolve common issues in Clouisle.

## Overview

This troubleshooting guide covers:

- **Installation issues**: Setup and deployment problems
- **Connection errors**: Database, Redis, API connectivity
- **Authentication problems**: Login, SSO, token issues
- **Performance issues**: Slow responses, timeouts
- **Feature problems**: Agents, workflows, knowledge bases
- **Error messages**: Common errors and solutions

## Quick Diagnostics

### Health Check

**Check system health:**

```bash
# Backend health
curl http://localhost:8000/health

# Expected response
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "qdrant": "connected",
  "version": "1.0.0"
}
```

### Service Status

**Check all services:**

```bash
# Docker Compose
docker compose ps

# Expected output
NAME                STATUS
clouisle-backend    Up
clouisle-frontend   Up
clouisle-postgres   Up
clouisle-redis      Up
clouisle-qdrant     Up
clouisle-celery     Up
```

### View Logs

**Check logs for errors:**

```bash
# All services
docker compose logs --tail=100

# Specific service
docker compose logs -f backend

# Search for errors
docker compose logs | grep ERROR
```

## Installation Issues

### Docker Compose Fails to Start

**Problem**: Services fail to start

**Symptoms**:
```
Error: Cannot start service backend: port is already allocated
```

**Solutions**:

1. **Check port conflicts:**
```bash
# Check if ports are in use
sudo lsof -i :8000  # Backend
sudo lsof -i :3000  # Frontend
sudo lsof -i :5432  # PostgreSQL
sudo lsof -i :6379  # Redis

# Kill process using port
sudo kill -9 <PID>
```

2. **Check Docker is running:**
```bash
docker info
```

3. **Rebuild containers:**
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

4. **Check disk space:**
```bash
df -h
docker system df
```

### Database Migration Fails

**Problem**: Cannot run migrations

**Symptoms**:
```
Error: could not connect to server: Connection refused
```

**Solutions**:

1. **Check database is running:**
```bash
docker compose ps postgres
docker compose logs postgres
```

2. **Wait for database to be ready:**
```bash
# Wait 10 seconds
sleep 10

# Then run migrations
docker compose exec backend alembic upgrade head
```

3. **Check database credentials:**
```bash
docker compose exec backend env | grep POSTGRES
```

4. **Reset database (development only):**
```bash
docker compose down -v
docker compose up -d postgres
sleep 10
docker compose exec backend alembic upgrade head
```

### Frontend Build Fails

**Problem**: Frontend fails to build

**Symptoms**:
```
Error: Cannot find module 'next'
```

**Solutions**:

1. **Rebuild frontend:**
```bash
cd frontend
rm -rf node_modules .next
bun install
bun run build
```

2. **Check Node version:**
```bash
node --version  # Should be 18+
```

3. **Clear cache:**
```bash
rm -rf .next
bun run build
```

## Connection Errors

### Cannot Connect to Backend

**Problem**: Frontend cannot reach backend

**Symptoms**:
- API requests fail
- "Network Error" in browser console
- CORS errors

**Solutions**:

1. **Check backend is running:**
```bash
curl http://localhost:8000/health
```

2. **Check CORS configuration:**
```bash
# In .env
CORS_ORIGINS=http://localhost:3000,https://your-domain.com
```

3. **Check network:**
```bash
# From frontend container
docker compose exec frontend curl http://backend:8000/health
```

4. **Check firewall:**
```bash
sudo ufw status
sudo ufw allow 8000
```

### Database Connection Failed

**Problem**: Cannot connect to PostgreSQL

**Symptoms**:
```
Error: could not connect to server: Connection refused
```

**Solutions**:

1. **Check PostgreSQL is running:**
```bash
docker compose ps postgres
docker compose logs postgres
```

2. **Test connection:**
```bash
docker compose exec postgres psql -U clouisle -d clouisle -c "SELECT 1"
```

3. **Check credentials:**
```bash
# Verify environment variables
docker compose exec backend env | grep POSTGRES

# Test with psql
docker compose exec postgres psql -U clouisle -d clouisle
```

4. **Check PostgreSQL logs:**
```bash
docker compose logs postgres | grep ERROR
```

### Redis Connection Failed

**Problem**: Cannot connect to Redis

**Symptoms**:
```
Error: Error connecting to Redis
```

**Solutions**:

1. **Check Redis is running:**
```bash
docker compose ps redis
docker compose logs redis
```

2. **Test connection:**
```bash
docker compose exec redis redis-cli ping
# Expected: PONG

# With password
docker compose exec redis redis-cli -a your-password ping
```

3. **Check Redis password:**
```bash
docker compose exec backend env | grep REDIS
```

### Qdrant Connection Failed

**Problem**: Cannot connect to Qdrant

**Symptoms**:
```
Error: Cannot connect to Qdrant
```

**Solutions**:

1. **Check Qdrant is running:**
```bash
docker compose ps qdrant
docker compose logs qdrant
```

2. **Test connection:**
```bash
curl http://localhost:6333/health
```

3. **Check Qdrant URL:**
```bash
docker compose exec backend env | grep QDRANT
```

## Authentication Issues

### Cannot Login

**Problem**: Login fails with valid credentials

**Symptoms**:
- "Invalid credentials" error
- Login button does nothing
- Redirects to login page

**Solutions**:

1. **Check user exists:**
```bash
docker compose exec backend python -m app.scripts.list_users
```

2. **Reset password:**
```bash
docker compose exec backend python -m app.scripts.reset_password \
  --email user@example.com \
  --password new-password
```

3. **Check account status:**
```bash
docker compose exec backend python -m app.scripts.user_info \
  --email user@example.com
```

4. **Check backend logs:**
```bash
docker compose logs backend | grep login
```

### Token Expired

**Problem**: Session expires too quickly

**Symptoms**:
- Logged out frequently
- "Token expired" errors

**Solutions**:

1. **Increase token lifetime:**
```bash
# In .env
JWT_EXPIRATION=3600  # 1 hour instead of 30 minutes
```

2. **Check system time:**
```bash
# Ensure system time is correct
date
timedatectl
```

3. **Clear browser cache:**
- Clear cookies and local storage
- Try incognito mode

### SSO Login Fails

**Problem**: SSO authentication fails

**Symptoms**:
- Redirect loop
- "Invalid state" error
- "OAuth error"

**Solutions**:

1. **Check SSO configuration:**
```bash
docker compose exec backend python -m app.scripts.check_sso
```

2. **Verify callback URL:**
```bash
# Should match SSO provider configuration
echo $SITE_URL/api/v1/auth/sso/callback
```

3. **Check SSO provider logs:**
- Review provider dashboard
- Check for errors

4. **Clear SSO session:**
- Log out from SSO provider
- Clear browser cookies
- Try again

## Performance Issues

### Slow API Responses

**Problem**: API requests are slow

**Symptoms**:
- Long response times (>5 seconds)
- Timeouts
- UI feels sluggish

**Solutions**:

1. **Check resource usage:**
```bash
docker stats
```

2. **Check database performance:**
```bash
# Check slow queries
docker compose exec postgres psql -U clouisle -d clouisle -c "
  SELECT query, calls, total_time, mean_time
  FROM pg_stat_statements
  ORDER BY mean_time DESC
  LIMIT 10;
"
```

3. **Check Redis:**
```bash
docker compose exec redis redis-cli info stats
```

4. **Increase resources:**
```yaml
# In docker-compose.yml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

5. **Enable caching:**
```bash
# In .env
ENABLE_CACHE=true
CACHE_TTL=300
```

### High Memory Usage

**Problem**: Services using too much memory

**Symptoms**:
- Out of memory errors
- Services crashing
- System slowdown

**Solutions**:

1. **Check memory usage:**
```bash
docker stats --no-stream
free -h
```

2. **Restart services:**
```bash
docker compose restart
```

3. **Increase Docker memory:**
```bash
# Edit Docker Desktop settings
# Or /etc/docker/daemon.json
{
  "default-ulimits": {
    "memlock": {
      "Hard": -1,
      "Soft": -1
    }
  }
}
```

4. **Optimize queries:**
- Add database indexes
- Reduce batch sizes
- Implement pagination

### Database Disk Full

**Problem**: Database running out of space

**Symptoms**:
```
Error: could not write to file: No space left on device
```

**Solutions**:

1. **Check disk usage:**
```bash
df -h
docker system df
```

2. **Clean up Docker:**
```bash
docker system prune -a --volumes
```

3. **Archive old data:**
```bash
# Backup and delete old audit logs
docker compose exec backend python -m app.scripts.archive_logs \
  --days 90
```

4. **Increase disk space:**
- Add more storage
- Move to larger volume

## Feature Issues

### Agent Not Responding

**Problem**: Agent doesn't respond to messages

**Symptoms**:
- Messages sent but no response
- Loading indicator stuck
- Timeout errors

**Solutions**:

1. **Check agent status:**
```bash
docker compose logs backend | grep agent
```

2. **Check LLM API key:**
```bash
docker compose exec backend env | grep OPENAI_API_KEY
```

3. **Test LLM connection:**
```bash
docker compose exec backend python -m app.scripts.test_llm
```

4. **Check rate limits:**
- Review LLM provider dashboard
- Check for quota exceeded

5. **Check Celery worker:**
```bash
docker compose logs celery
docker compose restart celery
```

### Workflow Execution Fails

**Problem**: Workflow fails to execute

**Symptoms**:
- Workflow stuck in "Running" status
- Execution fails immediately
- Nodes not executing

**Solutions**:

1. **Check workflow logs:**
```bash
docker compose logs backend | grep workflow
```

2. **Check Celery:**
```bash
docker compose ps celery
docker compose logs celery
```

3. **Restart Celery:**
```bash
docker compose restart celery celery-beat
```

4. **Check workflow definition:**
- Verify all nodes are configured
- Check for circular dependencies
- Test individual nodes

### Document Upload Fails

**Problem**: Cannot upload documents

**Symptoms**:
- Upload fails with error
- File too large error
- Processing stuck

**Solutions**:

1. **Check file size:**
```bash
# In .env
MAX_UPLOAD_SIZE=104857600  # 100 MB
```

2. **Check upload directory:**
```bash
docker compose exec backend ls -la /app/uploads
docker compose exec backend df -h /app/uploads
```

3. **Check permissions:**
```bash
docker compose exec backend chmod 755 /app/uploads
```

4. **Check Celery worker:**
```bash
docker compose logs celery | grep document
```

5. **Retry processing:**
```bash
docker compose exec backend python -m app.scripts.reprocess_document \
  --document-id doc-123
```

### Search Not Working

**Problem**: Document search returns no results

**Symptoms**:
- Search returns empty
- Relevant documents not found
- Search errors

**Solutions**:

1. **Check Qdrant:**
```bash
docker compose ps qdrant
curl http://localhost:6333/collections
```

2. **Check embeddings:**
```bash
docker compose exec backend python -m app.scripts.check_embeddings \
  --kb-id kb-123
```

3. **Reindex documents:**
```bash
docker compose exec backend python -m app.scripts.reindex_kb \
  --kb-id kb-123
```

4. **Check search logs:**
```bash
docker compose logs backend | grep search
```

## Error Messages

### "Internal Server Error"

**Error**: 500 Internal Server Error

**Solutions**:

1. **Check backend logs:**
```bash
docker compose logs backend --tail=100
```

2. **Check for exceptions:**
```bash
docker compose logs backend | grep -A 10 "Traceback"
```

3. **Restart backend:**
```bash
docker compose restart backend
```

### "Database Connection Error"

**Error**: Cannot connect to database

**Solutions**:

1. **Check PostgreSQL:**
```bash
docker compose ps postgres
docker compose logs postgres
```

2. **Verify credentials:**
```bash
docker compose exec backend env | grep POSTGRES
```

3. **Test connection:**
```bash
docker compose exec postgres psql -U clouisle -d clouisle -c "SELECT 1"
```

### "Rate Limit Exceeded"

**Error**: 429 Too Many Requests

**Solutions**:

1. **Wait for rate limit reset:**
- Check `Retry-After` header
- Wait specified time

2. **Increase rate limits:**
```bash
# In .env
RATE_LIMIT_PER_MINUTE=100
```

3. **Use API key with higher limits:**
- Create new API key
- Request limit increase

### "Permission Denied"

**Error**: 403 Forbidden

**Solutions**:

1. **Check user permissions:**
```bash
docker compose exec backend python -m app.scripts.user_info \
  --email user@example.com
```

2. **Check team membership:**
- Verify user is in correct team
- Check team role

3. **Check API key scopes:**
- Verify key has required scopes
- Create new key if needed

## Getting Help

### Collect Diagnostic Information

**Before contacting support:**

1. **System information:**
```bash
# OS and version
uname -a
cat /etc/os-release

# Docker version
docker --version
docker compose version

# Disk space
df -h

# Memory
free -h
```

2. **Service status:**
```bash
docker compose ps
docker compose logs --tail=100 > logs.txt
```

3. **Configuration:**
```bash
# Sanitize sensitive data first!
docker compose config > config.yml
```

4. **Error messages:**
- Copy exact error messages
- Include timestamps
- Note steps to reproduce

### Support Channels

1. **Documentation**: Review relevant guides
2. **GitHub Issues**: https://github.com/your-org/clouisle/issues
3. **Community Forum**: https://community.clouisle.com
4. **Email Support**: support@clouisle.com
5. **Enterprise Support**: For enterprise customers

### Reporting Bugs

**Include in bug report:**

1. **Description**: Clear description of issue
2. **Steps to reproduce**: Exact steps
3. **Expected behavior**: What should happen
4. **Actual behavior**: What actually happens
5. **Environment**: OS, Docker version, etc.
6. **Logs**: Relevant log excerpts
7. **Screenshots**: If applicable

**Bug report template:**

```markdown
## Description
Brief description of the issue

## Steps to Reproduce
1. Step 1
2. Step 2
3. Step 3

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Environment
- OS: Ubuntu 22.04
- Docker: 24.0.0
- Clouisle Version: 1.0.0

## Logs
```
Relevant log excerpts
```

## Screenshots
If applicable
```

## Related Documentation

- [Docker Deployment](./docker-compose.md) - Docker setup
- [Environment Variables](./environment-variables.md) - Configuration
- [User Management](../admin-guide/users/user-management.md) - User admin
- [Security Best Practices](../best-practices/security.md) - Security guide

---

**Last Updated**: 2026-02-11
