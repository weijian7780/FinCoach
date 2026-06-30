# FinCoach Project Context

## UI Reference

- Use `G:\My Drive\FYP 1 & 2\FinCoach UI` as the visual reference for the FinCoach Android application.
- If that folder contains another nested folder, ignore the nested folder unless the user explicitly points to it.
- When implementing screens, preserve the existing FinCoach UI direction instead of inventing a new visual style.

## Current Implementation Status

- Completed modules:
  - User Management: login and logout flows.
  - Financial Profile Management.
- Remaining modules should be built one by one, step by step:
  - Transaction and Receipt Capture.
  - Budget and Category Limit Management.
  - Savings Goal Management.
  - Financial Data Export and Backup.
  - AI Financial Coaching.
  - Financial Report and Analytics.
  - Alert and Reminder Management.

## Stack Decisions

- Frontend: React Native with Expo for Android development.
- Backend platform: Supabase Backend as a Service.
- Database: PostgreSQL through Supabase.
- Vector search: pgvector.
- LLM service layer: FastAPI for AI/RAG-related services.

## Working Rules

- Keep implementation staged. Do not expand into multiple unfinished modules unless the user explicitly asks.
- Preserve module boundaries. Financial Profile Management should store stable user context and personalization data, not absorb budgeting, savings, reporting, backup, alert, or AI-coaching logic.
- Prefer existing project patterns in `fincoach-mobile` before adding new abstractions.
- For Supabase work, keep schema, Row Level Security, and client usage aligned with the active module being implemented.
- For AI Financial Coaching, keep the FastAPI and pgvector responsibilities separate from the React Native UI layer.
