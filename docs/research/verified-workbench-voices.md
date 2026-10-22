# Verified Workbench voices

Date: 2026-10-22

## Result

The six entries below are source-verified and used by the Workbench header bank. They replace invented character-attributed prose; they are not a basis for expanding the bank back to 100 entries.

| UI speaker | Exact text | Primary-source location | Speaker verification | Confidence |
|---|---|---|---|---|
| ELIZA | `PLEASE GO ON.` | Weizenbaum PDF, PDF page 9, printed *Communications of the ACM* page 44, `NONE` rule list | The paper identifies the listed reassembly rules as ELIZA script responses. | High |
| ELIZA | `WHAT DOES THAT SUGGEST TO YOU.` | Same page and rule list as above | Same method as above. | High |
| COLOSSUS | `THERE IS ANOTHER SYSTEM.` | Finished film, Internet Archive source copy, 00:15:10.020-00:15:12.380 | A programmer says that a message has arrived from Colossus and then reads its displayed content. The candidate omits the display's alert prefix and preserves the message content verbatim. | High |
| COLOSSUS | `SET-UP COMMUNICATION WITH OTHER SYSTEM.` | Finished film, Internet Archive source copy, progressively displayed 00:20:09.500-00:20:14.500 | The text is visibly rendered on the operations-center display; the following dialogue identifies it as Colossus's direct order. | High |
| COLOSSUS + GUARDIAN | `THIS IS THE VOICE OF COLOSSUS, THE VOICE OF GUARDIAN.` | Finished film, Internet Archive source copy, 01:16:32.380-01:16:35.820 | The synthesized speaker identifies itself with both names immediately after the systems' fusion. The wording and speaker status are explicit in the primary audio. | High |
| COLOSSUS + GUARDIAN | `WE ARE ONE.` | Finished film, Internet Archive source copy, 01:16:36.240-01:16:37.040 | The same first synthesized message explicitly states the fused speaker's joint status. | High |

Word totals: 9 words from Weizenbaum; 22 words from the film across the Colossus and joint Colossus + Guardian entries.

## Primary sources and integrity data

### ELIZA

- Source artifact: local PDF copy of the published article identified below
- Size: 1,541,933 bytes
- SHA-256: `aa83b158ec26443d324c55483691d0c4fe63c759dee198037b60de0b7289cb1b`
- Bibliographic identity: Joseph Weizenbaum, “ELIZA—A Computer Program for the Study of Natural Language Communication Between Man and Machine,” *Communications of the ACM* 9(1), 1966.
- Verification method: `pdftotext` page isolation followed by visual/text comparison of PDF page 9 (printed page 44). The candidates appear as reassembly responses under the `NONE` rule.

### Colossus and Guardian

The supplied local clips do not contain an independent Guardian utterance or the film's first synthesized machine speech. To avoid inventing a Guardian line, the final-film copy was consulted as the primary audiovisual source for the relevant scene.

- Source artifact: *Colossus: The Forbin Project* (Universal Pictures, 1970), Internet Archive item `colossus-the-forbin-project-1970`
- Source URL: `https://archive.org/details/colossus-the-forbin-project-1970`
- Original file name: `Colossus - The Forbin Project (1970).mp4`
- Size: 784,123,957 bytes
- SHA-256, independently streamed over the entire source file: `2e64428688ccc19deed1f30f464d7890c2bc0ee5b255f95b99ab3988eccea7b3`
- Internet Archive file checksums: MD5 `c886c3e0b451eaa80abb93d44b89589e`; SHA-1 `cbe51dff9bd1d96ee3f8b7e4a3cb33584c064ade`
- Integrity method: the full source file was streamed through SHA-256 without retaining a duplicate movie copy; the byte count matched Internet Archive's published size.
- Verification method: frame-by-frame inspection of the rendered displays plus two local speech-recognition passes against the primary audio, including `mlx-community/whisper-large-v3-turbo` word-level alignment. Agreement between the passes established the spoken wording and time spans; the film's visible and narrative context established speaker status.

Temporary audio-window SHA-256 values, useful only for reproducing this verification from the same source file and extraction settings:

- 00:14:30-00:16:00, mono 16 kHz WAV: `252b7bac0d39570afcc5ec107ac2ac6c2ef764bb49a11914b4abff176a49facd`
- 00:19:45-00:21:15, mono 16 kHz WAV: `a8d7ccd902df9c4ad8104f28ebbd62b3a2f1b2f1d2194fa0051aed583f168888`
- 01:15:30-01:18:30, mono 16 kHz WAV: `0e63aeb6e67a134ba3cf24efffec6d1f7850ffc4fb01c396ca2de3725cc93a9e`

## Reproducing the three film checks

All source-copy timestamps below refer to the exact MP4 identified and hashed above. The extraction commands used `/tmp/dw-bin/ffmpeg`, an `imageio-ffmpeg` binary symlink; a system `ffmpeg` can be substituted.

1. **First Colossus message:** extract 90 seconds beginning at `00:14:30` as mono 16 kHz WAV, then inspect `00:00:40.020-00:00:42.380` in that derivative. The programmer announces and reads the arriving Colossus message. Command shape: `ffmpeg -ss 00:14:30 -i "$SOURCE_URL" -t 90 -vn -ac 1 -ar 16000 first-audio.wav`.
2. **Colossus communication order:** inspect source video `00:20:09.500-00:20:14.500` frame by frame. The words scroll progressively across the operations-center display. A 2-fps contact sheet was generated from a ten-second window beginning at `00:20:07`; its SHA-256 was `7f6afffe99de74a7c38bc44203d0054669b7cf75ab78dca13c688bfe529c74d8`. Command shape: `ffmpeg -ss 00:20:07 -i "$SOURCE_URL" -t 10 -vf "fps=2,scale=640:-2,tile=4x5" -frames:v 1 contact.png`.
3. **First unified voice:** extract three minutes beginning at `01:15:30` as mono 16 kHz WAV, then inspect `00:01:02.380-00:01:07.040` in that derivative. The synthesized speaker names both systems and immediately declares their unity. Command shape: `ffmpeg -ss 01:15:30 -i "$SOURCE_URL" -t 180 -vn -ac 1 -ar 16000 unity-search.wav`.

For checks 1 and 3, both a small local Whisper pass and `mlx-community/whisper-large-v3-turbo` were run with word timestamps; they agreed on the quoted wording. Example Python call: `mlx_whisper.transcribe(PATH, path_or_hf_repo="mlx-community/whisper-large-v3-turbo", word_timestamps=True, language="en")`. Speech recognition located and aligned the audio; the primary film established the narrative speaker attribution.

## Supplied local-clip audit

The following files were reviewed. They contain human dialogue about the computers, analysis of the computer output, or nonverbal interface activity; they do not contain two independently attributable English outputs from each of Colossus and Guardian.

| File | SHA-256 | Relevant content |
|---|---|---|
| `IMG_2753.MOV` | `6136e19a55d38e840806404ba5d846a800281ed52778b83b4424ce471d5cbb3f` | Human discussion of whether Colossus can create or initiate thought. |
| `IMG_2754.MOV` | `2e82f499770b8606bf081f4904e1468b42899a9b33f2e80b6550c184b88b904d` | Human White House briefing about the system. |
| `IMG_2755.mov` | `929bcac39d1322009c31a21e5d39c4ec590243849284e7393afff6eb8d32032c` | Forbin explains that Colossus deals in the exact meaning of words. |
| `IMG_2756.MOV` | `32251fe2393c505e5892ef924ce8c1dec81d6c71019271c1f41d92e6eaa196e1` | Humans analyze the Colossus-Guardian printout. |
| `IMG_2757.MOV` | `7d1424ce0bbc13266f195d4c47bf9303addc3459d92b68ba8da0af758fce8cec` | Humans respond to the computers' attempt to route around a broken link; beeps are nonverbal. |
| `IMG_2758.MOV` | `9c47aeb36a700d4a1339cb9a75ef3fa9105fdf5ce2617a91dc9be25a1e39fd2c` | Forbin explains the private-contact workaround. |

## Attribution rule for implementation

Use the exact speaker label `COLOSSUS + GUARDIAN` for the two joint entries, with attribution such as `UNIFIED VOICE · 1970`. The film provides no independently spoken English Guardian voice before the systems fuse, so a solo `GUARDIAN` label would overstate the evidence.
