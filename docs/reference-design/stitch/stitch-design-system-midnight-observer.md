# Design System Document: The Midnight Observer

## 1. Overview & Creative North Star
This design system is built for the solitary curator. It is a digital tribute to the hours between 2:00 AM and 5:00 AM—the quiet, the hum of a dashboard, and the weight of a curated music collection. 

**Creative North Star: "The Midnight Observer"**
The aesthetic rejects the "clean" sterility of modern SaaS in favor of a cinematic, editorial atmosphere. We are building a "Digital Archive" that feels like a physical space: a dimly lit room where the only light comes from a glowing monitor or a streetlamp through a rain-streaked window. 

To break the "template" look, designers must embrace **Intentional Asymmetry**. Metadata should be tucked into corners like catalog numbers on a vinyl sleeve; headlines should be oversized and authoritative, often overlapping imagery or bleeding off the grid. The goal is a layout that feels curated and "heavy," rather than buoyant and "tech-heavy."

---

## 2. Colors & Atmospheric Depth
Our palette is rooted in the absence of light. We use a range of blacks and graphites to create a sense of infinite depth.

### The Foundation
*   **Surface-Deep:** Use `surface-container-lowest` (#0e0e0e) for the primary background to anchor the experience in "true black."
*   **The Charcoal Mid-tones:** Use `surface` (#131313) and `surface-container-low` (#1c1b1b) to define secondary content areas.
*   **The Glow (Accents):** `primary` (#ffba3a) and `secondary` (#ffb598) are used sparingly. They represent the "on" light of a vintage amplifier or a distant signal.

### Critical Rules
*   **The "No-Line" Rule:** 1px solid borders are strictly prohibited for sectioning. Boundaries must be defined solely through tonal shifts. A `surface-container-low` card sits on a `surface` background without an outline.
*   **The Glass & Gradient Rule:** To achieve the "rain on glass" aesthetic, use Glassmorphism for floating navigation or playback bars. Use `surface_variant` at 60% opacity with a `20px` backdrop-blur. 
*   **Atmospheric Texture:** Apply a global, low-opacity (2-4%) film grain SVG filter over the entire UI. This "analog grit" prevents the dark UI from looking like a flat digital void.

---

## 3. Typography: The Editorial Voice
We contrast the traditional authority of a serif with the clinical precision of a sans-serif.

*   **Display & Headlines (Newsreader):** This is our "archivist" voice. It is used for artist names and collection titles. It should feel heavy and permanent. 
    *   *Constraint:* No italics. Avoid "dainty" styling. Use `display-lg` (3.5rem) to dominate the page.
*   **Metadata & Navigation (Inter):** This is the "technical" voice. It mimics the small print on the back of a CD jewel case or a studio log.
    *   *Constraint:* Use `label-md` and `body-sm` for almost all navigation. All-caps is preferred for navigation items to increase the "archival" feel.

---

## 4. Elevation & Depth
In this system, elevation is not achieved through shadows that "lift" objects toward the user; instead, it is achieved through **Tonal Layering** that "recedes" or "glows."

*   **The Layering Principle:** Stack surfaces to create focus.
    *   Base: `surface` (#131313)
    *   Inner Content: `surface-container-low` (#1c1b1b)
    *   Active/Interactive: `surface-bright` (#393939)
*   **Ambient Shadows:** If an element must float (e.g., a context menu), use an extra-diffused shadow: `box-shadow: 0 20px 40px rgba(0,0,0,0.6)`. The shadow should feel like a natural light obstruction, not a digital effect.
*   **The Ghost Border Fallback:** For accessibility in high-density areas, use `outline-variant` (#564334) at **15% opacity**. It should be barely felt, like a faint reflection on a dark surface.

---

## 5. Components

### Buttons: The "Indicator" Style
*   **Primary:** Background `primary_container` (#e29f00), text `on_primary_container` (#573a00). No rounded corners (use `sm` scale: 2px).
*   **Tertiary/Ghost:** No background. Text in `on_surface`. On hover, apply a subtle `primary` glow to the text itself (text-shadow).

### Cards & Lists: The "Archive Entry"
*   **Cards:** Forbid divider lines. Separate "entries" using vertical whitespace (32px or 48px) and background shifts. 
*   **Imagery:** All photography should have a "Nocturnal" treatment—low exposure, high contrast. Apply a subtle `0.5px` inner glow (`inset`) to images to make them feel like they are "set into" the dark interface.

### Input Fields: The "Terminal" Style
*   **Style:** Minimalist. Only a bottom border using `outline` (#a48c7a) at 30% opacity. 
*   **Focus State:** The bottom border becomes `primary` (#ffba3a) with a soft 4px outer glow of the same color. No "precious" animations; the transition should be an instant, sharp "on" state.

### Chips: The "Tag" Style
*   Use `surface_container_highest` for the background. Typography must be `label-sm` (Inter) in all-caps. These should look like small, dymo-label tapes stuck to a folder.

---

## 6. Do's and Don'ts

### Do
*   **Embrace the Dark:** Use `surface-container-lowest` for 80% of the layout.
*   **Use Cinematic Photography:** Ground the UI with real-world nocturnal textures (blurred headlights, rainy asphalt).
*   **Asymmetric Grids:** Align a headline to the far left and the metadata to the far right with significant "dead space" in between.

### Don't
*   **Don't use Icons for everything:** Favor text labels in Inter. Icons feel too "app-like" for a high-end archive.
*   **Don't use Rounded Corners:** Stick to `none` or `sm` (2px-4px). "Pill" shapes are strictly forbidden as they introduce "softness."
*   **Don't use Pure White:** Use `on_surface` (#e5e2e1) for text. Pure white (#FFFFFF) is too harsh and breaks the low-light cinematic immersion.
*   **Don't use Gothic tropes:** No skulls, no ornate filigree, no "vampiric" styling. This is about urban solitude, not horror.