# Handoff: re-check stems exported before the Cantai findings

Written 2026-09-25 for a fresh session. Read this file, then SKILL.md Step 9 (9.1–9.4) and
the Step 10 notes on timing. Everything below is in the repository; nothing needs to be
fetched.

## Suggested first message for the new session

> Read `~/Cowork/rehearsal-tracks/handoff-stem-audit.md` and do what it says for the song
> folders I connect. Report per song before re-exporting or remaking anything.

## Why

Two failures were found on one piece (a TTBB with piano, six Cantai voices) after several
sets of stems had already been made for other songs. Neither is audible on a casual listen,
and both leave every automatic check made at the time passing.

1. **Unfinished rendering exported as silence** (SKILL.md 9.1). Cantai renders in the
   background, from bar 1 on, after the file is opened or its cache cleared; File > Export >
   Audio writes only what has been rendered and silence for the rest, with no warning. Whole
   runs of phrases vanish, starting and ending on a phrase's first syllable, in any staff.
   Stems exported within a couple of minutes of opening a file are suspect.
2. **The export plug-in gives a stem the previous staff's opening** (SKILL.md 9.3), even with
   rendering finished: about the first 20 s (up to the first rest), over sung notes, right
   rhythm, plausible pitches, the wrong part. It hit every stem exported after another. Stems
   made with the plug-in (file names like `NAME 01 Tenor 1.aiff`, or the user says so) are
   suspect; stems made by hand, one staff at a time, are not, on this evidence.

Anything mixed from a bad stem is bad too: every rehearsal mp3 (all of them contain every
voice) and every follow-along video.

## What to do, per song folder

1. **Find the stems and the MusicXML they were rendered from.** That is usually the Cantai
   learning file (`... (Cantai).musicxml` or similar), not the print file. If the folder has
   several MusicXML files, or the dates suggest the stems came from an older version, ask
   which one. If there is none, ask once for it (SKILL.md 9.2); without it only the file and
   identical-audio checks can run, and the report must say NOT RUN for the rest.
2. **Match every stem to a part name** (`<part-name>` in the MusicXML). Ask if a name is
   ambiguous. Include the accompaniment stem: the alignment uses it.
3. **Run the audit**, staging the files into the workspace first (the linked computer's
   shell may lack numpy or ffmpeg, and three minutes is its limit):

   ```
   python3 stem_audit.py "SONG (Cantai).musicxml" "Tenor 1=..." "Tenor 2=..." "Baritone=..." \
     "Bass=..." "Piano=..." --out "SONG - stem audit.txt"
   ```

   About 40 s for a 3½-minute piece. Read SKILL.md 9.2 on reading it. In short:
   - `MISSING` stretches are dropouts (failure 1).
   - "sings another part's line" or "on no other part's either" in check 3, and `SAME AUDIO`
     where the parts are written differently in check 4, are the plug-in leak (failure 2).
   - Short or partly sounding flags, and a stretch silent in every voice at once, are the
     alignment, not the stem.
4. **Confirm before condemning.** For each flagged stem, look at the evidence against every
   part's written line, not only its own, and at which other stem it matches. On the piece
   above, a clean by-hand export was first called bad because it matched a leaked stem; the
   user's ears overruled it. If a flag is still unclear, ask the user to listen to that stem
   at that bar and say what they hear.
5. **Report per song**, in one table: stem, verdict (clean / re-export), why, bars. Put the
   audit's text file in the song's folder next to the stems. Say whether the song's mp3s and
   videos, if they exist, were made from any bad stem (the file dates and the mp3s' contents
   will tell: a stem's audio is inside every mp3 of its set).
6. **Do not re-export or remake anything until the user has seen the report.** When they
   re-export, ask for this recipe, in plain words:
   - open the file (or clear the cache) and wait: in the Mixer (Play > Mixer, or M), the gear
     on a Cantai voice's strip opens its panel; the singer's picture has a spinning halo and a
     pulsing dot beside "Rendering..." near the top left until that voice is rendered. When
     one stops, check every other voice's panel;
   - then File > Export > Audio, one staff at a time, soloed; not the batch plug-in.
   Run the audit again on the new stems, then remake the song's full set of mp3s
   (`rehearsal_mix.py`, SKILL.md 9.4) and, if the song has them, its videos (SKILL.md 10).

## Things that cost time on the piece above

- **Chorus Connection names.** Before mixing, confirm the section each part's files go under
  with a question card, one question per voice (SKILL.md 9.4). A division of a section is
  `(Tenor 2) a`, never `(Tenor 2a)`: an unknown section makes Chorus Connection show the file
  to everyone.
- **Check what landed.** Stage every delivery into a new directory, and compare the audio
  streams on the user's computer afterwards (`ffmpeg -i x -map 0:a -c copy -f md5 -`); files
  arrive a few KB larger with the audio intact. A re-staged file can arrive as its old copy:
  compare checksums before analysing.
- **Deleting.** The session cannot delete in connected folders. Give the user the `rm` lines
  in the same Terminal block as the git commands.
- **Video timing** (if videos are remade). Target the lights 25–30 ms ahead of the sound,
  per section; caesuras, a double barline after a bar rest and consonant-led staccato all
  moved the timing on that piece, and the 15 s check could not see any of them (SKILL.md 10).

## The user's working conventions

- The user runs all commits and pushes. Give one Terminal block with the git commands.
  Use `git --no-optional-locks` for read-only git on the user's computer.
- No song titles, composers or lyrics in repository files or commit messages; the song's own
  folder is where names belong.
- Write tempo in plain text ("half = 138"), not note glyphs.
- Style: no LinkedIn cadences, no softened criticism, no closing summary paragraphs. Verify
  any citation by fetching it and quote a sentence from it.
