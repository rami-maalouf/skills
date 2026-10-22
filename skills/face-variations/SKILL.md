---
name: face-variations
description: Generate new images of one specific real person from a library of their reference photos (all angles and expressions) - one or many variations with a chosen expression, pose, framing and backdrop, for thumbnails, posters and other designs. Uses Codex's built-in image tool (gpt-image-2 on the ChatGPT plan, no API key). Use when asked for "a picture of me looking shocked", face expressions, face variations, a new photo of a person from their references, or a face for a thumbnail.
---

# face-variations

make new photos of one real person that still look exactly like them. the person's reference photos carry the identity; the prompt carries only what changes (expression, pose, framing, backdrop).

the engine is codex's built-in `image_gen` tool, driven by `codex exec`. it runs on the chatgpt plan that codex is signed in with: no api key, but every image counts toward the codex usage limits. the reference photos are uploaded to openai.

## the face library

one folder per person, inside the workspace that uses it (in life-os: `design/faces/<person>/`):

```
faces/<person>/
  profile.md     # name, the identity-lock bullets, which refs exist and which are missing
  refs/          # 8-12 reference photos: the identity
  approved/      # generated images the person approved: safe to reuse as refs
  variations/    # default output: <date>-<slug>/ with images, manifest.json, contact-sheet.jpg
```

### reference photos

likeness improves with more good references. aim for 8-12, at least 1024 px on the short edge:

- angles: front, 3/4 left, 3/4 right, slightly from above, slightly from below
- expressions: neutral, smiling with teeth, talking, one strong expression (surprised, laughing)
- light: soft indoor light and harder daylight
- distance: mostly head and shoulders, one or two closer face shots
- one person per photo. no sunglasses, no hats, no heavy filters, no motion blur
- no two photos with the same pose and light: duplicates add nothing
- if the person sometimes wears glasses, keep most refs without them and say so in `profile.md`

name files by what they show: `front-neutral.jpg`, `3q-left-smile.jpg`, `below-talking.jpg`. the names help you pick refs per job.

### profile.md

```markdown
# <name>

## identity lock
- <a feature that drifts, said as a physical fact: "tight dark curls with high volume; one curl falls over the forehead">
- <...>

## refs
- have: <list>
- missing: <angles or expressions not yet covered>
```

the script copies every bullet under `## identity lock` into each prompt. write a bullet when a result drifts on that feature, so it does not drift again.

## workflow

1. **check the library.** read `profile.md` and list `refs/`. if there are fewer than 5 refs, say that likeness will suffer and name the missing angles before you spend images.
2. **pick the refs for the job.** by default the script sends all of `refs/` (up to 8). for a target angle, pick refs close to it with `--ref` (a 3/4 pose: the 3/4 refs plus the front one). each ref has one job: identity. never pass a style or layout example as a ref: it leaks into the face.
3. **write the variation in physical terms.** say what the face does, not the emotion word alone. one change per variation. see the expression table below.
4. **dry-run first** when you write new prompts. it prints every prompt and costs nothing:
   ```bash
   uv run scripts/generate.py --face design/faces/rami --prompt "..." --dry-run
   ```
5. **generate.** one `codex exec` per image, 3 at a time:
   ```bash
   uv run scripts/generate.py --face design/faces/rami \
     --prompt "laughing: wide open-mouth smile, cheeks raised, eyes narrowed, head tilted a little left" \
     --prompt "skeptical: one eyebrow raised, lips pressed to one side, chin slightly down" \
     --count 2 --out design/thumbnails/<slug>/faces
   ```
   options: `--aspect landscape|portrait|square`, `--framing "..."`, `--backdrop "..."`, `--asset "..."`, `--ref <file>` (repeat), `--parallel N`.
6. **review before you show.** open `contact-sheet.jpg` (refs on top, results below) and compare each result to the refs: eye shape, nose, hairline, hair texture, beard line, skin tone, age. drop any result that drifts, and say which feature drifted. a result can look like a sibling and still be wrong: if in doubt, drop it.
7. **show the person the kept results**, with paths. only when they approve one, copy it to `approved/`. never feed an unapproved result back in as a ref: drift adds up over generations.
8. **when a result drifts the same way twice**, add an identity-lock bullet to `profile.md`.

## expression table

| want | write |
|---|---|
| shocked | eyes wide open, eyebrows raised high, mouth open in an O, head pulled back slightly |
| laughing | wide open-mouth smile with teeth, cheeks raised, eyes narrowed, head tilted |
| excited | big closed-mouth grin, eyebrows up, eyes bright and wide, leaning toward the camera |
| skeptical | one eyebrow raised, lips pressed to one side, chin slightly down, eyes on the camera |
| focused | eyebrows drawn together slightly, lips closed, eyes looking down-left as if at a screen |
| worried | eyebrows raised in the middle, teeth clenched in a grimace, shoulders up |
| proud | small closed-mouth smile, chin up, arms crossed (hands shown) |
| calm, trustworthy | soft natural smile, relaxed eyes, direct eye contact, shoulders square |

hands often come out wrong. leave them out unless the design needs them, and then name the exact gesture.

## framing for designs

- **thumbnail plate:** the photo becomes the whole background, and the text goes on top in html. ask for the space you need: `--framing "landscape 16:9, head and shoulders on the right third, the left half empty for text"` and a `--backdrop` that matches the design colors.
- **cut-out person:** ask for a transparent background, and the png comes back with an alpha channel (tested 2026-10-22): `--backdrop "fully transparent background (alpha channel), the person cut out cleanly with no backdrop"`. the contact sheet shows it on a checkerboard, so you can judge the edges, especially in the curls.

## limits

- the built-in tool picks the output size. results come out near 16:9 for landscape (1672x941 in testing). crop or scale to the final size in the layout step.
- do not ask the image model to draw text or logos. add them in the layout.
- `codex exec -i` takes several files, so the script sends the prompt on stdin. keep it that way.
- the script finds each image in `$CODEX_HOME/generated_images/<thread id>/`, and falls back to the `IMAGE_PATH:` line of the reply.
