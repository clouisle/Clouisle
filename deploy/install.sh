#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

REPOSITORY="${CLOUISLE_REPOSITORY:-clouisle/Clouisle}"
REF="${CLOUISLE_REF:-main}"
RAW_BASE_URL="${CLOUISLE_BASE_URL:-https://raw.githubusercontent.com/${REPOSITORY}/${REF}/deploy}"
ARCHIVE_URL="${CLOUISLE_ARCHIVE_URL:-https://github.com/${REPOSITORY}/archive/${REF}.tar.gz}"
DRY_RUN="${CLOUISLE_DRY_RUN:-0}"
AUTO_APPROVE="${CLOUISLE_YES:-0}"
SOURCE_DIR="${CLOUISLE_SOURCE_DIR:-}"
TEMP_DIR=""
CHART_PATH=""
TTY_AVAILABLE=0

if { exec 3<>/dev/tty; } 2>/dev/null; then
  TTY_AVAILABLE=1
fi

cleanup() {
  if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
    rm -rf "$TEMP_DIR"
  fi
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

prompt() {
  local label="$1"
  local default_value="$2"
  local answer=""

  [[ "$TTY_AVAILABLE" == "1" ]] || die "Interactive input requires a terminal. Set CLOUISLE_DEPLOYMENT and CLOUISLE_YES=1 for non-interactive use."
  printf '%s [%s]: ' "$label" "$default_value" >&3
  IFS= read -r answer <&3 || true
  printf '%s' "${answer:-$default_value}"
}

confirm() {
  local answer=""
  if [[ "$AUTO_APPROVE" == "1" ]]; then
    return
  fi
  [[ "$TTY_AVAILABLE" == "1" ]] || die "Confirmation requires a terminal. Set CLOUISLE_YES=1 for non-interactive use."
  printf 'Continue? [Y/n]: ' >&3
  IFS= read -r answer <&3 || true
  case "${answer:-Y}" in
    Y|y|yes|YES) ;;
    *) die "Deployment cancelled" ;;
  esac
}

choose_deployment() {
  if [[ -n "${CLOUISLE_DEPLOYMENT:-}" ]]; then
    printf '%s' "$CLOUISLE_DEPLOYMENT"
    return
  fi

  [[ "$TTY_AVAILABLE" == "1" ]] || die "Set CLOUISLE_DEPLOYMENT=docker or CLOUISLE_DEPLOYMENT=helm."
  printf '\nChoose a deployment target:\n' >&3
  printf '  1) Docker Compose (single server)\n' >&3
  printf '  2) Kubernetes with Helm\n' >&3
  printf 'Selection [1]: ' >&3
  local selection=""
  IFS= read -r selection <&3 || true
  case "${selection:-1}" in
    1) printf 'docker' ;;
    2) printf 'helm' ;;
    *) die "Invalid deployment selection: $selection" ;;
  esac
}

download() {
  local url="$1"
  local destination="$2"
  curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 "$url" -o "$destination"
}

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
  fi
}

set_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  local temporary="${file}.tmp.$$"

  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    index($0, key "=") == 1 { print key "=" value; found = 1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$file" > "$temporary"
  mv "$temporary" "$file"
}

ensure_secret() {
  local file="$1"
  local key="$2"
  local insecure_value="${3:-}"
  local current=""

  current="$(awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$file")"
  if [[ -z "$current" || ( -n "$insecure_value" && "$current" == "$insecure_value" ) ]]; then
    set_env_value "$file" "$key" "$(random_secret)"
  fi
}

validate_kubernetes_name() {
  [[ "$2" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || die "$1 must be a valid Kubernetes DNS label: $2"
}

prepare_install_directory() {
  local install_dir="$1"

  if [[ ! -d "$install_dir" ]]; then
    if ! mkdir -p "$install_dir" 2>/dev/null; then
      require_command sudo
      log "Creating $install_dir with sudo"
      sudo mkdir -p "$install_dir"
      sudo chown "$(id -u):$(id -g)" "$install_dir"
    fi
  fi

  [[ -w "$install_dir" ]] || die "Installation directory is not writable: $install_dir"
}

install_docker() {
  require_command docker
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required"

  local install_dir="/opt/clouisle"
  if [[ "$TTY_AVAILABLE" == "1" ]]; then
    install_dir="$(prompt "Installation directory" "$install_dir")"
  fi
  install_dir="${install_dir/#\~/$HOME}"

  log ""
  log "Deployment target: Docker Compose"
  log "Installation directory: $install_dir"
  log "Configuration: $install_dir/.env"
  confirm

  prepare_install_directory "$install_dir"
  umask 077

  local compose_file="$install_dir/docker-compose.yml"
  local env_file="$install_dir/.env"
  local compose_temporary="$install_dir/.docker-compose.yml.tmp.$$"

  download "$RAW_BASE_URL/docker-compose.yml" "$compose_temporary"
  mv "$compose_temporary" "$compose_file"

  if [[ ! -f "$env_file" ]]; then
    download "$RAW_BASE_URL/.env.example" "$env_file"
  fi

  ensure_secret "$env_file" SECRET_KEY changethis-to-a-secure-random-secret-key
  ensure_secret "$env_file" POSTGRES_PASSWORD
  ensure_secret "$env_file" REDIS_PASSWORD
  ensure_secret "$env_file" QDRANT_API_KEY
  ensure_secret "$env_file" SANDBOX_ARTIFACT_UPLOAD_API_KEY
  chmod 600 "$env_file"

  local compose=(docker compose --project-directory "$install_dir" --env-file "$env_file" -f "$compose_file")
  "${compose[@]}" config --quiet

  if [[ "$DRY_RUN" == "1" ]]; then
    log "Docker Compose configuration validated. Dry run complete."
    return
  fi

  "${compose[@]}" pull
  "${compose[@]}" up -d --remove-orphans
  "${compose[@]}" ps

  log ""
  log "Clouisle is starting."
  log "Frontend: http://localhost:3000"
  log "API documentation: http://localhost:8000/docs"
  log "Configuration: $env_file"
}

write_helm_values() {
  local file="$1"
  local secret_name="$2"
  local ingress_host="$3"
  local ingress_class="$4"
  local storage_class="$5"
  local access_mode="$6"
  local image_pull_secret="$7"

  {
    printf 'secrets:\n'
    printf '  create: false\n'
    printf '  existingSecret: "%s"\n' "$secret_name"
    printf 'uploads:\n'
    printf '  accessModes:\n'
    printf '    - %s\n' "$access_mode"
    if [[ -n "$storage_class" ]]; then
      printf '  storageClassName: "%s"\n' "$storage_class"
    fi
    if [[ "$access_mode" == "ReadWriteOnce" ]]; then
      printf 'api:\n  replicas: 1\n'
      printf 'worker:\n  replicas: 1\n'
    fi
    if [[ -n "$image_pull_secret" ]]; then
      printf 'global:\n'
      printf '  imagePullSecrets:\n'
      printf '    - name: "%s"\n' "$image_pull_secret"
    fi
    if [[ -n "$ingress_host" ]]; then
      printf 'config:\n'
      printf '  FRONTEND_URL: "https://%s"\n' "$ingress_host"
      printf '  BACKEND_CORS_ORIGINS: '\''["https://%s"]'\''\n' "$ingress_host"
      printf 'ingress:\n'
      printf '  enabled: true\n'
      printf '  className: "%s"\n' "$ingress_class"
      printf '  hosts:\n'
      printf '    - host: "%s"\n' "$ingress_host"
      printf '      paths:\n'
      printf '        api:\n          path: /api\n          pathType: Prefix\n'
      printf '        frontend:\n          path: /\n          pathType: Prefix\n'
    else
      printf 'ingress:\n  enabled: false\n'
    fi
  } > "$file"
}

prepare_chart() {
  if [[ -n "$SOURCE_DIR" ]]; then
    CHART_PATH="$SOURCE_DIR/deploy/helm/clouisle"
    return
  fi

  require_command tar
  TEMP_DIR="$(mktemp -d)"
  local archive="$TEMP_DIR/source.tar.gz"
  local source="$TEMP_DIR/source"
  mkdir -p "$source"
  download "$ARCHIVE_URL" "$archive"
  tar -xzf "$archive" -C "$source" --strip-components=1
  CHART_PATH="$source/deploy/helm/clouisle"
}

install_helm() {
  require_command helm

  local namespace="${CLOUISLE_NAMESPACE:-}"
  local release_name="${CLOUISLE_RELEASE:-}"
  local ingress_host="${CLOUISLE_INGRESS_HOST:-}"
  local ingress_class="${CLOUISLE_INGRESS_CLASS:-nginx}"
  local storage_class="${CLOUISLE_STORAGE_CLASS:-}"
  local access_mode="${CLOUISLE_STORAGE_ACCESS_MODE:-ReadWriteMany}"
  local image_pull_secret="${CLOUISLE_IMAGE_PULL_SECRET:-}"
  local secret_name="${CLOUISLE_SECRET_NAME:-clouisle-secret}"

  [[ -n "$namespace" ]] || namespace="$(prompt "Kubernetes namespace" "clouisle")"
  [[ -n "$release_name" ]] || release_name="$(prompt "Helm release name" "clouisle")"
  if [[ -z "${CLOUISLE_INGRESS_HOST+x}" ]]; then
    ingress_host="$(prompt "Ingress hostname (empty disables Ingress)" "")"
  fi
  if [[ -z "${CLOUISLE_STORAGE_CLASS+x}" ]]; then
    storage_class="$(prompt "RWX StorageClass (empty uses cluster default)" "")"
  fi
  if [[ -z "${CLOUISLE_IMAGE_PULL_SECRET+x}" ]]; then
    image_pull_secret="$(prompt "Existing imagePullSecret (empty if ACR is public)" "")"
  fi

  validate_kubernetes_name "Namespace" "$namespace"
  validate_kubernetes_name "Release name" "$release_name"
  validate_kubernetes_name "Secret name" "$secret_name"
  [[ "$access_mode" == "ReadWriteMany" || "$access_mode" == "ReadWriteOnce" ]] || die "CLOUISLE_STORAGE_ACCESS_MODE must be ReadWriteMany or ReadWriteOnce"
  [[ -z "$ingress_host" || "$ingress_host" =~ ^[A-Za-z0-9.-]+$ ]] || die "Ingress hostname contains unsupported characters"
  [[ -z "$storage_class" || "$storage_class" =~ ^[A-Za-z0-9._-]+$ ]] || die "StorageClass contains unsupported characters"
  [[ -z "$image_pull_secret" ]] || validate_kubernetes_name "imagePullSecret" "$image_pull_secret"

  log ""
  log "Deployment target: Kubernetes with Helm"
  log "Namespace: $namespace"
  log "Release: $release_name"
  log "Ingress: ${ingress_host:-disabled}"
  log "Uploads access mode: $access_mode"
  log "Uploads StorageClass: ${storage_class:-cluster default}"
  confirm

  prepare_chart
  local chart="$CHART_PATH"
  [[ -f "$chart/Chart.yaml" ]] || die "Helm chart not found: $chart"

  if [[ -z "$TEMP_DIR" ]]; then
    TEMP_DIR="$(mktemp -d)"
  fi
  local values_file="$TEMP_DIR/clouisle-installer-values.yaml"
  write_helm_values "$values_file" "$secret_name" "$ingress_host" "$ingress_class" "$storage_class" "$access_mode" "$image_pull_secret"

  helm lint "$chart" -f "$values_file"

  if [[ "$DRY_RUN" == "1" ]]; then
    helm template "$release_name" "$chart" --namespace "$namespace" -f "$values_file" >/dev/null
    log "Helm chart validated. Dry run complete."
    return
  fi

  require_command kubectl
  kubectl cluster-info >/dev/null
  kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

  if ! kubectl -n "$namespace" get secret "$secret_name" >/dev/null 2>&1; then
    kubectl -n "$namespace" create secret generic "$secret_name" \
      --from-literal=SECRET_KEY="$(random_secret)" \
      --from-literal=POSTGRES_PASSWORD="$(random_secret)" \
      --from-literal=REDIS_PASSWORD="$(random_secret)" \
      --from-literal=QDRANT_API_KEY="$(random_secret)" \
      --from-literal=SANDBOX_ARTIFACT_UPLOAD_API_KEY="$(random_secret)" >/dev/null
  fi

  helm upgrade --install "$release_name" "$chart" \
    --namespace "$namespace" \
    --create-namespace \
    -f "$values_file" \
    --wait \
    --timeout 15m

  kubectl -n "$namespace" get pods
  log ""
  if [[ -n "$ingress_host" ]]; then
    log "Clouisle URL: https://$ingress_host"
  else
    log "Ingress is disabled. Access the frontend with:"
    log "kubectl -n $namespace port-forward service/frontend 3000:3000"
  fi
}

main() {
  require_command curl

  case "$(choose_deployment)" in
    docker) install_docker ;;
    helm) install_helm ;;
    *) die "CLOUISLE_DEPLOYMENT must be docker or helm" ;;
  esac
}

main "$@"
