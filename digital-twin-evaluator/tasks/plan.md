# Implementation plan

## MQTT processing roundtrip

The selected implementation adds `mqtt` for the existing MGridICSA Balance path.
It does not require provisioner changes. An unchanged returned input value is
the correlation key; it is randomized per sample in an explicit valid range.
Concurrency is restricted to one because actions may read latest stored values.

1. Add a signed WSS MQTT transport and verify subscription-before-publish,
   callback handling, endpoint lookup, and interruption behavior.
2. Resolve applied feedback configuration, validate target/property/range, and
   implement exact value matching with a monotonic callback completion time.
3. Register the new evaluation, add the MGridICSA example and documentation.
4. Verify deterministic cases, real local broker exchange, common reports,
   existing tests, and offline planning against applied MGridICSA state.

See todo.md for implementation and verification status.

1. Resolve applied deployment state into a provider context and typed target.
   Verify version handling, identity, ambiguous targets, and exclusion of staging.
2. Implement the evaluation registry, roundtrip protocol, and common reports.
   Verify exact correlation, retries, timeouts, errors, and warmup accounting.
3. Add the AWS adapter, CLI, and container. Verify SDK request contracts and run
   offline planning against MGridICSA without credentials or network calls.
4. Integrate an explicit evaluation service into the reproduce folder.
   Verify command dispatch, mounts, profile isolation, and error recovery.
5. Run both test suites, package the sibling service, build the container, and
   document commands and the process for adding another evaluation type.

All five steps are implemented and verified. See `todo.md` for completed checks.

## Parallel roundtrip

1. Add failing tests for bounded parallel cycles, timestamps, warmup ordering,
   independent failures, and AWS client initialization.
2. Add optional concurrency with one bounded worker pool for all targets.
3. Configure connection pooling and initialize clients before workers start.
4. Update examples and reports; verify with local substitutes and Docker offline.
