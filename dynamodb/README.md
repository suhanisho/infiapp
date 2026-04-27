# DynamoDB Table Specs

Each DynamoDB table is declared as one JSON file under the owning agent folder:

```text
dynamodb/<owner_agent>/<table_id>.json
```

Required fields:

- `table_name`: deployed DynamoDB table name.
- `owner_agent`: agent that owns the table. Must match the parent folder name.
- `billing_mode`: currently `PAY_PER_REQUEST`.
- `primary_key.partition_key`: object with `name` and DynamoDB scalar `type`.
- `primary_key.sort_key`: object with `name` and DynamoDB scalar `type`, or `null`.
- `attributes`: object mapping attribute names to DynamoDB scalar types.

Supported scalar types:

- `S`
- `N`
- `B`

Backwards compatibility:

- Partition key name and type must not change.
- Sort key presence, name, and type must not change.
- Non-key attributes may be added, changed, or removed.

`repo_tools/validate_dynamodb.py` validates every table and checks key compatibility against either Git history or `.infiloop/table-key-baseline.json` when that baseline exists.

