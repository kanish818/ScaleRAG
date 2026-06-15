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
  Upload one or more `PDF`, `HTML`, or `CSV` files.
  Response status is `202 Accepted` because ingestion continues in the background.
- `GET /api/documents/`
  Lists the current user's uploaded documents and processing state.
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
