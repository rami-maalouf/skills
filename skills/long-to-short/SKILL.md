---
name: long-to-short
description: Convert a finished long-form talking-head video into ranked short-form candidates - transcribe, apply the standalone gate, extract verbatim gem sections with headlines, and generate pre-bladed FCPXML projects for review. Use when turning a long video into shorts, finding "hidden gems" in a recording, or building vertical cuts from a horizontal master.
---

# long-to-short

turn one long talking-head video into a reviewed set of short-form cuts. works for both personal content (rami's brand) and expo content - mechanics are shared, voice is not (see voice note at the end).

## the process

the mechanics live in cutroom (https://github.com/rami-maalouf/CutRoom, the `cutroom` skill): it stores the candidates, checks their edges, plays them on a review page and exports them. this skill keeps the lessons behind the picks. the step-by-step is in the cutroom skill: `references/core.md` ("Shorts") for one finished video, `references/shorts.md` for hours of recording, `references/explainer.md` for demos and screen content.

1. **transcribe, word-level.** `cutroom review <video>` transcribes once (cache `<video>.transcript.json`, re-made when the video changes).
2. **find candidates verbatim** and write them under `shorts` in `<video>.cutroom.json`: title, why, theme, scores, rank, ranges (`"raw": true` for a finished export).
3. **apply the standalone gate (filter, do not rank yet).** see below. the review page flags leaning openings, cut-off endings, words that need the screen and words that point to earlier; check every edge by ear.
4. **rank the survivors** on five criteria, 10 points each: hook, standalone, emotion, relatability, payoff (explainers: clarity and usefulness instead of emotion and relatability).
5. **write headlines from the passage's own words** (rules below).
6. **review on the cutroom Shorts tab** (`cutroom review <video> --open`, or `--serve` on a phone): pick, maybe, reject, a note per short. then `cutroom export <video> S1 S4` for fcpxml, plus `--screenstudio <project>` for a short as its own screen studio project.

## lesson 1: the standalone gate is a gate, not a score

the biggest failure mode: ranking story beats by hook/emotion. story beats borrow power from setup that lives elsewhere in the video, and the short dies without it.

the test is mechanical: read the candidate passage's words only, with zero context. if any load-bearing word points outside the clip - a company name doing narrative work, "that email", "this program", "as i said" - it is disqualified. no score can save it.

- what survives is monologue and complete micro-stories, not plot points.
- generic references pass: "getting rejected" needs no antecedent; "rejected from next canada" does.
- story beats that fail the gate are still useful - as long-video promos or with a spoken intro line - but they are a different deliverable. label them as such.
- filter first, rank second. a criterion that is actually a requirement must never be averaged against the others.

## lesson 2: verbatim first, never rank from summaries

pull the exact transcript words of every candidate before judging it. summaries flatten everything to the same texture and hide which passages were already well-written in speech. the best picks are the ones where the improvised phrasing is already strong - that is only visible in the verbatim text.

deliverable rule: the review shows the full verbatim words of every pick, not a description of it (the cutroom Shorts tab does this).

## lesson 3: headlines come from the speaker's vocabulary

write headlines from words inside the passage ("side quest", "traumas are gifts", "quiet down the world"). a headline built from the speaker's own vocabulary cannot sound machine-made.

banned patterns (from the no-ai-slop skill - load it when writing headlines):

- faux-insight setups: "what nobody tells you", "the X nobody teaches you", "the part everyone misses"
- colon-reveal drama and fake binary contrasts ("it's not X, it's Y")
- listicle shapes and importance puffery

positive rules:

- first person and concrete beats abstract: "dedication didn't save me" over "the truth about dedication"
- a question caption must be answered by something said in the first 10-20 seconds, or it reads as bait
- on-screen captions stay under ~7 words; the platform title can be longer and different from the caption
- counterintuitive payoff is the strongest question form: the video's answer should reverse the expected one

## lesson 4: when rami rejects picks, extract the gate

a rejection usually means a hidden requirement was being treated as a weight. ask (or infer from the complaint) which constraint the picks violated, then re-run with that constraint as a hard filter. record the new gate in this skill.

## fcpxml mechanics (hard-won)

- every `<format>` needs `colorSpace="1-1-1 (Rec. 709)"` or fcp shows "encountered an unexpected value" and may fall back to wrong sequence settings. name known formats (`FFVideoFormat1080p30`); custom sizes (1080x1920) stay unnamed but keep colorSpace.
- **vertical reframe: use `<adjust-conform type="fill"/>`.** never conform none + hand-written `adjust-transform` scale/position - inspector semantics do not match hand-computed values. fill scales to full height and center-crops; verify framing first by extracting frames (ffmpeg) and checking where the face sits. if the face is off-center enough to matter, tell rami the one inspector nudge instead of encoding it.
- blade on word boundaries from the transcript (phrase-anchor lookup, snap to frames). after any blade pass, check the words at every cut boundary - dangling single words ("and", "we", "so") and mid-word cuts are the common defect.
- review pattern: nothing is deleted for the user. flags are bladed into their own clips named `FILLER? <reason>` / `GLITCH: <reason>` with markers, total duration unchanged; rami reviews by ripple-delete.
- never overwrite outputs unless updating in place was requested; version otherwise.
- transcripts, fcpxml outputs, and boards live next to the media files.

## voice note

these mechanics are shared between personal content and expo content. voice is not shared: personal shorts use rami's voice (`rami-voice`, `audience-profiles`); expo content uses expo's house voice (`expo/content/reference/voice-and-style.md`). never mix them.
