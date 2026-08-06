---
sc: "1.2.1"
technique: "audio-video-text-alternative"
title: "Time-based media without text alternative / unlabelled player"
applies_when:
  element_tag: [audio, video, source, track, object, embed, iframe]
signals:
  - field: element_html
    look_for: "<audio>/<video> with controls but no <track>, no caption, and no adjacent text alternative"
  - field: sr_transcript
    look_for: "the media player is skipped entirely (silence) or its controls read as unlabelled actions"
---
## Scope boundary
`<iframe>`/`<object>`/`<embed>` appear in `element_tag` above because they can
EMBED time-based media, and that is the only reason. Whether such an element has
an accessible name — a `title`, an `aria-label`, and whether that name describes
what it contains — is **4.1.2 Name, Role, Value**, which has its own skill
(`4.1.2/name-role-value`). Both skills can match one `<iframe>`; this one owns the
media inside it, not the frame's label.

So: a frame with no `title` is not a 1.2.1 finding, and its missing title is not
evidence about media. Where the capture shows only a frame and gives no sign of
audio or video inside it, this criterion has nothing to judge — say so and leave
the naming question to 4.1.2 rather than returning `insufficient_evidence` as
though the row were unreadable.

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
