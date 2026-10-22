---
name: youtube-thumbnail
description: Package a YouTube video - find the promise, write title options, pair each title with thumbnail text that does not repeat it, design 3-4 thumbnail concepts, build them as 1280x720 images (AI face from face-variations + an HTML layout for exact text and real logos), and check them the way YouTube shows them. Use for "make a thumbnail", "title for my video", "title and thumbnail", "package this video", or thumbnail A/B test variants.
---

# youtube-thumbnail

the title and the thumbnail are one promise. this skill finds the promise first, then writes the title, then designs the thumbnail that completes it, then checks it at the size people actually see it.

read `references/rules.md` (every rule with its source) and `references/house-style.md` (rami's past thumbnails and the gates from rejected picks) before you start.

## where the work lives

- an expo video: `life-os/expo/content/videos/<slug>/`. read `notes.md`, `script.md`, `titles.md`, `thumbnail.md` and the playbook at `expo/content/reference/youtube-tutorial-research/youtube-tutorial-playbook.md`. put the build in `videos/<slug>/thumbnail/`, and write the results back into `titles.md` and `thumbnail.md`.
- anything else: `life-os/design/thumbnails/<slug>/`, with a `brief.md` that holds the same sections.

## 1. find the promise

read the script, transcript or notes. write one sentence: what does the viewer get, or feel, by the end? if you cannot write it, stop and ask: the video is not ready to package.

also note: search-led or browse-led? a search-led video answers a query people type ("expo apple developer account"). a browse-led video must make people curious in the feed.

## 2. write titles

write 5 titles, one per lane: search-clear, browse-curious, result, contrarian, simple. for each, show the character count.

- 40-60 characters. the hook and the keyword in the first ~50.
- accurate: the video delivers every word.
- rami's own words. use the `rami-voice` skill when it is available, and phrases from the transcript. no ai-slop patterns (see `references/rules.md`).
- for expo videos, keep the playbook's pair: one search head, one browse head.

## 3. pair each title with thumbnail text

for the best 2-3 titles, write the thumbnail text that completes each one:

- 0-5 words, about 30 characters or fewer
- no word from the title, except the search keyword in a search-led package
- the title says what; the thumbnail shows the feeling, the stakes or the proof
- pick a pairing pattern from `references/rules.md` and name it

## 4. design 3-4 concepts

each concept differs from the others in one big way: the emotion, the focal subject, the text, or the layout. small tweaks do not count as different. for each concept write:

- the focal subject and at most 2 more elements
- the face: yes or no, and which expression in physical terms (browse-led: face first; search-led: try a clean label)
- the text and where it sits
- the background and the accent color (keep the series' visual system)
- what in the video proves this image is true (promise = delivery)

show the concepts to rami as a short list, and get a pick or a "make all" before you spend images.

## 5. make the assets

- **face:** first search the person's real photos with the `face-variations` catalog (`catalog.py find --where expression=... --where hands=...`); a real photo that fits beats a generated one. otherwise generate with the `face-variations` skill and the person's face library (`design/faces/<person>/`), in the look rami names. for a full-bleed photo, ask for a plate with the face on one side and space for the text, and a backdrop in the design colors. save to `<build folder>/faces/`.
- **logos:** real files from the official source (press kit, brand page, simple icons). run `file` on each download to make sure it is an image and not an html error page. never let the image model draw a logo.
- **screens and products:** real screenshots or frames from the video, so the thumbnail shows what the video shows.

## 6. build

copy `assets/template.html` once per concept (`thumb-a.html`, `thumb-b.html`, ...) into the build folder, fill the slots, and render them together:

```bash
uv run <skill dir>/scripts/render.py thumb-a.html thumb-b.html thumb-c.html \
  --title "title for a" --title "title for b" --title "title for c" \
  --channel "Expo" --duration 9:41
```

it writes for each: `<name>.png` (2560x1440 master), `<name>.jpg` (1280x720 upload file under 2 mb), `check-<name>.png` (home feed, search, up next, 120 px glance, mobile, with the length badge), and `compare.png` for all of them side by side. it warns when the layout is not exactly 1280x720.

## 7. check every thumbnail before you show it

open each `check-<name>.png` yourself and go through this list. fix and re-render until all pass:

- [ ] glance test: at 120 px you can still tell what it is about, and the text is readable at the 168 px up-next size
- [ ] one focal subject, 3 elements at most
- [ ] the text has 5 words or fewer and repeats no title word (except the search keyword)
- [ ] the title and thumbnail read as one promise, not the same sentence twice
- [ ] the length badge does not cover anything that matters
- [ ] a face, when used: big, eyes visible, and it looks like the person (compare with the refs)
- [ ] everything shown is in the video
- [ ] it fits the series' visual system and every gate in `references/house-style.md`
- [ ] no text or logo was drawn by the image model; nothing is misspelled

## 8. deliver

show `compare.png`, then each check sheet, with the title for each. recommend 2-3 clearly different variants for youtube's test & compare, and say why. remind rami that the test is judged by watch time.

for expo videos, write the chosen titles into `titles.md` and the concept, text and file paths into `thumbnail.md`.

## 9. learn from every rejection

when rami rejects a title or a thumbnail, find the rule it broke and ask if it is not clear. add that rule to the lessons list in `references/house-style.md`, with the date and the video. the next package must pass it.
