# AIRI Local — third-party notices

This distribution contains separately licensed models, software, and data. The AIRI repository's MIT license does not replace those licenses.

## Models and data

- **SARC-Taigi-LLM-12b Q4_K_M**, Speech AI Research Center, derives from Google Gemma 3. Read `gemma-terms.txt`, `gemma-prohibited-use-policy.txt`, `NOTICE-Gemma.txt`, and `sarc-model-card.md`. Gemma use restrictions govern this model and downstream derivatives.
- **Gemma 4 12B IT QAT**, Google, uses Apache License 2.0. Read `Apache-2.0.txt` and `gemma4-model-card.md`.
- **Qwen 3.5 0.8B**, Alibaba's Qwen team in China, uses Apache License 2.0. Read `qwen-model-card.md` and `qwen-Apache-2.0.txt`. The Lite preset uses this dense model for local conversation and vision.
- **Breeze ASR-26**, MediaTek Research, and the **MLX 4-bit conversion**, RayyTien, use Apache License 2.0. Both model cards accompany this distribution. The classroom tokenizer compatibility patch is in the published AIRI course source.
- **Kokoro-82M and voices**, hexgrad, use Apache License 2.0. `kokoro-model-card.md` and `kokoro-voices.md` preserve training-data attributions, including Koniwa and SIWIS. CC BY 3.0 and 4.0 texts accompany them.
- **KaedeTai GPT-SoVITS Taiwanese S1/S2 weights** use MIT as declared by their author. `kaedetai-model-card.md` and `kaedetai-MIT.txt` preserve that grant and upstream RVC-Boss attribution. The source revision is `81959852f75c972a0a78364f8ea6b14133a11f4a`. Weight revision is `fa251907be54b63277377a96a23377fd7f00e323`.
- **Chinese Hubert base**, TencentGameMate, is declared MIT in its original model card. The card preserves the model author's identity and MIT declaration. `MIT-standard.txt` supplies the standard permission text, without inventing a separate upstream copyright notice. The fetched GPT-SoVITS base-weight collection and its model card are identified separately.
- **ERes2NetV2_w24s4ep4 speaker encoder**, ModelScope / 3D-Speaker, uses Apache License 2.0 in its original model card and code. The collection's MIT label does not replace this upstream license.
- **Taibun** code uses MIT. Its dictionary data uses CC BY-SA 4.0. See the included README, MIT text, and CC BY-SA 4.0 text for source attribution.
- KaedeTai's bundled reference `demo_02_kin_a_jit_thinn_khi.mp3` is the author's synthetic demonstration from the MIT-licensed source repository. Its source and revision accompany the payload. No user recording is included.
- **MMS-TTS nan is not part of the default Mac payload**. The separate research adapter documents that model's CC BY-NC 4.0 license.

**Optional MotionGPT Base:** research weights are not included in the app or release assets. The installer downloads pinned, hash-verified files directly from OpenMotionLab only when selected. The upstream model card declares `cc` without an exact Creative Commons variant; this is not represented as a redistribution or commercial-use grant. MotionGPT code and the adapted VQ implementation retain the upstream MIT license in `course/ntu-vh2026/motiongpt/vendor/LICENSE.MotionGPT`. The pinned FLAN-T5 tokenizer retains its Apache-2.0 attribution separately in the download manifest. Model details and limitations are in the MotionGPT README. The native MLX implementation references Apple’s MIT-licensed T5 example; the retained license and pinned source are in `course/ntu-vh2026/motiongpt/vendor/`. The MLX/Metal packages retain their package notices in the standalone runtime. Locally converted MotionGPT caches are private model data and are not release assets.

## Runtime and codec components

Python and each installed package retain their `LICENSE`, `COPYING`, `NOTICE`, and `*.dist-info` records inside `runtimes/`. These include the Python standalone distribution, MLX, Torch, NumPy, SciPy, and their bundled libraries. Their individual notices remain authoritative.

**Ollama 0.35.1** is MIT-licensed. `ollama-MIT.txt` accompanies its runtime. Model licenses remain separate from the engine license.

**PyAV 19.0.1** is BSD-3-Clause. This particular wheel embeds **FFmpeg 9.0.2** built by `PyAV-Org/pyav-ffmpeg` tag `9.0.2-1`. Its runtime reports LGPL version 3 or later, but its build also links **x264** and **x265**, whose headers grant GPL version 2 or later. We retain the GPL terms and corresponding source for these components. This package is not described as LGPL-only.

The upstream build patch moves x264/x265 from FFmpeg's GPL feature list to its version-3 list. That patch changes the reported build classification; it does not replace the codec authors' licenses. Both the original FFmpeg source and the exact upstream patch/build scripts are provided.

The macOS codec set is FFmpeg 9.0.2, lamer 3.101.0, Opus 1.6.1, dav1d 1.5.4, SVT-AV1 4.2.0, libvpx 1.17.0, libpng 1.6.58, libwebp 1.6.0, VMAF 3.2.1, x264 commit `b35605ace3ddf7c1a5d67a2eb553f034aef41d55`, and x265 4.3. Their upstream source archives, license texts, and build recipes accompany this distribution.

**eSpeak NG 1.52.0** and **phonemizer-fork 3.3.2** use GPL version 3 or later. **espeakng-loader 0.2.4** has separate MIT loader code and bundled eSpeak libraries/data. Both source layers are included. The loader source is the author's `0.2.4` version-bump commit `146599e29be31bf17d99f0bcb7dbb2f92aef3d95`, including its vendored eSpeak source and build workflow.

**SoundFile 0.13.0** is BSD-licensed Python code. Its **libsndfile 1.2.2** library has separate LGPL terms. Corresponding source and the wheel's existing `COPYING` remain included. The app uses this library for WAV/MP3 output instead of copying the developer computer's FFmpeg command-line installation.

SoundFile 0.13.0 pins `bastibe/libsndfile-binaries` at `a3e6f9769d0c7e91d2d036cf0fdbe5b4bbf18b87`. Its Mac build statically includes libogg 1.3.5, libvorbis 1.3.7, FLAC 1.4.3, Opus 1.4, mpg123 1.32.3, and LAME 3.100. Their exact-version sources and the Mac build recipe accompany libsndfile. The upstream binary README preserves individual author credits.

## Source, modifications, and rebuilding

`source/` holds upstream source archives. `source-notices/` copies small license members from those archives. `upstream-source-manifest.json` records exact URLs and SHA-256 values. PyAV codec archive hashes are checked against the upstream build recipe. The source archives include the original author copyrights.

To rebuild PyAV's libraries, unpack `pyav-ffmpeg-9.0.2-1.tar.gz`, then follow its `.github/workflows/build-ffmpeg.yml` and `scripts/build-ffmpeg.py`. Supply the corresponding codec sources recorded in its `scripts/pkg.py`. Build PyAV 19.0.1 against those resulting libraries using its source instructions.

To rebuild eSpeak, use the supplied loader source's `build.sh`, `hatch_build.py`, and workflow, or the separately supplied eSpeak 1.52.0 source. Phonemizer is supplied as Python source. SoundFile and libsndfile contain their build instructions in the supplied archives.

The AIRI course repository publishes the local service adapters, frontend changes, compatibility patch, and packaging scripts. The installed Python adapters remain editable source. No extra restriction is imposed on modifying, relinking, replacing, or debugging these open-source components as allowed by their licenses. Re-signing a modified local Mac app can be necessary after changing a signed bundle.

These notices describe the collected components. They do not claim that the entire app has one license or that every model is suitable for every use.
