# Evaluation-only image. This is not part of the RONRO product image.
FROM mcr.microsoft.com/playwright:v1.63.0-noble

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends pulseaudio pulseaudio-utils dbus-x11 \
    && mkdir -p /etc/chromium/policies/managed \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /runner

COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund

COPY chrome-policies/ronro-t1a-auto.json /etc/chromium/policies/managed/ronro-t1a-auto.json
COPY runner.mjs ./runner.mjs
COPY start-loopback.sh ./start-loopback.sh
RUN chmod 0755 ./start-loopback.sh \
    && chown -R pwuser:pwuser /runner

USER pwuser

ENV RONRO_AUDIO_SINK=ronro_t1a_loopback \
    RONRO_AUDIO_SINK_DESCRIPTION=RONRO_T1A_Loopback \
    RONRO_AUDIO_SOURCE=ronro_t1a_input \
    RONRO_AUDIO_SOURCE_DESCRIPTION=RONRO_T1A_Input \
    T1A_AUTO_OUTPUT=/runner/runtime/t1a-auto-summary.json

ENTRYPOINT ["/runner/start-loopback.sh"]
