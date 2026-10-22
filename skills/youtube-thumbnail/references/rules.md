# title and thumbnail rules

each rule has its source. the data studies show correlation, not cause: they tell you what is common, not what wins. youtube's own test & compare decides.

## the package

- **decide the title and thumbnail before the video is made.** they are the promise; the video delivers it. if you cannot sketch a title and a 3-5 word thumbnail label, the idea is weak. (mrbeast production document; expo youtube tutorial playbook, "package test")
- **promise = delivery.** everything the thumbnail shows must be in the video, the way it is shown. a yellow castle in the thumbnail and a red one in the video makes viewers feel lied to, and they leave. youtube now picks test winners by watch time, so a misleading package loses. (mrbeast production document; youtube help, test & compare)
- **title and thumbnail are one unit. they must add to each other, not repeat or contradict.** viewers look at the thumbnail, then the title, then the thumbnail again. (paddy galloway; tyler germain's thumbnail skill)
- **the title says what. the thumbnail shows the feeling or the proof.** (tyler germain's thumbnail skill)

## titles

- **be accurate.** (youtube help, "tips for titles and thumbnails")
- **choose the job: a searchable title or an intriguing one.** search titles use the exact words people type. browse titles make a promise or open a gap. write both and test. (youtube help; expo playbook: "the keyword gets you considered, the promise gets you clicked")
- **length: about 40-60 characters, never over 100.** put the key words and the hook in the first ~50 characters, because mobile cuts the rest. (expo playbook; thecraighewitt title-craft "mobile preview"; youtube help: important words near the start)
- **limit all caps and emoji.** (youtube help)
- **use the creator's own words.** no ai-slop patterns: no "what nobody tells you", no "here's why", no "game-changer", no colon reveals ("X: the truth about Y"), no "ultimate guide" unless it is one. (rami's long-to-short headline rules)
- **5 lanes to draft in:** search-clear, browse-curious, result ("I did X, here is Y"), contrarian, simple. (thecraighewitt title-craft; expo playbook)
- **stakes beat effort.** "I survived" beats "I spent". more extreme is better, if it is true. (mrbeast production document)

## thumbnail text

- **0-5 words, about 30 characters or fewer.** median in breakout videos is 5 words; 4-6 words had a small edge over underperformers. (vidiq study of 500 breakout videos, june 2026; eden study of 507,478 videos)
- **never repeat the title.** the one exception is the search keyword in a search-led package. (chongdashu youtube-titles-thumbnails; paddy galloway)
- **pairing patterns** (chongdashu youtube-titles-thumbnails):
  - thumbnail asks, title answers ("$99?" / "How far can you get with Expo before paying Apple?")
  - thumbnail shows the result, title gives the method
  - thumbnail gives the number or stakes, title gives the context
  - thumbnail is a reaction, title is the event
  - thumbnail is a label for the outcome, title is the search query

## thumbnail image

- **one focal subject, 3 elements at most.** (tyler germain's thumbnail skill; paddy galloway "3 or fewer focus areas", search snippet only)
- **the glance test.** a viewer must get it in about a second at feed size. check it at 120 px and 320 px wide. (paddy galloway; higgsfield-youtube-thumbnail checks at about 120 px; expo playbook "legible at postage-stamp size")
- **high contrast, a readable font, a simple design, rule of thirds.** (youtube help)
- **faces are common, not magic.** 69% of breakout videos have a face (vidiq), but faces were almost the same in breakouts and underperformers (84.2% vs 82.2%, eden). only 5% use an exaggerated face (vidiq). use a face when the person is part of the promise: browse-led videos. use a clean label for search-led videos. (expo playbook)
- **a face, when used, is big:** about 30-60% of the frame, eyes clearly visible. (thumbnailtest guide, no data)
- **keep the bottom-right corner free:** youtube covers it with the video length. (higgsfield-youtube-thumbnail; render.py shows the badge)
- **code, logos and ui are credibility in the background, not the focal point.** (expo playbook)
- **one visual system per series:** the same accent color, type and logo placement. (expo playbook)
- **never let the image model draw text or logos.** text goes on in the layout; logos are real files. check every downloaded logo with `file`, because a failed download can be an html page. (higgsfield-youtube-thumbnail; tyler germain's thumbnail skill)

## specs (youtube help, "add video thumbnails")

- 16:9, 1280x720 is the standard, up to 3840x2160, at least 640 px wide.
- jpg or png. under 2 mb works on desktop and mobile.

## testing (youtube help, "test & compare")

- up to 3 variants. make them clearly different, not small tweaks.
- youtube picks the winner by watch time share, not click-through rate.
- low-traffic videos often end "performed the same": then ship the clearer, more honest one. (expo playbook)

## sources

- youtube help, tips for titles and thumbnails: https://support.google.com/youtube/answer/12340300
- youtube help, add video thumbnails: https://support.google.com/youtube/answer/72431
- youtube help, test & compare: https://support.google.com/youtube/answer/16391400
- expo youtube tutorial playbook: `life-os/expo/content/reference/youtube-tutorial-research/youtube-tutorial-playbook.md`
- higgsfield-youtube-thumbnail: https://github.com/higgsfield-ai/skills/tree/main/higgsfield-youtube-thumbnail
- tyler germain's thumbnail skill (copy with his credit): https://github.com/Samin12/claude-thumbnails/blob/main/.claude/skills/youtube-thumbnail/SKILL.md
- chongdashu youtube-titles-thumbnails and thecraighewitt title-craft: skills.sh
- vidiq breakout study (june 2026), eden study (507,478 videos), thumbnailtest guide
- mrbeast production document (leaked, not officially confirmed)
- paddy galloway on x: "view the title and thumbnail as one, do they compliment each other or contradict/repeat?"
