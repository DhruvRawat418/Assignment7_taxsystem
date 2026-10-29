# Browser case lifecycle implementation

1. Test persistent create/read/answer, duplicate ID rejection, stale-token rejection,
   safe real-image upload, incomplete-run rejection and real-provider handoff.
2. Implement a case service around existing SQLite interview/team graphs and an
   explicit credential-binding factory for the current model connector.
3. Add create/resume/one-question/upload/check screens, session-only model settings,
   workspace visibility and supported source/reviewer retry actions.
4. Verify UI create-to-draft and interrupted/resumed case using actual OCR and MCP
   with fake external-model responses. Run original full suite, native OCR tests,
   browser interaction and one independent review. Preserve teammate sources
   except narrowly required connector/integration changes, document local OCR pin.
5. Commit to the local feature branch and update the handoff package. No push,
   main merge, automatic paid call or simulated-data fallback in the user flow.
