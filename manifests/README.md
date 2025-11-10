# AgentLLM Kubernetes Manifests

This directory contains Kustomize manifests for deploying AgentLLM to Kubernetes.

## Structure

```
manifests/
├── base/                    # Base Kustomize configuration
│   ├── deployment.yaml      # AgentLLM deployment
│   ├── service.yaml         # Service definition
│   ├── secret.yaml          # Secret template (needs customization)
│   └── kustomization.yaml   # Base kustomization
└── environment/             # Environment-specific overlays
    ├── stage/               # Staging environment
    │   └── kustomization.yaml
    └── prod/                # Production environment
        └── kustomization.yaml
```

## Prerequisites

- Kubernetes cluster (1.20+)
- `kubectl` CLI tool
- `kustomize` (or use `kubectl -k`)
- Valid Anthropic API key

## Configuration

### 1. Configure API Key

Before deploying, you need to set your Anthropic API key. You have two options:

#### Option A: Edit the secret manifest directly

Edit `base/secret.yaml` and replace the placeholder API key:

```yaml
stringData:
  anthropic-api-key: "sk-ant-api03-YOUR_ACTUAL_KEY_HERE"
```

#### Option B: Use Kustomize secret generator (recommended)

Create a `.env` file with your API key:

```bash
echo "anthropic-api-key=sk-ant-api03-YOUR_ACTUAL_KEY_HERE" > .env
```

Then modify the kustomization.yaml to use secretGenerator instead of the secret.yaml resource.

### 2. Adjust Container Image

The manifests use the container image from Codeberg:
```
codeberg.org/b4mad/agentllm/agentllm:latest
```

You can override the image tag in the environment-specific kustomization files.

## Deployment

### Deploy to Staging

```bash
kubectl apply -k manifests/environment/stage/
```

### Deploy to Production

```bash
kubectl apply -k manifests/environment/prod/
```

### Deploy Base Configuration

```bash
kubectl apply -k manifests/base/
```

## Verify Deployment

Check the deployment status:

```bash
kubectl get deployments -n agentllm-stage
kubectl get pods -n agentllm-stage
kubectl get services -n agentllm-stage
```

Check the logs:

```bash
kubectl logs -n agentllm-stage -l app=agentllm -f
```

Test the health endpoint:

```bash
kubectl port-forward -n agentllm-stage svc/stage-agentllm 8890:8890
curl http://localhost:8890/health
```

## Environment Differences

### Staging (`environment/stage/`)
- Namespace: `agentllm-stage`
- Replicas: 1
- Resources: 512Mi-1Gi memory, 250m-1000m CPU
- Image tag: `latest`

### Production (`environment/prod/`)
- Namespace: `agentllm-prod`
- Replicas: 2 (for high availability)
- Resources: 1Gi-4Gi memory, 500m-4000m CPU
- Image tag: `stable`

## Customization

### Scaling

To change the number of replicas, edit the overlay's kustomization.yaml:

```yaml
replicas:
  - name: agentllm
    count: 3
```

### Resource Limits

Adjust resources using patches in the overlay kustomization files:

```yaml
patches:
  - target:
      kind: Deployment
      name: agentllm
    patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/resources/limits/memory
        value: "8Gi"
```

### Environment Variables

Add additional environment variables by patching the deployment:

```yaml
patches:
  - target:
      kind: Deployment
      name: agentllm
    patch: |-
      - op: add
        path: /spec/template/spec/containers/0/env/-
        value:
          name: YOUR_VAR
          value: "your_value"
```

## Cleanup

To remove the deployment:

```bash
kubectl delete -k manifests/environment/stage/
```

## Troubleshooting

### Pods not starting

Check pod events:
```bash
kubectl describe pod -n agentllm-stage <pod-name>
```

### Secret not found

Ensure the secret was created:
```bash
kubectl get secrets -n agentllm-stage
```

### Health check failing

Check container logs:
```bash
kubectl logs -n agentllm-stage -l app=agentllm
```

Verify the health endpoint is responding:
```bash
kubectl exec -n agentllm-stage <pod-name> -- curl localhost:8890/health
```
