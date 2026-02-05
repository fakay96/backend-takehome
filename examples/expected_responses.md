# Example responses (from the seed database)

These examples show **shape** and **key fields**. Your JSON key ordering does not matter, but the `blocks` array order does.

## 1) GET /tenants/1/users/10/lessons/100  (initial seed)

Expected highlights:

- 3 blocks with positions [1,2,3]
- block 200 uses tenant override (tenant_id = 1)
- progress: block 200 completed, block 201 seen, block 202 null
- progress_summary:
  - total_blocks = 3
  - seen_blocks = 2
  - completed_blocks = 1
  - last_seen_block_id = 201
  - completed = false

Example (abridged):
```json
{
  "lesson": {"id": 100, "slug": "ai-basics", "title": "AI Basics"},
  "blocks": [
    {
      "id": 200,
      "type": "markdown",
      "position": 1,
      "variant": {"id": 1100, "tenant_id": 1, "data": {"markdown": "Welcome Acme team — ..."}},
      "user_progress": "completed"
    },
    {
      "id": 201,
      "type": "quiz",
      "position": 2,
      "variant": {"id": 1001, "tenant_id": null, "data": {"question": "In one sentence, what is a neural network?"}},
      "user_progress": "seen"
    },
    {
      "id": 202,
      "type": "markdown",
      "position": 3,
      "variant": {"id": 1002, "tenant_id": null, "data": {"markdown": "Summary: ..."}},
      "user_progress": null
    }
  ],
  "progress_summary": {
    "total_blocks": 3,
    "seen_blocks": 2,
    "completed_blocks": 1,
    "last_seen_block_id": 201,
    "completed": false
  }
}
```

## 2) PUT /tenants/1/users/10/lessons/100/progress with {"block_id":202,"status":"seen"}

Expected highlights:

- stored_status = "seen"
- seen_blocks becomes 3
- last_seen_block_id becomes 202

## 3) PUT ... {"block_id":202,"status":"completed"}

Expected highlights:

- stored_status = "completed"
- completed_blocks becomes 2
- A later PUT with status "seen" should **not** downgrade it.
