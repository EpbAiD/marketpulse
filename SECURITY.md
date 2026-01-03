# Security Guide

This document outlines the security measures in place to protect credentials and sensitive data in this public repository.

## Current Security Status: ✅ SECURE

All credentials are properly protected and safe for public repository access.

---

## Protected Credentials

### Google Cloud Platform (BigQuery)
- **Credential File:** `regime01-*.json` (service account key)
- **Protection:** Gitignored, never committed to repository
- **Usage:** Loaded via GitHub Secrets in CI/CD, local file for development
- **Status:** ✅ Protected

### GitHub Actions Secrets
The following secrets are configured in GitHub Actions:
- `GCP_CREDENTIALS` - BigQuery service account JSON (added 2025-12-30)

**Access Control:**
- Only accessible within GitHub Actions workflows
- Not visible in forks
- Encrypted at rest
- Masked in logs (shown as `***`)

---

## Security Measures

### 1. .gitignore Protection

All sensitive files are explicitly ignored:

```gitignore
# BigQuery credentials
regime01-*.json
*credentials*.json

# Environment variables
.env
.env.local

# All JSON files except configs
*.json
!configs/*.json
```

**Verification:**
```bash
# Check if credentials are ignored
git check-ignore -v regime01-*.json
# Should output: .gitignore:58:regime01-*.json

# Verify credentials are NOT in git history
git log --all --full-history --name-only -- "**/regime01*.json"
# Should output: (empty)
```

### 2. No Hardcoded Secrets

The codebase uses configuration files and environment variables:

**Safe Pattern (Current):**
```python
# configs/bigquery_config.yaml
bigquery:
  credentials_path: "regime01-*.json"  # Generic pattern, not committed
```

**Unsafe Pattern (Avoided):**
```python
# NEVER DO THIS
api_key = "AIza..."  # Hardcoded secret
```

### 3. GitHub Actions Security

**Workflow Security Features:**
- Secrets loaded as environment variables at runtime
- Credentials written to temporary files, deleted after use
- No secrets in workflow logs
- Fork pull requests cannot access secrets

**Workflow Example:**
```yaml
- name: Setup credentials
  env:
    GCP_CREDENTIALS: ${{ secrets.GCP_CREDENTIALS }}
  run: |
    echo "$GCP_CREDENTIALS" > /tmp/gcp-key.json
    export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-key.json
```

### 4. Public Repository Safety

**What's Safe to Share:**
- ✅ Source code (Python, YAML, etc.)
- ✅ Documentation
- ✅ Configuration schemas (without actual credentials)
- ✅ Project structure
- ✅ Dependencies (requirements.txt)

**What's Protected:**
- 🔒 BigQuery service account credentials
- 🔒 API keys (if any were added)
- 🔒 Environment variables
- 🔒 Local data files (outputs/)

---

## Security Checklist

Use this checklist to verify repository security:

- [x] Credentials file (`regime01-*.json`) is gitignored
- [x] No credentials in git history
- [x] GitHub Secrets configured (`GCP_CREDENTIALS`)
- [x] Documentation doesn't expose credential paths
- [x] No hardcoded secrets in code
- [x] `.env` files are gitignored
- [x] BigQuery project ID is acceptable to share (no secrets in ID)
- [x] Local data folders are gitignored

---

## Best Practices

### For Development

1. **Keep credentials local:**
   ```bash
   # Store credentials in project root (gitignored)
   ls regime01-*.json
   # -rw-r--r-- 1 user staff 2346 Dec 7 17:28 regime01-[hash].json
   ```

2. **Never commit credentials:**
   ```bash
   # Before committing, verify no secrets
   git diff --cached
   ```

3. **Use environment variables:**
   ```bash
   # For additional API keys
   export API_KEY="your-key-here"
   # Or use .env file (gitignored)
   ```

### For Collaboration

1. **Share setup instructions, not credentials:**
   - Document where to get credentials (GCP Console)
   - Never share actual credential files via email/Slack

2. **Use service accounts with minimal permissions:**
   - BigQuery Data Editor (for writing)
   - BigQuery Job User (for queries)
   - Don't grant Owner/Editor roles

3. **Rotate credentials regularly:**
   - Recommended: Every 90 days
   - When team members leave
   - If credentials might be compromised

---

## If Credentials Are Exposed

If you accidentally commit credentials, follow these steps immediately:

### 1. Revoke Compromised Credentials

**For BigQuery:**
1. Go to [GCP Console](https://console.cloud.google.com/iam-admin/serviceaccounts?project=regime01)
2. Find the service account
3. Delete the exposed key
4. Create new key
5. Download new JSON file

### 2. Remove from Git History

```bash
# Install git-filter-repo if needed
brew install git-filter-repo  # macOS
# or: pip install git-filter-repo

# Remove file from all history
git filter-repo --path regime01-*.json --invert-paths

# Force push (CAUTION: rewrites history)
git push origin --force --all
```

### 3. Update GitHub Secrets

1. Go to repository Settings → Secrets
2. Delete old `GCP_CREDENTIALS` secret
3. Add new credentials from step 1

### 4. Verify Removal

```bash
# Check git history
git log --all --full-history -- "**/regime01*.json"
# Should be empty

# Check GitHub
# Browse repository files - credentials should not appear
```

---

## Monitoring

### Check for Exposed Secrets

**GitHub Secret Scanning:**
- Automatically enabled on public repositories
- Alerts you if known secret patterns are detected
- Check: Settings → Security → Secret scanning alerts

**Manual Audit:**
```bash
# Search for potential secrets in codebase
grep -r "private_key" --include="*.py" --include="*.yaml" .
grep -r "api_key" --include="*.py" --include="*.yaml" .
grep -r "password" --include="*.py" --include="*.yaml" .
```

### Regular Security Reviews

**Monthly:**
- Review .gitignore for completeness
- Check GitHub Secret Scanning alerts
- Verify no new credential files in repository

**Quarterly:**
- Rotate BigQuery service account keys
- Review service account permissions
- Audit GitHub Actions logs for anomalies

---

## Additional Security

### Dependabot Alerts

Enabled to monitor for vulnerable dependencies:
- Settings → Security → Dependabot alerts: ✅ Enabled
- Automatic security updates for Python packages

### Branch Protection

Consider enabling:
- Require pull request reviews
- Require status checks to pass
- Restrict who can push to main branch

### Access Control

**Current Setup:**
- Repository: Public (code visible to all)
- Secrets: Private (only accessible in workflows)
- Data: Private (BigQuery access controlled via service account)

---

## Questions?

**Is it safe to have the repository public?**
- Yes, if credentials are properly gitignored (current status)
- Code is safe to share - contains no secrets

**Can people who fork the repository access my data?**
- No - they don't have your credentials
- They would need their own BigQuery project

**What if I want to add new API keys?**
- Add to `.gitignore` pattern (e.g., `*_api_key.txt`)
- Store in GitHub Secrets for workflows
- Use environment variables locally

**How do I know if my credentials leaked?**
- Check: https://github.com/EpbAiD/marketpulse/security
- Enable notifications for secret scanning alerts
- Monitor GCP audit logs for unexpected access

---

## Summary

✅ **Current Status:** Repository is secure for public access
✅ **Credentials:** Protected via .gitignore and GitHub Secrets
✅ **History:** No credentials ever committed to git
✅ **Monitoring:** GitHub secret scanning enabled
✅ **Best Practices:** Followed throughout the project

**Confidence Level:** HIGH - Safe to keep repository public
