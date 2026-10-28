# Complete case lifecycle in the existing browser workbench

The user identified a missing required flow: staff can review saved cases but
cannot create a case or conduct Intake from the GUI. Add these actual workflows
to the existing Streamlit app, using Hanna's interview graph and the integrated
team graph rather than copied interview/calculation logic.

Scope: create collision-safe case IDs; save and resume each single-question
interview in the existing SQLite store; show unfinished interviews in the
workspace; validate and store immutable synthetic W-2 uploads under generated
names; allow the bundled actual image as an explicit convenience (never an OCR
record replacement); submit completed interviews to real Extraction/Rules/MCP/
Audit/model review; retain existing correction/stop/export gates. Missing input
and model failures require explicit supported retry paths, never a new case reset.

Use current OpenAI connector for this integrated branch. Allow its API key to be
supplied through the server environment or a password input retained only in the
current Streamlit session. Bind explicit credentials in a callable, not global
environment mutation and not graph/checkpoint state. No API call on creation,
answering, upload, page rendering or settings changes; only explicit check/retry
actions may call the model. Development tests mock only that external boundary.

Validate case IDs, stale checkpoint tokens, upload formats/size/count and paths;
prevent existing-case overwrite and arbitrary image-path entry. Preserve source
history and workflow revision/loop guards. Stop/resolution operations are
explicit and validated, with no financial overrides. Single-operator deployment
assumption remains; this does not introduce staff authentication.

Host OCR: an isolated probe verified actual image extraction plus all eight OCR
tests on ONNX Runtime1.21.1. Apply only to this local virtual environment, document
a separate macOS13 dependency profile, and preserve the team's default1.23.2 pin.
Do not claim actual model review until the user configures and runs their key.

Acceptance: a user creates a case in the GUI, answers one question at a time,
closes/reopens it, supplies a real synthetic W-2 image, explicitly runs checks,
handles a scope correction through existing controls, and exports the saved
reviewed draft. Tests and browser checks distinguish actual OCR/MCP from simulated
model replies. No terminal is required for the user after launching the app.
