# MMM Operator UI

The operator UI is a private, local-first control surface for MMM editorial work. It does not replace the static public site and it does not introduce a hosted backend into the core flow.

## What it does

- generates the next weekly draft in deterministic or AI mode
- optionally generates AI artwork during draft generation
- lists current drafts and recent published mixes
- edits draft JSON safely from the browser
- approves a reviewed draft
- releases an approved draft through the guarded publish flow
- reviews YouTube candidate state and stores explicit per-track selections in `data/youtube/<slug>.json`
- shows local preview routes plus an in-session workflow log

## Run it locally

Start the normal public-site preview in one terminal:

```bash
npm run dev
```

Start the private operator UI in another terminal:

```bash
npm run operator
```

Default URL:

```text
http://127.0.0.1:4199
```

If you want a token gate even on localhost:

```bash
MMM_OPERATOR_TOKEN="choose-a-long-random-string" npm run operator
```

You can also change host, port, or preview origin explicitly:

```bash
python3 scripts/operator_server.py \
  --host 127.0.0.1 \
  --port 4199 \
  --preview-origin http://127.0.0.1:3000
```

## Private tunnel pattern

The intended remote-use pattern is:

1. keep the operator server bound to `127.0.0.1`
2. set `MMM_OPERATOR_TOKEN`
3. expose it through your private network path or a Cloudflare tunnel
4. optionally add Cloudflare Access in front as a second gate

Example tunnel command:

```bash
MMM_OPERATOR_TOKEN="choose-a-long-random-string" npm run operator
cloudflared tunnel --url http://127.0.0.1:4199
```

Notes:

- Without a token, the server is intentionally localhost-only.
- The token gate is simple and pragmatic, not a full identity system.
- Cloudflare Access is a good additional outer layer when exposing the UI outside the machine.

## Browser workflow

1. open the operator UI
2. generate or pick a draft
3. edit title, summary, notes, tags, and tracks
4. save draft JSON
5. approve when reviewed
6. release when ready
7. pick a published mix, refresh YouTube candidates, and explicitly choose or clear each track match until the embed queue resolves

## Safety notes

- Draft edits are written with an atomic replace so partial JSON writes do not land on disk.
- Approval and release still go through the existing MMM approval and release logic.
- YouTube manual review preserves the existing saved candidate set and only updates explicit human selections plus the derived embed summary.
