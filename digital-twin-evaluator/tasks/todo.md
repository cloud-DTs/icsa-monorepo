# First implementation slice

## MQTT processing roundtrip

- [x] Add failing tests for client MQTT transport and processing reply matching.
- [x] Implement signed WSS MQTT transport, SUBACK gating, and bounded setup.
- [x] Resolve applied feedback and validate the unchanged DOUBLE echo contract.
- [x] Implement per-cycle unique values, callback timing, and error accounting.
- [x] Add the MGridICSA Balance example and common CLI/report support.
- [x] Complete real local broker validation and final regression checks.

Scope: only evaluation service source, tests, settings, and documentation.
No provisioner or deployed AWS resources are modified.

Verified: 129 tests pass, including 45 new MQTT tests. Real CRT MQTT clients
completed 12 measured and 2 warmup cycles through a temporary loopback broker
with a processing subscriber. The package wheel includes the verified source
and SDK dependency. Offline planning resolves the actual MGridICSA applied
feedback route. Reversing the exact-value match fails its regression test.
No evaluation traffic was sent to AWS. Docker was unavailable in this session;
package validation used an isolated Python wheel build.

- [x] Applied state adapter and validation tests.
- [x] Extensible evaluation registry and roundtrip with deterministic tests.
- [x] AWS adapter, CLI, reports, examples, and container.
- [x] Pipeline commands, Docker service, and integration tests.
- [x] Offline MGridICSA plan, container verification, and documentation.

Verified: 50 service tests; 131 pipeline tests and 27 subtests. Docker image
built successfully. MGridICSA planning passed with networking disabled and
through the actual orchestrator command. No evaluation traffic was sent to AWS.

## Parallel roundtrip

- [x] Add concurrency and scheduler regression tests.
- [x] Implement bounded worker execution, timestamps, and warmup ordering.
- [x] Initialize SDK clients before workers and configure connection pools.
- [x] Update examples and run the full test suite.
- [x] Verify the Docker image and pipeline config without AWS traffic.

Verified parallel execution: 84 service tests; 151 pipeline tests and 29 subtests.
The local Docker image passed 770 simulated cycles in each mode (storage and
ingestion), with peak concurrency 20. AWS clients were substituted and Docker
networking was disabled; no evaluation traffic was sent to AWS.
