# Rich Video Transcription Schema
## The data capture format for Creator-Joy's vector database

---

## What This Is

A **Rich Video Transcription** is a faithful, multi-dimensional record of everything observable in a video, written as structured text. It is NOT an analysis. It is NOT conclusions or recommendations.

It is the equivalent of what a very attentive person would write down if you asked them to document a video completely — capturing every dimension simultaneously, with no interpretation added.

The chatbot does the analysis. This document is the raw material the chatbot queries.

**The distinction:**
- `"Camera: MCU, static, eye-level"` → DATA ✓
- `"The MCU creates intimacy with the viewer"` → ANALYSIS ✗ (chatbot's job)

- `"Speaker leans forward ~15 degrees, pace slows, volume drops"` → DATA ✓
- `"Creator signals a key insight moment"` → ANALYSIS ✗ (chatbot's job)

- `"Text overlay: 'BIGGEST MISTAKE' in red bold font, center frame, 2.3 seconds"` → DATA ✓
- `"Creates urgency and hooks the viewer"` → ANALYSIS ✗ (chatbot's job)

---

## Schema Design Principles

**1. Event-driven segmentation**
A new segment begins when anything meaningfully changes — a cut, a speaker change, a new overlay appearing, a camera movement, music shift. Not fixed time intervals.

**2. Self-contained chunks**
Each segment entry must be understandable on its own. When it gets embedded into a vector DB and retrieved by a semantic search, it should carry enough context to be meaningful without reading the surrounding entries.

**3. Observable language only**
Every field uses words that describe what is physically present or physically happening. No words that describe effect, meaning, or intent.

**4. Exact over approximate where possible**
`"verbatim transcript"` over `"summary of what was said"`. `"MCU"` over `"close-ish shot"`. `"~120 BPM"` over `"fast music"`.

**5. Uncertainty over invention**
If something is unclear, the value is `[unclear]` or `[inaudible]`. Never fabricate to fill a field.

---

## The Schema

### Document-Level Fields (once per video)

```json
{
  "video_id": "unique_identifier",
  "source_url": "original URL",
  "platform": "youtube | tiktok | instagram | linkedin | other",
  "title": "video title as shown",
  "creator_name": "channel/handle name",
  "upload_date": "YYYY-MM-DD",
  "total_duration": "MM:SS",
  "resolution": "1080p | 720p | 4K | vertical | etc",
  "aspect_ratio": "16:9 | 9:16 | 1:1 | 4:3",
  "segments": [ ... ]
}
```

---

### Segment-Level Fields (one per observable event or change)

```json
{
  "segment_id": "sequential integer",
  "timecode_start": "MM:SS",
  "timecode_end": "MM:SS",
  "duration_seconds": 0,

  "speech": {
    "speaker_id": "Speaker_A | Speaker_B | Voiceover | [no speech]",
    "speaker_visible": true,
    "transcript": "exact verbatim words including um, uh, false starts",
    "language": "en | hi | es | [unclear]"
  },

  "frame": {
    "shot_type": "ECU | CU | MCU | MS | MWS | WS | EWS | OTS | POV | Two-shot | Insert | B-roll | Screen-recording | [unclear]",
    "camera_angle": "eye-level | high-angle | low-angle | dutch | [unclear]",
    "camera_movement": "static | pan-left | pan-right | tilt-up | tilt-down | dolly-in | dolly-out | handheld | gimbal | zoom-in | zoom-out | rack-focus | [unclear]",
    "subjects_in_frame": ["person", "laptop", "whiteboard"],
    "depth_of_field": "shallow (subject separated from background) | deep (all in focus) | [unclear]"
  },

  "background": {
    "type": "plain-wall | bookshelf | home-office | outdoor | studio | green-screen | blurred | [unclear]",
    "description": "brief factual description of what is visible behind the subject",
    "elements_visible": ["bookshelf", "plant", "monitor", "branded backdrop"]
  },

  "lighting": {
    "key_light_direction": "left | right | front | above | [unclear]",
    "light_quality": "soft | hard | mixed | [unclear]",
    "catch_light_in_eyes": true,
    "color_temperature_feel": "warm | cool | neutral | mixed | [unclear]",
    "notable": "ring light visible in catchlight | window light | neon accent | [none]"
  },

  "on_screen_text": {
    "present": true,
    "entries": [
      {
        "text": "exact text as it appears on screen",
        "position": "top-left | top-center | top-right | center | bottom-left | bottom-center | bottom-right",
        "style": "bold | italic | uppercase | lowercase | mixed",
        "color": "white | black | red | yellow | [describe]",
        "animation": "static | types-in | slides-in | fades-in | pops-in | [unclear]",
        "duration_on_screen_seconds": 0
      }
    ]
  },

  "graphics_and_animations": {
    "present": true,
    "entries": [
      {
        "type": "lower-third | counter | progress-bar | arrow | circle | logo | chart | meme | reaction-image | b-roll-overlay | [describe]",
        "description": "factual description of what the graphic is and where it appears",
        "position": "top-left | top-center | etc",
        "duration_seconds": 0
      }
    ]
  },

  "editing": {
    "cut_event": {
      "occurred": true,
      "type": "hard-cut | jump-cut | match-cut | J-cut | L-cut | smash-cut | dissolve | wipe | [unclear]"
    },
    "transition_effect": "none | whoosh | zoom-blur | spin | [describe] | [unclear]",
    "speed_change": "none | speed-ramp-up | speed-ramp-down | freeze-frame | [unclear]"
  },

  "audio": {
    "music": {
      "present": true,
      "tempo_feel": "slow | medium | fast | [unclear]",
      "genre_feel": "lo-fi | electronic | cinematic | upbeat-pop | ambient | dramatic | none | [unclear]",
      "volume_relative_to_speech": "background | equal | louder | no-speech | [unclear]",
      "notable_change": "drops | swells | cuts-out | new-track-starts | [none]"
    },
    "sound_effects": {
      "present": false,
      "entries": [
        {
          "type": "whoosh | ding | notification | impact | record-scratch | applause | [describe]",
          "timecode": "MM:SS"
        }
      ]
    },
    "ambient": "room-tone | outdoor | crowd | silence | [describe]",
    "audio_quality": "clean-studio | light-room-echo | heavy-reverb | background-noise | [unclear]"
  },

  "production_observables": {
    "microphone_type_inferred": "lav | shotgun | dynamic-desk | condenser | built-in | [unclear]",
    "props_in_use": ["list any props the speaker is physically using or holding"],
    "wardrobe_notable": "casual | professional | branded | [describe if relevant] | [none noted]",
    "color_grade_feel": "warm | cool | neutral | high-contrast | desaturated | vibrant | [unclear]"
  }
}
```

---

## Full Example: A 90-Second YouTube Video Transcription

```json
{
  "video_id": "yt_dQw4w9WgXcQ",
  "source_url": "https://youtube.com/watch?v=...",
  "platform": "youtube",
  "title": "I Tried Every Hook Strategy For 30 Days",
  "creator_name": "Creator Example",
  "upload_date": "2024-11-15",
  "total_duration": "01:32",
  "resolution": "1080p",
  "aspect_ratio": "16:9",

  "segments": [

    {
      "segment_id": 1,
      "timecode_start": "00:00",
      "timecode_end": "00:04",
      "duration_seconds": 4,

      "speech": {
        "speaker_id": "Speaker_A",
        "speaker_visible": true,
        "transcript": "I posted the same video twice.",
        "language": "en"
      },

      "frame": {
        "shot_type": "CU",
        "camera_angle": "eye-level",
        "camera_movement": "static",
        "subjects_in_frame": ["Speaker_A face"],
        "depth_of_field": "shallow"
      },

      "background": {
        "type": "blurred",
        "description": "blurred bookshelf, warm tones",
        "elements_visible": ["bookshelf"]
      },

      "lighting": {
        "key_light_direction": "left",
        "light_quality": "soft",
        "catch_light_in_eyes": true,
        "color_temperature_feel": "warm",
        "notable": "none"
      },

      "on_screen_text": {
        "present": false,
        "entries": []
      },

      "graphics_and_animations": {
        "present": false,
        "entries": []
      },

      "editing": {
        "cut_event": { "occurred": false, "type": null },
        "transition_effect": "none",
        "speed_change": "none"
      },

      "audio": {
        "music": {
          "present": true,
          "tempo_feel": "slow",
          "genre_feel": "ambient",
          "volume_relative_to_speech": "background",
          "notable_change": "none"
        },
        "sound_effects": { "present": false, "entries": [] },
        "ambient": "room-tone",
        "audio_quality": "clean-studio"
      },

      "production_observables": {
        "microphone_type_inferred": "shotgun",
        "props_in_use": [],
        "wardrobe_notable": "plain dark crew-neck",
        "color_grade_feel": "warm"
      }
    },

    {
      "segment_id": 2,
      "timecode_start": "00:04",
      "timecode_end": "00:07",
      "duration_seconds": 3,

      "speech": {
        "speaker_id": "Speaker_A",
        "speaker_visible": true,
        "transcript": "One got 300 views. One got 2.4 million.",
        "language": "en"
      },

      "frame": {
        "shot_type": "MCU",
        "camera_angle": "eye-level",
        "camera_movement": "static",
        "subjects_in_frame": ["Speaker_A torso and face"],
        "depth_of_field": "shallow"
      },

      "background": {
        "type": "blurred",
        "description": "same bookshelf",
        "elements_visible": ["bookshelf"]
      },

      "lighting": {
        "key_light_direction": "left",
        "light_quality": "soft",
        "catch_light_in_eyes": true,
        "color_temperature_feel": "warm",
        "notable": "none"
      },

      "on_screen_text": {
        "present": true,
        "entries": [
          {
            "text": "300 views",
            "position": "bottom-left",
            "style": "bold uppercase",
            "color": "white with red background block",
            "animation": "pops-in",
            "duration_on_screen_seconds": 1.5
          },
          {
            "text": "2,400,000 views",
            "position": "bottom-right",
            "style": "bold uppercase",
            "color": "white with green background block",
            "animation": "pops-in",
            "duration_on_screen_seconds": 1.5
          }
        ]
      },

      "graphics_and_animations": {
        "present": false,
        "entries": []
      },

      "editing": {
        "cut_event": { "occurred": true, "type": "hard-cut" },
        "transition_effect": "none",
        "speed_change": "none"
      },

      "audio": {
        "music": {
          "present": true,
          "tempo_feel": "slow",
          "genre_feel": "ambient",
          "volume_relative_to_speech": "background",
          "notable_change": "none"
        },
        "sound_effects": {
          "present": true,
          "entries": [
            { "type": "ding", "timecode": "00:05" },
            { "type": "ding", "timecode": "00:06" }
          ]
        },
        "ambient": "room-tone",
        "audio_quality": "clean-studio"
      },

      "production_observables": {
        "microphone_type_inferred": "shotgun",
        "props_in_use": [],
        "wardrobe_notable": "plain dark crew-neck",
        "color_grade_feel": "warm"
      }
    },

    {
      "segment_id": 3,
      "timecode_start": "00:07",
      "timecode_end": "00:12",
      "duration_seconds": 5,

      "speech": {
        "speaker_id": "Voiceover",
        "speaker_visible": false,
        "transcript": "[no speech — screen recording segment]",
        "language": "en"
      },

      "frame": {
        "shot_type": "Screen-recording",
        "camera_angle": "N/A",
        "camera_movement": "N/A",
        "subjects_in_frame": ["YouTube Studio analytics dashboard", "two video thumbnails side by side"],
        "depth_of_field": "N/A"
      },

      "background": {
        "type": "screen-recording",
        "description": "YouTube Studio dark mode interface",
        "elements_visible": ["analytics graphs", "view count numbers", "two video rows"]
      },

      "lighting": {
        "key_light_direction": "N/A",
        "light_quality": "N/A",
        "catch_light_in_eyes": false,
        "color_temperature_feel": "N/A",
        "notable": "screen-recording segment"
      },

      "on_screen_text": {
        "present": true,
        "entries": [
          {
            "text": "Video A — 312 views",
            "position": "center-left",
            "style": "platform UI text",
            "color": "white on dark",
            "animation": "static",
            "duration_on_screen_seconds": 5
          },
          {
            "text": "Video B — 2,419,847 views",
            "position": "center-right",
            "style": "platform UI text",
            "color": "white on dark",
            "animation": "static",
            "duration_on_screen_seconds": 5
          }
        ]
      },

      "graphics_and_animations": {
        "present": true,
        "entries": [
          {
            "type": "arrow",
            "description": "red arrow pointing at Video A view count, added in post",
            "position": "center-left",
            "duration_seconds": 5
          },
          {
            "type": "arrow",
            "description": "green arrow pointing at Video B view count, added in post",
            "position": "center-right",
            "duration_seconds": 5
          }
        ]
      },

      "editing": {
        "cut_event": { "occurred": true, "type": "hard-cut" },
        "transition_effect": "whoosh",
        "speed_change": "none"
      },

      "audio": {
        "music": {
          "present": true,
          "tempo_feel": "medium",
          "genre_feel": "electronic",
          "volume_relative_to_speech": "no-speech",
          "notable_change": "swells"
        },
        "sound_effects": { "present": false, "entries": [] },
        "ambient": "none",
        "audio_quality": "clean-studio"
      },

      "production_observables": {
        "microphone_type_inferred": "N/A",
        "props_in_use": [],
        "wardrobe_notable": "N/A",
        "color_grade_feel": "N/A"
      }
    }

  ]
}
```

---

## What This Schema Enables for the RAG System

Each segment entry becomes a vector-embedded chunk. The chatbot can then:

- **"What text overlays appear in the first 30 seconds of Video A?"**
  → Retrieves all segments with `timecode_start < 00:30` and `on_screen_text.present = true`

- **"When does the creator switch from talking-head to screen recording?"**
  → Retrieves the segment where `frame.shot_type` changes to `Screen-recording`

- **"Compare the music in Video A vs Video B during their hooks"**
  → Retrieves first 30s segments from both, returns `audio.music` fields side by side

- **"What animations does Creator A use that Creator B doesn't?"**
  → Retrieves all `graphics_and_animations` entries from both, chatbot compares

- **"Describe the production setup of this video"**
  → Retrieves `lighting`, `background`, `production_observables` from representative segments

- **"What exactly did the creator say at the 1-minute mark?"**
  → Retrieves the segment containing `timecode_start ≈ 01:00`, returns `speech.transcript`

None of these require analysis to be pre-baked into the data. The data is complete, and the chatbot reasons over it.

---

## Speaker Identification Strategy

For multi-speaker videos:

- Assign `Speaker_A`, `Speaker_B` etc. as neutral identifiers initially
- Capture a `speakers` block at the document level once Gemini identifies names from visual or audio cues:

```json
"speakers": {
  "Speaker_A": {
    "identified_name": "Alex Hormozi",
    "identification_source": "text-overlay-at-00:15 | verbal-introduction | [inferred]",
    "role": "host | guest | interviewer | subject | [unclear]"
  },
  "Speaker_B": {
    "identified_name": "[unclear]",
    "identification_source": "not identified",
    "role": "guest"
  }
}
```

---

## What Gemini Is Asked to Do

Gemini is NOT being asked to analyze or evaluate. It is being asked to **observe and record** — the same way a transcriptionist records speech, except extended to all sensory dimensions of the video.

The prompt instructs Gemini to act as a meticulous documentarian: capturing every observable fact without adding meaning to it. The data capture schema above is what Gemini fills in.
