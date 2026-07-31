---
name: MathGraph AI
colors:
  surface: '#faf8ff'
  surface-dim: '#d9d9e5'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f3fe'
  surface-container: '#ededf9'
  surface-container-high: '#e7e7f3'
  surface-container-highest: '#e1e2ed'
  on-surface: '#191b23'
  on-surface-variant: '#434655'
  inverse-surface: '#2e3039'
  inverse-on-surface: '#f0f0fb'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#b61722'
  on-secondary: '#ffffff'
  secondary-container: '#da3437'
  on-secondary-container: '#fffbff'
  tertiary: '#006242'
  on-tertiary: '#ffffff'
  tertiary-container: '#007d55'
  on-tertiary-container: '#bdffdb'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#ffdad7'
  secondary-fixed-dim: '#ffb3ad'
  on-secondary-fixed: '#410004'
  on-secondary-fixed-variant: '#930013'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#faf8ff'
  on-background: '#191b23'
  surface-variant: '#e1e2ed'
typography:
  display:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  math-code:
    fontFamily: JetBrains Mono
    fontSize: 15px
    fontWeight: '500'
    lineHeight: 22px
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  sidebar_width: 260px
  graph_viewer_min_width: 400px
  gutter: 16px
  margin: 24px
  stack_gap_sm: 8px
  stack_gap_md: 16px
  stack_gap_lg: 32px
---

## Brand & Style
The design system is engineered for cognitive clarity and mathematical precision. It targets an academic and professional audience, balancing the approachability of an AI assistant with the rigorous utility of a scientific graphing calculator.

The style is **Corporate Modern with a Mathematical Edge**. It utilizes high-density layouts, purposeful whitespace, and a systematic approach to information hierarchy. The interface avoids unnecessary decoration, focusing instead on structural integrity and the clarity of the generated data. The aesthetic reflects a "Workbench" philosophy: functional, high-tech, and relentlessly efficient.

## Colors
This design system uses a primary **AI Blue** to denote intelligence and interaction points. A spectrum of mathematical accents (Red, Green, Purple, Orange) is reserved strictly for data visualization—distinguishing between multiple equations or datasets in the graph viewer.

The foundation is built on a **High-Contrast Neutral** palette. Backgrounds utilize a soft grey to reduce eye strain during long research sessions, while typography remains near-black for maximum legibility. Borders are kept subtle to define the three-column structure without creating visual noise.

## Typography
The typography strategy employs a dual-font system. **Inter** serves as the primary UI typeface for its exceptional readability in dense layouts. For mathematical expressions, LaTeX strings, and code snippets, **JetBrains Mono** is used to ensure character distinction (e.g., distinguishing '0' from 'O').

Hierarchy is established through weight and scale. Large display styles are used sparingly for dashboard headers, while the majority of the interface relies on `body-md` and `math-code`. Captions and axis labels use `label-sm` in all-caps for a technical, blueprint-like feel.

## Layout & Spacing
The layout follows a **Functional Three-Column Workbench** model:
1.  **Navigation (Left):** A collapsible sidebar for session history and library management.
2.  **Interaction (Center):** A fluid chat-based interface where users prompt the AI. This column expands when the sidebar or graph viewer is collapsed.
3.  **Visualization (Right):** A fixed-aspect or fluid graph viewer that persists as the "source of truth."

On tablet devices, the sidebar collapses into a drawer. On mobile, the interface switches to a tabbed view (Chat / Graph / History) to maintain focus. We use an 8px base grid for all internal component spacing to maintain a mathematical rhythm.

## Elevation & Depth
This design system utilizes **Tonal Layers** rather than heavy shadows to indicate hierarchy. This reinforces the "flat" mathematical aesthetic.

-   **Base Level:** Soft grey (`#F9FAFB`) for the main application background.
-   **Mid Level:** Pure white (`#FFFFFF`) for active containers, chat bubbles, and the graph stage.
-   **High Level:** Subtle, low-opacity shadows (4% alpha) are used only for floating menus or modals to separate them from the work surface.
-   **Dividers:** 1px solid lines using the "border_subtle" color define the primary columns and toolbar boundaries.

## Shapes
To maintain a professional and technical appearance, the design system adopts a **Soft (0.25rem)** roundedness. 

-   **Standard Components:** Buttons, inputs, and cards use a 4px radius.
-   **Containers:** Larger graph panels or chat modules use an 8px radius (`rounded-lg`).
-   **Interactive Elements:** Toggle switches and pills use a fully rounded radius to distinguish them from structural layout blocks.

## Components
-   **Buttons:** Primary buttons use a solid "AI Blue" fill with white text. Secondary buttons use a subtle "border_subtle" outline.
-   **Input Fields:** Use "math-code" typography. Active states are indicated by a 1px "AI Blue" border.
-   **Math Chips:** Small, color-coded pills that represent specific variables or active equations. The chip's background color should match the line color in the graph viewer.
-   **Cards:** Chat bubbles from the AI are styled as white cards with a thin border. User prompts are subtly tinted with a 5% "AI Blue" background.
-   **Graph Viewer:** A dedicated component with a coordinate grid background, featuring overlay controls for zoom, pan, and "Export to LaTeX."
-   **Lists:** High-density lists in the sidebar use "label-sm" for metadata and "body-md" for titles, with a subtle hover state highlighting the row.