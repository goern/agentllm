# Token Encryption Deployment Guide

This guide covers deploying AgentLLM with encrypted token storage for production environments.

## Table of Contents

1. [Overview](#overview)
2. [Local Development Setup](#local-development-setup)
3. [Production Deployment (Kubernetes/OpenShift)](#production-deployment-kubernetesopenshift)
4. [Key Management Best Practices](#key-management-best-practices)
5. [Disaster Recovery](#disaster-recovery)
6. [Monitoring and Alerts](#monitoring-and-alerts)
7. [Troubleshooting](#troubleshooting)

---

## Overview

AgentLLM encrypts all sensitive tokens at rest using **Fernet symmetric encryption** (AES-128-CBC + HMAC-SHA256). This provides:

- **Confidentiality**: Tokens are unreadable without the encryption key
- **Integrity**: Tampered tokens are detected and rejected
- **Authentication**: Each encrypted token includes a timestamp and signature

### What's Encrypted

| Token Type | Encrypted Fields |
|------------|------------------|
| Jira | `token` |
| GitHub | `token` |
| Google Drive OAuth | `token`, `refresh_token`, `client_secret` |
| Red Hat Customer Portal | `offline_token` |

---

## Local Development Setup

### Step 1: Generate Encryption Key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Example output:
```
eSsSRZhHEmUJyrC43OFHUed0fDjhrKtTaDWQKVZpRRY=
```

### Step 2: Add to `.env.secrets`

Edit `.env.secrets` (create from `.env.secrets.template` if needed):

```bash
# Token Encryption (REQUIRED)
AGENTLLM_TOKEN_ENCRYPTION_KEY=eSsSRZhHEmUJyrC43OFHUed0fDjhrKtTaDWQKVZpRRY=
```

### Step 3: Delete Existing Database (Fresh Start)

```bash
rm ./tmp/agno_sessions.db
```

This removes any plaintext tokens. Users will need to re-enter credentials.

### Step 4: Start Application

```bash
# Full containerized stack (recommended)
just dev

# Or if you need local proxy mode
just proxy
```

### Step 5: Verify Encryption

Check logs for:
```
TokenStorage initialized with encryption enabled
```

Test token storage:
```bash
# Start chat with an agent
# Configure a Jira token
# Verify it's encrypted in database:
sqlite3 ./tmp/agno_sessions.db "SELECT token FROM jira_tokens;"
```

Output should start with `gAAAAA` (Fernet prefix), NOT plaintext.

---

## Production Deployment (Kubernetes/OpenShift)

### Step 1: Generate Production Encryption Key

**CRITICAL**: Use a separate key for production (never reuse local dev keys).

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Step 2: Create Kubernetes Secret

```bash
# Create secret from key
kubectl create secret generic agentllm-encryption \
  --from-literal=key=eSsSRZhHEmUJyrC43OFHUed0fDjhrKtTaDWQKVZpRRY= \
  -n your-namespace
```

### Step 3: Update Deployment Manifest

Add environment variable from secret:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: litellm-proxy
spec:
  template:
    spec:
      containers:
      - name: proxy
        image: your-image:tag
        env:
        - name: AGENTLLM_TOKEN_ENCRYPTION_KEY
          valueFrom:
            secretKeyRef:
              name: agentllm-encryption
              key: key
        # ... other env vars
```

### Step 4: Deploy Application

```bash
kubectl apply -f deployment.yaml
```

### Step 5: Verify Deployment

```bash
# Check pods are running
kubectl get pods -n your-namespace

# Check logs for encryption message
kubectl logs -n your-namespace deployment/litellm-proxy | grep "encryption enabled"
```

Expected output:
```
TokenStorage initialized with encryption enabled
```

### Step 6: Test End-to-End

1. Access application
2. Configure a token (e.g., Jira)
3. Verify token works
4. Check database to confirm encryption:

```bash
# Exec into pod
kubectl exec -it deployment/litellm-proxy -n your-namespace -- bash

# Check encrypted tokens
sqlite3 /app/tmp/agno_sessions.db "SELECT token FROM jira_tokens;"
```

---

## Key Management Best Practices

### Storage Options

#### Option 1: Kubernetes Secrets (Basic)

✅ **Pros**: Simple, built-in, works everywhere
⚠️ **Cons**: Base64-encoded only (not encrypted by default)

**Enable encryption at rest**:
- AWS EKS: Use KMS encryption for secrets
- GKE: Use Cloud KMS
- OpenShift: Enable etcd encryption

#### Option 2: External Secrets Operator (Recommended for Production)

✅ **Pros**: Centralized, automated rotation, audit trails
⚠️ **Cons**: Additional infrastructure

**Supported backends**:
- AWS Secrets Manager
- Azure Key Vault
- HashiCorp Vault
- Google Secret Manager

**Example with AWS Secrets Manager**:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: agentllm-encryption
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: agentllm-encryption
  data:
  - secretKey: key
    remoteRef:
      key: /agentllm/prod/encryption-key
```

### Key Rotation

**Current Limitation**: v1 does not support zero-downtime key rotation.

**Rotation Procedure** (requires downtime):

1. **Generate new key**
2. **Schedule maintenance window**
3. **Update Kubernetes Secret** with new key
4. **Restart pods** (application will fail to decrypt old tokens)
5. **Notify users** to re-enter credentials
6. **Delete old database** (optional, for clean slate)

**Future Enhancement**: MultiFernet support for zero-downtime rotation.

### Access Control

Restrict who can access encryption keys:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: secret-reader
rules:
- apiGroups: [""]
  resources: ["secrets"]
  resourceNames: ["agentllm-encryption"]
  verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind:  RoleBinding
metadata:
  name: read-agentllm-encryption
subjects:
- kind: ServiceAccount
  name: litellm-proxy
roleRef:
  kind: Role
  name: secret-reader
  apiGroup: rbac.authorization.k8s.io
```

### Backup Procedures

**Critical**: Backup encryption key securely!

```bash
# Extract key from Kubernetes (requires admin access)
kubectl get secret agentllm-encryption -n your-namespace -o jsonpath='{.data.key}' | base64 -d > encryption-key-backup.txt

# Store in secure vault
# DO NOT commit to git!
# DO NOT store in plaintext on disk long-term!
```

**Recommended**: Store backup in external vault (AWS Secrets Manager, HashiCorp Vault).

---

## Disaster Recovery

### Scenario 1: Key Loss

**Impact**: All tokens unrecoverable.

**Recovery Steps**:
1. Generate new encryption key
2. Update Kubernetes Secret
3. Restart application
4. Communicate to users: "Please re-enter your credentials"
5. Monitor for user configuration completions

**Prevention**: Regular key backups to secure vault.

### Scenario 2: Key Exposure

**Impact**: Encrypted tokens can be decrypted by unauthorized parties.

**Immediate Actions**:
1. **Rotate key immediately** (see Key Rotation above)
2. **Revoke compromised tokens** at source (Jira, GitHub, etc.)
3. **Audit access logs** to determine scope of exposure
4. **Notify security team** and affected users
5. **Investigate** how key was exposed

**Prevention**: RBAC, audit logging, secure key storage.

### Scenario 3: Decryption Failures

**Symptoms**: Users report "token not found" or authentication failures.

**Diagnosis**:
```bash
# Check logs for decryption errors
kubectl logs deployment/litellm-proxy -n your-namespace | grep "Failed to decrypt"
```

**Causes**:
- Wrong encryption key (e.g., using dev key in prod)
- Corrupt database
- Key rotation without re-encryption

**Recovery**:
1. Verify correct key is configured
2. If key is wrong, update Secret and restart
3. If database corrupt, restore from backup or have users re-enter

---

## Monitoring and Alerts

### Health Checks

Add readiness probe to verify encryption initialization:

```yaml
readinessProbe:
  exec:
    command:
    - python
    - -c
    - |
      import os
      assert os.getenv('AGENTLLM_TOKEN_ENCRYPTION_KEY'), 'Encryption key missing'
  initialDelaySeconds: 5
  periodSeconds: 10
```

### Recommended Alerts

#### 1. Application Startup Failure (Encryption Key Missing)

**Alert Rule** (Prometheus):
```yaml
- alert: AgentLLMEncryptionKeyMissing
  expr: up{job="litellm-proxy"} == 0
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "AgentLLM failed to start (likely encryption key missing)"
```

#### 2. High Decryption Failure Rate

**Log Pattern**: `Failed to decrypt .* token for user`

**Alert Rule**:
```yaml
- alert: HighDecryptionFailureRate
  expr: rate(agentllm_decryption_failures_total[5m]) > 0.1
  labels:
    severity: warning
  annotations:
    summary: "High rate of token decryption failures"
```

### Metrics to Track

Suggested custom metrics (requires instrumentation):

- `agentllm_encryption_operations_total{operation="encrypt|decrypt", status="success|failure"}`
- `agentllm_token_storage_latency_seconds{operation="upsert|get"}`
- `agentllm_active_tokens_total{type="jira|github|gdrive|rhcp"}`

---

## Troubleshooting

### Problem: Application Fails to Start

**Error**: `CRITICAL: Token encryption key not configured`

**Solution**:
```bash
# Verify secret exists
kubectl get secret agentllm-encryption -n your-namespace

# Verify pod has access
kubectl describe pod <pod-name> -n your-namespace | grep -A 5 "Environment"

# If missing, create secret (see Production Deployment)
```

### Problem: Tokens Return None (Decryption Failures)

**Error in logs**: `Failed to decrypt .* token for user`

**Causes**:
1. Wrong encryption key
2. Database migrated from different key
3. Corrupt encrypted data

**Diagnosis**:
```bash
# Check which key is being used
kubectl get secret agentllm-encryption -n your-namespace -o jsonpath='{.data.key}' | base64 -d

# Compare with expected key (from backup)
```

**Solution**:
- If key wrong: Update secret and restart
- If key correct: Database may be corrupt or from different key → users must re-enter tokens

### Problem: "Old" Plaintext Tokens Not Working

**Scenario**: Upgraded from pre-encryption version, tokens were in plaintext.

**Solution**: Encryption is required, no backward compatibility. Users must re-enter tokens.

**Migration Path**:
1. **Before upgrade**: Export tokens (if migration script available)
2. **After upgrade**: Re-encrypt and import
3. **Or**: Have users re-enter (simpler, recommended)

### Problem: Performance Degradation

**Symptom**: Slow token operations.

**Diagnosis**:
```python
# Benchmark encryption performance
import timeit
from cryptography.fernet import Fernet

key = Fernet.generate_key()
f = Fernet(key)

def encrypt_decrypt():
    encrypted = f.encrypt(b"test-token")
    f.decrypt(encrypted)

# Should be < 1ms for 1000 operations
time = timeit.timeit(encrypt_decrypt, number=1000)
print(f"{time*1000:.2f}ms for 1000 operations")
```

**Expected**: <100ms for 1000 encrypt/decrypt operations

**If slow**: Check system resources (CPU, memory), not encryption itself.

---

## Security Audit Checklist

- [ ] Encryption key stored in Kubernetes Secret (not ConfigMap or environment variable in deployment YAML)
- [ ] Kubernetes etcd encryption enabled (AWS KMS, Cloud KMS, etc.)
- [ ] RBAC configured to limit secret access
- [ ] Encryption key backed up in secure vault
- [ ] Monitoring alerts configured for startup failures and decryption errors
- [ ] Application logs do not contain plaintext tokens or encryption keys
- [ ] Database file has restrictive permissions (if using persistent volume)
- [ ] Disaster recovery procedures documented and tested
- [ ] Key rotation procedure documented (even if manual)
- [ ] Users notified about token re-entry requirements after key rotation

---

## Additional Resources

- [Cryptography.io - Fernet Documentation](https://cryptography.io/en/latest/fernet/)
- [Kubernetes Secrets Best Practices](https://kubernetes.io/docs/concepts/security/secrets-good-practices/)
- [External Secrets Operator](https://external-secrets.io/)
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
