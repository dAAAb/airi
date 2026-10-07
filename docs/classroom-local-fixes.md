# Local classroom fixes

Base: `moeru-ai/airi@94fa5d7cc5bcfb927a65d78c25ae20377802bc32`.
Verified on 2026-10-07 with Node 26.7.0 and pnpm 11.24.0.

## Provider configuration snapshots

Synced actions return values across a `structuredClone` boundary.
Returning Vue proxies caused `DataCloneError` during local provider setup.
`ensureProvider` and config updates now return detached snapshots with `cloneDeep` from the existing `es-toolkit` dependency.
Tests cover new providers, existing providers, additions and nested config updates.

## Multiple image attachments

The second image description retained a reactive proxy from the first description.
That nested proxy broke cloning of the chat result.
The cache now retains plain description records through `toRaw`.
A regression test sends two fresh images, clones the returned result and checks cache reuse on the next turn.

## Ollama Vision thinking

The OpenAI-compatible endpoint needs the provider's reasoning mapping.
Passing native Ollama `think` directly did not disable thinking on this route.
Vision now uses AIRI's existing generation options and reasoning mapper.
Tests inspect the outgoing request for `reasoning_effort: none` or `medium` and reject a stray `think` field.

Reference: [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).

## Scope of the classroom observations

- A local green-triangle test reached the character's reply through the vision model.
- A two-image request completed after these fixes. Its comparison still contained model errors.
- Transport success does not prove image comprehension.
- `builtIn_emitSparkCommand` is a character tool call. A tool error does not, by itself, prove microphone failure.
- Local speech experiments live in [the course lab](../course/ntu-vh2026/README.zh-TW.md).

## Validation

Run commands at the repository root with the pinned pnpm version.

| Check | Result |
| --- | --- |
| Related Vitest tests across six files | 120 passed |
| `pnpm -F @proj-airi/stage-ui typecheck` | Passed |
| `pnpm exec moeru-lint` on the six changed source/test files | Zero errors, two existing long-comment warnings |
| `git diff --check` | Passed |
| `pnpm typecheck` | Failed in the partial Web installation. Electron dependencies were absent. |
| `pnpm lint` | Failed while loading docs Uno config. `@radix-ui/colors` was absent. |

The full monorepo checks are not reported as passing.
The partial classroom installation omits unrelated desktop and documentation workspaces.
No compiler settings or lint rules were disabled to hide these failures.

Re-run the targeted checks:

```sh
pnpm -F @proj-airi/stage-ui exec vitest run \
  src/composables/vision/use-vision-inference.test.ts \
  src/stores/chat.contract.test.ts \
  src/stores/providers/config.test.ts \
  src/stores/providers/config-defaults.test.ts \
  src/stores/providers/merge.test.ts \
  src/stores/providers/provider.test.ts \
  --project node
pnpm -F @proj-airi/stage-ui typecheck
pnpm exec moeru-lint \
  packages/stage-ui/src/stores/chat.ts \
  packages/stage-ui/src/stores/chat.contract.test.ts \
  packages/stage-ui/src/stores/providers/config.ts \
  packages/stage-ui/src/stores/providers/config.test.ts \
  packages/stage-ui/src/composables/vision/use-vision-inference.ts \
  packages/stage-ui/src/composables/vision/use-vision-inference.test.ts
git diff --check
```

## Explicit tool-free local conversation

Some SARC models offer conversation without tool calling. Set `VITE_AIRI_DISABLE_TOOLS=true` before starting Vite for that classroom mode:

```sh
VITE_AIRI_DISABLE_TOOLS=true sh course/ntu-vh2026/start-airi-local.sh
```

The stage LLM store sets the existing core capability `supportsTools=false`. It omits both tool definitions and tool choice. It also skips MCP, character action, and custom-tool resolution. A console warning identifies the disabled functions. VRM idle animation and speech lip sync still work.

The portable helper leaves this flag unset by default. Restart Vite after changing it. Removing the flag restores the normal tool capability behavior. This switch does not add vision capability to SARC. Use a separate configured vision model, such as the tested local Gemma model, to describe images first.

Two added regression cases check that explicit disable sends no tools or tool choice, and that `false` preserves normal tool calling. The complete `llm.test.ts` suite has 36 passing cases. Stage UI typecheck also passes.

## Per-card compatible speech IDs

OpenAI-compatible speech servers can use model and voice IDs absent from a catalog. The card editor now accepts these IDs as text. Empty fields inherit the global settings. Other provider types retain their existing selectors.

The stage resolves the selected card/module model and voice before provider-level defaults. Previously, the stage replaced card overrides with those defaults. Two cards can now share one local endpoint and use separate voices. Provider instances receive the same behavior as the built-in compatible provider ID.

The [local speech hub](../course/ntu-vh2026/local-speech-hub/README.zh-TW.md) routes `kokoro` with `zf_xiaobei` to port 8880. It routes `taigi-hanzi` with `taigi-demo-reference` to port 8883. Failed synthesis never switches languages. It records only completion metadata, without input text or audio.

Validation: all 36 speech-store tests pass, including two checks of the outgoing model/voice pairs. Two headless Chrome tests save custom IDs and empty inherited values through the card editor. The tests cover both the built-in provider ID and a configured provider instance. Stage UI and Stage Pages typechecks pass. Targeted lint reports zero errors and 12 pre-existing long-comment warnings. The hub has 11 passing contract tests and real HTTP 200 responses from both backends. No user browser session was used for these automated tests.
