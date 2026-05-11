{{- define "clouisle.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" -}}
{{- end -}}

{{- define "clouisle.labels" -}}
helm.sh/chart: {{ include "clouisle.chart" . }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.global.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{- define "clouisle.componentLabels" -}}
{{ include "clouisle.labels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "clouisle.selectorLabels" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "clouisle.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
clouisle-secret
{{- end -}}
{{- end -}}

{{- define "clouisle.configName" -}}
clouisle-config
{{- end -}}

{{- define "clouisle.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default "clouisle" .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "clouisle.backendImage" -}}
{{- printf "%s:%s" .Values.images.backend.repository .Values.images.backend.tag -}}
{{- end -}}

{{- define "clouisle.sandboxWorkerImage" -}}
{{- printf "%s:%s" .Values.images.sandboxWorker.repository .Values.images.sandboxWorker.tag -}}
{{- end -}}

{{- define "clouisle.frontendImage" -}}
{{- printf "%s:%s" .Values.images.frontend.repository .Values.images.frontend.tag -}}
{{- end -}}

{{- define "clouisle.uploadsClaimName" -}}
{{- if .Values.uploads.existingClaim -}}
{{- .Values.uploads.existingClaim -}}
{{- else -}}
uploads-data
{{- end -}}
{{- end -}}

{{- define "clouisle.envFrom" -}}
envFrom:
  - configMapRef:
      name: {{ include "clouisle.configName" . }}
  - secretRef:
      name: {{ include "clouisle.secretName" . }}
{{- end -}}

{{- define "clouisle.podCommon" -}}
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
{{ toYaml . | indent 2 }}
{{- end }}
serviceAccountName: {{ include "clouisle.serviceAccountName" . }}
{{- with .Values.global.podSecurityContext }}
securityContext:
{{ toYaml . | indent 2 }}
{{- end }}
{{- with .Values.global.nodeSelector }}
nodeSelector:
{{ toYaml . | indent 2 }}
{{- end }}
{{- with .Values.global.affinity }}
affinity:
{{ toYaml . | indent 2 }}
{{- end }}
{{- with .Values.global.tolerations }}
tolerations:
{{ toYaml . | indent 2 }}
{{- end }}
{{- end -}}

{{- define "clouisle.beatReplicaGuard" -}}
{{- if and .Values.beat.enabled (ne (int .Values.beat.replicas) 1) -}}
{{- fail "beat.replicas must be 1 to avoid duplicate scheduled tasks" -}}
{{- end -}}
{{- end -}}
