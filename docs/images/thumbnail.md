# README thumbnail: image brief

Use this brief to generate the banner at the top of the README and the repository's social preview image. Paste the prompt below into an image generator such as ChatGPT.

## Specification

- **Size:** 1280 × 640 px (2:1). GitHub's documentation gives 1280 × 640 as the ideal size and 640 × 320 as the lowest good size: [customizing your repository's social media preview](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview).
- **File:** PNG (or JPG), under 1 MB.
- **Save as:** `docs/images/thumbnail.png`.

## Prompt to paste into the image generator

```text
Create a clean, flat, modern landscape banner, exactly 1280 by 640 pixels (2:1).

Background: a plain deep navy (#0B1F33), no texture.

Left half: the title "VeritasQA" in large, bold, white sans-serif letters. Under it, one smaller line in teal (#14B8A6): "Answers from documents, quoted with the page."

Right half: one white PDF page card, slightly tilted, with eight thin light-grey placeholder lines (abstract shapes, no readable words). One of the lines is highlighted in teal. A small teal tag beside that line reads "p. 50". A magnifying glass rests over the highlighted line, with a small teal check mark at its edge.

Style: minimal vector illustration, generous margins, no gradients, no people, no logos, no icons except the magnifying glass and the check mark.

Text rule: use only the words given above, spelled exactly. Add no other text, numbers, scores, percentages or claims.
```

## Checks before you use it

- The text reads exactly "VeritasQA", "Answers from documents, quoted with the page." and "p. 50". If a word is wrong, regenerate the image, or correct the text in an image editor.
- There is no score, percentage, logo, trademark, real document text, and no word "AI". The project uses no AI model, so the image must not suggest one.
- The size is 1280 × 640 and the file is under 1 MB.

## Where it goes

1. Save the file as `docs/images/thumbnail.png`.
2. Upload the same file as the repository's social preview (GitHub: Settings, then General, then Social preview).
3. Add this line at the top of `README.md`, under the title: `![VeritasQA](docs/images/thumbnail.png)`.
