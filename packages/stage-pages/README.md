# Stage Pages

`@proj-airi/stage-pages` contains route-level Vue pages that multiple AIRI stage applications share.

## Use

Add a page under `src/pages`. Each stage application scans this directory through its Vite router configuration.

Import a shared page through the package boundary when code needs the component directly:

```ts
import PolaroidPage from '@proj-airi/stage-pages/pages/devtools/polaroid.vue'
```

## When to use this package

Use this package when two or more stage applications need the same page behavior and route structure.

## When not to use this package

Keep application-specific pages in the owning application. Put reusable business components in `@proj-airi/stage-ui`.

Put primitive UI components in `@proj-airi/ui`. Put shared layouts in `@proj-airi/stage-layouts`.

## Provider settings

The active chat and vision provider routes live under `/settings/providers`. They use `ProviderGenerationSettings` from stage-ui to render protocol and native search options from the provider catalog. The V2 editor is a separate consumer and does not replace these routes.

## VRM motion module

`/settings/modules/motion` configures an optional local MotionGPT service and previews generated motion on the selected VRM.
The module card appears only for VRM characters. A direct route visit with another renderer explains that restriction.
Enable the module, test the service, then generate a short English motion description. Enable automatic conversation generation separately.
The page does not download model weights or launch the service. Replay and cancel controls operate on the last validated clip.
An independent, default-off OpenAI Decisions section offers a session-only password input or an existing OpenAI provider key.
It explains the text sent to the cloud, possible charges and local fallback. The authenticated proxy requires the packaged local manager origin.
