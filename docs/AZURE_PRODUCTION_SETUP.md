# Azure Production Rollout (Container Apps + CI/CD)

This guide keeps your local `.env` untouched and uses Azure/GitHub secrets for production.

## Target Architecture

- Frontend: Azure Container Apps (`frontend`) with custom domain, HTTPS.
- Backend: Azure Container Apps (`backend`) with custom domain, HTTPS.
- Database: Azure Database for PostgreSQL Flexible Server.
- Registry: Azure Container Registry (ACR).
- CI/CD: GitHub Actions with OpenID Connect (OIDC), no static cloud passwords.
- DNS: GoDaddy (recommended: `app.yourdomain.com` for frontend, `api.yourdomain.com` for backend).

## Prerequisites (Your Side)

- Azure subscription with available credit.
- GoDaddy domain.
- GitHub repo admin access.
- Azure CLI installed (`az --version`), Docker installed.

## 1) Create Azure Resources

Use Cloud Shell (Bash) or local terminal:

```bash
# ===== Change these first =====
RG="scanmybill-rg"
LOCATION="centralindia"
ACR_NAME="scanmybillacr001"               # globally unique, lowercase, no hyphen
ACA_ENV_NAME="scanmybill-aca-env"
BACKEND_APP="scanmybill-backend"
FRONTEND_APP="scanmybill-frontend"
PG_SERVER="scanmybill-pgsql-001"          # globally unique
PG_DB="scanmybill"
PG_ADMIN="scanmybill_admin"
PG_PASSWORD="<strong-password>"
# ==============================

az group create --name "$RG" --location "$LOCATION"
az acr create --name "$ACR_NAME" --resource-group "$RG" --location "$LOCATION" --sku Basic --admin-enabled false

# Required by Container Apps environment
az monitor log-analytics workspace create --resource-group "$RG" --workspace-name "${ACA_ENV_NAME}-logs" --location "$LOCATION"
LOG_WORKSPACE_ID=$(az monitor log-analytics workspace show --resource-group "$RG" --workspace-name "${ACA_ENV_NAME}-logs" --query customerId -o tsv)
LOG_WORKSPACE_KEY=$(az monitor log-analytics workspace get-shared-keys --resource-group "$RG" --workspace-name "${ACA_ENV_NAME}-logs" --query primarySharedKey -o tsv)

az containerapp env create \
  --name "$ACA_ENV_NAME" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --logs-workspace-id "$LOG_WORKSPACE_ID" \
  --logs-workspace-key "$LOG_WORKSPACE_KEY"

az postgres flexible-server create \
  --resource-group "$RG" \
  --name "$PG_SERVER" \
  --location "$LOCATION" \
  --admin-user "$PG_ADMIN" \
  --admin-password "$PG_PASSWORD" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32

az postgres flexible-server db create --resource-group "$RG" --server-name "$PG_SERVER" --database-name "$PG_DB"
```

## 2) Prepare Container Apps (One-Time)

Create apps first (placeholder image), then CI/CD will update images:

```bash
ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"
az containerapp create \
  --name "$BACKEND_APP" \
  --resource-group "$RG" \
  --environment "$ACA_ENV_NAME" \
  --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3

az containerapp create \
  --name "$FRONTEND_APP" \
  --resource-group "$RG" \
  --environment "$ACA_ENV_NAME" \
  --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
  --target-port 3000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3
```

Attach ACR pull permission:

```bash
ACR_ID=$(az acr show --name "$ACR_NAME" --resource-group "$RG" --query id -o tsv)

az containerapp identity assign --name "$BACKEND_APP" --resource-group "$RG" --system-assigned
az containerapp identity assign --name "$FRONTEND_APP" --resource-group "$RG" --system-assigned

BACKEND_PRINCIPAL=$(az containerapp show --name "$BACKEND_APP" --resource-group "$RG" --query identity.principalId -o tsv)
FRONTEND_PRINCIPAL=$(az containerapp show --name "$FRONTEND_APP" --resource-group "$RG" --query identity.principalId -o tsv)

az role assignment create --assignee-object-id "$BACKEND_PRINCIPAL" --assignee-principal-type ServicePrincipal --role AcrPull --scope "$ACR_ID"
az role assignment create --assignee-object-id "$FRONTEND_PRINCIPAL" --assignee-principal-type ServicePrincipal --role AcrPull --scope "$ACR_ID"
```

## 3) Configure Production Secrets and Env Vars in Container Apps

Set secrets once:

```bash
DATABASE_URL="postgresql+psycopg2://${PG_ADMIN}:${PG_PASSWORD}@${PG_SERVER}.postgres.database.azure.com:5432/${PG_DB}?sslmode=require"

az containerapp secret set --name "$BACKEND_APP" --resource-group "$RG" --secrets \
  database-url="$DATABASE_URL" \
  secret-key="<backend-secret-key-32-plus-chars>" \
  openai-api-key="<openai-or-azure-openai-key>" \
  azure-openai-api-key="<optional-azure-openai-key>" \
  razorpay-key-id="<razorpay-key-id>" \
  razorpay-key-secret="<razorpay-secret>" \
  razorpay-webhook-secret="<razorpay-webhook-secret>" \
  smtp-password="<smtp-password>"
```

Apply backend runtime env vars:

```bash
az containerapp update --name "$BACKEND_APP" --resource-group "$RG" \
  --set-env-vars \
  ENVIRONMENT=production \
  DEBUG=false \
  ENABLE_DOCS=false \
  PORT=8000 \
  DATABASE_URL_OVERRIDE=secretref:database-url \
  SECRET_KEY=secretref:secret-key \
  CORS_ORIGINS="https://app.yourdomain.com" \
  TRUSTED_HOSTS="api.yourdomain.com,app.yourdomain.com" \
  COOKIE_SECURE=true \
  ENFORCE_HTTPS=true \
  SEED_DEFAULT_ADMIN=false \
  EXPOSE_PASSWORD_RESET_TOKEN=false \
  OPENAI_MODEL=gpt-4o-mini \
  OPENAI_API_KEY=secretref:openai-api-key \
  AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key \
  STORAGE_BACKEND=local \
  UPLOADS_DIR=uploads
```

Frontend runtime env vars (for server runtime only):

```bash
az containerapp update --name "$FRONTEND_APP" --resource-group "$RG" \
  --set-env-vars \
  NODE_ENV=production \
  PORT=3000 \
  NEXT_PUBLIC_API_URL="https://api.yourdomain.com/api/v1" \
  NEXT_PUBLIC_APP_URL="https://app.yourdomain.com"
```

## 4) Configure GitHub OIDC + CI/CD

### 4.1 Create Azure AD App + Federated Credential

1. Create App Registration in Azure AD.
2. Add Federated Credential:
   - Issuer: `https://token.actions.githubusercontent.com`
   - Subject: `repo:<your-org-or-user>/<your-repo>:ref:refs/heads/main`
   - Audience: `api://AzureADTokenExchange`
3. Grant the app at least:
   - `Contributor` on Resource Group.
   - `AcrPush` on ACR.

### 4.2 Add GitHub Secrets

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

### 4.3 Add GitHub Repository Variables

- `ACR_NAME`
- `AZURE_RESOURCE_GROUP`
- `AZURE_CONTAINERAPP_BACKEND_NAME`
- `AZURE_CONTAINERAPP_FRONTEND_NAME`
- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_APP_URL`
- Optional: `NEXT_PUBLIC_SESSION_IDLE_TIMEOUT_MINUTES`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID`, `NEXT_PUBLIC_RAZORPAY_KEY_ID`

Important:
- `NEXT_PUBLIC_*` values are baked into the frontend image at build time.
- If you change any `NEXT_PUBLIC_*` variable, re-run the deploy workflow to rebuild and redeploy frontend.

### 4.4 Run Pipelines

- CI runs on PR and push (`.github/workflows/ci.yml`).
- Production deploy runs on push to `main` and manual dispatch (`.github/workflows/deploy.yml`).
- First deploy updates both container apps to your built images.

## 5) Connect GoDaddy Domain

Get generated ACA hostnames:

```bash
BACKEND_FQDN=$(az containerapp show --name "$BACKEND_APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)
FRONTEND_FQDN=$(az containerapp show --name "$FRONTEND_APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)
echo "$BACKEND_FQDN"
echo "$FRONTEND_FQDN"
```

Recommended DNS in GoDaddy:

- `app` CNAME -> `<FRONTEND_FQDN>`
- `api` CNAME -> `<BACKEND_FQDN>`

Then bind custom domains in Azure Container Apps:

```bash
az containerapp hostname add --name "$FRONTEND_APP" --resource-group "$RG" --hostname "app.yourdomain.com"
az containerapp hostname add --name "$BACKEND_APP" --resource-group "$RG" --hostname "api.yourdomain.com"
```

If domain validation TXT records are requested, add them in GoDaddy and retry.

## 6) Production Verification Checklist

- `https://api.yourdomain.com/health/live` returns 200.
- `https://app.yourdomain.com` loads successfully.
- Sign-in works.
- Upload bill flow works end-to-end (AI extraction + DB write + file access).
- Razorpay callbacks succeed with webhook signature verification.
- SMTP flow works for password reset/newsletter.

## 7) Cost and Reliability Tips for $200 Credit

- Keep both apps at `min-replicas=1`, `max-replicas=2/3` initially.
- Use Burstable PostgreSQL SKU first.
- Enable scale rules only after observing real traffic.
- Turn on Azure budget alerts from day one.
- Move secrets to Azure Key Vault after first stable release.
