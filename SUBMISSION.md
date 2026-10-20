# SealRoute — draft submission material

**Tagline:** Let AI suggest the queue without handing it the incident body or the keys.

**Intended event/track:** Mathematics for systems security, AI pipeline secret sharing. This document is preparation, not a Devpost draft or submission receipt.

## Inspiration

An AI assistant often needs to choose where work belongs before anyone should let it read sensitive incident details. SealRoute explores a smaller permission boundary: give a model the deliberately public intent it needs for a routing suggestion, while keeping the incident body encrypted and the decryption authority local.

## What it does

The terminal prototype seals a fictional incident body using AES-GCM. A hosted Qwen3 4B model receives public intent, authorized queue labels and an encrypted envelope. The local client accepts only one exact allowlisted queue label. The operator must explicitly approve local review before the fictional body is recovered. The application never delivers an incident, sends email or executes model commands.

The model does not understand the encrypted body. Public intent is deliberately disclosed and can reveal its topic. This is not fully homomorphic encryption or a promise that all inputs are hidden.

## How it was built

Python and the cryptography package provide authenticated encryption; public metadata is bound as associated data. A fresh key stays in each process, with fresh nonces tracked within the session. A small standard-library HTTP adapter calls a public Hugging Face Space's documented named Gradio API without an account, cookie session or paid fallback. The terminal interface shows the disclosure boundary, raw model output, local allowlist result and operator decision.

The current model is Qwen/Qwen3-4B-Instruct-2507, remotely hosted by Zacheus10/free-ai-chat. The model and Space metadata identify Apache-2.0 licensing. No weights or third-party Space implementation were redistributed. Codex generated this project's implementation, synthetic fixtures, tests and explanatory text; no unaided participant authorship, personal learning or user study is claimed.

## Challenges and evidence

Earlier SmolLM2 CPU experiments returned malformed output or misclassified billing requests as account-access requests. The local boundary refused malformed output and left wrong-but-authorized proposals for review. A different hosted model then returned all six expected labels in one batch of synthetic paraphrases. A separate live terminal billing run completed proposal, explicit local approval and synthetic decryption with no delivery.

Eighteen tests cover tampering, metadata binding, wrong keys, private-material exclusion, invalid proposals, local approval, per-session replay and bounded API result handling. Six successful designed scenarios are not a general accuracy benchmark. The included small raw outbound and result records allow inspection of what actually reached the provider. A later transport revision enforces byte limits before reading oversized responses; its additional failure tests are offline and do not imply another live inference experiment.

## What the prototype establishes

A useful hosted-model role can be narrower than plaintext custody: interpreting public intent while encryption and approval remain local. Standard cryptography and a constrained model proposal can be combined without claiming a new cipher or secret semantic computation.

## Next steps

Broader independent routing evaluation, accessible terminal ergonomics, authenticated recipient key exchange and durable replay controls require further work. The public Space is a limited third-party demo, not a production SLA. An authenticated paid quota is not used; anonymous quota exhaustion stops the request. Real incident data and deployment are out of scope for this synthetic prototype.

## Requirements and remaining platform steps

- Official video requirement is optional; no video is included under the user's no-video constraint.
- A local TUI and actual hosted API evidence address the observed AI-track criteria. The organizer ultimately determines scoring and eligibility.
- Registration, event-specific legal assent, final source/story readback and the existing single final sender's submission contract remain platform steps; no completion is asserted here.
- Public source repository created: https://github.com/estona815/sealroute-mathsecurity-2026
