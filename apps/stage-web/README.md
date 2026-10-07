<h1 align="center">アイリ VTuber</h1>

<p align="center">
  [<a href="https://airi.ayaka.io">Try it</a>]
</p>

> Heavily inspired by [Neuro-sama](https://www.youtube.com/@Neurosama)

## Local Mac desktop pet

The classroom Mac package exposes a narrow `window.airiDesktop` bridge.
Its title bar opens desktop pet mode with a transparent character stage and compact controls.
Drag the AIRI handle to move the window. Use the microphone, chat, view, pin, and settings buttons around the character.
The microphone indicator stays visible while microphone input is enabled.

Click-through applies to the whole window. Restore interaction through the native AIRI menu or Dock.
Switching modes keeps the stage mounted, preserves the selected background, and reuses the speech pipeline.
Opening settings returns to the ordinary window layout.

An ordinary browser has no native bridge, so it keeps the web layout.
Adding `?desktopPet=1` to a browser URL does not create a floating desktop window.

## Performance diagnostics

Run `pnpm dev:web:https` from the repository root. Open `/devtools/performance-visualizer` and enable FPS.
The floating overlay shows the last 10 seconds of FPS history, with time and FPS axes.
The minimum, maximum, and latest values describe the visible samples. Other metrics retain their distribution charts.

Start a recording, then navigate within the app to the scene you want to measure.
Stop the recording within 60 seconds, or let it stop automatically.
Return to the visualizer to inspect the recorded FPS history. Export the recording as CSV for individual timestamps and values.

Each FPS sample is `1000 / frameIntervalMs`, from `requestAnimationFrame` callbacks.
Use these samples to locate changes in animation frame timing. They do not measure GPU presentation or native application FPS.
Keep the page in the foreground. Reloading the page clears the recording.

For device comparisons, use the same scene, model, warm-up period, and recording duration.
The development server and the visible overlay affect performance, so record these conditions with the results.
