# Developing an application provider

L1ght5p33d extends OpenAdapt Flow. Its managed registry accepts ASCII JSON
envelopes around native Flow workflows. The existing interpreter owns graph
traversal, typed effects, checkpoints and recovery. Providers supply application
operations and fresh observations; they do not implement another workflow engine.

## Provider contract

Implement the synchronous protocol in
`packages/l1ght5p33d/src/l1ght5p33d/providers/base.py`:

```python
class ExampleProvider:
    name = "example"
    operations = frozenset({"fill", "save"})
    effect_tier = 4

    def execute(self, operation: str, args: dict) -> dict:
        ...

    def inspect(self) -> dict:
        ...

    def close(self) -> None:
        ...
```

`execute` performs one bounded operation and returns a receipt. `inspect` reads
current observable state. `close` releases resources without discarding the
user's work. The service uses a worker thread; browser and COM objects must
remain on their owning thread.

The preview uses an explicit registry in `WorkflowService._provider`. Workflows
cannot import modules or install plugins. Add the provider there and grant its
name and operations in local policy. Separately installable entry-point plugins
are planned, not implemented.

## Native workflow binding

```json
{
  "id": "save-artwork",
  "intent": "Save the prepared artwork",
  "action": "wait",
  "api_binding": {
    "kind": "tool",
    "on_unavailable": "halt",
    "url_template": "example",
    "method": "save",
    "body_template": {"name": "{artwork_name}"},
    "effects": [{
      "kind": "field_equals",
      "match": {"provider": "example"},
      "field": "save_state",
      "value": "Saved"
    }]
  }
}
```

`action: "wait"` preserves the native Step shape. The registered tool binding
delivers the action; `on_unavailable: "halt"` prevents an invented GUI fallback.
Simple named placeholders bind declared parameters. They cannot traverse Python
attributes, index objects, or execute expressions.

Every action requires an effect contract. `ProviderVerifier` supplies fresh
`inspect()` records to Flow's effect judge. An on-screen Saved label uses tier 4.
Reserve tier 1 for a separately observed authoritative result; returning the
requested value from memory is not verification. Shipped GUI providers use tier
4 and do not claim that UI readback proves durable persistence.

## Input and failure rules

Prefer an authorized official API, browser DOM/accessibility, Windows UIA/Win32,
then declared local OCR or image matching. Relative input belongs inside a
verified window or matched anchor. Reject ambiguous targets rather than choosing
the first of several matching buttons.

Check application identity immediately before input. Browser providers bind a
dedicated page, expected origin and title. Windows providers bind executable,
PID, process creation time, HWND, title pattern, bounds, display, DPI and
foreground state. A selector must not silently switch applications.

Raise `ProviderRefused` only when no input was delivered. After input might have
started, raise an ordinary exception. The actuator treats that case as uncertain
delivery and halts instead of trying another selector or repeating the action.
Retry bounded selector discovery and reads when safe; do not repeat an import
merely because its response was slow.

Receipts should include action, attempted selectors, successful method,
application identity, confidence, retry count, fallback and observed
verification. The runtime adds step IDs, duration, variables, effects and
recovery status. Do not return screenshots, credentials, session storage or
cookies. Authentication is manual in this preview.

## Permissions and tests

Installed providers are trusted local Python code, not a sandbox. Do not add
arbitrary shell, JavaScript, import, file-read or process-launch commands.
Validate paths and URLs in policy and in the provider where applicable.
Workflows require local approval of their exact digest. Trusted CLI demos grant
only their generated fixture documents; an AI patch cannot expand that grant.

Test identity mismatch, absent/ambiguous selectors, fallback ordering, low
confidence, path escape, pre-delivery refusal, uncertain delivery and stale
evidence. Use synthetic fixtures and temporary directories. Add an opt-in live
qualification command when desktop/login access is required, and report fixture
and live results separately.

See [Windows execution](windows.md), [BandLab integration](bandlab.md), and
[workflow specification](l1ght5p33d/workflow-spec.md).
