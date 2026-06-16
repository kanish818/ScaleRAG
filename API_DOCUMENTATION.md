# API Documentation

Interactive OpenAPI docs are available at `/docs` and `/redoc` when the backend is running.

## Authentication

- `POST /api/auth/register`
  Creates a user and returns a bearer token.
- `POST /api/auth/login`
  Authenticates an existing user and returns a bearer token.
- `GET /api/auth/google`
  Starts Google OAuth.
- `GET /api/auth/google/callback`
  Completes Google OAuth and redirects back to the frontend.
- `GET /api/auth/me`
  Returns the current authenticated user.

## Documents

- `POST /api/documents/upload`
  Upload one or more `PDF`, `HTML`, or `CSV` files. Supports bounded batched ingestion and optional namespace isolation.
  Response status is `202 Accepted` because ingestion continues in the background.
- `GET /api/documents/namespaces`
  Lists isolated document namespaces available to the authenticated user.
- `GET /api/documents/`
  Lists the current user's uploaded documents and processing state. Supports namespace-scoped listing.
- `DELETE /api/documents/namespaces/{namespace}`
  Deletes an isolated namespace and its associated uploaded documents.
- `DELETE /api/documents/{doc_id}`
  Deletes a document, its chunks, and its stored object.

## Chat

- `GET /api/chat/conversations`
  Lists saved conversations.
- `POST /api/chat/conversations`
  Creates a conversation scoped to selected document IDs.
- `DELETE /api/chat/conversations/{conv_id}`
  Deletes a conversation and its messages.
- `GET /api/chat/conversations/{conv_id}/messages`
  Returns stored conversation history.
- `POST /api/chat/conversations/{conv_id}/stream`
  Streams a chat answer over Server-Sent Events.

### Stream events

- `chunk`: partial model output
- `sources`: cited source chunks
- `hallucination`: grounding score and label
- `done`: terminal event
- `error`: error payload

## Operations

- `GET /`
  Basic service health.
- `GET /health`
  Detailed health, including database/storage status.
- `GET /metrics`
  Prometheus metrics endpoint.

## Evaluator guidance

For the public Render deployment, the most reliable scripted evaluation path is:

1. authenticate,
2. upload documents in batches of `25` to `50`,
3. poll `GET /api/documents/` until `ready`,
4. run sampled chat checks instead of a full uncontrolled public stress sweep.

This uses the real production paths while staying within the limits of the public demo environment.
