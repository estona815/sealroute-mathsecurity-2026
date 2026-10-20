"""Synthetic-only terminal demonstration; network use requires --live."""
import argparse
import datetime
import json
from pathlib import Path
import sys

from sealroute import Session, build_prompt, canonical, fingerprint
from hosted import BASE, MODEL, BACKEND, payload_for, request_model

FIXTURES = {
    "access": ("Fictional incident A: Mina Example, customer XZ-73291, contact mina@example.invalid.",
               "I forgot my password and cannot sign in", "ACCESS"),
    "billing": ("Fictional incident B: Noah Example, invoice ZX-41827, contact noah@example.invalid.",
                "I was charged twice and would like a refund", "BILLING"),
    "delivery": ("Fictional incident C: Ara Example, parcel QQ-95613, contact ara@example.invalid.",
                 "My parcel has not arrived and the tracking stopped", "DELIVERY")}


def write_new(path, value):
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=FIXTURES, default="access")
    parser.add_argument("--live", action="store_true", help="one anonymous ZeroGPU quota API request")
    parser.add_argument("--report-dir", type=Path, required=True,
                        help="new directory; refuses reuse to avoid duplicate API POSTs")
    args = parser.parse_args()
    # Exact fresh directory is a one-shot run boundary, not a global submit lock.
    args.report_dir.mkdir(parents=True, exist_ok=False)
    body, intent, expected = FIXTURES[args.fixture]
    session = Session()
    envelope = session.seal(body, intent)
    prompt = build_prompt(envelope)
    wire = canonical(payload_for(prompt))
    if body in prompt or session._key.hex() in prompt:
        raise RuntimeError("Disclosure preflight failed")
    print("╭─ SealRoute · synthetic incident desk ───────────────────╮")
    print("│ Sealed body → public intent → AI proposal → local review│")
    print("╰────────────────────────────────────────────────────────╯")
    print("PUBLIC INTENT:", intent)
    print("SEALED BODY:", len(body.encode()), "bytes →", len(envelope.ciphertext), "base64 characters")
    print("DISCLOSURE: intent, queue names, random ID, nonce, ciphertext and length.")
    print("PRIVATE: fictional body and session key stay local. No real data accepted by this demo.")
    print("No inference over hidden plaintext. No incident delivery.")
    write_new(args.report_dir / "outbound.json", json.loads(wire))
    write_new(args.report_dir / "intent.json", {
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "fixture": args.fixture, "live": args.live, "endpoint": BASE if args.live else None,
        "model": MODEL if args.live else None, "backend": BACKEND if args.live else None,
        "outbound_sha256": fingerprint(wire), "body_bytes": len(body.encode()),
        "body_absent_from_wire": body.encode() not in wire,
        "session_key_not_serialized": session._key.hex().encode() not in wire,
        "expected_queue": expected})
    if args.live:
        def submitted(event_id):
            write_new(args.report_dir / "submitted.json", {"event_id": event_id,
                      "instruction": "Do not POST again after uncertainty; inspect this event."})
        try:
            result = request_model(prompt, on_submitted=submitted)
        except Exception as error:
            write_new(args.report_dir / "unresolved.json", {"error_type": type(error).__name__,
                      "note": "Outcome unconfirmed. No automatic retry."})
            print("API outcome unresolved; inspect saved event before any retry.")
            return 2
    else:
        result = {"terminal": "offline_fixture", "response": expected,
                  "note": "Deterministic fixture, NOT a model response"}
    write_new(args.report_dir / "result.json", result)
    if "response" not in result:
        print("API terminal error; no proposal to review.")
        return 2
    print("MODEL RESPONSE:" if args.live else "OFFLINE FIXTURE:", repr(result["response"]))
    try:
        queue = session.validate_proposal(envelope, result["response"])
    except ValueError:
        write_new(args.report_dir / "review.json", {"state": "REJECTED_INVALID_PROPOSAL",
                                                   "local_delivery": False})
        print("REJECTED: model output does not match the local allowlist.")
        return 3
    print("LOCAL PROPOSAL:", queue, "· Correct fixture label:", expected)
    print("The allowlist checks authority, not whether the model understood the intent.")
    if not sys.stdin.isatty():
        write_new(args.report_dir / "review.json", {"state": "AWAITING_OPERATOR_REVIEW",
                  "queue": queue, "matches_fixture": queue == expected, "local_delivery": False})
        print("AWAITING OPERATOR REVIEW. No interactive approval; no delivery or decryption.")
        return 0
    choice = input("Type the displayed queue label to approve a LOCAL synthetic review, or Enter to cancel: ")
    if choice != queue:
        print("Cancelled. Body remains sealed; no delivery.")
        write_new(args.report_dir / "review.json", {"state": "OPERATOR_CANCELLED", "local_delivery": False})
        return 0
    reviewed = session.commit_local_review(envelope, result["response"], approved=True)
    # Do not export plaintext or key in evidence; reveal only this synthetic body locally.
    print("LOCAL FICTIONAL BODY:", reviewed["body"])
    print("NO DELIVERY. Session replay now refused.")
    write_new(args.report_dir / "review.json", {"state": "LOCAL_SYNTHETIC_REVIEW_COMPLETED",
              "queue": queue, "matches_fixture": queue == expected, "local_delivery": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
