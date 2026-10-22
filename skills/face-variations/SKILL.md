---
name: face-variations
description: Generate new images of one specific real person from a library of their reference photos (all angles and expressions) - one or many variations with a chosen expression, pose, framing and backdrop, for thumbnails, posters and other designs. Uses Codex's built-in image tool (gpt-image-2 on the ChatGPT plan, no API key). Also keeps a tagged catalog of every photo of the person (expression, gesture, facial hair, glasses, pose, light) to filter and mix them. Use when asked for "a picture of me looking shocked", face expressions, face variations, a new photo of a person from their references, a face for a thumbnail, or to tag, find or filter photos of a person.
---

# face-variations

make new photos of one real person that still look exactly like them. the person's reference photos carry the identity; the prompt carries only what changes (expression, pose, framing, backdrop).

the engine is codex's built-in `image_gen` tool, driven by `codex exec`. it runs on the chatgpt plan that codex is signed in with: no api key, but every image counts toward the codex usage limits. the reference photos are uploaded to openai.

## the face library

one folder per person, inside the workspace that uses it (in life-os: `design/faces/<person>/`):

```
faces/<person>/
  profile.md       # name, source photos folder, identity-lock bullets (shared and per look), which refs are missing
  catalog.json     # tags for every image of the person (see "the catalog")
  refs/<look>/     # 6-12 reference photos per look: the identity
  approved/        # generated images the person approved: safe to reuse as refs
  variations/      # default output: <date>-<look>-<slug>/ with images, manifest.json, contact-sheet.jpg
```

### looks

a look is how the person looked in one period: hair length, facial hair, glasses. each look gets its own folder under `refs/`, for example `refs/beard/` and `refs/mustache/`. never mix looks in one run: the model averages them, and the result matches neither. the script uses one look per run: `--look <name>`, or `default look: <name>` in `profile.md`, or the only look there is. a person with one look can keep the photos straight in `refs/`.

### reference photos

likeness improves with more good references. aim for 8-12, at least 1024 px on the short edge:

- angles: front, 3/4 left, 3/4 right, slightly from above, slightly from below
- expressions: neutral, smiling with teeth, talking, one strong expression (surprised, laughing)
- mix the expressions: when most refs show one expression, results keep it (a mustache set of mostly surprised photos gave a laughing face with wide, surprised eyes)
- light: soft indoor light and harder daylight
- distance: mostly head and shoulders, one or two closer face shots
- one person per photo. no sunglasses, no hats, no heavy filters, no motion blur
- no two photos with the same pose and light: duplicates add nothing
- if the person sometimes wears glasses, keep most refs without them and say so in `profile.md`

name files by what they show: `front-neutral.jpg`, `3q-left-smile.jpg`, `below-talking.jpg`. the names help you pick refs per job.

**crop raw photos with `scripts/prepare_refs.py`.** it finds the face, crops to head and shoulders at 4:5, and saves a jpg of at most 1600 px. tight crops give the model more pixels of the face, and keep hands and props out of the refs:

```bash
uv run scripts/prepare_refs.py --out-dir design/faces/rami/refs/beard "raw/IMG_1.jpg=front-neutral" "raw/IMG_2.jpg=3q-left-smile"
```

it fails, and says so, when it finds no face: crop that photo by hand. look at every crop before you keep it. photo booth file names such as "Photo on ... 1.14 PM.jpg" contain a narrow space before "PM": pass those paths through a shell glob, not typed by hand.

### profile.md

```markdown
# <name>

default look: <look>        (optional)

## identity lock
- <a feature that drifts in every look, said as a physical fact: "tight dark curls with high volume">

## look: <look>
- <what is true only in this look: "mustache only: the cheeks and chin are clean-shaven">

## refs
- <look> (<count>): <what is covered>. missing: <angles or expressions>
```

the script copies the bullets under `## identity lock` and under the chosen `## look: <name>` into each prompt. write a bullet when a result drifts on that feature, so it does not drift again.

## the catalog

`scripts/catalog.py` tags every image of the person with a fixed vocabulary, so you can filter and mix them. it covers `refs/`, `approved/`, `variations/` and the folders on the `source photos:` line of `profile.md`. codex looks at each image (`codex exec` with a json schema, about 10 seconds each, 4 at a time) on the chatgpt plan.

```bash
uv run scripts/catalog.py tag --face design/faces/rami          # new and changed images only; run it after adding photos
uv run scripts/catalog.py fields                                # the vocabulary
uv run scripts/catalog.py summary --face design/faces/rami      # how many images have each value
uv run scripts/catalog.py find --face design/faces/rami \
  --where look=mustache --where hands=pointing-up,pointing-up-both-hands --not expression=confused \
  --sheet /tmp/pointing.jpg                                     # paths, plus a contact sheet to look at
uv run scripts/catalog.py set --face design/faces/rami photo-12.jpg facial_hair=short-beard   # fix a wrong tag
uv run scripts/catalog.py finder --face design/faces/rami       # copy the tags to finder tags on the source photos
```

- fields: expression, mouth, eyes, eyebrows, gaze, head, hands (pointing and other gestures), facial_hair, glasses, hair, framing, lighting, background_type, quality, plus description, clothing, background, props, extra_tags. left and right are from the viewer's side.
- every record also has kind (photo, ref, generated, approved), look, taken (date), size and sha256. `--where` values are or-ed with commas; several `--where` are and-ed.
- a photo gets its look from its date: put `photos taken: <date>` lines under each `## look:` heading in `profile.md`.
- after tagging, the script lists images whose facial hair or glasses differ from the rest of their look. those are usually tagging mistakes: look at the image, then fix it with `set`. `tag --retag` tags everything again and overwrites fixes made with `set`.
- a file that moves keeps its tags (matched by its sha256). an entry is dropped when its file is gone from a folder that was scanned. entries from a folder that does not exist on this machine stay.
- `generate.py` tags its new images automatically when they are saved inside the face folder (`--no-tag` to skip).
- finder tags: `finder` writes the main tags into each source photo's finder tags, so finder search (`tag:pointing-up`) works. `finder --clear` removes them. run it again after `tag` or `set`.

use the catalog before you generate: when a real photo already has the expression and gesture you need, it beats a generated one.

## workflow

1. **look for a real photo first.** `catalog.py find` with the expression, gesture and look you need. if a real photo fits, use it and stop.
2. **check the library and pick the look.** read `profile.md` and list `refs/`. if the request does not say which look and there is no default look, ask. if the look has fewer than 5 refs, say that likeness will suffer and name the missing angles before you spend images.
3. **pick the refs for the job.** by default the script sends the whole look folder (up to 8). for a target angle, pick refs close to it with `--ref` (a 3/4 pose: the 3/4 refs plus the front one). each ref has one job: identity. never pass a style or layout example as a ref: it leaks into the face.
4. **write the variation in physical terms.** say what the face does, not the emotion word alone. one change per variation. see the expression table below.
5. **dry-run first** when you write new prompts. it prints every prompt and costs nothing:
   ```bash
   uv run scripts/generate.py --face design/faces/rami --look beard --prompt "..." --dry-run
   ```
6. **generate.** one `codex exec` per image, 3 at a time:
   ```bash
   uv run scripts/generate.py --face design/faces/rami --look beard \
     --prompt "laughing: wide open-mouth smile, cheeks raised, eyes narrowed, head tilted a little left" \
     --prompt "skeptical: one eyebrow raised, lips pressed to one side, chin slightly down" \
     --count 2 --out design/thumbnails/<slug>/faces
   ```
   options: `--look <name>`, `--aspect landscape|portrait|square`, `--framing "..."`, `--backdrop "..."`, `--asset "..."`, `--ref <file>` (repeat), `--parallel N`.
7. **review before you show.** open `contact-sheet.jpg` (refs on top, results below) and compare each result to the refs: eye shape, nose, hairline, hair texture, facial hair, glasses, skin tone, age. drop any result that drifts, and say which feature drifted. a result can look like a sibling and still be wrong: if in doubt, drop it.
8. **show the person the kept results**, with paths. only when they approve one, copy it to `approved/`. never feed an unapproved result back in as a ref: drift adds up over generations.
9. **when a result drifts the same way twice**, add an identity-lock bullet to `profile.md`.

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
