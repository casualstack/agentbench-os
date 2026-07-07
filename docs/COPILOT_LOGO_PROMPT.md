# Casualstack Logo — Copilot / Designer Prompt

Copy everything inside the block below into **GitHub Copilot**, **Microsoft Designer**, **DALL·E**, or **Figma AI**.

---

## Primary prompt (recommended)

```
Design a modern tech company logo for "Casualstack" — a developer-tools startup that builds CI and attestation infrastructure for AI coding agents.

Brand personality:
- Technical but approachable (the name plays on "casual" + "stack")
- Trustworthy, precise, infrastructure-grade — not playful or cartoonish
- Developer audience: platform engineers, OSS maintainers, AI tooling builders

Visual direction:
- Wordmark + optional icon (icon must work at 32×32 favicon size)
- Icon concept: abstract stacked layers or a minimal "stack" — could subtly suggest execution graphs, CI gates, or proof/attestation (checkmark, shield, or bracket motif) without being literal
- Avoid clichés: no robots, no brains, no chat bubbles, no magic wands
- Style: clean geometric sans-serif, flat or very subtle gradient, works on dark and light backgrounds
- Color palette: deep navy or charcoal base (#0d1117) with one accent — electric blue (#58a6ff) or teal-cyan — optional second accent for depth
- Must read clearly at small sizes (GitHub org avatar, browser tab, README header)

Deliverables:
1. Horizontal lockup (icon + "Casualstack" wordmark)
2. Square icon-only version for GitHub avatar
3. Monochrome white version for dark backgrounds
4. Monochrome black version for light backgrounds

Typography: modern geometric sans (similar feel to Inter, Geist, or SF Pro — not serif, not overly rounded)

Tagline for context only (do not put in logo): "Execution accountability for AI agents"

Output: vector-friendly, minimal detail, professional SaaS/devtools aesthetic comparable to Vercel, Railway, or Hashicorp — but distinct.
```

---

## Shorter prompt (if character-limited)

```
Logo for "Casualstack" — devtools company, AI agent CI infrastructure. Minimal geometric stack/layers icon + clean sans wordmark. Navy/charcoal + electric blue accent. Flat, professional, no robots or brains. Works at 32px favicon. Horizontal + square icon + mono variants. Vercel/Railway aesthetic.
```

---

## Iteration prompts (after first draft)

**If too playful:**
```
Make it more enterprise-devtools: sharper geometry, less rounded, reduce friendly/casual feel while keeping the name Casualstack. Think infrastructure, not consumer app.
```

**If too generic:**
```
Add a distinctive element: subtle "gate" or "proof" motif in the stack layers — three horizontal planes with the top one offset like a merge gate or attestation stamp. Keep minimal.
```

**If icon is too busy:**
```
Simplify to 2–3 shapes maximum. Must be recognizable as a blurry 32×32 GitHub org avatar. Remove all fine lines and gradients.
```

**For favicon / GitHub avatar only:**
```
Square app icon, 512×512 source. Abstract stacked layers, Casualstack brand colors navy + blue. No text. Centered, padding for circle crop. Flat vector style.
```

---

## Export checklist

After you have a logo you like:

- [ ] `logo-horizontal.svg` — README + website header
- [ ] `logo-icon.svg` — square mark
- [ ] `favicon.ico` + `favicon-32.png` + `apple-touch-icon.png`
- [ ] `og-image.png` — 1200×630 for social previews (logo + tagline on dark bg)
- [ ] `github-org-avatar.png` — 400×400 or 960×960

Store in `casualstack-brand/` or `examples/casualstack-landing/assets/` when ready.
