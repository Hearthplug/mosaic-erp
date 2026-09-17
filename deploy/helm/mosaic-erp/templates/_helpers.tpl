{{- define "mosaic.name" -}}{{ default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}{{- end }}
{{- define "mosaic.fullname" -}}{{ default (include "mosaic.name" .) .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}{{- end }}
{{- define "mosaic.labels" -}}
app.kubernetes.io/name: {{ include "mosaic.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}
{{- define "mosaic.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mosaic.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
