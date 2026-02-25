# Yap — Brand Design Brief

## Product

**Name**: Yap
**Tagline**: Voice dictation that just works.
**One-liner**: Hold a key, talk, let go — your words appear wherever you're typing.
**What it is**: A macOS menubar app for instant voice dictation. No app switching, no windows, no friction. Just a subtle overlay, audio feedback, and text in your active app.

## Audience

Broad — anyone who uses a Mac and types a lot:
- Developers and power users who value speed
- Knowledge workers (writers, PMs, analysts) who want hands-free input
- Creators and content people who dictate drafts and notes
- General Mac users who want quick dictation without fuss

**Common thread**: They value tools that stay out of the way and just work.

## Brand Personality

**Minimal & utilitarian.** Yap is the tool that disappears into your workflow. It doesn't demand attention — it earns trust through reliability and simplicity.

**Reference points**: Raycast, Linear, Arc — tools that are beautiful because they're purposeful, not decorative.

**Tone**: Confident, concise, unpretentious. No exclamation marks, no "magical AI" language. Say what it does, plainly.

**Voice examples**:
- Yes: "Hold to talk. Release to paste."
- Yes: "Your words, wherever you type."
- No: "Supercharge your productivity with AI-powered voice magic!"
- No: "The revolutionary dictation experience you've been waiting for."

---

## Color Palette

Warm earthy tones — approachable and grounded, but never loud.

### Primary

| Role | Name | Hex | Usage |
|------|------|-----|-------|
| **Brand** | Clay | `#C27B5A` | Logo, primary accent, active states, CTA buttons |
| **Dark** | Charcoal | `#2D2926` | Text, dark backgrounds, app icon base |
| **Light** | Parchment | `#F5F0E8` | Backgrounds, light surfaces |

### Supporting

| Role | Name | Hex | Usage |
|------|------|-----|-------|
| **Warm neutral** | Sand | `#D9CCBB` | Borders, dividers, secondary surfaces |
| **Accent** | Sage | `#7D8B6A` | Success states, recording active indicator |
| **Muted** | Stone | `#9B948A` | Placeholder text, disabled states, captions |

### Semantic

| State | Color | Hex |
|-------|-------|-----|
| Recording / active | Sage | `#7D8B6A` |
| Error | Muted red | `#B85C4A` |
| Warning | Amber | `#C4993D` |

### Dark mode adjustments
- Swap Parchment ↔ Charcoal for surfaces/text
- Clay accent stays consistent across modes
- Reduce contrast slightly — warm tones soften in dark mode

---

## Typography

### In-app (macOS)
Use **SF Pro** (system font) — it's what users expect in a native Mac app, and it keeps the footprint zero. Don't fight the platform.

### Marketing / website / docs

| Role | Font | Fallback | Weight |
|------|------|----------|--------|
| **Headings** | Satoshi | system-ui, sans-serif | 700 (Bold), 500 (Medium) |
| **Body** | DM Sans | system-ui, sans-serif | 400 (Regular), 500 (Medium) |
| **Mono / code** | JetBrains Mono | monospace | 400 |

**Why Satoshi**: Geometric but warm. Distinctive at heading sizes without being loud. Free via Fontshare.
**Why DM Sans**: Clean, excellent readability, pairs naturally with geometric headings. Free via Google Fonts.

### Type scale (website)
- Hero: 48–56px / Satoshi Bold
- H1: 36–40px / Satoshi Bold
- H2: 24–28px / Satoshi Medium
- Body: 16–18px / DM Sans Regular
- Caption: 13–14px / DM Sans Regular, Stone color

---

## Logo & App Icon Direction

### Concept

The logo should be a **simple geometric mark** that works at every size — from 16px menubar to 1024px app icon. It should feel like it belongs in the macOS dock next to Raycast, Things, and Arc.

### Suggested motifs (explore 2–3)

1. **Abstract speech bubble** — A rounded rectangular speech bubble, simplified to its essence. Slightly warm-cornered, not a perfect circle. The "tail" of the bubble could subtly reference a sound wave or cursor.

2. **Lettermark "Y"** — A stylized Y that doubles as a visual metaphor (e.g., the fork of the Y suggesting a voice emanating upward, or the Y forming a minimal waveform shape).

3. **Sound/voice glyph** — Concentric arcs (like sound waves) emanating from a single point, but rendered as a solid geometric mark rather than thin lines.

### Icon principles
- **Works monochrome**: The menubar icon is a template image (white on dark, dark on light — macOS handles this). The mark must read cleanly in single-color.
- **Distinctive at 16px**: Avoid fine details that collapse at small sizes.
- **No text in the icon**: "Yap" is only 3 letters — use it as a wordmark separately, not inside the icon.
- **Rounded, not sharp**: Matches macOS design language and the warm brand personality.
- **App icon treatment**: Clay (`#C27B5A`) mark on Charcoal (`#2D2926`) background, or vice versa. Subtle depth via slight shadow or inner glow — never glossy.

### Wordmark
- "yap" in lowercase Satoshi Bold
- Letterspace slightly (+2–4%)
- Can pair with the icon mark, but each should work independently

### Menubar icon
- 18x18 @1x, 36x36 @2x
- Monochrome template image (macOS auto-tints for light/dark mode)
- Same mark as the app icon, simplified if needed for legibility

---

## Visual Style

### Principles
1. **Quiet confidence** — Every element earns its place. If it doesn't serve the user, remove it.
2. **Warm minimalism** — Earthy tones prevent the coldness that pure minimalism can create.
3. **Platform-native** — In the app, follow macOS conventions. Save brand expression for the website and marketing.
4. **Show, don't decorate** — Communicate through layout and typography, not ornament.

### Do
- Generous whitespace
- Consistent 8px grid
- Rounded corners (8–12px for cards, 6px for inputs)
- Subtle shadows for elevation (warm-tinted, not pure black)
- Clean iconography (2px stroke, rounded caps)

### Don't
- Gradients (except very subtle background washes)
- Drop shadows with hard edges
- Decorative illustrations or mascots
- Bright/saturated colors
- Glossy or skeuomorphic effects

---

## Overlay (in-app recording indicator)

The frosted glass overlay is one of the few brand touchpoints inside the app:
- Use NSVisualEffectView (already implemented)
- Recording state: Sage accent dot or subtle pulse
- Text label in SF Pro, Parchment color
- Keep it small, corner-positioned, non-intrusive

---

## Deliverables Checklist

### Phase 1 — Ship (minimum for DMG release)
- [ ] App icon (icns: 16, 32, 128, 256, 512, 1024px)
- [ ] Menubar template icon (18x18 @1x, 36x36 @2x, monochrome)
- [ ] DMG installer background (~600x400)
- [ ] Color palette finalized (already defined above)

### Phase 2 — Presence (for sharing / discoverability)
- [ ] Landing page (single page, responsive)
- [ ] OG image for link previews (1200x630)
- [ ] GitHub README with branding
- [ ] Favicon + apple-touch-icon for website

### Phase 3 — Growth (later)
- [ ] App Store screenshots (if submitted)
- [ ] Social media templates
- [ ] Demo GIF / video
- [ ] Press kit

---

## References & Inspiration

Apps with a similar minimal-but-warm aesthetic:
- **Things 3** — Warm, muted, purposeful
- **Bear** — Earthy tones, clean typography
- **Raycast** — Utilitarian but polished
- **Linear** — Minimal with clear hierarchy
- **iA Writer** — Typography-first, confident restraint
