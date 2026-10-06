# Account Service Pilot demo switch

This candidate replaces the old Pilot **entrypoint**, not the service GA gate.
It uses the registered RONRO-only ZITADEL client and actual microphone audio.
The browser explains that all participants must consent, that raw audio is not
recorded on this route, and that meeting data has no restart/recovery guarantee.
The dedicated PostgreSQL data directory is Pod-local `emptyDir`; do not attach
the old evaluation/audio PVC or a backup. The existing Pilot PVC is not
deleted by these manifests.

The new Deployment is installed and checked for local readiness first. Then
change only the existing `ronro-pilot` Service selector to
`ronro-service-demo` (retain its NodePort type and port numbers) and run the
real-browser login/audio smoke through the fixed public OIDC callback. If that
smoke fails, restore the old selector. The edge NodePorts and `/live` path
remain unchanged. After a passing smoke, scale the old Deployment down; do
not delete its PVC as part of this switch.

The account operator screen is `/service-demo`; it opens `/shared` in a separate
view-only browser tab for the **same authenticated account**. `/shared` reuses
the established Semantic Canvas renderer and reads the owner-authorized
`/api/service/sessions/{id}/canvas` projection. The session identifier is
passed in the URL fragment, not a query or bearer credential. A different
device/browser is not authorized by this link; do not treat it as a public
participant sharing URL. The `ended_incomplete` final canvas retains its
recording-gap notice. This is a Pilot integration, not the GA sharing model.

The dedicated `ronro-service-demo-db` Secret (keys `password` and `dsn`) must
be created out-of-band. The DSN must point to
`127.0.0.1:5432/ronro_pilot_demo`, user `ronro_demo`, and the Secret password.
Never commit the Secret or print it to logs. The image must be replaced by the
CI-published immutable digest before application.

This route is for a short, consented Pilot demonstration. It does not satisfy
the Account Service v1 seven-day retention/recovery acceptance. A restart may
leave old encrypted rows inaccessible and consume session capacity; do not
silently claim those meetings are recoverable or automatically delete them.
