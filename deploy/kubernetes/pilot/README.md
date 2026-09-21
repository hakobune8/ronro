# Pilot overlay values

This overlay is intentionally safe-to-edit packaging, not a secret store.
Before applying it, replace the placeholder image registry, host, TLS secret,
and (when applicable) ingress class with values for the target cluster.

The OpenAI API Secret is created out-of-band and is not part of Kustomize.
