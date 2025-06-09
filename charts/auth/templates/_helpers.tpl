{{/*
Expand the name of the chart.
*/}}
{{- define "invoiceflow-auth.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "invoiceflow-auth.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "invoiceflow-auth.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "invoiceflow-auth.labels" -}}
helm.sh/chart: {{ include "invoiceflow-auth.chart" . }}
{{ include "invoiceflow-auth.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: authentication
app.kubernetes.io/part-of: invoiceflow
{{- end }}

{{/*
Selector labels
*/}}
{{- define "invoiceflow-auth.selectorLabels" -}}
app.kubernetes.io/name: {{ include "invoiceflow-auth.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "invoiceflow-auth.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "invoiceflow-auth.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the secret to use
*/}}
{{- define "invoiceflow-auth.secretName" -}}
{{- if .Values.secrets.jwtSecret.existingSecret }}
{{- .Values.secrets.jwtSecret.existingSecret }}
{{- else }}
{{- include "invoiceflow-auth.fullname" . }}
{{- end }}
{{- end }}

{{/*
Generate JWT secret
*/}}
{{- define "invoiceflow-auth.jwtSecret" -}}
{{- if .Values.secrets.jwtSecret.existingSecret }}
{{- /* Use existing secret */ -}}
{{- else if .Values.secrets.jwtSecret.generate }}
{{- randAlphaNum 32 | b64enc }}
{{- else }}
{{- required "JWT secret is required" .Values.secrets.jwtSecret.value | b64enc }}
{{- end }}
{{- end }}

{{/*
Generate database URL
*/}}
{{- define "invoiceflow-auth.databaseUrl" -}}
{{- if .Values.secrets.databaseUrl.existingSecret }}
{{- /* Use existing secret */ -}}
{{- else }}
{{- .Values.secrets.databaseUrl.value | b64enc }}
{{- end }}
{{- end }}

{{/*
Image name
*/}}
{{- define "invoiceflow-auth.image" -}}
{{- $registry := .Values.image.registry }}
{{- if .Values.global.imageRegistry }}
{{- $registry = .Values.global.imageRegistry }}
{{- end }}
{{- printf "%s/%s:%s" $registry .Values.image.repository (.Values.image.tag | default .Chart.AppVersion) }}
{{- end }}

{{/*
Return the proper image pull secrets
*/}}
{{- define "invoiceflow-auth.imagePullSecrets" -}}
{{- $pullSecrets := list }}
{{- if .Values.global.imagePullSecrets }}
{{- $pullSecrets = .Values.global.imagePullSecrets }}
{{- end }}
{{- if .Values.image.pullSecrets }}
{{- $pullSecrets = append $pullSecrets .Values.image.pullSecrets }}
{{- end }}
{{- if (not (empty $pullSecrets)) }}
imagePullSecrets:
{{- range $pullSecrets }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create ingress hostname
*/}}
{{- define "invoiceflow-auth.ingressHost" -}}
{{- if .Values.ingress.hosts }}
{{- (first .Values.ingress.hosts).host }}
{{- else }}
{{- printf "%s.%s" (include "invoiceflow-auth.fullname" .) .Values.clusterDomain }}
{{- end }}
{{- end }}

{{/*
Validate configuration
*/}}
{{- define "invoiceflow-auth.validateConfig" -}}
{{- if and (not .Values.secrets.jwtSecret.existingSecret) (not .Values.secrets.jwtSecret.generate) (not .Values.secrets.jwtSecret.value) }}
{{- fail "JWT secret must be provided via existingSecret, generate=true, or value" }}
{{- end }}
{{- if and (not .Values.secrets.databaseUrl.existingSecret) (not .Values.secrets.databaseUrl.value) }}
{{- fail "Database URL must be provided via existingSecret or value" }}
{{- end }}
{{- end }} 