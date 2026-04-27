# DynamoDB Table Specs

Each DynamoDB table is declared as one JSON file under the owning agent folder:

```text
dynamodb/<agent_name>/<table_id>.json
```

Required fields:

- `primary_key.partition_key`: object with `name` and repo scalar `type`.
- `primary_key.sort_key`: object with `name` and repo scalar `type`, or `null`.
- `attributes`: object mapping attribute names to repo scalar types.

Inferred/defaulted fields:

- The deployed DynamoDB table name is inferred from the JSON filename.
- The owning agent is inferred from the parent folder name.
- Billing mode is hardcoded to `PAY_PER_REQUEST`.

Supported attribute types:

- `String`
- `Number`
- `Binary`
- `Boolean`
- `List`
- `Map`

`List` and `Map` are for non-key attributes and generate Python helper types of `list[Any]` and `dict[str, Any]`.

Partition and sort keys must use `String`, `Number`, or `Binary`. Repo tools map these scalar key types to DynamoDB API types `S`, `N`, and `B` during deploy and deployed-state verification.

Backwards compatibility:

- Partition key name and type must not change.
- Sort key presence, name, and type must not change.
- Non-key attributes may be added, changed, or removed.

`repo_tools/validate_dynamodb.py` validates every table and checks key compatibility against `main` on pull requests. When running on `main`, it checks against the previous commit.
