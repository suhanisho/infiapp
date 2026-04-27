# DynamoDB Table Specs

Each DynamoDB table is declared as one JSON file under the owning agent folder:

```text
dynamodb/<agent_name>/<table_id>.json
```

Required fields:

- `table_name`: deployed DynamoDB table name.
- `primary_key.partition_key`: object with `name` and repo scalar `type`.
- `primary_key.sort_key`: object with `name` and repo scalar `type`, or `null`.
- `attributes`: object mapping attribute names to repo scalar types.

Inferred/defaulted fields:

- The owning agent is inferred from the parent folder name.
- Billing mode is hardcoded to `PAY_PER_REQUEST`.

Supported attribute types:

- `String`
- `Number`
- `Binary`
- `Boolean`

Partition and sort keys must use `String`, `Number`, or `Binary`. Repo tools map these to DynamoDB API types `S`, `N`, and `B` during deploy and deployed-state verification.

Backwards compatibility:

- Partition key name and type must not change.
- Sort key presence, name, and type must not change.
- Non-key attributes may be added, changed, or removed.

`repo_tools/validate_dynamodb.py` validates every table and checks key compatibility against either Git history or `.infiapp/table-key-baseline.json` when that baseline exists.
