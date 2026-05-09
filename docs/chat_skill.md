Skills Architecture Brainstorm                           

---                                                                                             
The Core Mechanic
                                                                                                
Every incoming query goes through an intent classifier — a fast, cheap LLM call that reads the
query and returns 1–2 skill names with confidence scores. Those skill names are keys. The system
pulls the corresponding skill definition, injects it into the system prompt, and registers only
that skill's tools in tool_choice. The agent now operates inside a scoped context. It cannot   
hallucinate cross-video comparisons when only one video was loaded. It cannot use
aggregate_metadata when the skill doesn't register it. Tool binding IS the constraint.

The classifier output looks like: { "primary": "TwoVideoComparison", "secondary":               
"HookDiagnosis", "confidence": 0.91 }. When confidence is below threshold or two skills are
needed, both are loaded simultaneously — their system prompt sections stack, their tool sets    
merge.          

---
The Skills

⎿  Referenced file docs/rag-pipeline-research.md
⎿  Read docs/multimodal-prompting-research.md (306 lines)
⎿  Read docs/rich-video-transcription-schema.md (517 lines)
⎿  Read ../../.claude/settings.json (10 lines)
⎿  Read .claude/settings.json (9 lines)

● Skills Architecture Brainstorm

---
The Core Mechanic

Every incoming query goes through an intent classifier — a fast, cheap LLM call that reads the
query and returns 1–2 skill names with confidence scores. Those skill names are keys. The system
pulls the corresponding skill definition, injects it into the system prompt, and registers only
that skill's tools in tool_choice. The agent now operates inside a scoped context. It cannot
hallucinate cross-video comparisons when only one video was loaded. It cannot use
aggregate_metadata when the skill doesn't register it. Tool binding IS the constraint.

The classifier output looks like: { "primary": "TwoVideoComparison", "secondary":
"HookDiagnosis", "confidence": 0.91 }. When confidence is below threshold or two skills are
needed, both are loaded simultaneously — their system prompt sections stack, their tool sets
merge.

---
The Skills

SingleVideoAnalysis
The workhorse. Activated when the creator asks about one specific video. Loads context about
that video's metadata (duration, upload date, platform). Binds:
semantic_search(dense_transcript), semantic_search(dense_production), aggregate_metadata,
keyword_search. The skill instruction tells the agent: every claim must cite segment_id and
timecode. Never generalize beyond what the data shows.

TwoVideoComparison
Activated when two videos are explicitly named or implied (my video vs. competitor's). This is
the highest-stakes skill — it's the reason creators will pay. Binds: compare_across_videos,     
aggregate_metadata(video_ids=[A,B]), semantic_search with video filter on both. The skill
instruction forces parallel retrieval: always get the same field from both videos before        
comparing. Never compare asymmetrically. If one side is missing data, say [unclear] for that
side rather than omitting the comparison dimension.

HookDiagnosis
Activated by temporal keywords: "hook", "opening", "first 30 seconds", "intro", "thumbnail
moment". Filters all retrieval to timecode_start < 00:30. Binds: semantic_search with timecode  
filter, keyword_search with time-bounded filter, aggregate_metadata restricted to the first 30
seconds. The skill knows the anatomy of a hook: the setup line, the credibility signal, the     
pattern interrupt, the promise. It retrieves verbatim transcript and every overlay/graphic/cut
event in that window. It never infers intent — it returns the data and lets the chatbot's
reasoning layer explain.

ProductionAudit
Activated by questions about how something looks or sounds: lighting, camera, setup, mic,
background, color grade, production quality. Binds: semantic_search(dense_production),          
aggregate_metadata scoped to lighting, background, frame, production_observables fields. The
skill instruction: retrieve representative segments (not all segments — sample from beginning,  
middle, end to capture consistency or drift). Report exact values observed:
"key_light_direction: left in 82% of segments."

EditingAnalysis
Activated by questions about pacing, cuts, rhythm, transitions, energy. Binds:
aggregate_metadata scoped to editing and frame.shot_type, keyword_search for specific cut types.
This skill knows to compute cut frequency (cuts per minute = total cut events / video duration
in minutes). It retrieves the full editing timeline if needed. Reports: cut type distribution,  
average segment duration, transition_effect inventory, speed_ramp locations.

ScriptAnalysis
Activated by questions about what was said, language, structure, verbatim quotes, pacing of
speech. Binds: semantic_search(dense_transcript), keyword_search, aggregate_metadata scoped to  
speech fields. The skill instruction: always return verbatim text from speech.transcript. Never
paraphrase. If the creator asks "what did I say at 2:30?" this skill retrieves the exact segment
containing that timecode and returns the raw transcript field.

OverlayAudit
Activated by questions specifically about text overlays, graphics, animations, lower-thirds,
captions, visual elements added in post. Binds: aggregate_metadata scoped to on_screen_text and 
graphics_and_animations, keyword_search for specific text content. Returns the complete overlay
timeline: what appeared, when, for how long, in what style, at what position.                   
                
AudioAnalysis
Activated by questions about music, sound effects, audio quality, ambient sound. Binds:
aggregate_metadata scoped to audio, semantic_search(dense_production), keyword_search. Reports: 
music genre distribution across the video, where notable changes occur (drops, swells,
cut-outs), what sound effects were used and at what timecodes, audio quality assessment.        
                
SeriesAnalysis
Activated when the creator references multiple of their own videos or asks about patterns over
time. Binds: aggregate_metadata with multi-video_id filter, compare_across_videos (used to find 
consistency rather than contrast). The skill instruction: identify what is stable across videos
(recurring production choices) and what varies. This requires the agent to synthesize across    
documents rather than within one.

CompetitorIntelligence
Activated when the query is about a competitor's strategy, patterns, or approach — not a direct
comparison to the creator's own video. Binds: aggregate_metadata for the competitor's videos,   
semantic_search filtered to competitor videos, compare_across_videos if multiple competitor
videos are in context. The skill is oriented toward extraction, not comparison: "what is this   
creator's signature approach?"

EngagementCorrelation                                                                           
Activated when the creator brings in performance data alongside video content questions. "Why
did this video get X views?" "Which of my videos performed best and what did they have in       
common?" Binds: all four tools, with the instruction to retrieve production data AND
cross-reference against engagement metadata stored at the document level (views, watch time, CTR
if available). This skill has the hardest job: it cannot invent causation. It can only surface
correlation in the data and signal that the chatbot is presenting observable patterns, not
causal explanations.

---
The Question Taxonomy
                    
These are organized by what can fail, from most catastrophic to less so.
                                                                                                
---
CRITICAL TIER — Failure here destroys the product                                               
                                                                                                
"What does [competitor] do in their first 30 seconds?"
The hook is why creators are paying. If this answer is wrong, vague, or misattributed — it's    
over. Must return: verbatim opening line, shot type, first visible text overlay with exact text,
whether there's a pattern interrupt, the setup-to-promise structure in observable terms.
                                                                                                
"What does [competitor] say at [timecode]?"
Verbatim retrieval. Not a paraphrase. Not a summary. The creator may be taking notes to steal
the framing. Returns speech.transcript raw with segment_id and exact timecodes.                 

"Compare my hook to [competitor]'s hook"                                                        
The money query. Must compare: opening line, shot type, first overlay, music at that moment, any
graphics in first 30 seconds, camera angle, cut events. Side by side. Not narrative —          
structured. Missing data gets [unclear], never omitted.
                                                                                                
"What are [competitor] doing that I'm not?"                                                     
Gap analysis. This is the hardest question in the system. Requires: enumerate all dimensions
present in competitor's video, cross-check each dimension against creator's video, surface only 
differences. The agent must not hallucinate similarities or differences — must cite segment and
field for every claim.                                                                          
                
"Why is [competitor]'s video performing better than mine?"
Cannot answer with certainty — but must not dodge it. The correct behavior: return observable
differences across production, editing, and script; label them as "observable differences" not  
"reasons for performance"; resist inserting the analysis the chatbot hasn't been asked to do.
                                                                                                
"Transcribe exactly what I said from [timecode] to [timecode]"                                  
Verbatim. Segment boundary retrieval. Multiple segments if the range spans a cut. Returns them
stitched in order with timecodes.                                                               
                
---                                                                                             
HIGH-VALUE TIER — Failure frustrates but doesn't kill
                                                                                                
"List every text overlay in this video with timestamps"
Full overlay timeline. Should be complete — every on_screen_text.entries item across all        
segments, in chronological order, with duration.                                                

"How many jump cuts does [creator] use per minute?"                                             
Requires aggregation. Count editing.cut_event.type = jump-cut across all segments, divide by
total_duration in minutes. This is a computed answer, not a retrieval answer — the agent must do
arithmetic.
                                                                                                
"What shot types does [creator] use and how often?"
Distribution query. Count frame.shot_type values across all segments weighted by
duration_seconds. Returns: "MCU: 48% of video duration, CU: 22%, B-roll: 15%, Screen-recording: 
15%."
                                                                                                
"What's [competitor]'s background setup?"                                                       
Retrieve background fields from representative segments. Report type, description,
elements_visible. Note if it changes across the video.                                          
                
"What music does [creator] use and when does it change?"                                        
Retrieve audio.music across all segments. Report tempo_feel, genre_feel, and every
notable_change event with its timecode.                                                         

"Does [creator] use graphics and what kind?"                                                    
Full inventory of graphics_and_animations.entries across all segments. Types, positions,
durations.                                                                                      

"What's my production quality like compared to [competitor]?"                                   
ProductionAudit skill on both + TwoVideoComparison. Lighting quality, audio quality, color
grade, microphone type — side by side.                                                          
                
"At what point did I switch from talking-head to B-roll?"                                       
Find segments where frame.shot_type changes from MCU/CU/MS to B-roll. Return exact timecodes.
                                                                                                
"What does [competitor]'s audio setup tell me about their budget?"                              
ProductionAudit + inference from production_observables.microphone_type_inferred +              
audio.audio_quality. The agent observes, does not invent.                                       
                
---                                                                                             
SERIES/PATTERN TIER — Multi-video intelligence
                                                                                                
"What do my best-performing videos have in common production-wise?"
SeriesAnalysis across top N videos. Find what lighting, frame.shot_type, audio.music.genre_feel,
editing patterns recur in videos with high engagement metadata. Returns common values per      
field, not narrative.                                                                           
                                                                                                
"Has my editing style changed over my last 10 videos?"                                          
Time-ordered SeriesAnalysis. Compare editing field distributions across videos sorted by
upload_date. Report what shifted.                                                               
                
"Which of my competitors consistently uses text overlays?"                                      
CompetitorIntelligence across multiple competitor video_ids. Aggregate on_screen_text.present
frequency per creator.                                                                          
                
"Do all finance YouTubers use the same hook style?"                                             
Cross-creator SeriesAnalysis. Compare first-30-second segments across all ingested creators in
the finance category. Surface common patterns in speech.transcript, on_screen_text,             
frame.shot_type.
                                                                                                
"What are [competitor]'s signature production choices?"                                         
CompetitorIntelligence skill. Look for values that appear consistently across multiple
competitor videos: recurring background, consistent lighting setup, always using lav mic, always
opening with a specific shot type.
                                                                                                
---             
SPECIFIC TECHNICAL TIER — Precision retrieval
                                            
"What was the exact wording of the lower-third at 00:45?"
Exact segment retrieval by timecode. Return on_screen_text.entries for that segment.            
                                                                                                
"What was happening visually when [competitor] said [quote]?"                                   
Keyword search speech.transcript for the quote → get segment → return frame, background,        
on_screen_text fields for that same segment. Multi-field retrieval within one segment.          
                
"Did the music cut out before or after the graphic appeared?"                                   
Compare audio.music.notable_change timecode against                                             
graphics_and_animations.entries.duration_seconds start timecode. Requires precise segment-level 
data.    
                                                                                                
"List every moment the creator was not on camera"                                               
Filter for segments where speech.speaker_visible = false OR frame.shot_type = B-roll OR
frame.shot_type = Screen-recording. Return timecode ranges.                                     
            
"What were the subjects in frame throughout the video?"                                         
Aggregate frame.subjects_in_frame across all segments. Deduplicate. Note timecodes of first and
last appearance per subject.                                                                    
                
---                                                                                             
EDGE CASES AND MULTI-SKILL FAILURES
                                    
The hardest queries to handle:
                                                                                                
Query involves a video that hasn't been ingested yet. Agent must detect "no data" state         
immediately and ask the creator to submit the URL before proceeding — not produce a hallucinated
answer.                                                                                        

Creator asks about engagement performance but no engagement data was ingested.                  
EngagementCorrelation skill activates but the metadata fields are empty. Agent must say
explicitly: "Engagement data is not available for this video. I can analyze the observable      
production choices but cannot correlate them to performance."

Creator asks about "my competitor" without naming a video. Ambiguous target. Agent must ask     
which video, not assume.        
                                                                                                
Creator asks the same question about 7 videos. SeriesAnalysis. But if it's 7 different creators'
videos (cross-creator comparison), that's CompetitorIntelligence + SeriesAnalysis stacked. The
agent must load both and understand it's doing a benchmark, not a pairwise comparison.          

Creator asks "what should I steal from [competitor]?" This is EngagementCorrelation +           
CompetitorIntelligence + analysis. The agent can only return observable choices the competitor
makes that the creator doesn't. It cannot recommend what to steal — that's the user's judgment. 
Returning the gap is correct. Recommending the gap as action is overstepping.

Ambiguous timecode: "around the 2-minute mark." ScriptAnalysis/TimecodeQuery must retrieve      
segments from roughly 01:45–02:15 and return all of them, not just one.
                                                                                                
---
Skill Loading Decision Rules
                                                                                                
Some heuristics for the classifier:                 
                                                                                                
- Mentions "hook", "intro", "opening", "first [N] seconds" → HookDiagnosis (always; may stack   
with others)                                              
- Mentions two video titles or "my video AND their video" or "compare" → TwoVideoComparison     
(always; may stack)                                                                             
- Mentions "lighting", "setup", "camera", "background", "production", "quality" →
ProductionAudit                                                                                 
- Mentions "cut", "jump cut", "editing", "pacing", "transitions", "rhythm" → EditingAnalysis
- Mentions "text", "overlay", "graphic", "animation", "lower-third" → OverlayAudit              
- Mentions "what did [creator] say", "transcript", "words", "quote" → ScriptAnalysis            
- Mentions "music", "audio", "sound", "SFX" → AudioAnalysis                                     
- Mentions "all my videos", "across [N] videos", "over time", "pattern" → SeriesAnalysis        
- Mentions a competitor with no explicit comparison to self → CompetitorIntelligence            
- Mentions engagement, views, watch time, performance → EngagementCorrelation                   
- None of the above, single video → SingleVideoAnalysis (default)                               
                                                                                                
When two skills activate, they share the tool set (union, no duplicates). The system prompt gets
both skill instruction blocks stacked. The agent receives both skill personas and must satisfy 
both retrieval requirements.                                                                    

---
What This Architecture Buys
                            
The agent without skills is a general reasoner with four tools. The agent with skills is a
focused instrument — it knows why it's retrieving, what shape the answer should take, and which 
fields matter for this query type. The HookDiagnosis skill knows to look at the first 30      
seconds. The EditingAnalysis skill knows to compute cuts-per-minute. The TwoVideoComparison     
skill knows to retrieve the same field from both videos before ever attempting a comparison.
                                                                                                
The failure modes narrow dramatically. A creator won't get a vague narrative about "your video
uses good production" — they'll get a structured output that compares                         
lighting.key_light_direction: left in their video vs right in the competitor's, at segment 3    
(00:06–00:12) and segment 1 (00:00–00:05) respectively, and notes this directly.
                                                                                                
The most critical design rule: every claim the agent makes must be grounded to a specific 
segment_id and timecode. That is the discipline that separates this from a hallucinating      
chatbot. The skills enforce this. The data supports it. The schema was built to make it         
unavoidable. 