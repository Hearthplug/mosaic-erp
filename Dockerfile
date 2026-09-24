# Pinned multi-architecture base. Dependabot updates the digest through reviewed PRs.
FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ARG SOURCE_DATE_EPOCH=0
ARG VCS_REF=unknown
ARG VERSION=dev
LABEL org.opencontainers.image.title="Mosaic ERP" \
      org.opencontainers.image.description="Conversational retail ERP architect" \
      org.opencontainers.image.source="https://github.com/Hearthplug/mosaic-erp" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.licenses="MIT"

ENV MOSAIC_HOST=0.0.0.0 \
    PORT=8000 \
    MOSAIC_DB_PATH=/data/mosaic.db \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 10001 mosaic \
 && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin mosaic \
 && install -d -o mosaic -g mosaic -m 0700 /data
WORKDIR /app
COPY --chown=10001:10001 requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt
COPY --chown=10001:10001 app.py oauth.py provider_assets.py store.py postgres_store.py postgres_erp_schema.py migration_schema.py migration_packs.py tax_verification_schema.py provisioning_schema.py provisioning.py identity.py extra_packs.py accounting.py accounting_schema.py retail.py retail_schema.py operational_profile.py onboarding.py onboarding_schema.py operating_model.py operating_model_schema.py rbac.py tax_engine.py branding.py business_twin.py assistant_setup.py assistant_setup_schema.py assistant_preview.py assistant_preview_schema.py artifact_builder.py artifact_builder_schema.py static.html static.css static.js interview.html interview.css interview.js retail.html retail.css retail.js accounting.html accounting.css accounting.js migration.html migration.css migration.js operations.html operations.css operations.js signin.html signin.css signin.js invite.html invite.js auth.js assistant.html assistant.css assistant.js assist.css assist.js jev_client.py jev_mapper.py jev_reconfigure.py byok_clients.py ai_prefs.py ai_prefs_schema.py mosaic-logo.svg LICENSE ./
COPY --chown=10001:10001 local_assistant_finetune/v3/runtime.py local_assistant_finetune/v3/intent_label.gbnf local_assistant_finetune/v3/label_map.json local_assistant_finetune/v3/slot_schemas.json local_assistant_finetune/v3/
USER 10001:10001
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)"]
ENTRYPOINT ["python", "app.py"]
CMD ["serve"]
