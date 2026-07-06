---
sc: "1.2.1"
technique: "audio-video-text-alternative"
title: "Time-based media without text alternative / unlabelled player"
applies_when:
  element_tag: [audio, video, source, track, object, iframe]
  ax_role: [application, document, presentation, none]
axe_ids: [audio-caption, video-caption, frame-title]
signals:
  - field: element_html_raw
    look_for: "<audio>/<video> with controls but no <track>, no caption, and no adjacent text alternative"
  - field: sr_transcript
    look_for: "the media player is skipped entirely (silence) or its controls read as unlabelled actions"
---
## Violation criteria (1.2.1 Audio-only and Video-only)
Flag `inaccessible` under `1.2.1` when time-based media has no text alternative
and its player is not perceivable/operable via assistive tech:
- `<audio>`/`<video>` with `controls` whose player layer is **skipped entirely**
  by the screen reader (announced as silence) — the user is never told a media
  player exists.
- Player controls that are read as **completely unlabelled** actions.
- Prerecorded audio-only / video-only content presented with **no** transcript,
  caption track, or equivalent text alternative nearby.

## Pass criteria
- The media element is announced with an accessible name/role and provides (or
  is accompanied by) a transcript or captions.

## Examples
- INACCESSIBLE: `<audio controls src="…AudioTest.ogg"></audio>` → SR silence, no
  transcript.
- INACCESSIBLE: `<video controls>…<source …></video>` → player skipped, no captions.
