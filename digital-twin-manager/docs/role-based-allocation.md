# Role-based twin allocation: provisioning order and dependencies

This page details paper Section IV-B. The deployer reads the four configuration files of a twin and provisions its resources in an order that satisfies their dependencies.

## Deployment order

[`deployers/aws/all.py`](../src/deployers/aws/all.py) runs five groups in this order: `core`, `iot`, `hierarchy`, `event_actions` and `init_values`. `destroy` runs them in reverse. The `core` group has the layers of [Core Infrastructure Layers](core-infrastructure-layers.md): L1 (dispatcher), L2 (processing, persistence, events), L3 (hot, cold and archive storage), L4 (TwinMaker) and L5 (Grafana). The `iot` group creates the per-device resources, `hierarchy` the TwinMaker entities and components, `event_actions` the Lambda functions of the actions, and `init_values` publishes the initial values.

## Dependency templates

[`dependency/template.json`](../dependency/template.json) lists the 72 resource templates of the deployer. A template has:

- an `id` of the form `group:layer:name:type`, for example `iot:l1:iot_thing:iot_thing`,
- the `owner_deployer` that creates it,
- `depends_on`, a list of template ids, each with a type: `create_after` (creation order), `runtime_uses` (used while the twin runs) or `blocks_delete` (must not be deleted while another resource needs it),
- optionally `lifecycle_artifact`, for parts of a resource such as a permission, a backup or a cleanup step.

[`dependency_graph/validation.py`](../src/dependency_graph/validation.py) checks the ids, the references and that the `create_after` edges have no cycle.

## Runtime graph

[`build_runtime_graph`](../src/dependency_graph/runtime_graph_builder.py) expands the templates with the configuration. Shared templates give one node. The `iot:l1` and `iot:l2` templates give one node per IoT device, the `iot:l4` templates one per distinct component type, the hierarchy templates one per entity or component, the action templates one per action and the initial-value templates one per device with an initial value. Each node gets its logical and physical name. `plan` uses this graph ([`analyze_plan_dependencies`](../src/dependency_graph/dependency_analyzer.py)) to mark planned changes that other resources depend on as blocked.

The number of resources that this produces for a twin is counted by [`scripts/resource_inventory.py`](../scripts/resource_inventory.py), which also states the formula.
